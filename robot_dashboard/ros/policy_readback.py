"""Fixed asynchronous Humble parameter/lifecycle observer on the existing node.

Only GetParameters/GetState are issued. No start, set, clear, action or motion
endpoint exists here. Every batch is bounded and invalidated by parameter events
and authority incarnation changes; render/mission gates only copy the cache.
"""
from __future__ import annotations

import copy
import threading
import time

from ..navigation_policy import POLICY_SCHEMA, POLICY_TTL_S

PARAMETERS = {
    "/planner_server": ("planner_plugins", "GridBased.plugin", "GridBased.allow_unknown", "GridBased.use_astar", "GridBased.tolerance"),
    "/controller_server": ("controller_plugins", "FollowPath.plugin", "FollowPath.primary_controller", "FollowPath.use_collision_detection", "FollowPath.max_allowed_time_to_collision_up_to_carrot"),
    "/bt_navigator": ("default_nav_to_pose_bt_xml", "global_frame", "robot_base_frame"),
    "/global_costmap/global_costmap": ("global_frame", "robot_base_frame", "robot_radius", "footprint", "footprint_padding", "track_unknown_space", "plugins", "filters", "static_layer.plugin", "static_layer.map_topic", "static_layer.enabled", "keepout_filter.plugin", "keepout_filter.enabled", "keepout_filter.filter_info_topic"),
    "/local_costmap/local_costmap": ("global_frame", "robot_base_frame", "robot_radius", "footprint", "footprint_padding", "track_unknown_space", "plugins", "filters", "static_layer.plugin", "static_layer.map_topic", "static_layer.enabled", "keepout_filter.plugin", "keepout_filter.enabled", "keepout_filter.filter_info_topic"),
}


def parameter_value(value):
    """Decode only bounded scalar/array parameter types, preserving NOT_SET."""
    fields = {1: "bool_value", 2: "integer_value", 3: "double_value", 4: "string_value",
              6: "bool_array_value", 7: "integer_array_value", 8: "double_array_value", 9: "string_array_value"}
    if value.type == 0:
        return None
    if value.type not in fields:
        raise ValueError("unsupported parameter type")
    result = getattr(value, fields[value.type])
    if value.type >= 6:
        if len(result) > 64:
            raise ValueError("parameter array exceeds bound")
        result = list(result)
    def checked(item):
        import math
        if type(item) not in {str, bool, int, float} or isinstance(item, float) and not math.isfinite(item):
            raise ValueError("invalid parameter value")
        if isinstance(item, str) and len(item) > 512:
            raise ValueError("parameter string exceeds bound")
        return item
    return [checked(item) for item in result] if isinstance(result, list) else checked(result)


class RosPolicyReadback:
    def __init__(self, node, *, clock=time.monotonic):
        self.node, self.clock = node, clock
        self._lock = threading.Lock()
        self._batch = None
        self._sequence = 0
        self._epoch = 0
        self._cache = {"schema": POLICY_SCHEMA, "status": "unavailable", "parameters": {}, "authorities": {}, "lifecycle": {}}
        self._received = None
        self._clients = {}

    def setup(self):
        from rcl_interfaces.msg import ParameterEvent
        from rcl_interfaces.srv import GetParameters
        from lifecycle_msgs.srv import GetState
        from rclpy.qos import qos_profile_parameter_events
        from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
        self._group = MutuallyExclusiveCallbackGroup()
        for node in PARAMETERS:
            self._clients[node] = (
                self.node.create_client(GetParameters, node + "/get_parameters", callback_group=self._group),
                self.node.create_client(GetState, node + "/get_state", callback_group=self._group))
        self._param_type, self._state_type = GetParameters, GetState
        self._events = self.node.create_subscription(ParameterEvent, "/parameter_events", self._on_event,
            qos_profile_parameter_events, callback_group=self._group)
        self._timer = self.node.create_timer(0.25, self.tick, callback_group=self._group)

    def _on_event(self, message):
        if message.node in PARAMETERS:
            self._epoch += 1
            self._invalidate("PARAMETERS_CHANGED")

    def _invalidate(self, reason):
        with self._lock:
            self._cache["status"], self._cache["reason"] = "invalid", reason

    def _authorities(self):
        result = {name: [] for name in PARAMETERS}
        for info in self.node.get_publishers_info_by_topic("/parameter_events"):
            name = (info.node_namespace.rstrip("/") + "/" + info.node_name)
            if name in result:
                gid = bytes(info.endpoint_gid)
                if len(gid) != 24 or not any(gid):
                    raise ValueError("POLICY_AUTHORITY_NOT_UNIQUE")
                result[name].append(gid.hex())
        if any(len(values) != 1 or not values[0].strip("0") for values in result.values()):
            raise ValueError("POLICY_AUTHORITY_NOT_UNIQUE")
        return {name: values[0] for name, values in result.items()}

    def tick(self):
        now = self.clock()
        try:
            identities = self._authorities()
            if self._batch is None:
                with self._lock:
                    if self._cache["authorities"] != identities:
                        self._cache.update(status="invalid", reason="POLICY_AUTHORITY_CHANGED", authorities=identities)
                if any(not c.service_is_ready() for pair in self._clients.values() for c in pair):
                    raise ValueError("POLICY_SERVICES_UNAVAILABLE")
                futures = {}
                # Own every dispatched future before the next call can fail,
                # including a parameter request whose state partner never starts.
                self._batch = (now, self._epoch, identities, futures)
                for name, (params, state) in self._clients.items():
                    pair = futures[name] = []
                    request = self._param_type.Request()
                    request.names = list(PARAMETERS[name])
                    pair.append(params.call_async(request))
                    pair.append(state.call_async(self._state_type.Request()))
                return
            started, epoch, original, futures = self._batch
            if original != identities or epoch != self._epoch:
                raise ValueError("POLICY_SOURCE_CHANGED_DURING_READBACK")
            if now - started > 0.5:
                raise ValueError("POLICY_READBACK_TIMEOUT")
            if not all(f.done() for pair in futures.values() for f in pair):
                return
            parameters, lifecycle = {}, {}
            for name, (params, state) in futures.items():
                values = params.result().values
                if len(values) != len(PARAMETERS[name]):
                    raise ValueError("POLICY_PARTIAL_READBACK")
                parameters[name] = {key: parameter_value(value) for key, value in zip(PARAMETERS[name], values)}
                lifecycle[name] = state.result().current_state.id
            self._sequence += 1
            with self._lock:
                self._cache = {"schema": POLICY_SCHEMA, "status": "current", "parameters": parameters,
                    "lifecycle": lifecycle, "authorities": identities, "sequence": self._sequence, "reason": None}
                # Age is measured from request start, never rebased to a late reply.
                self._received = started
            self._batch = None
        except Exception as exc:
            # Do not export exception strings (paths/environment/remote data).
            known = {"POLICY_AUTHORITY_NOT_UNIQUE", "POLICY_SERVICES_UNAVAILABLE",
                "POLICY_SOURCE_CHANGED_DURING_READBACK", "POLICY_READBACK_TIMEOUT", "POLICY_PARTIAL_READBACK"}
            self._invalidate(str(exc) if isinstance(exc, ValueError) and str(exc) in known else "POLICY_READBACK_FAILED")
            if self._batch is not None:
                for pair in self._batch[3].values():
                    for future in pair:
                        if not future.done():
                            future.cancel()
                self._batch = None

    def snapshot(self):
        with self._lock:
            value = copy.deepcopy(self._cache)
            received = self._received
        age = None if received is None else max(0.0, self.clock() - received)
        value["age_s"] = age
        if age is None or age > POLICY_TTL_S:
            value["status"] = "stale" if received is not None else "unavailable"
        return value
