"""Bounded, ROS-free recorder for an explicit stationary LiDAR diagnostic interval.

This records received ROS message fields, never drives the robot or changes a
subscription. ``PointCloud2.data`` is preserved byte for byte, alongside a
separate complete numeric XYZ conversion. It is a reconstructed field record,
not a CDR/rosbag archive. All associations use host callback receipt time;
source header clocks and physical stationarity remain unverified.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import os
import re
import time
from typing import Any, Callable

from .ros.observation_identity import subscription_evidence_key
from .ros.raw_pointcloud_capture import RawCaptureValidationError, capture_xyz


MIB = 1024 * 1024
MAX_CLOUD_BYTES = 32 * MIB
MAX_TOTAL_BYTES = 256 * MIB
MAX_EVENTS = 5000
MAX_FIELDS = 64
MAX_TF_EDGES = 16
PRE_ROLL_S = .5
RECEIPT_PAIR_S = .150
RECEIPT_GAP_S = 1.
MAX_MANIFEST_BYTES = 4 * MIB
RUNTIME_SUMMARY_RESERVE = 512
_FIELD_SIZE = {1: 1, 2: 1, 3: 2, 4: 2, 5: 4, 6: 4, 7: 4, 8: 8}
_GID = re.compile(r"(?:[a-f0-9]{32}|[a-f0-9]{48})\Z")


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _name(value: Any, label: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or any(ord(c) < 33 or ord(c) == 127 for c in value)):
        raise ValueError(f"{label} is invalid")
    return value


def _topic(value: Any, label: str) -> str:
    text = _name(value, label)
    if not text.startswith("/") or len(text) > 128 or "//" in text:
        raise ValueError(f"{label} must be an absolute ROS topic")
    return text


@dataclass(frozen=True)
class TFEdge:
    parent: str
    child: str
    static: bool


@dataclass(frozen=True)
class CapturePlan:
    cloud_topic: str
    odom_topic: str
    tf_edges: tuple[TFEdge, ...]
    duration_s: float = 5.
    cloud_count: int = 3
    max_cloud_bytes: int = MAX_CLOUD_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_events: int = MAX_EVENTS

    @classmethod
    def from_dict(cls, value: Any) -> "CapturePlan":
        required = {"cloud_topic", "odom_topic", "tf_edges"}
        optional = {"duration_s", "cloud_count", "max_cloud_bytes", "max_total_bytes", "max_events"}
        if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
            raise ValueError("capture plan requires explicit cloud_topic, odom_topic and tf_edges")
        raw_edges = value["tf_edges"]
        if not isinstance(raw_edges, list) or not 1 <= len(raw_edges) <= MAX_TF_EDGES:
            raise ValueError("capture plan requires 1 to 16 TF edges")
        edges = []
        for item in raw_edges:
            if not isinstance(item, dict) or set(item) != {"parent", "child", "static"} or type(item["static"]) is not bool:
                raise ValueError("TF edge requires parent, child and static")
            parent, child = _name(item["parent"], "TF parent"), _name(item["child"], "TF child")
            if parent == child:
                raise ValueError("TF edge parent and child must differ")
            edges.append(TFEdge(parent, child, item["static"]))
        if len(set(edges)) != len(edges) or len({(e.parent, e.child) for e in edges}) != len(edges):
            raise ValueError("TF edges must be unique")
        duration = _number(value.get("duration_s", 5.), "duration_s")
        clouds = _integer(value.get("cloud_count", 3), "cloud_count", 1)
        cloud_bytes = _integer(value.get("max_cloud_bytes", MAX_CLOUD_BYTES), "max_cloud_bytes", 24)
        total_bytes = _integer(value.get("max_total_bytes", MAX_TOTAL_BYTES), "max_total_bytes", 64 * 1024)
        events = _integer(value.get("max_events", MAX_EVENTS), "max_events", 1)
        if not (0 < duration <= 15 and 1 <= clouds <= 3 and cloud_bytes <= MAX_CLOUD_BYTES
                and total_bytes <= MAX_TOTAL_BYTES and events <= MAX_EVENTS):
            raise ValueError("capture plan exceeds the fixed duration, cloud or storage limits")
        cloud_topic, odom_topic = _topic(value["cloud_topic"], "cloud_topic"), _topic(value["odom_topic"], "odom_topic")
        if cloud_topic == odom_topic or {cloud_topic, odom_topic} & {"/tf", "/tf_static"}:
            raise ValueError("cloud, odometry and TF topics must be distinct")
        return cls(cloud_topic, odom_topic, tuple(edges), duration, clouds, cloud_bytes, total_bytes, events)

    def as_dict(self) -> dict[str, Any]:
        return {"cloud_topic": self.cloud_topic, "odom_topic": self.odom_topic,
                "tf_edges": [vars(edge) for edge in self.tf_edges], "duration_s": self.duration_s,
                "cloud_count": self.cloud_count, "max_cloud_bytes": self.max_cloud_bytes,
                "max_total_bytes": self.max_total_bytes, "max_events": self.max_events,
                "pre_roll_s": PRE_ROLL_S, "receipt_pair_tolerance_s": RECEIPT_PAIR_S}


def _stamp(header: Any, *, zero_allowed: bool = False) -> tuple[dict[str, int], str]:
    value = getattr(header, "stamp", None)
    sec = _integer(getattr(value, "sec", None), "header.stamp.sec")
    nanosec = _integer(getattr(value, "nanosec", None), "header.stamp.nanosec")
    if nanosec >= 1_000_000_000 or (not zero_allowed and sec == nanosec == 0):
        raise ValueError("header stamp is unavailable or invalid")
    return {"sec": sec, "nanosec": nanosec}, str(sec * 1_000_000_000 + nanosec)


def _vector(value: Any, names: tuple[str, ...]) -> dict[str, float]:
    return {key: _number(getattr(value, key, None), key) for key in names}


def _quaternion(value: Any) -> dict[str, float]:
    result = _vector(value, ("x", "y", "z", "w"))
    norm_squared = sum(component * component for component in result.values())
    if not math.isfinite(norm_squared) or not math.isclose(norm_squared, 1., rel_tol=.02, abs_tol=.02):
        raise ValueError("orientation quaternion must have approximately unit norm")
    return result


def _covariance(value: Any) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 36:
        raise ValueError("covariance must contain 36 values")
    return [_number(item, "covariance") for item in value]


def _cloud_fields(message: Any) -> list[dict[str, Any]]:
    fields = getattr(message, "fields", None)
    if not isinstance(fields, (list, tuple)) or not 1 <= len(fields) <= MAX_FIELDS:
        raise ValueError("PointCloud2 fields must be a bounded list")
    point_step = _integer(getattr(message, "point_step", None), "point_step", 1)
    result, names = [], set()
    for field in fields:
        name = _name(getattr(field, "name", None), "PointField name")
        datatype = _integer(getattr(field, "datatype", None), "PointField datatype", 1)
        offset = _integer(getattr(field, "offset", None), "PointField offset")
        count = _integer(getattr(field, "count", None), "PointField count", 1)
        if name in names or datatype not in _FIELD_SIZE or count * _FIELD_SIZE[datatype] > point_step - offset:
            raise ValueError("PointCloud2 field layout is invalid")
        names.add(name)
        result.append({"name": name, "offset": offset, "datatype": datatype, "count": count})
    return result


def _edge_key(edge: TFEdge) -> str:
    """Injective identity even when ROS frame names contain separators."""
    return json.dumps([edge.parent, edge.child, edge.static], separators=(",", ":"))


def _safe_text(value: Any, *, length: int = 128) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= length and all(32 <= ord(c) < 127 for c in value) else None


def _identity(observation: Any, receipt: float, stamp_ns: str, stream: str,
              *, static_repeat: bool = False) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise ValueError("observation identity is unavailable")
    reset_reason = observation.get("reset_reason")
    if (observation.get("invalidated") or reset_reason and not
            (static_repeat and reset_reason in {"SOURCE_STAMP_STALLED", "RECEIPT_GAP"})):
        raise ValueError("observation source was reset or invalidated")
    observed_receipt = _number(observation.get("received_monotonic_s"), "observation receipt")
    if (abs(observed_receipt - receipt) > 1e-6 or observation.get("source_stamp_ns") != stamp_ns
            or observation.get("receipt_clock") != "OBSERVER_HOST_MONOTONIC"):
        raise ValueError("observation receipt or source stamp differs from the message")
    observer_id = _safe_text(observation.get("observer_id"))
    observer_epoch = _safe_text(observation.get("publisher_epoch"))
    if not observer_id or not observer_epoch:
        raise ValueError("local observer identity is unavailable")
    gid = observation.get("publisher_gid")
    gid = gid if isinstance(gid, str) and _GID.fullmatch(gid) and any(c != "0" for c in gid) else None
    implementation = _safe_text(observation.get("publisher_implementation_identifier"))
    # The generic identity helper treats a repeated source stamp as stale.
    # A byte-identical declared static TF can legitimately retain stamp zero:
    # revalidate its actual local graph/session evidence without that one
    # time-progress flag. Every provenance field is still fenced below.
    evidence_source = ({**observation, "reset_reason": None}
                       if static_repeat and reset_reason == "SOURCE_STAMP_STALLED"
                       else observation)
    evidence = subscription_evidence_key(evidence_source, receipt)
    raw_evidence = observation.get("subscription_evidence")
    local_session = _safe_text(raw_evidence.get("session_id")) if isinstance(raw_evidence, dict) else None
    if local_session and not re.fullmatch(r"[a-f0-9]{32}", local_session):
        local_session = None
    native = gid is not None and observation.get("identity_status") == "OBSERVED_PUBLISHER"
    unique = observation.get("publisher_count") == 1 and type(observation.get("publisher_count")) is int
    if stream in {"cloud", "odom"}:
        continuity = ("RMW_GID_AND_SINGLE_ENDPOINT_GRAPH" if native and unique and evidence
                      else "LOCAL_SUBSCRIPTION_GRAPH" if unique and evidence else "UNAVAILABLE")
    else:
        # /tf may have several publishers. A stable per-message GID identifies
        # this declared edge's observed sender, without proving a native session.
        continuity = "RMW_MESSAGE_GID_OBSERVED_FOR_EDGE" if gid else "LOCAL_SUBSCRIPTION_GRAPH" if evidence else "UNAVAILABLE"
    if continuity == "UNAVAILABLE":
        raise ValueError("publisher or fresh single-endpoint subscription continuity is unavailable")
    source_clock = _safe_text(observation.get("source_clock"))
    info = observation.get("rmw_message_info")
    if info is not None and not isinstance(info, dict):
        raise ValueError("RMW MessageInfo metadata is malformed")
    rmw_fields = ("source_timestamp", "received_timestamp", "publication_sequence_number",
                  "reception_sequence_number")
    if isinstance(info, dict) and (set(info) - set(rmw_fields)
                                   or any(value is not None and (type(value) is not int or not -(2**63) <= value < 2**64)
                                          for value in info.values())):
        raise ValueError("RMW MessageInfo metadata is malformed")
    return {"observer_id": observer_id, "observer_epoch": observer_epoch,
            "observer_reset_reason": reset_reason if static_repeat else None,
            "publisher_gid": gid, "publisher_implementation_identifier": implementation,
            "publisher_count": observation.get("publisher_count") if type(observation.get("publisher_count")) is int else None,
            "native_session_id": None, "native_session_verified": False,
            "subscription_session_id": local_session,
            "subscription_graph_fingerprint": evidence[1] if evidence else None,
            "publisher_gid_observed": gid is not None,
            "per_message_publisher_verified": native,
            "publisher_identity_status": _safe_text(observation.get("identity_status")),
            "continuity_basis": continuity, "source_clock": source_clock or "UNVERIFIED",
            "static_replay_local_epoch_exception": static_repeat,
            "source_clock_verified": False, "receipt_clock": "OBSERVER_HOST_MONOTONIC",
            "rmw_message_info": {key: info.get(key) if info else None for key in rmw_fields},
            "rmw_timestamp_basis": "RMW_MESSAGE_INFO_CLOCK_UNVERIFIED"}


class StationaryCapture:
    """Own a private diagnostic directory and a bounded single interval."""

    def __init__(self, plan: CapturePlan, output_path: str | os.PathLike[str], *,
                 now: Callable[[], float] = time.monotonic, data_kind: str = "UNSPECIFIED",
                 stationary_confirmed: bool = False) -> None:
        if not isinstance(plan, CapturePlan):
            raise ValueError("plan must be a CapturePlan")
        checked = CapturePlan.from_dict({"cloud_topic": plan.cloud_topic, "odom_topic": plan.odom_topic,
            "tf_edges": [vars(edge) for edge in plan.tf_edges], "duration_s": plan.duration_s,
            "cloud_count": plan.cloud_count, "max_cloud_bytes": plan.max_cloud_bytes,
            "max_total_bytes": plan.max_total_bytes, "max_events": plan.max_events})
        if checked != plan:
            raise ValueError("capture plan is not normalized")
        if data_kind not in {"UNSPECIFIED", "SYNTHETIC", "LIVE_ROS_SUBSCRIPTION"} or type(stationary_confirmed) is not bool:
            raise ValueError("capture data kind or operator stationary assertion is invalid")
        self.plan, self._now = plan, now
        self.data_kind, self.stationary_confirmed = data_kind, stationary_confirmed
        self.started = _number(now(), "start receipt")
        self.deadline = self.started + plan.duration_s
        path = Path(output_path)
        if not path.is_absolute() or ".." in path.parts or not path.name:
            raise ValueError("output_path must name a new absolute directory")
        for ancestor in path.parents:
            if ancestor.is_symlink():
                raise ValueError("output parent may not contain a symlink")
        self.path = path
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir(path.name, mode=0o700, dir_fd=parent_fd)
            self._fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        self.clouds: list[dict[str, Any]] = []
        self.odometry: list[dict[str, Any]] = []
        self.tf: list[dict[str, Any]] = []
        self._streams: dict[str, tuple[Any, ...]] = {}
        self._last_stamp: dict[str, int] = {}
        self._last_receipt: dict[str, float] = {}
        self._faults: list[str] = []
        self._stored_bytes = 0
        self._events_seen = 0
        self._seen_by_kind = {"cloud": 0, "odom": 0, "tf": 0}
        self._finished: dict[str, Any] | None = None
        self._closed = False

    def _fault(self, reason: str) -> None:
        if reason not in self._faults and len(self._faults) < 64:
            self._faults.append(reason)

    def note_fault(self, reason: str) -> None:
        """Record a bounded external subscription/context fault, never as proof."""
        if self._closed:
            raise RuntimeError("capture is already finished")
        if not isinstance(reason, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", reason):
            raise ValueError("diagnostic fault code is invalid")
        self._fault(reason)

    def _seen(self, kind: str) -> bool:
        if self._closed:
            raise RuntimeError("capture is already finished")
        self._events_seen += 1
        self._seen_by_kind[kind] += 1
        if self._events_seen > self.plan.max_events:
            self._fault("EVENT_LIMIT_EXCEEDED")
            return False
        return True

    def _admit(self, stream: str, receipt: Any, stamp_ns: str, observation: Any,
               *, frame: str, child: str = "", static_repeat: bool = False,
               static_stream: bool = False) -> tuple[float, dict[str, Any]] | None:
        try:
            received = _number(receipt, "callback receipt")
            processing_age = _number(self._now(), "processing receipt") - received
            if not self.started <= received <= self.deadline or not 0 <= processing_age <= RECEIPT_GAP_S:
                raise ValueError("callback receipt is outside the interval")
            identity = _identity(observation, received, stamp_ns, stream, static_repeat=static_repeat)
            key = (frame, child, identity["observer_id"], identity["observer_epoch"], identity["publisher_gid"],
                   identity["publisher_implementation_identifier"], identity["subscription_session_id"],
                   identity["subscription_graph_fingerprint"], identity["continuity_basis"],
                   identity["publisher_count"])
            prior = self._streams.get(stream)
            if prior is None:
                self._streams[stream] = key
            elif static_repeat and prior[:3] == key[:3] and prior[4:] == key[4:]:
                # A static-stamp reset changes only the local observer epoch.
                # Carry that new epoch forward so the next ordinary replay is
                # accepted, without waiving source/session/graph/GID changes.
                self._streams[stream] = key
            elif prior != key:
                self._fault(f"SOURCE_IDENTITY_CHANGED:{stream}")
            stamp = int(stamp_ns)
            if stream in self._last_stamp and stamp <= self._last_stamp[stream] and not static_stream:
                self._fault(f"SOURCE_STAMP_NOT_INCREASING:{stream}")
            if stream in self._last_receipt:
                if received < self._last_receipt[stream]:
                    self._fault(f"RECEIPT_REVERSED:{stream}")
                elif received - self._last_receipt[stream] > RECEIPT_GAP_S and not static_stream:
                    self._fault(f"RECEIPT_GAP:{stream}")
            self._last_stamp[stream] = stamp
            self._last_receipt[stream] = received
            return received, identity
        except (TypeError, ValueError):
            self._fault(f"INVALID_IDENTITY_OR_TIME:{stream}")
            return None

    def _write(self, name: str, payload: bytes, *, reserve_manifest: bool = True) -> bool:
        reserve = (min(MAX_MANIFEST_BYTES, max(1024, self.plan.max_total_bytes // 8))
                   if reserve_manifest else 0) + RUNTIME_SUMMARY_RESERVE
        if self._stored_bytes + len(payload) + reserve > self.plan.max_total_bytes:
            self._fault("TOTAL_BYTE_LIMIT_EXCEEDED")
            return False
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self._fd)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
        except Exception:
            try:
                os.unlink(name, dir_fd=self._fd)
            except OSError:
                pass
            raise
        self._stored_bytes += len(payload)
        return True

    def add_cloud(self, message: Any, receipt: float, observation: dict[str, Any] | None) -> None:
        if not self._seen("cloud"):
            return
        try:
            header = getattr(message, "header", None)
            frame = _name(getattr(header, "frame_id", None), "cloud frame")
            stamp, stamp_ns = _stamp(header)
            received = _number(receipt, "cloud callback receipt")
            if self.started <= received < self.started + PRE_ROLL_S:
                # Expected warm-up: allow odometry and TF to arrive before the
                # first scan, but never copy a pre-arm callback into the record.
                return
            admitted = self._admit("cloud", receipt, stamp_ns, observation, frame=frame)
            if admitted is None or len(self.clouds) >= self.plan.cloud_count:
                return
            fields = _cloud_fields(message)
            if (type(getattr(message, "is_dense", None)) is not bool
                    or type(getattr(message, "is_bigendian", None)) is not bool):
                raise ValueError("PointCloud2 density or endian metadata is unavailable")
            payload = memoryview(getattr(message, "data", b""))
            if not payload.c_contiguous or payload.nbytes > self.plan.max_cloud_bytes:
                raise ValueError("PointCloud2 source data is over limit or noncontiguous")
            raw = payload.cast("B").tobytes()
            decoded = capture_xyz(message, max_points=min(1_000_000, self.plan.max_cloud_bytes // 24),
                                  max_bytes=self.plan.max_cloud_bytes)
            post_copy = _number(self._now(), "post-copy receipt")
            if post_copy > self.deadline or not 0 <= post_copy - received <= RECEIPT_GAP_S:
                self._fault("CLOUD_COPY_EXPIRED")
                return
            index = len(self.clouds)
            raw_name, xyz_name = f"cloud-{index:03d}.pointcloud2-data.bin", f"cloud-{index:03d}.xyz-f64le.bin"
            reserve = min(MAX_MANIFEST_BYTES, max(1024, self.plan.max_total_bytes // 8))
            if (self._stored_bytes + len(raw) + len(decoded["xyz_bytes"]) + reserve
                    + RUNTIME_SUMMARY_RESERVE > self.plan.max_total_bytes):
                self._fault("TOTAL_BYTE_LIMIT_EXCEEDED")
                return
            if not self._write(raw_name, raw) or not self._write(xyz_name, decoded["xyz_bytes"]):
                return
            received, identity = admitted
            self.clouds.append({"topic": self.plan.cloud_topic, "frame_id": frame, "header_stamp": stamp,
                "source_stamp_ns": stamp_ns, "received_monotonic_s": received, "identity": identity,
                "layout": {"height": message.height, "width": message.width, "fields": fields,
                    "is_bigendian": message.is_bigendian, "point_step": message.point_step,
                    "row_step": message.row_step, "is_dense": message.is_dense},
                "raw_data": {"file": raw_name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                "full_xyz": {"file": xyz_name, "encoding": "float64_le_xyz", "bytes": len(decoded["xyz_bytes"]),
                    "sha256": decoded["xyz_sha256"], "source_points": decoded["source_points"],
                    "captured_points": decoded["captured_points"], "finite_points": decoded["finite_points"],
                    "nonfinite_points": decoded["nonfinite_points"], "sampling_applied": False,
                    "spatial_filter_applied": False, "transform_applied": False}})
        except (AttributeError, TypeError, ValueError, OSError, RawCaptureValidationError):
            self._fault("INVALID_OR_OVERSIZED_CLOUD")

    def add_odom(self, message: Any, receipt: float, observation: dict[str, Any] | None) -> None:
        if not self._seen("odom"):
            return
        try:
            header = message.header
            frame, child = _name(header.frame_id, "odom frame"), _name(message.child_frame_id, "odom child")
            stamp, stamp_ns = _stamp(header)
            pose, twist = message.pose, message.twist
            values = {"pose": {"position": _vector(pose.pose.position, ("x", "y", "z")),
                               "orientation": _quaternion(pose.pose.orientation),
                               "covariance": _covariance(pose.covariance)},
                      "twist": {"linear": _vector(twist.twist.linear, ("x", "y", "z")),
                                "angular": _vector(twist.twist.angular, ("x", "y", "z")),
                                "covariance": _covariance(twist.covariance)}}
            admitted = self._admit("odom", receipt, stamp_ns, observation, frame=frame, child=child)
            if admitted:
                received, identity = admitted
                self.odometry.append({"topic": self.plan.odom_topic, "frame_id": frame, "child_frame_id": child,
                    "header_stamp": stamp, "source_stamp_ns": stamp_ns, "received_monotonic_s": received,
                    "identity": identity, **values})
        except (AttributeError, TypeError, ValueError):
            self._fault("INVALID_ODOMETRY")

    def add_tf(self, transform_stamped: Any, receipt: float, observation: dict[str, Any] | None,
               *, static: bool = False) -> None:
        if not self._seen("tf"):
            return
        try:
            if type(static) is not bool:
                raise ValueError("static must be boolean")
            header = transform_stamped.header
            parent = _name(header.frame_id, "TF parent")
            child = _name(transform_stamped.child_frame_id, "TF child")
            edge = TFEdge(parent, child, static)
            if edge not in self.plan.tf_edges:
                raise ValueError("TF edge was not declared")
            stamp, stamp_ns = _stamp(header, zero_allowed=static)
            transform = transform_stamped.transform
            values = {"translation": _vector(transform.translation, ("x", "y", "z")),
                      "rotation": _quaternion(transform.rotation)}
            stream = "tf:" + _edge_key(edge)
            previous = [item for item in self.tf if item["parent"] == parent and item["child"] == child
                        and item["static"] == static]
            same_static = bool(static and previous and all(
                item["translation"] == values["translation"] and item["rotation"] == values["rotation"]
                for item in previous))
            if static and previous and not same_static:
                self._fault(f"STATIC_TF_CHANGED:{_edge_key(edge)}")
            repeat_reset = bool(same_static and isinstance(observation, dict)
                                and observation.get("reset_reason") in {"SOURCE_STAMP_STALLED", "RECEIPT_GAP"})
            admitted = self._admit(stream, receipt, stamp_ns, observation, frame=parent, child=child,
                                   static_repeat=repeat_reset, static_stream=static)
            if admitted:
                received, identity = admitted
                self.tf.append({"parent": parent, "child": child, "static": static,
                    "header_stamp": stamp, "source_stamp_ns": stamp_ns, "received_monotonic_s": received,
                    "identity": identity, **values})
        except (AttributeError, TypeError, ValueError):
            self._fault("INVALID_OR_UNDECLARED_TF")

    @staticmethod
    def _bracket(events: list[dict[str, Any]], receipt: float) -> dict[str, Any] | None:
        before = [(i, item) for i, item in enumerate(events) if item["received_monotonic_s"] <= receipt]
        after = [(i, item) for i, item in enumerate(events) if item["received_monotonic_s"] >= receipt]
        if not before or not after:
            return None
        left = max(before, key=lambda pair: pair[1]["received_monotonic_s"])
        right = min(after, key=lambda pair: pair[1]["received_monotonic_s"])
        delta_before = receipt - left[1]["received_monotonic_s"]
        delta_after = right[1]["received_monotonic_s"] - receipt
        if max(delta_before, delta_after) > RECEIPT_PAIR_S:
            return None
        return {"before_index": left[0], "after_index": right[0],
                "before_delta_s": delta_before, "after_delta_s": delta_after,
                "basis": "OBSERVER_HOST_RECEIPT_ONLY_NOT_SOURCE_CLOCK_SYNC"}

    def finish(self, now: float | None = None, *, cancelled: bool = False,
               reason: str | None = None) -> dict[str, Any]:
        if self._finished is not None:
            return self._finished
        if self._closed:
            raise RuntimeError("capture output is closed after a failed finish")
        finished = _number(self._now() if now is None else now, "finish receipt")
        if finished < self.started:
            self._fault("FINISH_RECEIPT_REVERSED")
        if type(cancelled) is not bool or (reason is not None and (not isinstance(reason, str) or len(reason) > 128)):
            raise ValueError("invalid finish reason or cancellation flag")
        associations = []
        for index, cloud in enumerate(self.clouds):
            receipt = cloud["received_monotonic_s"]
            odom = self._bracket(self.odometry, receipt)
            edges = []
            for edge_index, edge in enumerate(self.plan.tf_edges):
                matching = [(i, item) for i, item in enumerate(self.tf)
                            if (item["parent"], item["child"], item["static"]) ==
                            (edge.parent, edge.child, edge.static)]
                if edge.static:
                    association = ({"index": matching[0][0], "basis": "DECLARED_STATIC_NOT_FRESH_DYNAMIC"}
                                   if matching else None)
                else:
                    bracket = self._bracket([item for _, item in matching], receipt)
                    association = ({**bracket, "before_index": matching[bracket["before_index"]][0],
                                    "after_index": matching[bracket["after_index"]][0]} if bracket else None)
                edges.append({"edge_index": edge_index, "parent": edge.parent, "child": edge.child,
                              "static": edge.static, "association": association})
            if odom is None or any(item["association"] is None for item in edges):
                self._fault("RECEIPT_BRACKET_INCOMPLETE")
            associations.append({"cloud_index": index, "odometry": odom, "tf_edges": edges,
                                 "source_clock_synchronized": False, "body_pose_verified": False})
        if len(self.clouds) != self.plan.cloud_count:
            self._fault("CLOUD_COUNT_INCOMPLETE")
        if not self.odometry:
            self._fault("ODOMETRY_MISSING")
        for edge in self.plan.tf_edges:
            if not any((item["parent"], item["child"], item["static"]) ==
                       (edge.parent, edge.child, edge.static) for item in self.tf):
                self._fault(f"TF_EDGE_MISSING:{_edge_key(edge)}")
        # An early complete set of brackets does not establish that the
        # declared interval continued to receive dynamic data. Static TF has
        # no dynamic freshness claim and is intentionally excluded.
        required_streams = [("cloud", None), ("odom", None)] + [
            ("tf:" + _edge_key(edge), edge) for edge in self.plan.tf_edges if not edge.static]
        tail_coverage = []
        for stream, tail_edge in required_streams:
            last = self._last_receipt.get(stream)
            gap = self.deadline - last if last is not None else None
            covered = gap is not None and 0 <= gap <= RECEIPT_GAP_S
            tail_coverage.append({"stream": "tf" if tail_edge else stream,
                                  "edge": vars(tail_edge) if tail_edge else None,
                                  "last_received_monotonic_s": last,
                                  "seconds_before_deadline": gap, "within_one_second": covered})
            if finished >= self.deadline and last is not None and not covered:
                self._fault(f"TAIL_RECEIPT_GAP:{stream}")
        if finished < self.deadline:
            self._fault("EARLY_FINISH_BEFORE_DECLARED_INTERVAL")
        if reason is not None:
            self._fault("EXPLICIT_FAILURE_REASON")
        if cancelled:
            status = "CANCELLED"
        elif reason is not None:
            status = "PARTIAL"
        elif "CLOUD_COUNT_INCOMPLETE" in self._faults and finished >= self.deadline:
            status = "TIMED_OUT"
        elif self._faults:
            status = "PARTIAL"
        else:
            status = "READY_FOR_OFFLINE_INSPECTION"
        seen = dict(self._seen_by_kind)
        stored = {"cloud": len(self.clouds), "odom": len(self.odometry), "tf": len(self.tf)}
        omitted = {key: seen[key] - stored[key] for key in seen}
        manifest = {"schema": "robot-scope.stationary-lidar-diagnostic.v1", "status": status,
            "reason": reason, "faults": self._faults, "plan": self.plan.as_dict(),
            "data_kind": self.data_kind, "execution_mode": self.data_kind,
            "operator_stationary_asserted": self.stationary_confirmed,
            "started_monotonic_s": self.started, "deadline_monotonic_s": self.deadline,
            "finished_monotonic_s": finished, "events_seen": self._events_seen,
            "callbacks_seen": seen, "callbacks_stored": stored, "callbacks_omitted": omitted,
            "stored_data_bytes": self._stored_bytes, "clouds": self.clouds,
            "odometry": self.odometry, "tf": self.tf, "receipt_associations": associations,
            "dynamic_tail_coverage": tail_coverage,
            "raw_message_archive": False, "pointcloud2_data_exact_for_stored_clouds": True,
            "source_clock_verified": False, "source_clock_synchronized": False,
            "native_session_verified": False, "physical_stationarity_verified": False,
            "body_extrinsic_verified": False, "body_pose_verified": False,
            "tracking_verified": False, "current_pose": None, "operational_application": "NOT_RUN"}
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if (len(payload) > MAX_MANIFEST_BYTES or self._stored_bytes + len(payload)
                + RUNTIME_SUMMARY_RESERVE > self.plan.max_total_bytes):
            # Still leave a bounded labelled record even when event metadata exhausted
            # the budget. The large arrays are never promoted to a complete capture.
            manifest = {"schema": manifest["schema"], "status": "PARTIAL", "reason": "MANIFEST_BYTE_LIMIT",
                        "faults": [*self._faults, "MANIFEST_BYTE_LIMIT"], "plan": self.plan.as_dict(),
                        "stored_data_bytes": self._stored_bytes, "events_seen": self._events_seen,
                        "callbacks_seen": seen, "callbacks_stored": stored, "callbacks_omitted": omitted,
                        "data_kind": self.data_kind, "execution_mode": self.data_kind,
                        "operator_stationary_asserted": self.stationary_confirmed,
                        "cloud_artifacts": [{"raw_data": item["raw_data"], "full_xyz": item["full_xyz"]}
                                            for item in self.clouds],
                        "receipt_association_metadata_omitted_due_to_limit": True,
                        "raw_message_archive": False, "pointcloud2_data_exact_for_stored_clouds": True,
                        "source_clock_verified": False, "source_clock_synchronized": False,
                        "native_session_verified": False, "physical_stationarity_verified": False,
                        "body_extrinsic_verified": False, "body_pose_verified": False,
                        "tracking_verified": False, "current_pose": None,
                        "operational_application": "NOT_RUN"}
            payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        try:
            if self._stored_bytes + len(payload) + RUNTIME_SUMMARY_RESERVE > self.plan.max_total_bytes:
                raise OSError("capture output budget cannot fit even the partial manifest")
            if not self._write("manifest.json", payload, reserve_manifest=False):
                raise OSError("capture output budget cannot fit the manifest")
            os.fsync(self._fd)
        finally:
            self._closed = True
            os.close(self._fd)
        self._finished = manifest
        return manifest
