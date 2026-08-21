"""ROS graph discovery and bounded topic-rate observation."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from ..serializers import classify_type, is_observable_type
from .telemetry import RateMeter


class RosGraphMonitor:
    """Own discovered endpoints, subscriptions, and non-safety UI metrics."""

    def __init__(self, lock: threading.RLock) -> None:
        self._lock = lock
        self.graph: Dict[str, Dict[str, Any]] = {}
        self.metrics: Dict[str, RateMeter] = {}
        self.subscriptions: Dict[str, Any] = {}
        self.special_subscription_topics: Dict[str, str] = {}

    @staticmethod
    def discover(node: Any) -> Dict[str, Dict[str, Any]]:
        discovered: Dict[str, Dict[str, Any]] = {}
        for topic, types in node.get_topic_names_and_types():
            if topic.startswith("/_"):
                continue
            type_name = types[0] if len(types) == 1 else ""
            category = classify_type(type_name) if type_name else "conflict"
            discovered[topic] = {
                "name": topic,
                "types": list(types),
                "type": type_name,
                "category": category,
                "publishers": node.count_publishers(topic),
                "subscribers": node.count_subscribers(topic),
                "supported": bool(
                    type_name
                    and (
                        is_observable_type(type_name)
                        or category
                        in {"camera", "pointcloud", "occupancy_grid", "path"}
                    )
                ),
            }
        return discovered

    def tick(self, topic: str, now: float) -> None:
        with self._lock:
            self.metrics.setdefault(topic, RateMeter()).tick(now)

    def metric_snapshot(self, topic: str, category: str) -> Dict[str, Any]:
        now = time.monotonic()
        meter = self.metrics.get(topic)
        hz = meter.hz() if meter else None
        age = round(now - meter.last, 3) if meter and meter.last is not None else None
        threshold = 3.0 if category in {"imu", "robot_state", "odometry"} else 5.0
        if not meter or meter.last is None:
            state = "waiting"
        elif category == "occupancy_grid":
            state = "ok"
        elif age is not None and age > threshold:
            state = "stale"
        else:
            state = "ok"
        return {
            "hz": hz,
            "jitter_ms": meter.jitter_ms() if meter else None,
            "age_s": age,
            "samples": meter.samples if meter else 0,
            "state": state,
        }

    def topics_snapshot(self, selected_topics: set[str]) -> List[Dict[str, Any]]:
        with self._lock:
            result: List[Dict[str, Any]] = []
            for topic, item in self.graph.items():
                row = dict(item)
                row.update(self.metric_snapshot(topic, item.get("category", "")))
                row["selected"] = topic in selected_topics
                result.append(row)
        return sorted(result, key=lambda row: (row["category"], row["name"]))
