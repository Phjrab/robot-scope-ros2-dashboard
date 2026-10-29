"""Fixed asynchronous Humble parameter/lifecycle observer on the existing node.

Only GetParameters/GetState are issued. No start, set, clear, action or motion
endpoint exists here. Every batch is bounded and invalidated by parameter events
and authority incarnation changes; render/mission gates only copy the cache.
"""
from __future__ import annotations

import copy
import threading
import time

from ..goal_precision_parameters import CONTROLLER_FIELDS, PLANNER_FIELDS

from ..navigation_policy import POLICY_DIAGNOSTICS_SCHEMA, POLICY_ENDPOINTS, POLICY_SCHEMA, POLICY_TTL_S
from ..navigation_collision_profile import BINDING_TOPIC, MASK_TTL_S, parse_mask_binding
from .collision_mask_publisher import source_authorities
from .policy_parameters import declaration_names, complete_parameters

PARAMETERS = {
    "/planner_server": ("planner_plugins", "GridBased.plugin", "GridBased.allow_unknown", "GridBased.use_astar", "GridBased.tolerance"),
    "/controller_server": ("controller_plugins", "FollowPath.plugin", "FollowPath.primary_controller", "FollowPath.use_collision_detection", "FollowPath.max_allowed_time_to_collision_up_to_carrot"),
    "/bt_navigator": ("default_nav_to_pose_bt_xml", "global_frame", "robot_base_frame"),
    "/global_costmap/global_costmap": ("global_frame", "robot_base_frame", "robot_radius", "footprint", "footprint_padding", "track_unknown_space", "plugins", "filters", "static_layer.plugin", "static_layer.map_topic", "static_layer.enabled", "keepout_filter.plugin", "keepout_filter.enabled", "keepout_filter.filter_info_topic"),
    "/local_costmap/local_costmap": ("global_frame", "robot_base_frame", "robot_radius", "footprint", "footprint_padding", "track_unknown_space", "plugins", "filters", "static_layer.plugin", "static_layer.map_topic", "static_layer.enabled", "keepout_filter.plugin", "keepout_filter.enabled", "keepout_filter.filter_info_topic"),
}
PARAMETERS['/planner_server'] = tuple(dict.fromkeys(PARAMETERS['/planner_server'] + PLANNER_FIELDS))
PARAMETERS['/controller_server'] = tuple(dict.fromkeys(PARAMETERS['/controller_server'] + CONTROLLER_FIELDS))

for _costmap in ("/global_costmap/global_costmap", "/local_costmap/local_costmap"):
    PARAMETERS[_costmap] += (
        "policy_layer.plugin", "policy_layer.enabled", "policy_layer.map_topic",
        "policy_layer.map_subscribe_transient_local", "policy_layer.subscribe_to_updates",
        "policy_layer.footprint_clearing_enabled", "use_maximum", "unknown_cost_value",
        "lethal_cost_threshold", "trinary_costmap",
        "inflation_layer.inflation_radius", "resolution", "rolling_window",
    )


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
        self._list_clients = {}
        self._list_batch = None
        self._declarations = None
        self._request_names = {}
        self._last_tick = None
        self._attempt_sequence = 0
        self._dispatch_duration = None
        self._diagnostics = None
        self._diagnostics_received = None
        self._mask_cache = None
        self._mask_received = None

    def setup(self):
        from rcl_interfaces.msg import ParameterEvent
        from rcl_interfaces.srv import GetParameters, ListParameters
        from lifecycle_msgs.srv import GetState
        from rclpy.qos import qos_profile_parameter_events
        from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
        from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
        from std_msgs.msg import String
        self._group = MutuallyExclusiveCallbackGroup()
        for node in PARAMETERS:
            self._list_clients[node] = self.node.create_client(
                ListParameters, node + '/list_parameters', callback_group=self._group)
            self._clients[node] = (
                self.node.create_client(GetParameters, node + "/get_parameters", callback_group=self._group),
                self.node.create_client(GetState, node + "/get_state", callback_group=self._group))
        self._param_type, self._state_type = GetParameters, GetState
        self._list_type = ListParameters
        self._events = self.node.create_subscription(ParameterEvent, "/parameter_events", self._on_event,
            qos_profile_parameter_events, callback_group=self._group)
        self._mask_subscription = self.node.create_subscription(String, BINDING_TOPIC, self._on_mask,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE), callback_group=self._group)
        self._timer = self.node.create_timer(0.25, self.tick, callback_group=self._group)

    def _mask_invalid(self, reason):
        with self._lock:
            if self._mask_cache is not None:
                self._mask_cache.update(status="invalid", reason=reason)

    def _check_mask_source(self):
        # No mask configured remains backward-compatible. If a publication has
        # been observed, source loss invalidates it independently of service GETs.
        with self._lock:
            previous = None if self._mask_cache is None else self._mask_cache.get("authorities")
        if previous is None:
            return
        try:
            if source_authorities(self.node) != previous:
                self._mask_invalid("MASK_SOURCE_CHANGED")
        except Exception:
            self._mask_invalid("MASK_SOURCE_NOT_UNIQUE")

    def _on_mask(self, message, info):
        try:
            binding = parse_mask_binding(message.data)
            authorities = source_authorities(self.node)
            if bytes(info.publisher_gid).hex() != authorities["binding"]:
                raise ValueError("MASK_MESSAGE_AUTHORITY_MISMATCH")
            now = self.clock()
            with self._lock:
                previous = self._mask_cache
                if previous is not None:
                    prior = previous.get("binding", {})
                    same_incarnation = prior.get("incarnation") == binding["incarnation"]
                    prior_semantic = {k: v for k, v in prior.items() if k != "sequence"}
                    current_semantic = {k: v for k, v in binding.items() if k != "sequence"}
                    if same_incarnation and (prior_semantic != current_semantic
                            or previous.get("authorities") != authorities
                            or binding["sequence"] <= prior.get("sequence", 0)):
                        raise ValueError("MASK_SOURCE_CHANGED")
                self._mask_cache = {"status": "current", "reason": None, "binding": binding,
                                    "authorities": authorities}
                self._mask_received = now
        except Exception:
            # Never expose remote payloads/exceptions; a malformed message cannot
            # preserve a fresh source heartbeat or attest costmap ingestion.
            with self._lock:
                if self._mask_cache is None:
                    self._mask_cache = {"status": "invalid", "reason": "MASK_SOURCE_INVALID"}
                else:
                    self._mask_cache.update(status="invalid", reason="MASK_SOURCE_INVALID")

    def _on_event(self, message):
        if message.node in PARAMETERS:
            self._epoch += 1
            self._invalidate("PARAMETERS_CHANGED")

    def _ensure_declarations(self, identities, now):
        # Cache only within one authority incarnation and parameter-event epoch.
        # Discovery has its own existing 0.5s deadline. Parameter freshness still
        # starts at GetParameters dispatch; no service deadline is relaxed.
        if self._declarations is not None and self._declarations[:2] == (self._epoch, identities):
            return True
        self._declarations = None
        if self._list_batch is None:
            if set(self._list_clients) != set(PARAMETERS) or any(
                    not c.service_is_ready() for c in self._list_clients.values()):
                raise ValueError('POLICY_SERVICES_UNAVAILABLE')
            futures = {}
            self._list_batch = (now, self._epoch, identities, futures)
            for name, client in self._list_clients.items():
                request = self._list_type.Request()
                request.depth = 0
                request.prefixes = []
                futures[name] = client.call_async(request)
            return False
        started, epoch, original, futures = self._list_batch
        if original != identities or epoch != self._epoch:
            raise ValueError('POLICY_SOURCE_CHANGED_DURING_READBACK')
        if now - started > .5:
            raise ValueError('POLICY_READBACK_TIMEOUT')
        if not all(f.done() for f in futures.values()):
            return False
        declared = {name: declaration_names(f.result()) for name, f in futures.items()}
        self._declarations = (epoch, original, declared)
        self._list_batch = None
        return True

    def _invalidate(self, reason):
        with self._lock:
            self._cache["status"], self._cache["reason"] = "invalid", reason
            if 'node_status' in self._cache:
                self._cache['node_status'] = {name: 'invalid' for name in PARAMETERS}

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

    def _finish_diagnostics(self, *, reason, now, tick_gap, authority_duration):
        """Keep one bounded attempt, with future state observed before cleanup.

        A done future at a late poll does not prove its completion time or transport
        latency. Pending client futures likewise do not identify a server failure.
        """
        batch = self._batch
        endpoints = {name: {"dispatched": False, "done": None, "cancelled": None}
                     for name in POLICY_ENDPOINTS}
        if batch is not None:
            for name, pair in batch[3].items():
                for service, future in zip(("get_parameters", "get_state"), pair):
                    # A diagnostic failure must not disrupt cleanup or policy gates.
                    try:
                        done = bool(future.done())
                    except Exception:
                        done = None
                    try:
                        is_cancelled = bool(future.cancelled())
                    except Exception:
                        is_cancelled = None
                    endpoints[name + "/" + service] = {
                        "dispatched": True, "done": done, "cancelled": is_cancelled}
        with self._lock:
            self._diagnostics = {"schema": POLICY_DIAGNOSTICS_SCHEMA,
                "attempt_sequence": self._attempt_sequence,
                "outcome": "failed" if reason else "completed", "reason": reason,
                "batch_age_s": None if batch is None else max(0.0, now - batch[0]),
                "tick_gap_s": tick_gap, "authority_duration_s": authority_duration,
                "dispatch_duration_s": self._dispatch_duration, "endpoints": endpoints}
            self._diagnostics_received = now

    def tick(self):
        self._check_mask_source()
        now = self.clock()
        tick_gap = None if self._last_tick is None else max(0.0, now - self._last_tick)
        self._last_tick = now
        authority_duration = None
        if self._batch is None:
            self._attempt_sequence = min(2**63 - 1, self._attempt_sequence + 1)
            self._dispatch_duration = None
        try:
            authority_start = self.clock()
            try:
                identities = self._authorities()
            finally:
                authority_duration = max(0.0, self.clock() - authority_start)
            if self._batch is None:
                with self._lock:
                    if self._cache["authorities"] != identities:
                        self._cache.update(status="invalid", reason="POLICY_AUTHORITY_CHANGED", authorities=identities)
                if not self._ensure_declarations(identities, now):
                    return
                if any(not c.service_is_ready() for pair in self._clients.values() for c in pair):
                    raise ValueError("POLICY_SERVICES_UNAVAILABLE")
                futures = {}
                # Own every dispatched future before the next call can fail,
                # including a parameter request whose state partner never starts.
                self._batch = (now, self._epoch, identities, futures)
                dispatch_start = self.clock()
                try:
                    for name, (params, state) in self._clients.items():
                        pair = futures[name] = []
                        request = self._param_type.Request()
                        request.names = [key for key in PARAMETERS[name] if key in self._declarations[2][name]]
                        self._request_names[name] = request.names
                        pair.append(params.call_async(request))
                        pair.append(state.call_async(self._state_type.Request()))
                finally:
                    self._dispatch_duration = max(0.0, self.clock() - dispatch_start)
                return
            started, epoch, original, futures = self._batch
            if original != identities or epoch != self._epoch:
                raise ValueError("POLICY_SOURCE_CHANGED_DURING_READBACK")
            if now - started > 0.5:
                raise ValueError("POLICY_READBACK_TIMEOUT")
            if not all(f.done() for pair in futures.values() for f in pair):
                return
            parameters, lifecycle, applicability, missing = {}, {}, {}, {}
            for name, (params, state) in futures.items():
                values = params.result().values
                names = self._request_names[name]
                # One broken node must not erase valid controller/planner
                # metrology. Overall policy still fails closed.
                observed = {} if len(values) != len(names) else {
                    key: parameter_value(value) for key, value in zip(names, values)}
                parameters[name], applicability[name], missing[name] = complete_parameters(
                    name, PARAMETERS[name], observed)
                lifecycle[name] = state.result().current_state.id
            reason = 'POLICY_PARTIAL_READBACK' if any(missing.values()) else None
            self._sequence += 1
            with self._lock:
                self._cache = {"schema": POLICY_SCHEMA, "status": "invalid" if reason else "current", "parameters": parameters,
                    "lifecycle": lifecycle, "authorities": identities, "sequence": self._sequence, "reason": reason,
                    "applicability": applicability, "missing_required": missing,
                    "node_status": {name: 'invalid' if missing[name] else 'current' for name in PARAMETERS}}
                # Age is measured from request start, never rebased to a late reply.
                self._received = started
            self._finish_diagnostics(reason=reason, now=self.clock(), tick_gap=tick_gap,
                                     authority_duration=authority_duration)
            self._batch = None
            if reason:
                self._declarations = None
        except Exception as exc:
            # Do not export exception strings (paths/environment/remote data).
            known = {"POLICY_AUTHORITY_NOT_UNIQUE", "POLICY_SERVICES_UNAVAILABLE",
                "POLICY_SOURCE_CHANGED_DURING_READBACK", "POLICY_READBACK_TIMEOUT", "POLICY_PARTIAL_READBACK"}
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in known else "POLICY_READBACK_FAILED"
            self._invalidate(reason)
            # Record pre-cleanup state: our own cancellation must not disguise a
            # still-pending endpoint as a response received before the deadline.
            self._finish_diagnostics(reason=reason, now=self.clock(), tick_gap=tick_gap,
                                     authority_duration=authority_duration)
            if self._batch is not None:
                for pair in self._batch[3].values():
                    for future in pair:
                        if not future.done():
                            future.cancel()
                self._batch = None
            if self._list_batch is not None:
                for future in self._list_batch[3].values():
                    if not future.done():
                        future.cancel()
                self._list_batch = None

    def snapshot(self):
        with self._lock:
            value = copy.deepcopy(self._cache)
            received = self._received
            diagnostics = copy.deepcopy(self._diagnostics)
            diagnostics_received = self._diagnostics_received
            mask = copy.deepcopy(self._mask_cache)
            mask_received = self._mask_received
        age = None if received is None else max(0.0, self.clock() - received)
        value["age_s"] = age
        if diagnostics is not None:
            diagnostics["age_s"] = max(0.0, self.clock() - diagnostics_received)
            value["diagnostics"] = diagnostics
        if age is None or age > POLICY_TTL_S:
            value["status"] = "stale" if received is not None else "unavailable"
            if 'node_status' in value:
                value['node_status'] = {name: value['status'] for name in PARAMETERS}
        if mask is not None:
            mask["age_s"] = None if mask_received is None else max(0.0, self.clock() - mask_received)
            if mask["age_s"] is None or mask["age_s"] > MASK_TTL_S:
                mask["status"] = "unavailable" if mask_received is None else "stale"
            value["collision_mask_source"] = mask
        return value
