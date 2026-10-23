#!/usr/bin/env python3
"""One bounded, subscription-only stationary LiDAR/odometry/TF record.

The default command validates an explicit JSON plan without loading ROS or
creating output. Live subscription requires both --execute and
--stationary-confirmed. This tool never starts a sensor, localization process,
controller, or robot action. Its output is historical observation only. Native
rclpy may create node infrastructure such as /parameter_events even though this
application creates no publishers, clients, services, or actions.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_dashboard.ros.observation_identity import (  # noqa: E402
    ObservationIdentity,
    subscription_graph_snapshot,
    subscription_qos_snapshot,
    wrap_observation_callback,
)
from robot_dashboard.stationary_lidar_capture import CapturePlan, StationaryCapture  # noqa: E402


MAX_PLAN_BYTES = 16 * 1024
MAX_GRAPH_ENDPOINTS = 8
MAX_TF_TRANSFORMS_PER_MESSAGE = 256
GRAPH_PERIOD_S = 1.0
SPIN_SLICE_S = 0.1
PRE_ROLL_S = 0.5
GRAPH_PREFLIGHT_S = 3.0


class SourcePreflightUnavailable(RuntimeError):
    """Required graph evidence did not appear before the bounded deadline."""


def load_plan(path: Path) -> CapturePlan:
    """Read a small explicit plan; no ROS import, network access or output write."""
    with path.open("rb") as stream:
        raw = stream.read(MAX_PLAN_BYTES + 1)
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError("capture plan exceeds 16 KiB")
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("capture plan contains a duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("capture plan is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("capture plan must be a JSON object")
    return CapturePlan.from_dict(value)


def _stamp_ns(message: Any) -> int:
    stamp = getattr(getattr(message, "header", None), "stamp", None)
    sec, nanosec = getattr(stamp, "sec", None), getattr(stamp, "nanosec", None)
    if (type(sec) is not int or type(nanosec) is not int or sec < 0
            or not 0 <= nanosec < 1_000_000_000):
        return 0
    return sec * 1_000_000_000 + nanosec


def _rmw_message_info(message_info: Any) -> dict[str, Any]:
    """Keep supported native numbers separate from ROS header/host clocks."""
    result: dict[str, Any] = {}
    for name in ("source_timestamp", "received_timestamp",
                 "publication_sequence_number", "reception_sequence_number"):
        value = (message_info.get(name) if isinstance(message_info, dict)
                 else getattr(message_info, name, None))
        if type(value) is not int or value < 0 or value > (1 << 64) - 1:
            value = None
        if name.endswith("timestamp") and value == 0:
            value = None
        result[name] = value
    return result


def _safe_graph_endpoint(endpoint: Any) -> dict[str, Any] | None:
    """Bound metadata before handing a native endpoint to the evidence helper."""
    values: dict[str, Any] = {}
    for name in ("node_name", "node_namespace", "topic_type"):
        value = getattr(endpoint, name, None)
        if not isinstance(value, str) or len(value) > 128:
            return None
        values[name] = value
    gid = getattr(endpoint, "endpoint_gid", None)
    if not isinstance(gid, (bytes, bytearray, tuple, list, memoryview)):
        return None
    if len(gid) not in (16, 24):
        return None
    values["endpoint_gid"] = gid
    values["qos"] = subscription_qos_snapshot(getattr(endpoint, "qos_profile", None))
    return values


def _node_kwargs(node_type: Any) -> dict[str, Any]:
    """Require safety flags; never retry a constructor with weakened flags."""
    parameters = inspect.signature(node_type).parameters
    required = {"enable_rosout", "start_parameter_services"}
    if not required.issubset(parameters):
        raise RuntimeError("ROS Node lacks required rosout/service disable flags")
    options: dict[str, Any] = {"enable_rosout": False, "start_parameter_services": False}
    for name in ("enable_logger_service", "enable_parameter_events"):
        if name in parameters:
            options[name] = False
    if "use_global_arguments" in parameters:
        options["use_global_arguments"] = False
    return options


def load_ros() -> dict[str, Any]:
    """Import ROS only on the explicit live path."""
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import (
        DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy,
    )
    from sensor_msgs.msg import PointCloud2
    from tf2_msgs.msg import TFMessage
    return {"rclpy": rclpy, "Node": Node, "Odometry": Odometry,
            "PointCloud2": PointCloud2, "TFMessage": TFMessage,
            "QoSProfile": QoSProfile, "HistoryPolicy": HistoryPolicy,
            "ReliabilityPolicy": ReliabilityPolicy, "DurabilityPolicy": DurabilityPolicy}


def run_capture(
    plan: CapturePlan,
    output: Path,
    *,
    ros: dict[str, Any] | None = None,
    recorder_factory: Callable[..., Any] = StationaryCapture,
    monotonic: Callable[[], float] = time.monotonic,
    stationary_confirmed: bool = False,
    data_kind: str = "LIVE_ROS_SUBSCRIPTION",
) -> dict[str, Any]:
    """Subscribe to exactly the plan's sources for one finite observation window."""
    if stationary_confirmed is not True:
        raise ValueError("stationary confirmation is required for live subscription")
    if data_kind not in {"LIVE_ROS_SUBSCRIPTION", "SYNTHETIC"}:
        raise ValueError("invalid capture data kind")
    if (ros is None and data_kind != "LIVE_ROS_SUBSCRIPTION"
            or ros is not None and data_kind != "SYNTHETIC"):
        raise ValueError("injected ROS facade must be labelled SYNTHETIC")
    ros = load_ros() if ros is None else ros
    rclpy, node_type = ros["rclpy"], ros["Node"]
    qos_type = ros["QoSProfile"]
    history, reliability, durability = (ros["HistoryPolicy"], ros["ReliabilityPolicy"],
                                        ros["DurabilityPolicy"])
    sensor_qos = qos_type(history=history.KEEP_LAST, depth=5,
                          reliability=reliability.BEST_EFFORT, durability=durability.VOLATILE)
    tf_qos = qos_type(history=history.KEEP_LAST, depth=100,
                      reliability=reliability.RELIABLE, durability=durability.VOLATILE)
    static_qos = qos_type(history=history.KEEP_LAST, depth=100,
                          reliability=reliability.RELIABLE, durability=durability.TRANSIENT_LOCAL)
    topics = {plan.cloud_topic: "sensor_msgs/msg/PointCloud2",
              plan.odom_topic: "nav_msgs/msg/Odometry"}
    if any(not edge.static for edge in plan.tf_edges):
        topics["/tf"] = "tf2_msgs/msg/TFMessage"
    if any(edge.static for edge in plan.tf_edges):
        topics["/tf_static"] = "tf2_msgs/msg/TFMessage"
    expected_edges = {(edge.parent, edge.child, edge.static) for edge in plan.tf_edges}
    expected_children = {edge.child for edge in plan.tf_edges}
    graph: dict[str, dict[str, Any]] = {}
    graph_digests: dict[str, str] = {}
    counts: dict[str, int | None] = {}
    contexts: dict[str, dict[str, Any]] = {}
    trackers: dict[tuple[str, str, str, bool], ObservationIdentity] = {}
    subscriptions: list[Any] = []
    node = None
    recorder = None
    active = True
    finish_attempted = False
    initialized = False
    result: dict[str, Any] | None = None
    runtime_error: Exception | None = None
    cleanup_errors: list[str] = []
    try:
        rclpy.init(args=[])
        initialized = True
        node = node_type("robot_scope_stationary_lidar_capture", **_node_kwargs(node_type))

        def refresh_graph() -> None:
            observed = monotonic()
            for topic, type_name in topics.items():
                try:
                    publisher_count = node.count_publishers(topic)
                    endpoints = node.get_publishers_info_by_topic(topic)
                    if type(publisher_count) is not int or publisher_count < 0:
                        raise ValueError("invalid publisher count")
                    if len(endpoints) > MAX_GRAPH_ENDPOINTS:
                        raise ValueError("too many graph endpoints")
                    bounded = [_safe_graph_endpoint(row) for row in endpoints]
                    if any(row is None for row in bounded):
                        raise ValueError("invalid graph endpoint")
                    snapshot = subscription_graph_snapshot(
                        topic, type_name, publisher_count, bounded, observed,
                    )
                except Exception:
                    publisher_count = None
                    snapshot = subscription_graph_snapshot(topic, type_name, None, [], observed)
                    snapshot["reason"] = "GRAPH_QUERY_OR_BOUND_FAILED"
                digest_source = {"topic": topic, "type_name": type_name,
                                 "publisher_count": publisher_count,
                                 "endpoints": snapshot["endpoints"], "state": snapshot["state"]}
                digest = hashlib.sha256(json.dumps(digest_source, sort_keys=True,
                                                    separators=(",", ":")).encode()).hexdigest()
                if recorder is not None and topic in graph_digests and graph_digests[topic] != digest:
                    recorder.note_fault("TF_GRAPH_ENDPOINT_SET_CHANGED" if topic in {"/tf", "/tf_static"}
                                        else "SOURCE_GRAPH_ENDPOINT_SET_CHANGED")
                graph_digests[topic] = digest
                counts[topic], graph[topic] = publisher_count, snapshot

        def preflight_ready() -> bool:
            if any(graph.get(topic, {}).get("state") != "ok"
                   for topic in (plan.cloud_topic, plan.odom_topic)):
                return False
            for topic in ("/tf", "/tf_static"):
                if topic not in topics:
                    continue
                count, snapshot = counts.get(topic), graph.get(topic, {})
                if (type(count) is not int or not 1 <= count <= MAX_GRAPH_ENDPOINTS
                        or snapshot.get("endpoint_count") != count
                        or any(row.get("topic_type") != topics[topic]
                               for row in snapshot.get("endpoints", []))):
                    return False
            return True

        preflight_deadline = monotonic() + GRAPH_PREFLIGHT_S
        while rclpy.ok() and monotonic() < preflight_deadline:
            refresh_graph()
            if preflight_ready():
                break
            now = monotonic()
            rclpy.spin_once(node, timeout_sec=max(0.0, min(SPIN_SLICE_S, preflight_deadline - now)))
        if not rclpy.ok() or not preflight_ready():
            raise SourcePreflightUnavailable("SOURCE_GRAPH_PREFLIGHT_UNAVAILABLE")

        recorder = recorder_factory(plan, output, now=monotonic,
                                    data_kind=data_kind, stationary_confirmed=True)
        started = monotonic()
        deadline = started + plan.duration_s

        def context_for(topic: str) -> dict[str, Any] | None:
            context = contexts.get(topic)
            if not active or context is None or not context["ready"]:
                return None
            snapshot = graph.get(topic)
            now = monotonic()
            if (snapshot is None or not 0 <= now - snapshot["observed_monotonic_s"] <= 3.0):
                return None
            return {"subscription_qos": context["qos"], "graph": snapshot}

        def observe(topic: str, message: Any, message_info: Any, evidence: Any,
                    receipt: float, *, parent: str = "", child: str = "", static: bool = False) -> dict[str, Any]:
            key = (topic, parent, child, static)
            tracker = trackers.setdefault(key, ObservationIdentity())
            context = evidence() if callable(evidence) else None
            observation = tracker.observe(
                topic=topic, frame=parent or str(getattr(getattr(message, "header", None), "frame_id", "")),
                child=child or str(getattr(message, "child_frame_id", "")),
                stamp_ns=_stamp_ns(message), received=receipt,
                message_info=message_info, publisher_count=counts.get(topic),
                observation_context=context,
            )
            observation["rmw_message_info"] = _rmw_message_info(message_info)
            return observation

        def on_cloud(topic: str, _type_name: str, message: Any, *, message_info: Any = None,
                     observation_context: Any = None) -> None:
            receipt = monotonic()
            observation = observe(topic, message, message_info, observation_context, receipt)
            recorder.add_cloud(message, receipt, observation)

        def on_odom(topic: str, _type_name: str, message: Any, *, message_info: Any = None,
                    observation_context: Any = None) -> None:
            receipt = monotonic()
            observation = observe(topic, message, message_info, observation_context, receipt)
            recorder.add_odom(message, receipt, observation)

        def on_tf(topic: str, _type_name: str, message: Any, *, message_info: Any = None,
                  observation_context: Any = None) -> None:
            receipt = monotonic()
            transforms = getattr(message, "transforms", None)
            if transforms is None or len(transforms) > MAX_TF_TRANSFORMS_PER_MESSAGE:
                raise ValueError("TF message exceeds the bounded transform count")
            static = topic == "/tf_static"
            for transform in transforms:
                parent = str(getattr(getattr(transform, "header", None), "frame_id", ""))
                child = str(getattr(transform, "child_frame_id", ""))
                if (parent, child, static) not in expected_edges:
                    if child in expected_children:
                        # A competing parent or static/dynamic authority for a
                        # required child is evidence of conflict, not noise.
                        recorder.add_tf(transform, receipt, None, static=static)
                    continue
                observation = observe(topic, transform, message_info, observation_context,
                                      receipt, parent=parent, child=child, static=static)
                if counts.get(topic) != 1 and not observation.get("publisher_gid"):
                    observation["tf_authority_status"] = "INCOMPLETE_MULTIPLE_PUBLISHERS_NO_MESSAGE_GID"
                recorder.add_tf(transform, receipt, observation, static=static)

        subscriptions_to_create = [(plan.odom_topic, ros["Odometry"], on_odom, sensor_qos)]
        if "/tf" in topics:
            subscriptions_to_create.append(("/tf", ros["TFMessage"], on_tf, tf_qos))
        if "/tf_static" in topics:
            subscriptions_to_create.append(("/tf_static", ros["TFMessage"], on_tf, static_qos))

        def subscribe(topic: str, message_type: Any, callback: Any, qos: Any) -> None:
            context = {"ready": False, "qos": subscription_qos_snapshot(qos)}
            contexts[topic] = context
            wrapped = wrap_observation_callback(
                callback, topic, topics[topic], lambda: active,
                observation_context=lambda name=topic: context_for(name),
            )
            subscription = node.create_subscription(message_type, topic, wrapped, qos)
            context["qos"] = subscription_qos_snapshot(getattr(subscription, "qos_profile", qos))
            context["ready"] = True
            subscriptions.append(subscription)

        for topic, message_type, callback, qos in subscriptions_to_create:
            subscribe(topic, message_type, callback, qos)
        # Retain actual pre-scan odometry and transforms. This is inside the
        # original finite deadline; a short/quiet plan may remain incomplete.
        pre_roll_deadline = min(deadline, monotonic() + PRE_ROLL_S)
        while rclpy.ok() and monotonic() < pre_roll_deadline:
            now = monotonic()
            rclpy.spin_once(node, timeout_sec=max(0.0, min(SPIN_SLICE_S, pre_roll_deadline - now)))
        if rclpy.ok() and monotonic() < deadline:
            subscribe(plan.cloud_topic, ros["PointCloud2"], on_cloud, sensor_qos)

        next_graph = started + GRAPH_PERIOD_S
        while rclpy.ok() and monotonic() < deadline:
            now = monotonic()
            if now >= next_graph:
                refresh_graph()
                next_graph = now + GRAPH_PERIOD_S
            rclpy.spin_once(node, timeout_sec=max(0.0, min(SPIN_SLICE_S, deadline - now)))
        reason = None if rclpy.ok() else "ROS_CONTEXT_STOPPED"
        finish_attempted = True
        result = recorder.finish(now=monotonic(), reason=reason)
    except SourcePreflightUnavailable:
        result = {"status": "NOT_RUN", "reason": "SOURCE_GRAPH_PREFLIGHT_UNAVAILABLE",
                  "data_kind": "NOT_RUN", "output_created": False}
    except KeyboardInterrupt:
        if recorder is None:
            result = {"status": "NOT_RUN", "reason": "OPERATOR_CANCELLED",
                      "data_kind": "NOT_RUN", "output_created": False}
        else:
            finish_attempted = True
            result = recorder.finish(now=monotonic(), cancelled=True, reason="OPERATOR_CANCELLED")
    except Exception as exc:
        runtime_error = exc
        if recorder is not None and not finish_attempted:
            finish_attempted = True
            try:
                result = recorder.finish(now=monotonic(), reason="ROS_CAPTURE_ERROR")
            except Exception:
                pass
    finally:
        active = False
        if node is not None:
            for subscription in reversed(subscriptions):
                try:
                    node.destroy_subscription(subscription)
                except Exception as exc:
                    cleanup_errors.append(type(exc).__name__)
            try:
                node.destroy_node()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if initialized:
            try:
                if rclpy.ok():
                    rclpy.shutdown()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
    cleanup_status = "COMPLETE" if not cleanup_errors else "ERROR"
    if recorder is not None:
        try:
            data_status = result.get("status") if result else None
            _write_runtime_summary(output, data_kind=data_kind,
                                   data_status=data_status if isinstance(data_status, str) else "ERROR",
                                   cleanup_status=cleanup_status,
                                   runtime_error=type(runtime_error).__name__ if runtime_error else None)
        except Exception:
            cleanup_errors.append("RuntimeSummaryWriteError")
            cleanup_status = "ERROR"
    if runtime_error is not None:
        raise runtime_error
    assert result is not None
    return {**result, "middleware_cleanup_status": cleanup_status,
            "middleware_cleanup_errors": cleanup_errors[:4]}


def _write_runtime_summary(output: Path, *, data_kind: str, data_status: str,
                           cleanup_status: str, runtime_error: str | None) -> None:
    """Persist middleware cleanup separately from the immutable sensor manifest."""
    payload = json.dumps({"schema": "robot-scope.stationary-lidar-runtime-summary.v1",
                          "data_kind": data_kind, "data_status": data_status,
                          "middleware_cleanup_status": cleanup_status,
                          "runtime_error_type": runtime_error}, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > 512:
        raise ValueError("runtime summary exceeds 512 bytes")
    directory = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open("runtime-summary.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path, help="explicit bounded JSON capture plan")
    parser.add_argument("--execute", action="store_true", help="perform one bounded live ROS subscription")
    parser.add_argument("--stationary-confirmed", action="store_true",
                        help="operator confirms robot remains stationary for the observation")
    parser.add_argument("--output", type=Path, help="new private result directory (live only)")
    options = parser.parse_args(argv)
    try:
        plan = load_plan(options.plan)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not options.execute:
        if options.stationary_confirmed or options.output is not None:
            parser.error("--output and --stationary-confirmed require --execute")
        print(json.dumps({"status": "PLAN_VALIDATED_ONLY", "cloud_topic": plan.cloud_topic,
                          "odom_topic": plan.odom_topic, "duration_s": plan.duration_s,
                          "cloud_count": plan.cloud_count,
                          "tf_edges": len(plan.tf_edges)}, sort_keys=True))
        return 0
    if not options.stationary_confirmed or options.output is None:
        parser.error("--execute requires --stationary-confirmed and --output")
    if not options.output.is_absolute():
        parser.error("--output must be an absolute path")
    try:
        result = run_capture(plan, options.output, stationary_confirmed=True)
    except Exception as exc:
        print(f"stationary capture failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result.get("status"),
                      "output": str(options.output) if result.get("status") != "NOT_RUN" else None,
                      "reason": result.get("reason"),
                      "data_kind": result.get("data_kind", "LIVE_ROS_SUBSCRIPTION"),
                      "middleware_cleanup_status": result.get("middleware_cleanup_status"),
                      "middleware_cleanup_errors": result.get("middleware_cleanup_errors")}, sort_keys=True))
    return (0 if result.get("status") == "READY_FOR_OFFLINE_INSPECTION"
            and result.get("middleware_cleanup_status") == "COMPLETE" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
