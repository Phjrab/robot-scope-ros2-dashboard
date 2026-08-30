#!/usr/bin/env python3
"""Bounded, observation-only perception runtime for the robot-side Jetson.

The process consumes the existing RealSense relay.  It never opens a camera,
imports robot control code, publishes ROS data, or owns a motion lease.
"""

from __future__ import annotations

import ctypes
import hashlib
import http.client
import ipaddress
import json
import math
import os
import platform
import re
import signal
import socket
import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence


MODEL_SCHEMA = "robot-scope.perception-model/v1"
HEALTH_SCHEMA = "robot-scope.perception-shadow-health/v1"
RESULT_SCHEMA = "robot-scope.perception-result/v1"
SNAPSHOT_SCHEMA = "robot-scope.perception-snapshot/v1"
RUNTIME_MODE = "SHADOW"
MODEL_ROOT = Path("/var/lib/robot-scope/perception/models")
ALLOWED_TASKS = frozenset({"lane", "object", "depth_summary"})
ALLOWED_BACKENDS = frozenset({"onnx", "tensorrt"})
ALLOWED_POINTCLOUD_MODES = frozenset({"OFF", "SUMMARY"})
ALLOWED_RESOLUTIONS = frozenset({(320, 240), (640, 480), (1280, 720)})
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
CLASS_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}\Z")
BOOT_ID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,35}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_TENSORRT_BINDINGS = 16
MAX_TENSORRT_DEVICE_BYTES = 512 * 1024 * 1024
MAX_DETECTIONS = 100
MAX_ERROR_CHARS = 240
METRIC_SAMPLES = 120
METRIC_WINDOW_S = 5.0
SOURCE_RECONNECT_MAX_S = 5.0
SOURCE_HEADER_BYTES = 8192
SOURCE_HEADER_LINES = 16
HEALTH_BIND_HOST = "127.0.0.1"
HEALTH_PORT = 8091
RESULT_PORT = 8092
RESULT_PATH = "/api/v1/perception/snapshot"
RESULT_SOURCE_ID = "go2-internal-realsense"
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
)


class ShadowSetupError(RuntimeError):
    """Fail-closed configuration/model contract error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip().lower()
    except (OSError, UnicodeError) as exc:
        raise ShadowSetupError("BOOT_ID_UNAVAILABLE", "kernel boot identity is unavailable") from exc
    if not BOOT_ID_PATTERN.fullmatch(value):
        raise ShadowSetupError("BOOT_ID_UNAVAILABLE", "kernel boot identity is invalid")
    return value


def _redacted_error(value: object) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = re.sub(
        r"(?i)\b(password|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    return text[:MAX_ERROR_CHARS]


def _finite(value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric metric")
    result = float(str(value))
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError("metric is outside the allowed range")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                raise ShadowSetupError("MODEL_TOO_LARGE", "model artifact exceeds the size limit")
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RuntimeIdentity:
    machine: str
    jetpack: str
    tensorrt: str

    @classmethod
    def discover(cls) -> "RuntimeIdentity":
        jetpack = "unavailable"
        try:
            line = Path("/etc/nv_tegra_release").read_text(encoding="ascii")[:512]
            match = re.search(r"# R(\d+) \(release\), REVISION: ([0-9.]+)", line)
            if match:
                jetpack = f"R{match.group(1)}.{match.group(2)}"
        except (OSError, UnicodeError):
            pass
        tensorrt = "unavailable"
        try:
            import tensorrt as trt_module  # type: ignore[import-not-found]

            tensorrt = str(trt_module.__version__)[:32]
        except (ImportError, AttributeError):
            pass
        return cls(platform.machine().lower(), jetpack, tensorrt)


@dataclass(frozen=True)
class ModelManifest:
    model_id: str
    task: str
    backend: str
    artifact: Path
    artifact_sha256: str
    source_model_sha256: str
    output_adapter: str
    input_width: int
    input_height: int
    input_color: str
    classes: tuple[str, ...]
    target: RuntimeIdentity

    @classmethod
    def load(
        cls,
        filename: str,
        *,
        model_root: Path = MODEL_ROOT,
        runtime: Optional[RuntimeIdentity] = None,
    ) -> "ModelManifest":
        if not NAME_PATTERN.fullmatch(filename) or not filename.endswith(".json"):
            raise ShadowSetupError("INVALID_MANIFEST", "manifest must be one safe JSON filename")
        try:
            root = model_root.resolve(strict=True)
            candidate = root / filename
            path = candidate.resolve(strict=True)
        except OSError as exc:
            raise ShadowSetupError("INVALID_MANIFEST", "model root or manifest is unavailable") from exc
        if path.parent != root or candidate.is_symlink() or not path.is_file():
            raise ShadowSetupError("INVALID_MANIFEST", "manifest escaped the fixed model root")
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ShadowSetupError("INVALID_MANIFEST", "manifest exceeds the size limit")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ShadowSetupError("INVALID_MANIFEST", "manifest is not valid JSON") from exc
        if not isinstance(payload, Mapping) or payload.get("schema") != MODEL_SCHEMA:
            raise ShadowSetupError("INVALID_MANIFEST", "unknown model manifest schema")
        model_id = str(payload.get("model_id", ""))
        task = str(payload.get("task", ""))
        backend = str(payload.get("backend", "")).lower()
        artifact_name = str(payload.get("artifact", ""))
        artifact_sha256 = str(payload.get("artifact_sha256", "")).lower()
        source_hash = str(payload.get("source_model_sha256", "")).lower()
        output_adapter = str(payload.get("output_adapter", ""))
        if not NAME_PATTERN.fullmatch(model_id):
            raise ShadowSetupError("INVALID_MANIFEST", "invalid model ID")
        if task not in ALLOWED_TASKS or backend not in ALLOWED_BACKENDS:
            raise ShadowSetupError("INVALID_MANIFEST", "task or backend is not allowlisted")
        if not NAME_PATTERN.fullmatch(artifact_name):
            raise ShadowSetupError("INVALID_MANIFEST", "artifact must be one safe filename")
        if not SHA256_PATTERN.fullmatch(artifact_sha256) or not SHA256_PATTERN.fullmatch(source_hash):
            raise ShadowSetupError("INVALID_MANIFEST", "model hashes must be lowercase SHA-256")
        try:
            artifact_candidate = root / artifact_name
            artifact = artifact_candidate.resolve(strict=True)
        except OSError as exc:
            raise ShadowSetupError("INVALID_MANIFEST", "model artifact is unavailable") from exc
        if artifact.parent != root or artifact_candidate.is_symlink() or not artifact.is_file():
            raise ShadowSetupError("INVALID_MANIFEST", "artifact escaped the fixed model root")
        if _sha256_file(artifact) != artifact_sha256:
            raise ShadowSetupError("MODEL_HASH_MISMATCH", "artifact SHA-256 does not match manifest")
        input_contract = payload.get("input")
        target_contract = payload.get("target")
        if not isinstance(input_contract, Mapping) or not isinstance(target_contract, Mapping):
            raise ShadowSetupError("INVALID_MANIFEST", "input and target contracts are required")
        try:
            width = int(input_contract.get("width", 0))
            height = int(input_contract.get("height", 0))
        except (TypeError, ValueError) as exc:
            raise ShadowSetupError("INVALID_MANIFEST", "input dimensions are invalid") from exc
        color = str(input_contract.get("color", "")).upper()
        if (width, height) not in ALLOWED_RESOLUTIONS or color not in {"RGB", "BGR"}:
            raise ShadowSetupError("INVALID_MANIFEST", "input profile is not allowlisted")
        raw_classes = payload.get("classes", ())
        if not isinstance(raw_classes, Sequence) or isinstance(raw_classes, (str, bytes)):
            raise ShadowSetupError("INVALID_MANIFEST", "model classes must be a bounded list")
        classes = tuple(str(item) for item in raw_classes)
        if len(classes) > 256 or any(not CLASS_NAME_PATTERN.fullmatch(item) for item in classes):
            raise ShadowSetupError("INVALID_MANIFEST", "model classes are invalid")
        if task == "object" and not classes:
            raise ShadowSetupError("INVALID_MANIFEST", "object model classes are required")
        if task != "object" and classes:
            raise ShadowSetupError("INVALID_MANIFEST", "classes are only valid for object models")
        target = RuntimeIdentity(
            str(target_contract.get("machine", "")).lower(),
            str(target_contract.get("jetpack", ""))[:32],
            str(target_contract.get("tensorrt", ""))[:32],
        )
        if not target.machine or not target.jetpack or (backend == "tensorrt" and not target.tensorrt):
            raise ShadowSetupError("INVALID_MANIFEST", "target runtime identity is incomplete")
        current = runtime or RuntimeIdentity.discover()
        if backend == "tensorrt" and target != current:
            raise ShadowSetupError(
                "RUNTIME_MISMATCH",
                "TensorRT engine target does not match this Jetson runtime",
            )
        expected_output_adapter = {
            "lane": "lane_v1",
            "object": "yolo_xyxy_v1",
            "depth_summary": "depth_summary_v1",
        }[task]
        if output_adapter != expected_output_adapter:
            raise ShadowSetupError("INVALID_MANIFEST", "output adapter does not match task")
        return cls(
            model_id,
            task,
            backend,
            artifact,
            artifact_sha256,
            source_hash,
            output_adapter,
            width,
            height,
            color,
            classes,
            target,
        )


@dataclass(frozen=True)
class Frame:
    sequence: int
    capture_monotonic_ns: int
    received_monotonic_ns: int
    width: int
    height: int
    pixel_format: str
    jpeg: bytes
    source_sequence: int = 0
    source_epoch: int = 0

    @property
    def age_s(self) -> float:
        return max(0.0, (time.monotonic_ns() - self.capture_monotonic_ns) / 1e9)


class LatestFrameHub:
    """One latest frame; consumers never create an unbounded backlog."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest: Optional[Frame] = None
        self._closed = False
        self._published = 0
        self._rejected = 0

    def publish(self, frame: Frame) -> bool:
        if (
            frame.sequence <= 0
            or frame.capture_monotonic_ns <= 0
            or frame.received_monotonic_ns <= 0
            or frame.source_sequence <= 0
            or frame.source_epoch <= 0
            or (frame.width, frame.height) not in ALLOWED_RESOLUTIONS
            or frame.pixel_format != "JPEG"
            or len(frame.jpeg) > MAX_FRAME_BYTES
            or not frame.jpeg.startswith(b"\xff\xd8")
            or not frame.jpeg.endswith(b"\xff\xd9")
        ):
            with self._condition:
                self._rejected += 1
            return False
        with self._condition:
            if self._closed or (self._latest and frame.sequence <= self._latest.sequence):
                self._rejected += 1
                return False
            self._latest = frame
            self._published += 1
            self._condition.notify_all()
        return True

    def wait_after(self, sequence: int, timeout_s: float = 0.5) -> Optional[Frame]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._closed or bool(self._latest and self._latest.sequence > sequence),
                timeout=max(0.01, min(timeout_s, 1.0)),
            )
            if self._latest and self._latest.sequence > sequence:
                return self._latest
            return None

    def snapshot(self) -> dict[str, object]:
        with self._condition:
            latest = self._latest
            return {
                "queue_depth": 1 if latest else 0,
                "published": self._published,
                "rejected": self._rejected,
                "latest_sequence": latest.sequence if latest else 0,
                "latest_age_s": round(latest.age_s, 3) if latest else None,
            }

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._latest = None
            self._condition.notify_all()


class EngineAdapter(Protocol):
    manifest: ModelManifest

    def infer(self, frame: Frame) -> Mapping[str, object]: ...


class LaneEngine:
    task = "lane"

    @staticmethod
    def validate(result: Mapping[str, object]) -> dict[str, object]:
        return {
            "lateral_error_normalized": round(_finite(result.get("lateral_error_normalized"), minimum=-1, maximum=1), 4),
            "heading_error_rad": round(_finite(result.get("heading_error_rad"), minimum=-math.pi, maximum=math.pi), 4),
            "curvature": round(_finite(result.get("curvature"), minimum=-10, maximum=10), 5),
            "left_lane_visible": result.get("left_lane_visible") is True,
            "right_lane_visible": result.get("right_lane_visible") is True,
            "confidence": round(_finite(result.get("confidence"), minimum=0, maximum=1), 4),
            "reason": str(result.get("reason", ""))[:96],
        }


class ObjectEngine:
    task = "object"

    @staticmethod
    def validate(result: Mapping[str, object]) -> dict[str, object]:
        raw = result.get("detections", ())
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError("detections must be a bounded sequence")
        if len(raw) > MAX_DETECTIONS:
            raise ValueError("detection count exceeds the bound")
        detections = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise ValueError("detection is not an object")
            box = item.get("box_xyxy")
            if not isinstance(box, Sequence) or len(box) != 4:
                raise ValueError("detection box is invalid")
            detections.append(
                {
                    "class_id": int(_finite(item.get("class_id"), minimum=0, maximum=65535)),
                    "class_name": str(item.get("class_name", "")),
                    "x1": round(_finite(box[0], minimum=0, maximum=8192), 2),
                    "y1": round(_finite(box[1], minimum=0, maximum=8192), 2),
                    "x2": round(_finite(box[2], minimum=0, maximum=8192), 2),
                    "y2": round(_finite(box[3], minimum=0, maximum=8192), 2),
                    "confidence": round(_finite(item.get("confidence"), minimum=0, maximum=1), 4),
                }
            )
            if not CLASS_NAME_PATTERN.fullmatch(detections[-1]["class_name"]):
                raise ValueError("detection class name is invalid")
            if detections[-1]["x2"] <= detections[-1]["x1"] or detections[-1]["y2"] <= detections[-1]["y1"]:
                raise ValueError("detection coordinates are not ordered")
        return {"detections": detections, "detection_count": len(detections)}


class DepthSummaryEngine:
    task = "depth_summary"

    @staticmethod
    def validate(result: Mapping[str, object]) -> dict[str, object]:
        return {
            "front_min_distance_m": round(_finite(result.get("front_min_distance_m"), minimum=0, maximum=100), 3),
            "left_clearance_m": round(_finite(result.get("left_clearance_m"), minimum=0, maximum=100), 3),
            "right_clearance_m": round(_finite(result.get("right_clearance_m"), minimum=0, maximum=100), 3),
            "obstacle_count": int(_finite(result.get("obstacle_count"), minimum=0, maximum=10000)),
            "ground_confidence": round(_finite(result.get("ground_confidence"), minimum=0, maximum=1), 4),
            "mode": "SUMMARY",
        }


RESULT_VALIDATORS = {
    "lane": LaneEngine.validate,
    "object": ObjectEngine.validate,
    "depth_summary": DepthSummaryEngine.validate,
}


def _adapt_array_output(manifest: ModelManifest, values: Any) -> Mapping[str, object]:
    if manifest.output_adapter == "lane_v1":
        flat = values.reshape(-1)
        if flat.size < 6:
            raise ValueError("lane output is incomplete")
        return {
            "lateral_error_normalized": flat[0],
            "heading_error_rad": flat[1],
            "curvature": flat[2],
            "left_lane_visible": bool(flat[3] >= 0.5),
            "right_lane_visible": bool(flat[4] >= 0.5),
            "confidence": flat[5],
            "reason": "model_output",
        }
    if manifest.output_adapter == "yolo_xyxy_v1":
        if values.size % 6:
            raise ValueError("object output is not an Nx6 tensor")
        rows = values.reshape(-1, 6)
        if len(rows) > MAX_DETECTIONS:
            raise ValueError("object output exceeds the detection bound")
        return {
            "detections": [
                {
                    "box_xyxy": row[:4].tolist(),
                    "confidence": row[4],
                    "class_id": row[5],
                    "class_name": manifest.classes[int(row[5])]
                    if 0 <= int(row[5]) < len(manifest.classes)
                    else "",
                }
                for row in rows
            ]
        }
    if manifest.output_adapter == "depth_summary_v1":
        flat = values.reshape(-1)
        if flat.size < 5:
            raise ValueError("depth summary output is incomplete")
        return {
            "front_min_distance_m": flat[0],
            "left_clearance_m": flat[1],
            "right_clearance_m": flat[2],
            "obstacle_count": flat[3],
            "ground_confidence": flat[4],
        }
    raise ValueError("output adapter is not implemented")


class InferenceWorker:
    def __init__(
        self,
        hub: LatestFrameHub,
        adapter: EngineAdapter,
        *,
        max_hz: float,
        stale_after_s: float,
        source_id: str = RESULT_SOURCE_ID,
        boot_id: str = "00000000-0000-0000-0000-000000000000",
    ) -> None:
        self.hub = hub
        self.adapter = adapter
        self.max_hz = _finite(max_hz, minimum=0.1, maximum=30)
        self.stale_after_s = _finite(stale_after_s, minimum=0.1, maximum=10)
        if not NAME_PATTERN.fullmatch(source_id) or not BOOT_ID_PATTERN.fullmatch(boot_id):
            raise ShadowSetupError("INVALID_CONFIG", "result source or boot identity is invalid")
        self.source_id = source_id
        self.boot_id = boot_id
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._state = "STARTING"
        self._last_error = ""
        self._last_result: Optional[dict[str, object]] = None
        self._last_sequence = 0
        self._superseded = 0
        self._stale_frames = 0
        self._failures = 0
        self._latencies_ms: deque[float] = deque(maxlen=METRIC_SAMPLES)
        self._completion_times: deque[float] = deque(maxlen=METRIC_SAMPLES)

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"shadow-{self.adapter.manifest.task}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        next_allowed = 0.0
        while not self._stop.is_set():
            frame = self.hub.wait_after(self._last_sequence)
            if frame is None:
                continue
            if self._last_sequence:
                self._superseded += max(0, frame.sequence - self._last_sequence - 1)
            self._last_sequence = frame.sequence
            now = time.monotonic()
            if now < next_allowed:
                continue
            next_allowed = now + (1.0 / self.max_hz)
            if frame.age_s > self.stale_after_s:
                with self._lock:
                    self._stale_frames += 1
                    self._state = "FAILED"
                    self._last_result = None
                    self._last_error = "SOURCE_STALE: frame exceeded the inference age limit"
                continue
            started_ns = time.monotonic_ns()
            try:
                raw = self.adapter.infer(frame)
                validated = RESULT_VALIDATORS[self.adapter.manifest.task](raw)
                completed_ns = time.monotonic_ns()
                latency_ms = (completed_ns - started_ns) / 1e6
                confidence = validated.get("confidence")
                if confidence is None and self.adapter.manifest.task == "object":
                    detections = validated.get("detections", ())
                    confidence = max(
                        (float(item["confidence"]) for item in detections),
                        default=0.0,
                    )
                if confidence is None:
                    confidence = validated.get("ground_confidence", 0.0)
                observation = {
                    "schema_version": RESULT_SCHEMA,
                    "source_id": self.source_id,
                    "boot_id": self.boot_id,
                    "sequence": frame.sequence,
                    "source_sequence": frame.source_sequence,
                    "source_epoch": frame.source_epoch,
                    "task": self.adapter.manifest.task,
                    "capture_timestamp": frame.capture_monotonic_ns,
                    "capture_clock_domain": "robot-monotonic",
                    "inference_started_at": started_ns,
                    "inference_completed_at": completed_ns,
                    "model_id": self.adapter.manifest.model_id,
                    "model_sha256": self.adapter.manifest.artifact_sha256,
                    "backend": self.adapter.manifest.backend,
                    "input_width": self.adapter.manifest.input_width,
                    "input_height": self.adapter.manifest.input_height,
                    "result_status": "LIVE",
                    "confidence": round(_finite(confidence, minimum=0, maximum=1), 4),
                    "payload": validated,
                }
                with self._lock:
                    self._last_result = observation
                    self._last_error = ""
                    self._state = "LIVE"
                    self._latencies_ms.append(latency_ms)
                    self._completion_times.append(time.monotonic())
            except Exception as exc:  # inference adapters are an isolation boundary
                with self._lock:
                    self._failures += 1
                    self._state = "FAILED"
                    self._last_result = None
                    self._last_error = _redacted_error(exc)

    def health(self) -> dict[str, object]:
        now = time.monotonic()
        with self._lock:
            while self._completion_times and now - self._completion_times[0] > METRIC_WINDOW_S:
                self._completion_times.popleft()
            latencies = list(self._latencies_ms)
            p50 = statistics.median(latencies) if latencies else None
            p95 = (
                sorted(latencies)[max(0, math.ceil(len(latencies) * 0.95) - 1)]
                if latencies
                else None
            )
            return {
                "task": self.adapter.manifest.task,
                "state": self._state,
                "model_id": self.adapter.manifest.model_id,
                "model_sha256": self.adapter.manifest.artifact_sha256,
                "backend": self.adapter.manifest.backend,
                "fps": round(len(self._completion_times) / METRIC_WINDOW_S, 2),
                "inference_p50_ms": round(p50, 3) if p50 is not None else None,
                "inference_p95_ms": round(p95, 3) if p95 is not None else None,
                "last_source_sequence": self._last_sequence,
                "superseded_frames": self._superseded,
                "stale_frames": self._stale_frames,
                "failures": self._failures,
                "last_error": self._last_error,
                "latest_result": self._last_result,
            }

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.5)
        close = getattr(self.adapter, "close", None)
        if callable(close):
            close()


class ThermalProbe:
    """Read fixed sysfs thermal inputs; missing data remains UNVERIFIED."""

    def __init__(self, paths: Optional[Sequence[Path]] = None, *, failure_c: float = 90.0):
        self.paths = tuple(paths) if paths is not None else tuple(
            Path("/sys/devices/virtual/thermal").glob("thermal_zone*/temp")
        )
        self.failure_c = _finite(failure_c, minimum=70, maximum=100)

    def status(self) -> dict[str, object]:
        readings = []
        for path in self.paths[:32]:
            try:
                readings.append(float(path.read_text(encoding="ascii")[:16].strip()) / 1000)
            except (OSError, UnicodeError, ValueError):
                continue
        if not readings:
            return {"state": "UNVERIFIED", "max_c": None, "throttling": "UNVERIFIED"}
        maximum = max(readings)
        return {
            "state": "FAILED" if maximum >= self.failure_c else "DEGRADED",
            "max_c": round(maximum, 1),
            "throttling": "UNVERIFIED",
        }


class PerceptionRuntime:
    def __init__(
        self,
        workers: Sequence[InferenceWorker],
        *,
        hub: Optional[LatestFrameHub] = None,
        thermal_probe: Optional[ThermalProbe] = None,
        pointcloud_mode: str = "OFF",
        source_diagnostics: Optional[Callable[[], Mapping[str, object]]] = None,
        source_stale_after_s: float = 1.0,
    ) -> None:
        mode = str(pointcloud_mode).upper()
        if mode not in ALLOWED_POINTCLOUD_MODES:
            raise ShadowSetupError("INVALID_CONFIG", "raw/diagnostic point cloud is not implemented")
        self.hub = hub or (workers[0].hub if workers else LatestFrameHub())
        self.workers = tuple(workers)
        self.thermal_probe = thermal_probe or ThermalProbe()
        self.pointcloud_mode = mode
        self.source_diagnostics = source_diagnostics
        self.source_stale_after_s = _finite(
            source_stale_after_s, minimum=0.1, maximum=10
        )
        self._started_at = time.monotonic()

    def start(self) -> None:
        for worker in self.workers:
            worker.start()

    def submit(self, frame: Frame) -> bool:
        return self.hub.publish(frame)

    def health(self) -> dict[str, object]:
        source = self.hub.snapshot()
        if self.source_diagnostics is not None:
            source.update(self.source_diagnostics())
        engines = [worker.health() for worker in self.workers]
        thermal = self.thermal_probe.status()
        source_age = source.get("latest_age_s")
        source_stale = source_age is None or _finite(
            source_age, minimum=0, maximum=86400
        ) > self.source_stale_after_s
        source["state"] = "FAILED" if source_stale else "LIVE"
        if source_stale:
            engines = [
                {
                    **engine,
                    "state": "FAILED",
                    "latest_result": None,
                    "last_error": "SOURCE_STALE: no fresh relay frame",
                }
                for engine in engines
            ]
        live = sum(1 for engine in engines if engine["state"] == "LIVE")
        if not engines or live == 0 or thermal["state"] == "FAILED":
            state = "FAILED"
        elif live < len(engines) or thermal["state"] != "LIVE":
            state = "DEGRADED"
        else:
            state = "LIVE"
        return {
            "schema": HEALTH_SCHEMA,
            "mode": RUNTIME_MODE,
            "state": state,
            "clock_domain": "robot-monotonic",
            "motion_authority": False,
            "command_publishers": 0,
            "pointcloud_mode": self.pointcloud_mode,
            "raw_pointcloud_generated": False,
            "source": source,
            "engines": engines,
            "thermal": thermal,
            "uptime_s": round(time.monotonic() - self._started_at, 1),
        }

    def result_snapshot(self) -> dict[str, object]:
        engines = [worker.health() for worker in self.workers]
        results = [
            engine["latest_result"]
            for engine in engines
            if engine.get("state") == "LIVE" and isinstance(engine.get("latest_result"), Mapping)
        ]
        return {
            "schema_version": SNAPSHOT_SCHEMA,
            "server_monotonic": time.monotonic_ns(),
            "mode": RUNTIME_MODE,
            "results": results,
        }

    def stop(self) -> None:
        self.hub.close()
        for worker in self.workers:
            worker.stop()


class MjpegFrameSource:
    """Fixed-host consumer of relay frames carrying capture metadata."""

    def __init__(self, host: str, port: int, width: int, height: int) -> None:
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.last_error = ""
        self.reconnects = 0
        self._runtime_sequence = 0

    @staticmethod
    def _part_headers(response: http.client.HTTPResponse) -> Optional[dict[str, str]]:
        total = 0
        headers: dict[str, str] = {}
        for _index in range(SOURCE_HEADER_LINES):
            line = response.readline(SOURCE_HEADER_BYTES + 1)
            total += len(line)
            if not line or len(line) > SOURCE_HEADER_BYTES or total > SOURCE_HEADER_BYTES:
                raise ValueError("multipart headers exceed the bound")
            if line in {b"\r\n", b"\n"}:
                return headers
            name, separator, value = line.decode("ascii", errors="strict").partition(":")
            if not separator:
                raise ValueError("malformed multipart header")
            key = name.strip().lower()
            if key in headers:
                raise ValueError("duplicate multipart header")
            headers[key] = value.strip()
        raise ValueError("too many multipart headers")

    def run_once(self, runtime: PerceptionRuntime, stop: threading.Event) -> None:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3.0)
        try:
            connection.request(
                "GET",
                "/stream",
                headers={"Host": f"{self.host}:{self.port}", "Accept": "multipart/x-mixed-replace"},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OSError(f"relay returned HTTP {response.status}")
            while not stop.is_set():
                boundary = response.readline(256)
                if not boundary:
                    raise OSError("relay stream ended")
                if boundary.rstrip(b"\r\n") != b"--robot-scope-frame":
                    continue
                headers = self._part_headers(response)
                if headers is None:
                    continue
                length = int(headers.get("content-length", "-1"))
                content_type = headers.get("content-type", "")
                if content_type != "image/jpeg":
                    if 0 <= length <= 1024:
                        response.read(length + 2)
                    continue
                if not 4 <= length <= MAX_FRAME_BYTES:
                    raise ValueError("JPEG content length is outside the bound")
                sequence = int(headers.get("x-robot-scope-sequence", "0"))
                source_epoch = int(headers.get("x-robot-scope-source-epoch", "0"))
                capture_ns = int(headers.get("x-robot-scope-capture-monotonic-ns", "0"))
                capture_clock = headers.get("x-robot-scope-capture-clock", "")
                jpeg = response.read(length)
                response.read(2)
                if len(jpeg) != length:
                    raise OSError("truncated relay JPEG")
                if (
                    sequence <= 0
                    or source_epoch <= 0
                    or capture_ns <= 0
                    or capture_clock != "robot-monotonic"
                ):
                    raise ValueError("relay frame identity metadata is missing")
                self.last_error = ""
                self._runtime_sequence += 1
                runtime.submit(
                    Frame(
                        self._runtime_sequence,
                        capture_ns,
                        time.monotonic_ns(),
                        self.width,
                        self.height,
                        "JPEG",
                        jpeg,
                        sequence,
                        source_epoch,
                    )
                )
        finally:
            connection.close()

    def supervise(self, runtime: PerceptionRuntime, stop: threading.Event) -> None:
        delay = 0.5
        while not stop.is_set():
            try:
                self.run_once(runtime, stop)
                delay = 0.5
            except (OSError, ValueError, http.client.HTTPException) as exc:
                self.last_error = _redacted_error(exc)
                self.reconnects += 1
                stop.wait(delay)
                delay = min(SOURCE_RECONNECT_MAX_S, delay * 2)


class OnnxAdapter:
    """Optional comparison backend; target TensorRT remains separately gated."""

    def __init__(self, manifest: ModelManifest) -> None:
        self.manifest = manifest
        if manifest.backend != "onnx":
            raise ShadowSetupError("BACKEND_UNAVAILABLE", "TensorRT adapter requires target validation")
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy  # type: ignore[import-not-found]
            import onnxruntime  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ShadowSetupError("BACKEND_UNAVAILABLE", "ONNX comparison dependencies are unavailable") from exc
        self._cv2 = cv2
        self._np = numpy
        self._session = onnxruntime.InferenceSession(
            str(manifest.artifact), providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name

    def infer(self, frame: Frame) -> Mapping[str, object]:
        image = self._cv2.imdecode(self._np.frombuffer(frame.jpeg, dtype=self._np.uint8), 1)
        if image is None:
            raise ValueError("JPEG decode failed")
        image = self._cv2.resize(image, (self.manifest.input_width, self.manifest.input_height))
        if self.manifest.input_color == "RGB":
            image = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
        tensor = image.astype(self._np.float32) / 255.0
        tensor = self._np.transpose(tensor, (2, 0, 1))[None, ...]
        outputs = self._session.run(None, {self._input_name: tensor})
        values = self._np.asarray(outputs[0])
        return _adapt_array_output(self.manifest, values)


class _CudaRuntime:
    LIBRARIES = (
        "/usr/local/cuda/targets/aarch64-linux/lib/libcudart.so.11.0",
        "/usr/local/cuda/targets/aarch64-linux/lib/libcudart.so",
    )

    def __init__(self) -> None:
        library = next((Path(item) for item in self.LIBRARIES if Path(item).is_file()), None)
        if library is None:
            raise ShadowSetupError("BACKEND_UNAVAILABLE", "allowlisted CUDA runtime is unavailable")
        try:
            self.lib = ctypes.CDLL(str(library))
        except OSError as exc:
            raise ShadowSetupError("BACKEND_UNAVAILABLE", "CUDA runtime could not be loaded") from exc
        self.lib.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.lib.cudaMalloc.restype = ctypes.c_int
        self.lib.cudaFree.argtypes = [ctypes.c_void_p]
        self.lib.cudaFree.restype = ctypes.c_int
        self.lib.cudaMemcpy.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_int,
        ]
        self.lib.cudaMemcpy.restype = ctypes.c_int
        self.lib.cudaDeviceSynchronize.argtypes = []
        self.lib.cudaDeviceSynchronize.restype = ctypes.c_int

    @staticmethod
    def _check(code: int, operation: str) -> None:
        if code != 0:
            raise RuntimeError(f"CUDA_{operation.upper()}_FAILED: code {code}")

    def allocate(self, size: int) -> ctypes.c_void_p:
        pointer = ctypes.c_void_p()
        self._check(self.lib.cudaMalloc(ctypes.byref(pointer), size), "allocation")
        return pointer

    def free(self, pointer: ctypes.c_void_p) -> None:
        if pointer.value:
            self._check(self.lib.cudaFree(pointer), "free")

    def host_to_device(self, pointer: ctypes.c_void_p, array: Any) -> None:
        source = ctypes.c_void_p(int(array.ctypes.data))
        self._check(self.lib.cudaMemcpy(pointer, source, array.nbytes, 1), "copy_h2d")

    def device_to_host(self, array: Any, pointer: ctypes.c_void_p) -> None:
        destination = ctypes.c_void_p(int(array.ctypes.data))
        self._check(self.lib.cudaMemcpy(destination, pointer, array.nbytes, 2), "copy_d2h")

    def synchronize(self) -> None:
        self._check(self.lib.cudaDeviceSynchronize(), "synchronize")


class TensorRtAdapter:
    """Fixed TensorRT 8.x adapter with bounded bindings and CUDA allocations."""

    def __init__(self, manifest: ModelManifest) -> None:
        self.manifest = manifest
        if manifest.backend != "tensorrt":
            raise ShadowSetupError("BACKEND_UNAVAILABLE", "manifest is not a TensorRT engine")
        try:
            import cv2
            import numpy
            import tensorrt as trt
        except ImportError as exc:
            raise ShadowSetupError("BACKEND_UNAVAILABLE", "TensorRT dependencies are unavailable") from exc
        self._cv2 = cv2
        self._np = numpy
        self._trt = trt
        self._cuda = _CudaRuntime()
        logger = trt.Logger(trt.Logger.ERROR)
        serialized = manifest.artifact.read_bytes()
        self._trt_runtime = trt.Runtime(logger)
        self._engine = self._trt_runtime.deserialize_cuda_engine(serialized)
        if self._engine is None:
            raise ShadowSetupError("ENGINE_LOAD_FAILED", "TensorRT engine deserialization failed")
        if not 2 <= self._engine.num_bindings <= MAX_TENSORRT_BINDINGS:
            raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "TensorRT binding count is invalid")
        self._context = self._engine.create_execution_context()
        if self._context is None:
            raise ShadowSetupError("ENGINE_LOAD_FAILED", "TensorRT execution context failed")
        inputs = [index for index in range(self._engine.num_bindings) if self._engine.binding_is_input(index)]
        if len(inputs) != 1:
            raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "exactly one TensorRT input is required")
        self._input_index = inputs[0]
        expected_shape = (1, 3, manifest.input_height, manifest.input_width)
        declared_shape = tuple(self._engine.get_binding_shape(self._input_index))
        if -1 in declared_shape:
            if not self._context.set_binding_shape(self._input_index, expected_shape):
                raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "dynamic input shape was rejected")
        elif declared_shape != expected_shape:
            raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "TensorRT input shape does not match manifest")
        if self._trt.nptype(self._engine.get_binding_dtype(self._input_index)) != self._np.float32:
            raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "TensorRT input must be FP32 NCHW")
        self._host_buffers: dict[int, Any] = {}
        self._device_buffers: dict[int, ctypes.c_void_p] = {}
        total_bytes = 0
        try:
            for index in range(self._engine.num_bindings):
                shape = tuple(self._context.get_binding_shape(index))
                if not shape or any(dimension <= 0 for dimension in shape):
                    raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "TensorRT binding shape is unresolved")
                dtype = self._trt.nptype(self._engine.get_binding_dtype(index))
                host = self._np.empty(shape, dtype=dtype)
                total_bytes += int(host.nbytes)
                if total_bytes > MAX_TENSORRT_DEVICE_BYTES:
                    raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "TensorRT bindings exceed memory limit")
                self._host_buffers[index] = host
                self._device_buffers[index] = self._cuda.allocate(int(host.nbytes))
        except Exception:
            self.close()
            raise
        self._bindings = [int(self._device_buffers[index].value or 0) for index in range(self._engine.num_bindings)]
        self._output_indices = [
            index for index in range(self._engine.num_bindings) if index != self._input_index
        ]
        if len(self._output_indices) != 1:
            self.close()
            raise ShadowSetupError("ENGINE_CONTRACT_FAILED", "exactly one TensorRT output is required")

    def infer(self, frame: Frame) -> Mapping[str, object]:
        image = self._cv2.imdecode(self._np.frombuffer(frame.jpeg, dtype=self._np.uint8), 1)
        if image is None:
            raise ValueError("JPEG decode failed")
        image = self._cv2.resize(image, (self.manifest.input_width, self.manifest.input_height))
        if self.manifest.input_color == "RGB":
            image = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
        tensor = self._np.transpose(image.astype(self._np.float32) / 255.0, (2, 0, 1))[None, ...]
        input_host = self._host_buffers[self._input_index]
        self._np.copyto(input_host, tensor)
        self._cuda.host_to_device(self._device_buffers[self._input_index], input_host)
        if not self._context.execute_v2(self._bindings):
            raise RuntimeError("TENSORRT_EXECUTION_FAILED")
        for index in self._output_indices:
            self._cuda.device_to_host(self._host_buffers[index], self._device_buffers[index])
        self._cuda.synchronize()
        return _adapt_array_output(self.manifest, self._host_buffers[self._output_indices[0]])

    def close(self) -> None:
        for pointer in getattr(self, "_device_buffers", {}).values():
            try:
                self._cuda.free(pointer)
            except RuntimeError:
                pass
        self._device_buffers = {}

    def __del__(self) -> None:
        self.close()


class HealthServer(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 4

    def __init__(self, runtime: PerceptionRuntime):
        self.runtime = runtime
        super().__init__((HEALTH_BIND_HOST, HEALTH_PORT), HealthHandler)


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "RobotScopePerceptionShadow/1"
    sys_version = ""

    def do_GET(self) -> None:
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            self.send_error(HTTPStatus.BAD_REQUEST, "request body is not accepted")
            return
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        server = self.server
        if not isinstance(server, HealthServer):
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        payload = json.dumps(server.runtime.health(), separators=(",", ":")).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def log_message(self, _fmt: str, *_args: object) -> None:
        return


class ResultServer(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 4

    def __init__(self, runtime: PerceptionRuntime, host: str, peer: str, port: int):
        self.runtime = runtime
        self.allowed_peer = peer
        super().__init__((host, port), ResultHandler)


class ResultHandler(BaseHTTPRequestHandler):
    server_version = "RobotScopePerceptionResult/1"
    sys_version = ""

    def do_GET(self) -> None:
        server = self.server
        if not isinstance(server, ResultServer):
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.client_address[0] != server.allowed_peer:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            self.send_error(HTTPStatus.BAD_REQUEST, "request body is not accepted")
            return
        if self.path != RESULT_PATH:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = json.dumps(
            server.runtime.result_snapshot(), allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        if len(payload) > MAX_MANIFEST_BYTES:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "result snapshot exceeds limit")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def log_message(self, _fmt: str, *_args: object) -> None:
        return


def _config_integer(values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    text = str(values.get(name, default))
    if not text.isascii() or not text.isdecimal() or not minimum <= int(text) <= maximum:
        raise ShadowSetupError("INVALID_CONFIG", f"{name} is outside the allowed range")
    return int(text)


def _manifest_names(values: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    names = tuple(
        (task, str(values.get(name, "")).strip())
        for task, name in (
            ("lane", "ROBOT_SCOPE_PERCEPTION_LANE_MANIFEST"),
            ("object", "ROBOT_SCOPE_PERCEPTION_OBJECT_MANIFEST"),
            ("depth_summary", "ROBOT_SCOPE_PERCEPTION_DEPTH_MANIFEST"),
        )
        if str(values.get(name, "")).strip()
    )
    if not names:
        raise ShadowSetupError("INVALID_CONFIG", "at least one model manifest is required")
    return names


def _config_rate(values: Mapping[str, str], task: str) -> float:
    name = {
        "lane": "ROBOT_SCOPE_PERCEPTION_LANE_HZ",
        "object": "ROBOT_SCOPE_PERCEPTION_OBJECT_HZ",
        "depth_summary": "ROBOT_SCOPE_PERCEPTION_DEPTH_HZ",
    }[task]
    try:
        return _finite(values.get(name, "10"), minimum=0.1, maximum=30)
    except (TypeError, ValueError) as exc:
        raise ShadowSetupError("INVALID_CONFIG", f"{name} is outside the allowed range") from exc


def _local_private_ipv4(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ShadowSetupError(
            "INVALID_CONFIG", "source host must be an explicit local IPv4 address"
        ) from exc
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or not any(address in network for network in PRIVATE_NETWORKS)
        or address.is_unspecified
        or address.is_loopback
        or address.is_multicast
    ):
        raise ShadowSetupError(
            "INVALID_CONFIG", "source host must be a private or link-local IPv4 address"
        )
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((str(address), 0))
    except OSError as exc:
        raise ShadowSetupError(
            "SOURCE_ADDRESS_MISSING", "source host is not assigned to this Jetson"
        ) from exc
    finally:
        probe.close()
    return str(address)


def _private_ipv4(value: str, *, label: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ShadowSetupError("INVALID_CONFIG", f"{label} must be an explicit private IPv4 address") from exc
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or not any(address in network for network in PRIVATE_NETWORKS)
        or address.is_unspecified
        or address.is_loopback
        or address.is_multicast
    ):
        raise ShadowSetupError("INVALID_CONFIG", f"{label} must be an explicit private IPv4 address")
    return str(address)


def main(argv: Sequence[str] = ()) -> int:
    if argv:
        print("robot_side_perception_shadow.py accepts no arguments", file=sys.stderr)
        return 2
    values = os.environ
    source_host = _local_private_ipv4(
        str(values.get("ROBOT_SCOPE_PERCEPTION_SOURCE_HOST", "")).strip()
    )
    source_port = _config_integer(values, "ROBOT_SCOPE_PERCEPTION_SOURCE_PORT", 8090, 1024, 65535)
    result_host = _local_private_ipv4(
        str(values.get("ROBOT_SCOPE_PERCEPTION_RESULT_HOST", source_host)).strip()
    )
    result_peer = _private_ipv4(
        str(values.get("ROBOT_SCOPE_PERCEPTION_RESULT_PEER", "")).strip(),
        label="result peer",
    )
    result_port = _config_integer(values, "ROBOT_SCOPE_PERCEPTION_RESULT_PORT", RESULT_PORT, 1024, 65535)
    width = _config_integer(values, "ROBOT_SCOPE_PERCEPTION_WIDTH", 640, 320, 1280)
    height = _config_integer(values, "ROBOT_SCOPE_PERCEPTION_HEIGHT", 480, 240, 720)
    if (width, height) not in ALLOWED_RESOLUTIONS:
        raise ShadowSetupError("INVALID_CONFIG", "source profile is not allowlisted")
    pointcloud_mode = str(values.get("ROBOT_SCOPE_PERCEPTION_POINTCLOUD_MODE", "OFF")).upper()
    hub = LatestFrameHub()
    boot_id = _boot_id()
    runtime_identity = RuntimeIdentity.discover()
    workers = []
    seen_tasks = set()
    for expected_task, filename in _manifest_names(values):
        manifest = ModelManifest.load(filename, runtime=runtime_identity)
        if manifest.task != expected_task:
            raise ShadowSetupError(
                "INVALID_CONFIG", "manifest task does not match its configured slot"
            )
        if manifest.task in seen_tasks:
            raise ShadowSetupError("INVALID_CONFIG", "only one model per task is allowed")
        seen_tasks.add(manifest.task)
        adapter = (
            TensorRtAdapter(manifest)
            if manifest.backend == "tensorrt"
            else OnnxAdapter(manifest)
        )
        workers.append(
            InferenceWorker(
                hub,
                adapter,
                max_hz=_config_rate(values, manifest.task),
                stale_after_s=1.0,
                source_id=RESULT_SOURCE_ID,
                boot_id=boot_id,
            )
        )
    if pointcloud_mode == "SUMMARY" and "depth_summary" not in seen_tasks:
        raise ShadowSetupError(
            "INVALID_CONFIG", "SUMMARY mode requires one depth_summary manifest"
        )
    if pointcloud_mode == "OFF" and "depth_summary" in seen_tasks:
        raise ShadowSetupError(
            "INVALID_CONFIG", "depth_summary manifest requires SUMMARY mode"
        )
    source = MjpegFrameSource(source_host, source_port, width, height)
    runtime = PerceptionRuntime(
        workers,
        hub=hub,
        pointcloud_mode=pointcloud_mode,
        source_diagnostics=lambda: {
            "reconnects": source.reconnects,
            "last_error": _redacted_error(source.last_error),
        },
    )
    stop = threading.Event()
    server = HealthServer(runtime)
    result_server = ResultServer(runtime, result_host, result_peer, result_port)
    result_thread = threading.Thread(
        target=result_server.serve_forever,
        kwargs={"poll_interval": 0.25},
        name="shadow-result-server",
        daemon=True,
    )

    def request_stop(_signum: int, _frame: object) -> None:
        if not stop.is_set():
            stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()
            threading.Thread(target=result_server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    runtime.start()
    result_thread.start()
    source_thread = threading.Thread(
        target=source.supervise, args=(runtime, stop), name="shadow-frame-source", daemon=True
    )
    source_thread.start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        stop.set()
        server.server_close()
        result_server.shutdown()
        result_server.server_close()
        runtime.stop()
        source_thread.join(timeout=2.0)
        result_thread.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ShadowSetupError as exc:
        print(f"[Robot Scope Perception Shadow] {exc}", file=sys.stderr)
        raise SystemExit(2) from None
