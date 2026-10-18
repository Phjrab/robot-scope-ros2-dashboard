"""Read-only observation epochs; publisher identity never qualifies a map origin."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
from importlib import import_module
import json
import math
import re
import secrets
from typing import Any


OBSERVER_ID = secrets.token_hex(16)
SUBSCRIPTION_GRAPH_MAX_AGE_S = 3.0
SUBSCRIPTION_EVIDENCE_SCHEMA = "robot-scope.subscription-observation.v1"
SUBSCRIPTION_EVIDENCE_BASIS = "LOCAL_SUBSCRIPTION_AND_ROS_GRAPH_ONLY"


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def _gid_hex(gid: Any) -> str | None:
    if isinstance(gid, (bytes, bytearray)):
        raw = bytes(gid)
    elif isinstance(gid, memoryview) and gid.ndim == 1 and gid.itemsize == 1:
        raw = gid.tobytes()
    elif isinstance(gid, (list, tuple)) and all(type(value) is int and 0 <= value <= 255 for value in gid):
        raw = bytes(gid)
    else:
        return None
    return raw.hex() if len(raw) in {16, 24} and any(raw) else None


def subscription_qos_snapshot(qos: Any) -> dict[str, Any]:
    """Normalize actual native QoS fields without supplying policy defaults."""
    result: dict[str, Any] = {}
    for name in ("reliability", "durability", "history", "liveliness"):
        value = _field(qos, name)
        policy = value if isinstance(value, str) else getattr(value, "name", None)
        if isinstance(policy, str):
            result[name] = policy
    depth = _field(qos, "depth")
    if type(depth) is int:
        result["depth"] = depth
    for name in ("deadline", "lifespan", "liveliness_lease_duration"):
        value = _field(qos, name + "_ns")
        if value is None:
            value = getattr(_field(qos, name), "nanoseconds", None)
        if type(value) is int:
            result[name + "_ns"] = value
    avoid = _field(qos, "avoid_ros_namespace_conventions")
    if type(avoid) is bool:
        result["avoid_ros_namespace_conventions"] = avoid
    return result


def _qos_observed(qos: dict[str, Any]) -> bool:
    return bool(
        qos.get("reliability") in {"RELIABLE", "BEST_EFFORT"}
        and qos.get("durability") in {"VOLATILE", "TRANSIENT_LOCAL"}
        and qos.get("history") in {"KEEP_LAST", "KEEP_ALL"}
        and type(qos.get("depth")) is int and qos["depth"] >= 0
    )


def subscription_graph_snapshot(
    topic: str, type_name: str, publisher_count: int | None,
    endpoints: Any, observed_monotonic_s: float,
) -> dict[str, Any]:
    """Record graph endpoints; their GIDs never identify an individual message."""
    rows = []
    for endpoint in endpoints:
        gid = _field(endpoint, "endpoint_gid")
        # Normalized fixtures/snapshots carry hex; native endpoint APIs carry bytes/list.
        graph_gid = gid if isinstance(gid, str) and re.fullmatch(r"(?:[a-f0-9]{32}|[a-f0-9]{48})", gid) and any(c != '0' for c in gid) else _gid_hex(gid)
        rows.append({
            "node_name": _field(endpoint, "node_name"),
            "node_namespace": _field(endpoint, "node_namespace"),
            "topic_type": _field(endpoint, "topic_type"),
            "endpoint_gid": graph_gid,
            "qos": subscription_qos_snapshot(_field(endpoint, "qos") if isinstance(endpoint, Mapping) else _field(endpoint, "qos_profile")),
        })
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    valid = bool(
        type(publisher_count) is int and publisher_count == 1 and len(rows) == 1
        and all(isinstance(row["node_name"], str) and row["node_name"]
                and isinstance(row["node_namespace"], str) and row["node_namespace"]
                and row["topic_type"] == type_name and row["endpoint_gid"] and _qos_observed(row["qos"])
                for row in rows)
    )
    contract = {"topic": topic, "type_name": type_name, "reported_publisher_count": publisher_count,
                "endpoint_count": len(rows), "endpoints": rows}
    fingerprint = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if valid else None
    return {"state": "ok" if valid else "unavailable", "reason": None if valid else "GRAPH_ENDPOINT_CONTRACT_UNAVAILABLE",
            "observed_monotonic_s": observed_monotonic_s, "endpoint_count": len(rows),
            "reported_publisher_count": publisher_count, "endpoints": rows, "fingerprint": fingerprint}


def make_subscription_evidence(
    session_id: str, topic: str, type_name: str, subscription_qos: Any, graph: dict[str, Any],
) -> dict[str, Any]:
    return {"schema": SUBSCRIPTION_EVIDENCE_SCHEMA, "session_id": session_id,
            "topic": topic, "type_name": type_name,
            "subscription_qos": subscription_qos_snapshot(subscription_qos), "graph": copy.deepcopy(graph),
            "per_message_publisher_verified": False, "identity_basis": SUBSCRIPTION_EVIDENCE_BASIS}


def subscription_evidence_key(observation: Any, now: float) -> tuple[str, str] | None:
    """Validate separately labelled subscription evidence; never promote native identity."""
    if _field(observation, "invalidated") or _field(observation, "reset_reason") == "SOURCE_STAMP_STALLED":
        return None
    evidence = _field(observation, "subscription_evidence")
    if not isinstance(evidence, Mapping):
        return None
    session, graph = evidence.get("session_id"), evidence.get("graph")
    topic, type_name = evidence.get("topic"), evidence.get("type_name")
    if (evidence.get("schema") != SUBSCRIPTION_EVIDENCE_SCHEMA
            or evidence.get("identity_basis") != SUBSCRIPTION_EVIDENCE_BASIS
            or evidence.get("per_message_publisher_verified") is not False
            or not isinstance(session, str) or not re.fullmatch(r"[a-f0-9]{32}", session)
            or not isinstance(topic, str) or not topic.startswith("/")
            or not isinstance(type_name, str) or not type_name
            or not _qos_observed(subscription_qos_snapshot(evidence.get("subscription_qos")))
            or not isinstance(graph, Mapping) or graph.get("state") != "ok"):
        return None
    observed = graph.get("observed_monotonic_s")
    if (type(observed) not in {int, float} or not math.isfinite(observed)
            or not math.isfinite(now) or not 0 <= now - observed <= SUBSCRIPTION_GRAPH_MAX_AGE_S
            or graph.get("endpoint_count") != 1 or type(graph.get("endpoint_count")) is not int
            or graph.get("reported_publisher_count") != 1 or type(graph.get("reported_publisher_count")) is not int
            or not isinstance(graph.get("endpoints"), list) or len(graph["endpoints"]) != 1):
        return None
    checked = subscription_graph_snapshot(topic, type_name, 1, graph["endpoints"], observed)
    if checked["state"] != "ok" or graph.get("fingerprint") != checked["fingerprint"]:
        return None
    return session, checked["fingerprint"]


def _supports_message_info() -> bool:
    """Detect the native callback-dispatch API, not a ROS version string."""
    try:
        subscription_module = import_module("rclpy.subscription")
    except ImportError:
        return False
    for name in ("Subscription", "BaseSubscription"):
        subscription_type = getattr(subscription_module, name, None)
        callback_type = getattr(subscription_type, "CallbackType", None)
        if getattr(callback_type, "WithMessageInfo", None) is not None:
            return True
    return False


def wrap_observation_callback(
    callback: Any, topic: str, type_name: str, is_current: Any, *, observation_context: Any = None,
) -> Any:
    """Keep Humble message-only dispatch safe and request native info when supported.

    Newer rclpy tries binding one argument before two, so only that path must
    require the second argument. Humble ignores callback arity and sends one.
    Missing native metadata remains unavailable; it is never inferred here.
    """
    session_id = secrets.token_hex(16)

    def context_snapshot() -> dict[str, Any] | None:
        values = observation_context()
        if values is None:
            return None
        return make_subscription_evidence(session_id, topic, type_name, values.get("subscription_qos"), values.get("graph", {}))

    def dispatch(message: Any, message_info: Any) -> None:
        if is_current():
            kwargs = {"message_info": message_info}
            if observation_context is not None:
                # The hub resolves this under the shared lock, fencing a queued old callback.
                kwargs["observation_context"] = context_snapshot
            callback(topic, type_name, message, **kwargs)

    if _supports_message_info():
        def wrapped(message: Any, message_info: Any) -> None:
            dispatch(message, message_info)
        wrapped.subscription_session_id = session_id
        return wrapped

    def wrapped(message: Any, message_info: Any = None) -> None:
        dispatch(message, message_info)
    wrapped.subscription_session_id = session_id
    return wrapped


def _publisher_identity(message_info: Any) -> tuple[str | None, str | None]:
    """Read only supplied native GID bytes, including the Rolling dict shape."""
    gid = (message_info.get("publisher_gid") if isinstance(message_info, Mapping)
           else getattr(message_info, "publisher_gid", None))
    implementation = None
    structured_gid = False
    if isinstance(gid, Mapping):
        structured_gid = True
        implementation, gid = gid.get("implementation_identifier"), gid.get("data")
    elif gid is not None and (
        hasattr(gid, "implementation_identifier") or hasattr(gid, "data")
    ):
        structured_gid = True
        implementation, gid = getattr(gid, "implementation_identifier", None), getattr(gid, "data", None)
    if structured_gid and (
        not isinstance(implementation, str) or not implementation
        or len(implementation) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in implementation)
    ):
        return None, None
    return _gid_hex(gid), implementation


class ObservationIdentity:
    """Fence display anchors on source replacement, backwards time, or a gap.

    An RMW GID identifies a publisher lifetime, not a verified native map session.
    Missing MessageInfo is explicitly unavailable, including on older runtimes.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.epoch = secrets.token_hex(16)
        self.key: tuple[str, ...] | None = None
        self.stamp = 0
        self.received = 0.0
        self.progress_received = 0.0

    def observe(
        self, *, topic: str, frame: str, child: str = "", stamp_ns: int,
        received: float, message_info: Any = None, publisher_count: int | None = None,
        observation_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gid, implementation = _publisher_identity(message_info)
        valid = (gid is not None and type(publisher_count) is int and publisher_count == 1
                 and type(stamp_ns) is int and stamp_ns > 0)
        context = copy.deepcopy(observation_context) if isinstance(observation_context, Mapping) else None
        evidence_key = subscription_evidence_key({"subscription_evidence": context}, received)
        session = context.get("session_id", "") if context else ""
        fingerprint = (context.get("graph") or {}).get("fingerprint", "") if context else ""
        key = (topic, frame, child, implementation or "", gid or "", str(publisher_count),
               str(session), str(fingerprint), "fresh" if evidence_key else "unavailable")
        reason = None
        if self.key != key or stamp_ns != self.stamp:
            self.progress_received = received
        elif received - self.progress_received > 1.0:
            valid = False
            reason = "SOURCE_STAMP_STALLED"
        if self.key is not None:
            if key != self.key:
                reason = "SOURCE_CHANGED"
            elif stamp_ns < self.stamp:
                reason = "SOURCE_TIME_REVERSED"
            elif received - self.received > 1.0:
                reason = "RECEIPT_GAP"
            if reason:
                self.epoch = secrets.token_hex(16)
        self.key, self.stamp, self.received = key, stamp_ns, received
        return {
            "observer_id": OBSERVER_ID,
            "publisher_epoch": self.epoch,
            "publisher_gid": gid,
            "publisher_implementation_identifier": implementation,
            "subscription_evidence": context,
            "publisher_count": publisher_count,
            "identity_status": "OBSERVED_PUBLISHER" if valid else "UNAVAILABLE",
            "identity_basis": "RMW_MESSAGE_INFO",
            "native_session_id": None,
            "source_stamp_ns": str(stamp_ns),
            "source_clock": "ROS_HEADER_UNVERIFIED",
            "received_monotonic_s": received,
            "receipt_clock": "OBSERVER_HOST_MONOTONIC",
            "reset_reason": reason,
            "origin_verified": False,
        }
