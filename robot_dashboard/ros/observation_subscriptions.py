"""Observation graph evidence and token-fenced ROS subscription lifecycle."""

from __future__ import annotations

import copy
import time
from typing import Any, Callable, Dict

from .observation_identity import (
    subscription_graph_snapshot,
    subscription_qos_snapshot,
    wrap_observation_callback,
)
from .telemetry import RateMeter


class ObservationSubscriptionMixin:
    """Keep observation bookkeeping alongside the agent's subscription lifecycle.

    The facade supplies its shared lock, graph, sources, hubs and native node.
    Message-type lookup is injected by the facade so this module can be tested
    without importing ROS or opening a ROS connection.
    """

    def _invalidate_observation_graph_locked(self, reason: str) -> None:
        self._replace_observation_graph_locked({
            topic: {**subscription_graph_snapshot(topic, "", None, [], time.monotonic()), "reason": reason}
            for topic in self._observation_graph_snapshots
        })

    def _replace_observation_graph_locked(self, snapshots: Dict[str, Dict[str, Any]]) -> None:
        previous = self._observation_graph_snapshots
        self._observation_graph_snapshots = snapshots
        for category in ("pointcloud", "odometry"):
            topic = self._sources.get(category, "")
            before, after = previous.get(topic, {}), snapshots.get(topic, {})
            if (before.get("state"), before.get("fingerprint")) == (after.get("state"), after.get("fingerprint")):
                continue
            if category == "pointcloud":
                self._reset_cloud_locked(topic)
            else:
                self._reset_pose_locked(topic)

    def _refresh_observation_graph(self, node: Any, discovered: Dict[str, Dict[str, Any]]) -> None:
        snapshots = {}
        for topic, descriptor in discovered.items():
            type_name = descriptor.get("type", "")
            if type_name not in {"sensor_msgs/msg/PointCloud2", "nav_msgs/msg/Odometry"}:
                continue
            try:
                endpoints = list(node.get_publishers_info_by_topic(topic))
                snapshots[topic] = subscription_graph_snapshot(
                    topic, type_name, descriptor.get("publishers"), endpoints, time.monotonic(),
                )
            except Exception:
                snapshots[topic] = {**subscription_graph_snapshot(topic, type_name, None, [], time.monotonic()),
                                    "reason": "GRAPH_ENDPOINT_QUERY_FAILED"}
        with self._lock:
            self._replace_observation_graph_locked(snapshots)

    def _observation_context_snapshot(self, key: str, token: object) -> Dict[str, Any] | None:
        # Called by a hub under the shared RLock. An old queued wrapper cannot
        # obtain a new subscription's context after destruction or recreation.
        with self._lock:
            if self._observation_callbacks.get(key) is not token:
                return None
            context = self._observation_subscription_contexts.get(key)
            if context is None or not context.get("ready"):
                return None
            graph = self._observation_graph_snapshots.get(context["topic"])
            if graph is None:
                graph = subscription_graph_snapshot(context["topic"], context["type_name"], None, [], time.monotonic())
            return {"subscription_qos": copy.deepcopy(context["subscription_qos"]), "graph": copy.deepcopy(graph)}

    def _create_observation_aware_subscription(
        self, key: str, topic: str, callback: Any, message_type_for: Callable[[str], Any],
    ) -> bool:
        node = self._node
        with self._lock:
            descriptor = self._graph.get(topic, {})
            type_name = descriptor.get("type", "")
        if not node or not type_name:
            return False
        callback_token = object()
        try:
            message_type = message_type_for(type_name)
            observation_callback = callback in (self._summary_callback, self._pointcloud_callback)
            qos = self._qos_for(topic, type_name)
            if observation_callback:
                with self._lock:
                    self._observation_callbacks[key] = callback_token
                    self._observation_subscription_contexts[key] = {
                        "topic": topic, "type_name": type_name, "subscription_qos": subscription_qos_snapshot(qos),
                        "ready": False,
                    }
                    if topic == self._sources.get("pointcloud") and callback == self._pointcloud_callback:
                        self._reset_cloud_locked(topic)
                    elif topic == self._sources.get("odometry") and callback == self._summary_callback:
                        self._reset_pose_locked(topic)

            def wrapped(message: Any, topic_name: str = topic, ros_type: str = type_name) -> None:
                callback(topic_name, ros_type, message)

            subscription_callback = wrap_observation_callback(
                callback, topic, type_name,
                lambda: self._observation_callbacks.get(key) is callback_token,
                observation_context=lambda: self._observation_context_snapshot(key, callback_token),
            ) if observation_callback else wrapped
            subscription = node.create_subscription(message_type, topic, subscription_callback, qos)
            with self._lock:
                current = not observation_callback or self._observation_callbacks.get(key) is callback_token
                if current:
                    self._subscriptions[key] = subscription
                    self._metrics.setdefault(topic, RateMeter())
                if current and observation_callback:
                    self._observation_subscription_contexts[key]["subscription_qos"] = subscription_qos_snapshot(
                        getattr(subscription, "qos_profile", qos),
                    )
                    self._observation_subscription_contexts[key]["session_id"] = subscription_callback.subscription_session_id
                    self._observation_subscription_contexts[key]["ready"] = True
            if not current:
                node.destroy_subscription(subscription)
                return False
            return True
        except Exception as exc:
            with self._lock:
                if self._observation_callbacks.get(key) is callback_token:
                    self._observation_callbacks.pop(key, None)
                    self._observation_subscription_contexts.pop(key, None)
                self._last_error = f"subscribe {topic}: {exc}"
            return False

    def _destroy_subscription(self, key: str) -> None:
        node = self._node
        with self._lock:
            self._observation_callbacks.pop(key, None)
            context = self._observation_subscription_contexts.pop(key, None)
            subscription = self._subscriptions.pop(key, None)
            if context and context["topic"] == self._sources.get("pointcloud"):
                self._reset_cloud_locked(context["topic"])
            elif context and context["topic"] == self._sources.get("odometry"):
                self._reset_pose_locked(context["topic"])
        if node and subscription:
            try:
                node.destroy_subscription(subscription)
            except Exception:
                pass
