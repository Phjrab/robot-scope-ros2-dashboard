"""Owned, bounded SDK IR1/depth acquisition for a separate calibration session.

No ROS publication, alignment, option writes, device calibration or body-pose
assumption occurs here. The broker retains its camera reservation until stop is
confirmed; automatic expiry stops acquisition but never releases that lock.
"""
from __future__ import annotations

from copy import deepcopy
import datetime as dt
import importlib
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable

from .depth_capture_contract import validate_confirmation
from .slam_camera import CameraBusy
from .slam_managed_scope import (
    DomainReservation, ManagedScopeError, load_managed_scope, private_json,
    validate_reservation_proof,
)
from .slam_sessions import SlamError


MAX_PAIR_SKEW_MS = 1.0
FRAME_WAIT_MS = 1000
CAPTURE_WAIT_S = 3.0
MAX_FRAME_AGE_S = 1.0
NO_FRAME_TIMEOUT_S = 5.0


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _finite(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise SlamError("DEPTH_CAPTURE_NONFINITE_METADATA", 422)
    return result


def _profile(profile: Any) -> dict[str, Any]:
    result = {"stream": str(profile.stream_type()), "index": int(profile.stream_index()),
              "format": str(profile.format()), "fps": int(profile.fps())}
    if profile.is_video_stream_profile():
        video = profile.as_video_stream_profile()
        result.update(width=int(video.width()), height=int(video.height()))
    return result


def _intrinsics(profile: Any) -> dict[str, Any]:
    value = profile.as_video_stream_profile().get_intrinsics()
    return {"width": int(value.width), "height": int(value.height),
            "fx": _finite(value.fx), "fy": _finite(value.fy),
            "ppx": _finite(value.ppx), "ppy": _finite(value.ppy),
            "model": str(value.model), "coeffs": [_finite(v) for v in value.coeffs]}


def _extrinsics(source: Any, target: Any) -> dict[str, Any]:
    value = source.get_extrinsics_to(target)
    rotation, translation = list(value.rotation), list(value.translation)
    if len(rotation) != 9 or len(translation) != 3:
        raise SlamError("DEPTH_CAPTURE_EXTRINSICS_INVALID", 422)
    return {"rotation": [_finite(v) for v in rotation],
            "translation": [_finite(v) for v in translation],
            "translation_unit": "metres", "rotation_layout": "column_major"}


class RealSenseDepthCaptureAdapter:
    engine_id = "realsense_depth"

    def __init__(self, *, config_path: Path | None = None, enabled: bool = False,
                 sdk_loader: Callable[[], Any] | None = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.config_path = config_path
        self.enabled = enabled
        self._sdk_loader = sdk_loader or (lambda: importlib.import_module("pyrealsense2"))
        self._injected_sdk = sdk_loader is not None
        self._clock = monotonic
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._job: dict[str, Any] | None = None
        self._camera_coordinator: Any = None

    @classmethod
    def from_environment(cls) -> "RealSenseDepthCaptureAdapter":
        path = os.environ.get("ROBOT_SCOPE_DEPTH_CAPTURE_CONFIG")
        return cls(config_path=Path(path) if path else None,
                   enabled=os.environ.get("ROBOT_SCOPE_DEPTH_CAPTURE_ENABLE") == "1")

    def bind_camera_coordinator(self, camera: Any) -> None:
        with self._lock:
            if self._job is not None:
                raise ManagedScopeError("session", "reservation_owner_change")
            self._camera_coordinator = camera

    def capability(self) -> dict[str, Any]:
        # Importing a binding is read-only; a namespace package alone is not an
        # installed pipeline implementation. No context/device is created here.
        try:
            self._load_sdk()
            installed = True
        except SlamError:
            installed = False
        reason = ("DEPTH_CAPTURE_DISABLED" if not self.enabled else
                  "DEPTH_CAPTURE_CONFIG_MISSING" if self.config_path is None else
                  "REALSENSE_SDK_UNAVAILABLE" if not installed else None)
        return {"engine_id": self.engine_id, "supported_in_source": True,
                "installed": installed, "available_now": reason is None,
                "blocked_reason": reason, "tasks": ["calibration"],
                "effective_modes": {"calibration": "depth_calibration"},
                "software_verified": False, "hardware_verified": False,
                "operational_pose_approved": False}

    def _load_sdk(self) -> Any:
        try:
            sdk = self._sdk_loader()
            if not self._injected_sdk and not callable(getattr(sdk, "pipeline", None)):
                sdk = importlib.import_module("pyrealsense2.pyrealsense2")
            if not all(callable(getattr(sdk, name, None)) for name in ("pipeline", "context", "config")):
                raise ImportError("SDK pipeline binding is absent")
            return sdk
        except (ImportError, OSError) as exc:
            raise SlamError("REALSENSE_SDK_UNAVAILABLE", 503) from exc

    def _configuration(self) -> dict[str, Any]:
        if not self.enabled:
            raise SlamError("DEPTH_CAPTURE_DISABLED")
        if self.config_path is None:
            raise SlamError("DEPTH_CAPTURE_CONFIG_MISSING")
        try:
            value = private_json(self.config_path)
            fields = {"schema_version", "serial", "width", "height", "fps", "managed_scope", "max_session_s"}
            if (set(value) - fields or not fields - {"max_session_s"} <= set(value)
                    or type(value["schema_version"]) is not int or value["schema_version"] != 1
                    or not isinstance(value["serial"], str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value["serial"])
                    or not isinstance(value["managed_scope"], str)):
                raise ValueError("invalid config")
            for name, lower, upper in (("width", 1, 1920), ("height", 1, 1080), ("fps", 1, 90)):
                if type(value[name]) is not int or not lower <= value[name] <= upper:
                    raise ValueError("invalid requested profile")
            lifetime = value.setdefault("max_session_s", 120)
            if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or not 1 <= lifetime <= 300:
                raise ValueError("invalid bounded lifetime")
            value["_scope"] = load_managed_scope(Path(value["managed_scope"]))
            return value
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SlamError("DEPTH_CAPTURE_CONFIG_INVALID", 422) from exc

    def preflight(self, task: str = "calibration") -> None:
        if task != "calibration":
            raise SlamError("MODE_UNSUPPORTED", 422)
        self._configuration()
        with self._lock:
            if self._job is not None:
                raise SlamError("RESOURCE_CONFLICT", resources=[{"resource": "camera", "reason": "depth_capture_owned"}])

    @staticmethod
    def _identity(session: dict[str, Any]) -> tuple[str, int]:
        identifier, generation = session.get("session_id"), session.get("generation")
        if (not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier)
                or type(generation) is not int or generation < 1
                or session.get("engine_id") != "realsense_depth" or session.get("task") != "calibration"):
            raise SlamError("DEPTH_CAPTURE_SESSION_INVALID", 422)
        return identifier, generation

    def _owned(self, session: dict[str, Any]) -> dict[str, Any]:
        identity = self._identity(session)
        with self._lock:
            if self._job is None or self._job["identity"] != identity:
                raise SlamError("SESSION_GENERATION_CONFLICT")
            return self._job

    def _reserve_domain(self, job: dict[str, Any]) -> None:
        scope, session = job["config"]["_scope"], job["session"]
        if self._camera_coordinator is None:
            raise ManagedScopeError("camera", "managed_reservation_missing")
        proof = self._camera_coordinator.reservation_proof(session)
        if proof.get("scope_id") != scope["scope_id"] or proof.get("scope_sha256") != scope["scope_sha256"]:
            raise ManagedScopeError("camera", "managed_scope_changed")
        reservation = DomainReservation(scope)
        job["domain_reservation"] = reservation
        reservation.acquire()
        validate_reservation_proof(dict(proof, schema_version=1, evidence_kind="live_managed_reservation",
            session_id=session["session_id"], generation=session["generation"], domain_id=scope["domain_id"],
            domain_lock=reservation.evidence()), scope)

    def start(self, session: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        identity = self._identity(session)
        self.preflight(session["task"])
        job: dict[str, Any] = {"identity": identity, "session": dict(session), "config": self._configuration(),
            "stop_event": threading.Event(), "cancel": cancel, "pipeline": None, "thread": None,
            "pipeline_started": False, "cleanup_complete": False, "cleanup_required": False,
            "latest": None, "sequence": 0, "reason": None, "started_monotonic": self._clock()}
        with self._lock:
            if self._job is not None:
                raise SlamError("OPERATION_IN_PROGRESS")
            self._job = job
        try:
            self._reserve_domain(job)
            if cancel.is_set():
                raise SlamError("START_CANCELLED")
            self._open_pipeline(job)
            if cancel.is_set():
                raise SlamError("START_CANCELLED")
            thread = threading.Thread(target=self._collect, args=(job,), name="robot-scope-depth-capture", daemon=True)
            job["thread"] = thread
            thread.start()
            return {"ready": False, "effective_mode": "depth_calibration", "operational_pose_applied": False}
        except Exception as exc:
            self._shutdown_pipeline(job)
            # Keep ownership until the broker's explicit stop/release settlement.
            if job["cleanup_required"]:
                raise SlamError("CLEANUP_REQUIRED") from exc
            if isinstance(exc, (SlamError, ManagedScopeError, CameraBusy)):
                raise
            raise SlamError("DEPTH_CAPTURE_START_FAILED", 503) from exc

    def _matches(self, profile: Any, stream: Any, index: int, fmt: Any, config: dict[str, Any]) -> bool:
        value = _profile(profile)
        return (profile.stream_type() == stream and profile.stream_index() == index and profile.format() == fmt
                and all(value.get(key) == config[key] for key in ("width", "height", "fps")))

    def _open_pipeline(self, job: dict[str, Any]) -> None:
        sdk = self._load_sdk()
        job["sdk"] = sdk
        context, config = sdk.context(), job["config"]
        devices = [device for device in context.query_devices()
                   if device.supports(sdk.camera_info.serial_number)
                   and device.get_info(sdk.camera_info.serial_number) == config["serial"]]
        if len(devices) != 1:
            raise SlamError("DEPTH_CAPTURE_DEVICE_MISSING" if not devices else "DEPTH_CAPTURE_DEVICE_AMBIGUOUS")
        device = devices[0]
        sensors = list(device.query_sensors())
        profiles = [profile for sensor in sensors for profile in sensor.get_stream_profiles()]
        if len(profiles) > 4096:
            raise SlamError("DEPTH_CAPTURE_PROFILE_INVENTORY_LIMIT")
        expected = {"ir1": (sdk.stream.infrared, 1, sdk.format.y8), "depth": (sdk.stream.depth, 0, sdk.format.z16)}
        if any(not any(self._matches(p, *spec, config) for p in profiles) for spec in expected.values()):
            raise SlamError("DEPTH_CAPTURE_PROFILE_UNSUPPORTED")
        job["supported_profiles"] = [_profile(profile) for profile in profiles]
        job["device"] = self._device_metadata(device, sdk)
        job["sensor_options_before_start"] = self._sensor_options(sensors, sdk)
        pipeline, requested = sdk.pipeline(context), sdk.config()
        job["pipeline"] = pipeline
        requested.enable_device(config["serial"])
        requested.enable_stream(sdk.stream.infrared, 1, config["width"], config["height"], sdk.format.y8, config["fps"])
        requested.enable_stream(sdk.stream.depth, config["width"], config["height"], sdk.format.z16, config["fps"])
        # start may acquire a device before raising; conservative cleanup then
        # retains the reservation if the SDK cannot confirm stop.
        job["pipeline_started"] = True
        active = pipeline.start(requested)
        actual_device = active.get_device()
        if actual_device.get_info(sdk.camera_info.serial_number) != config["serial"]:
            raise SlamError("DEPTH_CAPTURE_EFFECTIVE_DEVICE_MISMATCH")
        actual = list(active.get_streams())
        if len(actual) != 2:
            raise SlamError("DEPTH_CAPTURE_EFFECTIVE_PROFILE_MISMATCH")
        resolved: dict[str, Any] = {}
        for name, spec in expected.items():
            matches = [p for p in actual if self._matches(p, *spec, config)]
            if len(matches) != 1:
                raise SlamError("DEPTH_CAPTURE_EFFECTIVE_PROFILE_MISMATCH")
            resolved[name] = matches[0]
        scale = _finite(actual_device.first_depth_sensor().get_depth_scale())
        if scale <= 0:
            raise SlamError("DEPTH_CAPTURE_SCALE_INVALID")
        job.update(profiles=resolved, effective_profiles={key: _profile(p) for key, p in resolved.items()},
            depth_scale_m=scale, device=self._device_metadata(actual_device, sdk),
            sensor_options_after_start=self._sensor_options(list(actual_device.query_sensors()), sdk),
            extrinsics={"ir1_to_depth": _extrinsics(resolved["ir1"], resolved["depth"]),
                        "depth_to_ir1": _extrinsics(resolved["depth"], resolved["ir1"])})

    @staticmethod
    def _device_metadata(device: Any, sdk: Any) -> dict[str, Any]:
        result = {}
        for name in ("name", "serial_number", "firmware_version", "product_id", "product_line", "physical_port", "usb_type_descriptor"):
            key = getattr(sdk.camera_info, name, None)
            if key is not None and device.supports(key):
                result[name] = str(device.get_info(key))
        return result

    @staticmethod
    def _sensor_options(sensors: list[Any], sdk: Any) -> list[dict[str, Any]]:
        result = []
        for sensor in sensors:
            entry: dict[str, Any] = {"options": {}}
            try:
                if sensor.supports(sdk.camera_info.name):
                    entry["sensor_name"] = str(sensor.get_info(sdk.camera_info.name))
                for option in sensor.get_supported_options():
                    try:
                        entry["options"][str(option)] = {"value": _finite(sensor.get_option(option)), "read_only_observation": True}
                    except Exception:
                        entry["options"][str(option)] = {"available": False}
            except Exception:
                entry["option_readback_available"] = False
            result.append(entry)
        return result

    def _frame(self, frame: Any, name: str, job: dict[str, Any]) -> dict[str, Any]:
        if not frame:
            raise SlamError("DEPTH_CAPTURE_FRAME_MISSING")
        profile = frame.get_profile()
        actual = _profile(profile)
        if actual != job["effective_profiles"][name]:
            raise SlamError("DEPTH_CAPTURE_FRAME_PROFILE_MISMATCH")
        width, height = int(frame.get_width()), int(frame.get_height())
        stride, bits = int(frame.get_stride_in_bytes()), int(frame.get_bits_per_pixel())
        expected_bits = 8 if name == "ir1" else 16
        data = bytes(frame.get_data())
        if (width != actual["width"] or height != actual["height"] or bits != expected_bits
                or stride < width * (bits // 8) or len(data) != stride * height):
            raise SlamError("DEPTH_CAPTURE_FRAME_LAYOUT_INVALID")
        metadata = {}
        members = getattr(job["sdk"].frame_metadata_value, "__members__", {})
        for key, value in members.items():
            if frame.supports_frame_metadata(value):
                metadata[key] = int(frame.get_frame_metadata(value))
        return {"width": width, "height": height, "stride_bytes": stride,
                "bytes_per_pixel": bits // 8, "format": "Y8" if name == "ir1" else "Z16",
                "byte_order": "not_applicable" if name == "ir1" else sys.byteorder,
                "profile": actual, "intrinsics": _intrinsics(profile), "data": data,
                "frame_id": "realsense_ir1_optical" if name == "ir1" else "realsense_depth_optical",
                "frame_id_source": "sdk_logical_optical_not_ros_tf",
                "frame_number": int(frame.get_frame_number()), "timestamp_ms": _finite(frame.get_timestamp()),
                "timestamp_domain": str(frame.get_frame_timestamp_domain()), "metadata": metadata}

    def _collect(self, job: dict[str, Any]) -> None:
        last_valid = self._clock()
        try:
            while not job["stop_event"].is_set() and not job["cancel"].is_set():
                now = self._clock()
                if now - job["started_monotonic"] >= job["config"]["max_session_s"]:
                    job["reason"] = "DEPTH_CAPTURE_SESSION_EXPIRED"
                    break
                try:
                    frameset = job["pipeline"].wait_for_frames(FRAME_WAIT_MS)
                except RuntimeError:
                    job["reason"] = "DEPTH_CAPTURE_FRAME_TIMEOUT"
                    if self._clock() - last_valid >= NO_FRAME_TIMEOUT_S:
                        break
                    continue
                received = self._clock()
                ir1 = self._frame(frameset.get_infrared_frame(1), "ir1", job)
                depth = self._frame(frameset.get_depth_frame(), "depth", job)
                if ir1["timestamp_domain"] != depth["timestamp_domain"]:
                    raise SlamError("DEPTH_CAPTURE_TIMESTAMP_DOMAIN_MISMATCH")
                skew = abs(ir1["timestamp_ms"] - depth["timestamp_ms"])
                if skew > MAX_PAIR_SKEW_MS:
                    raise SlamError("DEPTH_CAPTURE_TIMESTAMP_MISMATCH")
                with self._condition:
                    job["sequence"] += 1
                    job["latest"] = {"frames": {"ir1": ir1, "depth": depth},
                        "frameset": {"verified": True, "ir_frame_number": ir1["frame_number"],
                                     "depth_frame_number": depth["frame_number"], "source_skew_ms": skew},
                        "wait_started_monotonic": now, "received_monotonic": received, "received_at_utc": _utc()}
                    job["reason"] = None
                    last_valid = received
                    self._condition.notify_all()
        except Exception as exc:
            job["reason"] = exc.code if isinstance(exc, SlamError) else "DEPTH_CAPTURE_ACQUISITION_FAILED"
        finally:
            self._shutdown_pipeline(job)
            with self._condition:
                self._condition.notify_all()

    def _shutdown_pipeline(self, job: dict[str, Any]) -> None:
        try:
            if job["pipeline_started"]:
                job["pipeline"].stop()
                job["pipeline_started"] = False
            if job.get("domain_reservation") is not None:
                job["domain_reservation"].release()
            job["cleanup_complete"] = True
            job["cleanup_required"] = False
        except Exception:
            job["cleanup_required"] = True
            job["cleanup_complete"] = False
            job["reason"] = "CLEANUP_REQUIRED"

    def status(self, session: dict[str, Any]) -> dict[str, Any]:
        job = self._owned(session)
        with self._lock:
            latest = job["latest"]
            alive = job["pipeline_started"] and not job["cleanup_required"] and not job["stop_event"].is_set()
            ready = bool(alive and latest and self._clock() - latest["received_monotonic"] <= MAX_FRAME_AGE_S)
            return {"alive": bool(alive), "ready": ready, "tracking_state": "UNAVAILABLE",
                "state": "CAPTURING" if alive else "STOPPED", "reason": job["reason"],
                "cleanup_required": job["cleanup_required"], "cleanup_complete": job["cleanup_complete"],
                "effective_mode": "depth_calibration", "operational_pose_approved": False,
                "effective_profiles": deepcopy(job.get("effective_profiles", {})),
                "depth_scale_m": job.get("depth_scale_m"), "sequence": job["sequence"],
                "max_session_s": job["config"]["max_session_s"]}

    def capture(self, session: dict[str, Any], confirmation: dict[str, Any]) -> dict[str, Any]:
        validate_confirmation(confirmation)
        job = self._owned(session)
        received, received_at = self._clock(), _utc()
        deadline = received + CAPTURE_WAIT_S
        with self._condition:
            sequence = job["sequence"]
            while True:
                if self._job is not job or job["cleanup_complete"] or job["cleanup_required"] or job["stop_event"].is_set():
                    raise SlamError(job["reason"] or "DEPTH_CAPTURE_STOPPED")
                if job["cancel"].is_set():
                    raise SlamError("DEPTH_CAPTURE_STOPPING")
                if self._clock() - job["started_monotonic"] >= job["config"]["max_session_s"]:
                    raise SlamError("DEPTH_CAPTURE_SESSION_EXPIRED")
                latest = job["latest"]
                if (latest and job["sequence"] > sequence and latest["wait_started_monotonic"] >= received
                        and self._clock() - latest["received_monotonic"] <= MAX_FRAME_AGE_S):
                    captured = deepcopy(latest)
                    break
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise SlamError("DEPTH_CAPTURE_POST_CONFIRMATION_FRAME_TIMEOUT")
                self._condition.wait(min(remaining, 0.1))
        return {"schema_version": 1, "session_id": session["session_id"], "generation": session["generation"],
            "captured_at_utc": captured["received_at_utc"], "request_received_at_utc": received_at,
            "confirmation": deepcopy(confirmation), "post_confirmation_sdk_wait": True,
            "sensor_exposure_after_confirmation_independently_verified": False,
            "device": deepcopy(job["device"]), "supported_profiles": deepcopy(job["supported_profiles"]),
            "effective_profiles": deepcopy(job["effective_profiles"]), "depth_scale_m": job["depth_scale_m"],
            "extrinsics": deepcopy(job["extrinsics"]), "frames": captured["frames"], "frameset": captured["frameset"],
            "sensor_options_before_start": deepcopy(job["sensor_options_before_start"]),
            "sensor_options_after_start": deepcopy(job["sensor_options_after_start"]),
            "processing": {"alignment": "none", "filters": [], "sdk_option_writes": False,
                           "body_level_assumed": False, "operational_tf_published": False}}

    def stop(self, session: dict[str, Any]) -> None:
        self._identity(session)
        with self._lock:
            if self._job is None:
                return
            job = self._owned(session)
            job["stop_event"].set()
            self._condition.notify_all()
        thread = job["thread"]
        if thread is not None:
            thread.join(timeout=FRAME_WAIT_MS / 1000 + 2)
            if thread.is_alive():
                job["cleanup_required"] = True
                job["reason"] = "CLEANUP_REQUIRED"
                raise SlamError("CLEANUP_REQUIRED")
        if not job["cleanup_complete"]:
            self._shutdown_pipeline(job)
        if not job["cleanup_complete"]:
            raise SlamError("CLEANUP_REQUIRED")
        with self._lock:
            if self._job is job:
                self._job = None

    def frame(self, session: dict[str, Any]) -> dict[str, Any]:
        self._owned(session)
        return {"reason": "DEPTH_CAPTURE_USE_EXPLICIT_CAPTURE", "engine_id": self.engine_id}
