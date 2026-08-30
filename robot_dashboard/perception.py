"""Fail-closed shadow-perception result bridge owned by the dashboard runtime."""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import re
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping


RESULT_SCHEMA = "robot-scope.perception-result/v1"
SNAPSHOT_SCHEMA = "robot-scope.perception-snapshot/v1"
POLICY_SCHEMA = "robot-scope.perception-policy/v1"
RESULT_PATH = "/api/v1/perception/snapshot"
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RESULTS = 3
MAX_DETECTIONS = 100
MAX_HISTORY = 120
STALE_AFTER_NS = 2_000_000_000
SOURCE_STALE_AFTER_NS = 1_500_000_000
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
CLASS_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
BOOT_ID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,35}\Z")
TASKS = frozenset({"lane", "object", "depth_summary"})
BACKENDS = frozenset({"onnx", "tensorrt"})
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
)


class PerceptionConfigurationError(RuntimeError):
    """Local deployment configuration is invalid."""


class PerceptionValidationError(ValueError):
    """A remote result failed the fixed contract."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _private_ipv4(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise PerceptionConfigurationError("perception source must be an explicit private IPv4") from exc
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or not any(address in network for network in PRIVATE_NETWORKS)
        or address.is_unspecified
        or address.is_loopback
        or address.is_multicast
    ):
        raise PerceptionConfigurationError("perception source must be an explicit private IPv4")
    return str(address)


def _integer(value: object, minimum: int, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PerceptionValidationError(code)
    return value


def _number(value: object, minimum: float, maximum: float, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PerceptionValidationError(code)
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise PerceptionValidationError(code)
    return result


def _exact_keys(value: Mapping[str, object], expected: frozenset[str], code: str) -> None:
    if frozenset(value) != expected:
        raise PerceptionValidationError(code)


@dataclass(frozen=True)
class ModelPolicy:
    task: str
    model_id: str
    model_sha256: str
    backend: str
    input_width: int
    input_height: int
    classes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PerceptionPolicy:
    source_id: str
    models: Mapping[str, ModelPolicy]

    @classmethod
    def load(cls, path: Path) -> "PerceptionPolicy":
        candidate = Path(path).expanduser()
        if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_file():
            raise PerceptionConfigurationError("perception policy must be one real absolute file")
        if candidate.stat().st_size > MAX_RESPONSE_BYTES:
            raise PerceptionConfigurationError("perception policy exceeds its size limit")
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PerceptionConfigurationError("perception policy is not valid JSON") from exc
        if not isinstance(payload, Mapping) or frozenset(payload) != frozenset(
            {"schema_version", "source_id", "models"}
        ):
            raise PerceptionConfigurationError("perception policy shape is invalid")
        if payload.get("schema_version") != POLICY_SCHEMA:
            raise PerceptionConfigurationError("perception policy schema is unknown")
        source_id = str(payload.get("source_id", ""))
        if not NAME_PATTERN.fullmatch(source_id):
            raise PerceptionConfigurationError("perception source ID is invalid")
        raw_models = payload.get("models")
        if not isinstance(raw_models, list) or not 1 <= len(raw_models) <= MAX_RESULTS:
            raise PerceptionConfigurationError("perception model allowlist is invalid")
        models: Dict[str, ModelPolicy] = {}
        for item in raw_models:
            if not isinstance(item, Mapping) or frozenset(item) != frozenset(
                {"task", "model_id", "model_sha256", "backend", "input_width", "input_height", "classes"}
            ):
                raise PerceptionConfigurationError("perception model policy shape is invalid")
            task = str(item.get("task", ""))
            model_id = str(item.get("model_id", ""))
            digest = str(item.get("model_sha256", ""))
            backend = str(item.get("backend", ""))
            width = item.get("input_width")
            height = item.get("input_height")
            classes_value = item.get("classes")
            if (
                task not in TASKS
                or task in models
                or not NAME_PATTERN.fullmatch(model_id)
                or not SHA256_PATTERN.fullmatch(digest)
                or backend not in BACKENDS
                or isinstance(width, bool)
                or not isinstance(width, int)
                or isinstance(height, bool)
                or not isinstance(height, int)
                or (width, height) not in {(320, 240), (640, 480), (1280, 720)}
                or not isinstance(classes_value, list)
            ):
                raise PerceptionConfigurationError("perception model policy is invalid")
            classes = tuple(str(value) for value in classes_value)
            if len(classes) > 256 or any(not CLASS_NAME_PATTERN.fullmatch(value) for value in classes):
                raise PerceptionConfigurationError("perception class allowlist is invalid")
            if (task == "object") != bool(classes):
                raise PerceptionConfigurationError("classes must exist only for the object model")
            models[task] = ModelPolicy(task, model_id, digest, backend, width, height, classes)
        return cls(source_id, models)


COMMON_KEYS = frozenset(
    {
        "schema_version",
        "source_id",
        "boot_id",
        "sequence",
        "task",
        "capture_timestamp",
        "capture_clock_domain",
        "inference_started_at",
        "inference_completed_at",
        "model_id",
        "model_sha256",
        "backend",
        "input_width",
        "input_height",
        "result_status",
        "confidence",
        "payload",
    }
)


class PerceptionStore:
    """Validate, deduplicate, and retain only a fixed result window."""

    def __init__(self, source_ip: str, policy: PerceptionPolicy, *, history_size: int = MAX_HISTORY):
        self.source_ip = _private_ipv4(source_ip)
        self.policy = policy
        if not 1 <= history_size <= MAX_HISTORY:
            raise PerceptionConfigurationError("perception history size is invalid")
        self._history: deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._identity: Dict[str, tuple[str, int]] = {}
        self._lock = threading.RLock()
        self._transport_state = "WAITING"
        self._last_transport_error = ""
        self._last_poll_ns = 0
        self._last_success_ns = 0
        self._accepted = 0
        self._rejected: Dict[str, int] = {}
        self._duplicates = 0
        self._reconnects = 0

    def _reject(self, code: str) -> None:
        with self._lock:
            self._rejected[code] = self._rejected.get(code, 0) + 1
        raise PerceptionValidationError(code)

    def _payload(self, result: Mapping[str, object], model: ModelPolicy) -> Dict[str, Any]:
        payload = result.get("payload")
        if not isinstance(payload, Mapping):
            self._reject("MALFORMED_PAYLOAD")
        if model.task == "lane":
            _exact_keys(
                payload,
                frozenset({"lateral_error_normalized", "heading_error_rad", "curvature", "left_lane_visible", "right_lane_visible", "confidence", "reason"}),
                "MALFORMED_LANE",
            )
            if not isinstance(payload["left_lane_visible"], bool) or not isinstance(payload["right_lane_visible"], bool):
                self._reject("MALFORMED_LANE")
            reason = payload["reason"]
            if not isinstance(reason, str) or len(reason) > 96 or any(ord(char) < 32 for char in reason):
                self._reject("MALFORMED_LANE")
            return {
                "lateral_error_normalized": _number(payload["lateral_error_normalized"], -1, 1, "INVALID_LANE_NUMBER"),
                "heading_error_rad": _number(payload["heading_error_rad"], -math.pi, math.pi, "INVALID_LANE_NUMBER"),
                "curvature": _number(payload["curvature"], -10, 10, "INVALID_LANE_NUMBER"),
                "left_lane_visible": payload["left_lane_visible"],
                "right_lane_visible": payload["right_lane_visible"],
                "confidence": _number(payload["confidence"], 0, 1, "INVALID_CONFIDENCE"),
                "reason": reason,
            }
        if model.task == "object":
            _exact_keys(payload, frozenset({"detections", "detection_count"}), "MALFORMED_OBJECT")
            detections = payload["detections"]
            if not isinstance(detections, list) or len(detections) > MAX_DETECTIONS:
                self._reject("DETECTION_LIMIT")
            if payload["detection_count"] != len(detections):
                self._reject("MALFORMED_OBJECT")
            validated = []
            keys = frozenset({"class_id", "class_name", "x1", "y1", "x2", "y2", "confidence"})
            for detection in detections:
                if not isinstance(detection, Mapping):
                    self._reject("MALFORMED_OBJECT")
                _exact_keys(detection, keys, "MALFORMED_OBJECT")
                class_id = _integer(detection["class_id"], 0, len(model.classes) - 1, "UNKNOWN_CLASS")
                if detection["class_name"] != model.classes[class_id]:
                    self._reject("UNKNOWN_CLASS")
                x1 = _number(detection["x1"], 0, model.input_width, "INVALID_COORDINATE")
                y1 = _number(detection["y1"], 0, model.input_height, "INVALID_COORDINATE")
                x2 = _number(detection["x2"], 0, model.input_width, "INVALID_COORDINATE")
                y2 = _number(detection["y2"], 0, model.input_height, "INVALID_COORDINATE")
                if x2 <= x1 or y2 <= y1:
                    self._reject("INVALID_COORDINATE")
                validated.append({
                    "class_id": class_id,
                    "class_name": model.classes[class_id],
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": _number(detection["confidence"], 0, 1, "INVALID_CONFIDENCE"),
                })
            return {"detections": validated, "detection_count": len(validated)}
        _exact_keys(payload, frozenset({"front_min_distance_m", "left_clearance_m", "right_clearance_m", "obstacle_count", "ground_confidence", "mode"}), "MALFORMED_DEPTH")
        if payload["mode"] != "SUMMARY":
            self._reject("MALFORMED_DEPTH")
        return {
            "front_min_distance_m": _number(payload["front_min_distance_m"], 0, 100, "INVALID_DEPTH_NUMBER"),
            "left_clearance_m": _number(payload["left_clearance_m"], 0, 100, "INVALID_DEPTH_NUMBER"),
            "right_clearance_m": _number(payload["right_clearance_m"], 0, 100, "INVALID_DEPTH_NUMBER"),
            "obstacle_count": _integer(payload["obstacle_count"], 0, 10000, "INVALID_DEPTH_NUMBER"),
            "ground_confidence": _number(payload["ground_confidence"], 0, 1, "INVALID_CONFIDENCE"),
            "mode": "SUMMARY",
        }

    def _validated_result(self, raw: object, server_ns: int) -> Dict[str, Any]:
        if not isinstance(raw, Mapping):
            self._reject("MALFORMED_RESULT")
        _exact_keys(raw, COMMON_KEYS, "MALFORMED_RESULT")
        if raw["schema_version"] != RESULT_SCHEMA or raw["result_status"] != "LIVE":
            self._reject("UNKNOWN_SCHEMA")
        source_id = raw["source_id"]
        boot_id = raw["boot_id"]
        task = raw["task"]
        if source_id != self.policy.source_id or not isinstance(boot_id, str) or not BOOT_ID_PATTERN.fullmatch(boot_id):
            self._reject("UNKNOWN_SOURCE")
        if not isinstance(task, str) or task not in self.policy.models:
            self._reject("UNKNOWN_MODEL")
        model = self.policy.models[task]
        if (
            raw["model_id"] != model.model_id
            or raw["model_sha256"] != model.model_sha256
            or raw["backend"] != model.backend
            or raw["input_width"] != model.input_width
            or raw["input_height"] != model.input_height
        ):
            self._reject("UNKNOWN_MODEL")
        sequence = _integer(raw["sequence"], 1, 2**63 - 1, "INVALID_SEQUENCE")
        capture = _integer(raw["capture_timestamp"], 1, 2**63 - 1, "INVALID_TIMESTAMP")
        started = _integer(raw["inference_started_at"], 1, 2**63 - 1, "INVALID_TIMESTAMP")
        completed = _integer(raw["inference_completed_at"], 1, 2**63 - 1, "INVALID_TIMESTAMP")
        if raw["capture_clock_domain"] != "robot-monotonic" or not capture <= started <= completed <= server_ns:
            self._reject("INVALID_TIMESTAMP")
        if server_ns - completed > SOURCE_STALE_AFTER_NS:
            self._reject("STALE_RESULT")
        confidence = _number(raw["confidence"], 0, 1, "INVALID_CONFIDENCE")
        payload = self._payload(raw, model)
        if model.task == "lane" and not math.isclose(confidence, payload["confidence"], abs_tol=0.0001):
            self._reject("INVALID_CONFIDENCE")
        if model.task == "depth_summary" and not math.isclose(confidence, payload["ground_confidence"], abs_tol=0.0001):
            self._reject("INVALID_CONFIDENCE")
        if model.task == "object":
            expected = max((item["confidence"] for item in payload["detections"]), default=0.0)
            if not math.isclose(confidence, expected, abs_tol=0.0001):
                self._reject("INVALID_CONFIDENCE")
        return {**raw, "payload": payload, "confidence": confidence, "sequence": sequence}

    def ingest(self, snapshot: object, *, source_ip: str, received_monotonic_ns: int | None = None) -> int:
        if source_ip != self.source_ip:
            self._reject("SOURCE_IP_REJECTED")
        if not isinstance(snapshot, Mapping) or frozenset(snapshot) != frozenset(
            {"schema_version", "server_monotonic", "mode", "results"}
        ):
            self._reject("MALFORMED_SNAPSHOT")
        if snapshot["schema_version"] != SNAPSHOT_SCHEMA or snapshot["mode"] != "SHADOW":
            self._reject("UNKNOWN_SCHEMA")
        server_ns = _integer(snapshot["server_monotonic"], 1, 2**63 - 1, "INVALID_TIMESTAMP")
        results = snapshot["results"]
        if not isinstance(results, list) or len(results) > MAX_RESULTS:
            self._reject("RESULT_LIMIT")
        now_ns = received_monotonic_ns or time.monotonic_ns()
        validated = [self._validated_result(raw, server_ns) for raw in results]
        tasks = [str(item["task"]) for item in validated]
        if len(tasks) != len(set(tasks)):
            self._reject("DUPLICATE_TASK")
        accepted = 0
        duplicates = 0
        pending: list[Dict[str, Any]] = []
        with self._lock:
            for result in validated:
                task = result["task"]
                identity = self._identity.get(task)
                gap = 0
                if identity and identity[0] == result["boot_id"]:
                    if result["sequence"] == identity[1]:
                        duplicates += 1
                        continue
                    if result["sequence"] < identity[1]:
                        self._reject("NON_MONOTONIC_SEQUENCE")
                    gap = result["sequence"] - identity[1] - 1
                pending.append({
                    **result,
                    "received_monotonic": now_ns,
                    "receive_sequence_gap": gap,
                    "last_receive_age": 0.0,
                    "transport_state": "LIVE",
                    "clock_domain_verified": False,
                })
            self._duplicates += duplicates
            for enriched in pending:
                task = enriched["task"]
                self._identity[task] = (enriched["boot_id"], enriched["sequence"])
                self._latest[task] = enriched
                self._history.append(enriched)
                self._accepted += 1
                accepted += 1
        self.note_transport("LIVE", now_ns=now_ns)
        return accepted

    def note_transport(self, state: str, error: str = "", *, now_ns: int | None = None) -> None:
        now = now_ns or time.monotonic_ns()
        normalized = state if state in {"LIVE", "WAITING", "OFFLINE"} else "OFFLINE"
        with self._lock:
            previous = self._transport_state
            self._transport_state = normalized
            self._last_poll_ns = now
            if normalized == "LIVE":
                self._last_success_ns = now
                self._last_transport_error = ""
                if previous == "OFFLINE":
                    self._reconnects += 1
            else:
                self._last_transport_error = " ".join(str(error).split())[:160]

    def _project(
        self,
        result: Mapping[str, Any],
        now_ns: int,
        fps: float = 0.0,
        p95_ms: float = 0.0,
    ) -> Dict[str, Any]:
        age = max(0.0, (now_ns - int(result["received_monotonic"])) / 1e9)
        state = "LIVE" if age <= STALE_AFTER_NS / 1e9 and self._transport_state == "LIVE" else "STALE"
        latency_ms = (int(result["inference_completed_at"]) - int(result["inference_started_at"])) / 1e6
        return {
            **result,
            "last_receive_age": round(age, 3),
            "transport_state": state,
            "result_status": state,
            "inference_latency_ms": round(latency_ms, 3),
            "inference_fps": round(fps, 2),
            "inference_p95_ms": round(p95_ms, 3),
        }

    def _task_fps(self, now_ns: int) -> Dict[str, float]:
        cutoff = now_ns - 5_000_000_000
        counts: Dict[str, int] = {}
        for result in self._history:
            if int(result["received_monotonic"]) >= cutoff:
                task = str(result["task"])
                counts[task] = counts.get(task, 0) + 1
        return {task: count / 5.0 for task, count in counts.items()}

    def _task_latency_p95(self, now_ns: int) -> Dict[str, float]:
        cutoff = now_ns - 5_000_000_000
        values: Dict[str, list[float]] = {}
        for result in self._history:
            if int(result["received_monotonic"]) < cutoff:
                continue
            latency = (
                int(result["inference_completed_at"])
                - int(result["inference_started_at"])
            ) / 1e6
            values.setdefault(str(result["task"]), []).append(latency)
        projected: Dict[str, float] = {}
        for task, samples in values.items():
            ordered = sorted(samples)
            index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
            projected[task] = ordered[index]
        return projected

    def latest_snapshot(self, *, now_ns: int | None = None) -> Dict[str, Any]:
        now = now_ns or time.monotonic_ns()
        with self._lock:
            fps = self._task_fps(now)
            p95 = self._task_latency_p95(now)
            results = [self._project(value, now, fps.get(task, 0.0), p95.get(task, 0.0)) for task, value in self._latest.items()]
            transport = self._transport_state
        return {"mode": "SHADOW", "transport_state": transport, "results": results}

    def history_snapshot(self, limit: int = 50, *, now_ns: int | None = None) -> Dict[str, Any]:
        bounded = max(1, min(int(limit), MAX_HISTORY))
        now = now_ns or time.monotonic_ns()
        with self._lock:
            fps = self._task_fps(now)
            p95 = self._task_latency_p95(now)
            results = [self._project(value, now, fps.get(str(value["task"]), 0.0), p95.get(str(value["task"]), 0.0)) for value in list(self._history)[-bounded:]]
        return {"mode": "SHADOW", "bounded": True, "limit": bounded, "results": results}

    def health_snapshot(self, *, now_ns: int | None = None) -> Dict[str, Any]:
        now = now_ns or time.monotonic_ns()
        with self._lock:
            age = None if not self._last_success_ns else max(0.0, (now - self._last_success_ns) / 1e9)
            state = self._transport_state
            if age is not None and age > STALE_AFTER_NS / 1e9:
                state = "OFFLINE"
            return {
                "mode": "SHADOW",
                "state": state,
                "source_ip": self.source_ip,
                "clock_domain_verified": False,
                "last_success_age_s": None if age is None else round(age, 3),
                "accepted": self._accepted,
                "duplicates": self._duplicates,
                "reconnects": self._reconnects,
                "rejected": dict(self._rejected),
                "history_size": len(self._history),
                "last_error": self._last_transport_error,
                "motion_authority": False,
            }

    def metadata_reference(self) -> Dict[str, Any]:
        latest = self.latest_snapshot()
        references = []
        for result in latest["results"]:
            references.append({key: result[key] for key in (
                "source_id", "boot_id", "task", "sequence", "model_id", "model_sha256",
                "capture_timestamp", "capture_clock_domain", "result_status", "last_receive_age",
                "clock_domain_verified",
            )})
        return {"mode": "SHADOW", "results": references}


class PerceptionBridgeClient:
    """Poll one fixed private endpoint; it exposes no mutation or URL input."""

    def __init__(self, store: PerceptionStore, *, port: int = 8092, interval_s: float = 0.25):
        if not 1024 <= int(port) <= 65535 or not 0.1 <= float(interval_s) <= 5:
            raise PerceptionConfigurationError("perception bridge timing or port is invalid")
        self.store = store
        self.port = int(port)
        self.interval_s = float(interval_s)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="perception-result-poll", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self.store.note_transport("OFFLINE", "receiver stopped")

    def poll_once(self) -> int:
        connection = http.client.HTTPConnection(self.store.source_ip, self.port, timeout=1.0)
        try:
            connection.request("GET", RESULT_PATH, headers={"Accept": "application/json"})
            peer = connection.sock.getpeername()[0] if connection.sock else ""
            if peer != self.store.source_ip:
                raise OSError("fixed perception endpoint rejected the request")
            response = connection.getresponse()
            if response.status != 200:
                raise OSError("fixed perception endpoint rejected the request")
            if response.getheader("Content-Type", "").split(";", 1)[0] != "application/json":
                raise ValueError("perception endpoint returned an invalid content type")
            length_text = response.getheader("Content-Length", "")
            if not length_text.isascii() or not length_text.isdecimal():
                raise ValueError("perception endpoint omitted a bounded content length")
            length = int(length_text)
            if not 1 <= length <= MAX_RESPONSE_BYTES:
                raise ValueError("perception response exceeds its size limit")
            body = response.read(length + 1)
            if len(body) != length:
                raise ValueError("perception response length is invalid")
            payload = json.loads(body)
            return self.store.ingest(payload, source_ip=peer)
        finally:
            connection.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except (OSError, ValueError, json.JSONDecodeError, http.client.HTTPException, socket.timeout) as exc:
                self.store.note_transport("OFFLINE", str(exc))
            self._stop.wait(self.interval_s)
