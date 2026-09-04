"""Signed ROS transport for the fail-closed mobile-robot control manager."""

from __future__ import annotations

import math
import os
import secrets
import threading
import time
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional, Tuple

from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from ..control import ControlClosed, ControlDisabled, ControlManager
from ..control_datagram import (
    CONTROL_TRANSPORT_ROS,
    CONTROL_TRANSPORT_UDP,
    ConnectedControlDatagram,
    ControlDatagramConfig,
    ControlDatagramError,
    DatagramStringPublisher,
    control_transport_mode,
)
from ..control_protocol import (
    ControlProtocolError,
    decode_signed,
    encode_signed,
    shared_key,
)
from ..go2_bridge import (
    API_MOVE,
    API_STOP_MOVE,
    SAFE_ACTION_API_IDS,
    SPORT_REQUEST_EVIDENCE_MAX_COUNT,
    SPORT_REQUEST_EVIDENCE_SCHEMA,
    SPORT_MODE_STATE_MAX_ABS_VELOCITY,
    SPORT_MODE_STATE_MAX_AGE_MS,
    SPORT_MODE_STATE_MAX_ERROR_CODE,
    SPORT_MODE_STATE_TOPICS,
)
from ..serializers import GO2_JOINT_LIMITS, GO2_JOINT_ORDER, go2_joint_state_payload


CONTROL_COMMAND_TOPIC = "/robot_scope/control/command"
CONTROL_STATUS_TOPIC = "/robot_scope/control/status"


class ControlTransport:
    """Own the authenticated dashboard-to-watchdog ROS transport.

    ``ControlManager`` remains ROS-independent.  This component composes that
    manager with the fixed, signed ROS endpoints and exposes one operation lock
    for the facade and navigation gateway to share.  Navigation policy is
    deliberately not imported here: the facade retains the exact pre/post
    interlock ordering around ``manager_tick_locked``.
    """

    def __init__(
        self,
        profile: Dict[str, Any],
        *,
        environ: Optional[Mapping[str, str]] = None,
        manager: Optional[ControlManager] = None,
        ensure_target: Optional[Callable[[], None]] = None,
        go2_target: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.profile = profile
        environment = os.environ if environ is None else environ
        self._environment = dict(environment)
        self.manager = (
            manager
            if manager is not None
            else ControlManager(profile, environ=environment)
        )

        control_profile = profile.get("control", {})
        if not isinstance(control_profile, dict):
            control_profile = {}
        self.status_timeout_s = self.bounded_timeout(
            control_profile.get("bridge_status_timeout_s"),
            default=0.75,
            low=0.25,
            high=5.0,
        )
        self.lowstate_timeout_s = self.bounded_timeout(
            control_profile.get("telemetry_timeout_s"),
            default=0.50,
            low=0.20,
            high=2.0,
        )
        expected_bare_sport_publishers = control_profile.get(
            "expected_bare_sport_publishers", 0
        )
        if (
            isinstance(expected_bare_sport_publishers, bool)
            or not isinstance(expected_bare_sport_publishers, int)
            or not 0 <= expected_bare_sport_publishers <= 64
        ):
            raise ValueError(
                "control.expected_bare_sport_publishers must be an integer "
                "from 0 to 64"
            )
        self.expected_bare_sport_publishers = expected_bare_sport_publishers

        try:
            self.bridge_key: Optional[bytes] = shared_key(
                environment.get("ROBOT_SCOPE_CONTROL_BRIDGE_KEY", "")
            )
            bridge_key_error = ""
        except ControlProtocolError as exc:
            self.bridge_key = None
            bridge_key_error = str(exc)
        try:
            self.transport_mode = control_transport_mode(environment)
            transport_mode_error = ""
        except ControlDatagramError as exc:
            self.transport_mode = "invalid"
            transport_mode_error = str(exc)
        if transport_mode_error:
            bridge_key_error = transport_mode_error

        self.source_id = f"robot-scope-agent-{os.getpid()}-{secrets.token_hex(8)}"
        self.bridge_seq = -1
        self.bridge_epoch = ""

        # The operation lock serializes every manager mutation with publication.
        # A completed terminal stop/release can therefore never be followed by a
        # drive output drained by an earlier timer tick.
        self.operation_lock = threading.RLock()
        self.transport_lock = threading.RLock()
        if (
            (ensure_target is not None and not callable(ensure_target))
            or (go2_target is not None and not callable(go2_target))
        ):
            raise ValueError("control target policy callbacks must be callable")
        self._ensure_target_policy: Callable[[], None] = (
            ensure_target if ensure_target is not None else self._target_policy_unbound
        )
        self._go2_target_policy: Callable[[], bool] = (
            go2_target if go2_target is not None else lambda: False
        )
        self.callback_group: Optional[MutuallyExclusiveCallbackGroup] = None
        self.command_publisher: Any = None
        self.status_subscription: Any = None
        self.timer: Any = None
        self._datagram_endpoint: ConnectedControlDatagram | None = None
        self._datagram_stop = threading.Event()
        self._datagram_thread: threading.Thread | None = None
        # A new dashboard process has a new signed source id while a running
        # Bridge can still remember the previous source for its bounded
        # ownership window.  The first authenticated UDP status therefore
        # triggers one StopMove-only handoff before control becomes ready.
        # Status loss requires the same fail-closed handoff again on recovery.
        self._datagram_sync_epoch = ""
        self._datagram_sync_required = self.transport_mode == CONTROL_TRANSPORT_UDP
        self._datagram_sync_pending: tuple[str, int, float] | None = None
        self._retired_bridge_epochs: List[str] = []
        self.status_received = 0.0
        self.status: Dict[str, Any] = {
            "state": "not_configured" if bridge_key_error else "waiting",
            "ready": False,
            "connected": False,
            "available": False,
            "message": bridge_key_error or "signed Go2 bridge status waiting",
        }
        self.shutdown_started = False

    @staticmethod
    def _target_policy_unbound() -> None:
        raise ControlDisabled("control target policy is not bound")

    def bind_target_policy(
        self,
        ensure_target: Callable[[], None],
        go2_target: Callable[[], bool],
    ) -> None:
        """Bind facade-owned startup-target checks without owning target state."""

        if not callable(ensure_target) or not callable(go2_target):
            raise ValueError("control target policy callbacks must be callable")
        with self.operation_lock:
            self._ensure_target_policy = ensure_target
            self._go2_target_policy = go2_target

    def ensure_target(self) -> None:
        """Require the facade's immutable startup Go2 transport target."""

        with self.operation_lock:
            self._ensure_target_policy()

    def go2_target(self) -> bool:
        """Return false when the facade-owned target check cannot be established."""

        with self.operation_lock:
            try:
                return bool(self._go2_target_policy())
            except Exception:
                return False

    @staticmethod
    def bounded_timeout(
        value: object,
        *,
        default: float,
        low: float,
        high: float,
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return max(low, min(parsed, high))

    def setup(self, node: Any, timer_callback: Callable[[], None]) -> None:
        """Create only the two fixed signed endpoints and their 50 ms timer."""

        pending_endpoint: ConnectedControlDatagram | None = None
        try:
            callback_group = MutuallyExclusiveCallbackGroup()
            if self.transport_mode == CONTROL_TRANSPORT_UDP:
                endpoint = ConnectedControlDatagram(
                    ControlDatagramConfig.from_environment(self._environment)
                )
                pending_endpoint = endpoint
                timer = node.create_timer(
                    0.05,
                    timer_callback,
                    callback_group=callback_group,
                )
                receiver = threading.Thread(
                    target=self._receive_datagram_status,
                    args=(endpoint,),
                    name="control-datagram-status",
                    daemon=True,
                )
                with self.transport_lock:
                    self.callback_group = callback_group
                    self.command_publisher = DatagramStringPublisher(endpoint)
                    self.status_subscription = endpoint
                    self.timer = timer
                    self._datagram_endpoint = endpoint
                    self._datagram_thread = receiver
                receiver.start()
                pending_endpoint = None
                return
            if self.transport_mode != CONTROL_TRANSPORT_ROS:
                raise ControlDatagramError("control transport is invalid")
            reliable = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            publisher = node.create_publisher(
                String,
                CONTROL_COMMAND_TOPIC,
                reliable,
                callback_group=callback_group,
            )
            subscription = node.create_subscription(
                String,
                CONTROL_STATUS_TOPIC,
                self.status_callback,
                reliable,
                callback_group=callback_group,
            )
            timer = node.create_timer(
                0.05,
                timer_callback,
                callback_group=callback_group,
            )
            with self.transport_lock:
                self.callback_group = callback_group
                self.command_publisher = publisher
                self.status_subscription = subscription
                self.timer = timer
        except Exception as exc:
            if pending_endpoint is not None:
                pending_endpoint.close()
            self.set_unready(f"control transport unavailable: {exc}")

    def _receive_datagram_status(
        self, endpoint: ConnectedControlDatagram
    ) -> None:
        while not self._datagram_stop.is_set():
            try:
                encoded = endpoint.receive_text()
            except ControlDatagramError as exc:
                self.set_unready(f"rejected bridge status datagram: {exc}")
                continue
            except OSError as exc:
                if self._datagram_stop.is_set():
                    return
                self.set_unready(f"control status datagram failed: {exc}")
                # A connected UDP socket can report a transient network error
                # while its fixed peer or interface is unavailable. Keep the
                # receiver alive so authenticated status can recover without a
                # dashboard restart; readiness remains revoked meanwhile.
                if self._datagram_stop.wait(0.2):
                    return
                continue
            if encoded is None:
                continue
            message = String()
            message.data = encoded
            self.status_callback(message)

    @staticmethod
    def status_readiness(
        payload: Dict[str, Any],
        *,
        lowstate_timeout_s: float,
        expected_bare_sport_publishers: int = 0,
    ) -> Tuple[bool, bool, str]:
        """Validate bridge health fields after signature verification."""

        if payload.get("type") != "bridge_status":
            raise ControlProtocolError("unexpected bridge status type")
        request_evidence = ControlTransport.status_request_evidence(payload)
        ControlTransport.status_sport_mode_state(payload)
        ControlTransport.status_command_ack(payload)
        reported_ready = payload.get("ready")
        if not isinstance(reported_ready, bool):
            raise ControlProtocolError("bridge ready flag is invalid")
        subscribers = payload.get("sport_subscribers")
        if isinstance(subscribers, bool) or not isinstance(subscribers, int):
            raise ControlProtocolError("bridge subscriber count is invalid")
        sport_publishers = payload.get("sport_publishers")
        if (
            isinstance(sport_publishers, bool)
            or not isinstance(sport_publishers, int)
            or sport_publishers < 0
            or sport_publishers > 128
        ):
            raise ControlProtocolError("sport request publisher count is invalid")
        publisher_fields = {
            "own_sport_publishers": 16,
            "foreign_named_sport_publishers": 16,
            "bare_unitree_sport_publishers": 64,
            "expected_bare_sport_publishers": 64,
        }
        publisher_counts: Dict[str, int] = {}
        for field, upper_bound in publisher_fields.items():
            value = payload.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value > upper_bound
            ):
                raise ControlProtocolError(f"{field} is invalid")
            publisher_counts[field] = value
        if publisher_counts["expected_bare_sport_publishers"] != int(
            expected_bare_sport_publishers
        ):
            raise ControlProtocolError(
                "bridge bare sport publisher expectation does not match profile"
            )
        if sport_publishers != (
            publisher_counts["own_sport_publishers"]
            + publisher_counts["foreign_named_sport_publishers"]
            + publisher_counts["bare_unitree_sport_publishers"]
        ):
            raise ControlProtocolError(
                "sport request publisher counts are inconsistent"
            )
        publishers = payload.get("lowstate_publishers")
        if isinstance(publishers, bool) or not isinstance(publishers, int):
            raise ControlProtocolError("LowState publisher count is invalid")
        bridge_epoch = payload.get("bridge_epoch")
        if not isinstance(bridge_epoch, str) or not 16 <= len(bridge_epoch) <= 128:
            raise ControlProtocolError("bridge epoch is invalid")
        lowstate_age_ms = payload.get("lowstate_age_ms")
        if (
            isinstance(lowstate_age_ms, bool)
            or not isinstance(lowstate_age_ms, (int, float))
            or not math.isfinite(float(lowstate_age_ms))
            or float(lowstate_age_ms) < 0.0
        ):
            lowstate_ready = False
        else:
            lowstate_ready = (
                float(lowstate_age_ms) <= float(lowstate_timeout_s) * 1_000.0
            )
        bridge_ready = (
            reported_ready
            and subscribers == 1
            and publisher_counts["own_sport_publishers"] == 1
            and publisher_counts["foreign_named_sport_publishers"] == 0
            and publisher_counts["bare_unitree_sport_publishers"]
            == expected_bare_sport_publishers
            and publishers == 1
            and (
                not request_evidence
                or (
                    request_evidence["malformed_move_count"] == 0
                    and request_evidence["other_count"] == 0
                )
            )
        )
        return bridge_ready, lowstate_ready, bridge_epoch

    @staticmethod
    def status_command_ack(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate the Bridge's optional signed last-command acknowledgement."""

        acknowledgement = payload.get("command_ack")
        if acknowledgement is None:
            return {}
        expected = {"source_id", "seq", "type", "age_ms"}
        if not isinstance(acknowledgement, Mapping) or set(acknowledgement) != expected:
            raise ControlProtocolError("bridge command acknowledgement is invalid")
        source_id = acknowledgement.get("source_id")
        sequence = acknowledgement.get("seq")
        kind = acknowledgement.get("type")
        age_ms = acknowledgement.get("age_ms")
        if not isinstance(source_id, str) or not 8 <= len(source_id) <= 128:
            raise ControlProtocolError("bridge command acknowledgement is invalid")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 0 <= sequence <= 2_147_483_647
            or kind not in {"stop", "drive", "action"}
            or isinstance(age_ms, bool)
            or not isinstance(age_ms, int)
            or not 0 <= age_ms <= 2_147_483_647
        ):
            raise ControlProtocolError("bridge command acknowledgement is invalid")
        return {
            "source_id": source_id,
            "seq": sequence,
            "type": kind,
            "age_ms": age_ms,
        }

    @staticmethod
    def status_request_evidence(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate optional signed, bounded bridge-owned publish evidence."""

        evidence = payload.get("request_evidence")
        if evidence is None:
            return {}
        expected = {
            "schema",
            "scope",
            "published_count",
            "stop_count",
            "move_count",
            "zero_move_count",
            "nonzero_move_count",
            "malformed_move_count",
            "action_count",
            "other_count",
            "last_api_id",
            "last_publish_age_ms",
            "max_abs_linear_x",
            "max_abs_linear_y",
            "max_abs_angular_z",
            "motion_run_id",
            "motion_run_active",
            "motion_run_nonzero_move_count",
            "motion_run_max_abs_linear_x",
            "motion_run_max_abs_linear_y",
            "motion_run_max_abs_angular_z",
        }
        if not isinstance(evidence, Mapping) or set(evidence) != expected:
            raise ControlProtocolError("bridge request evidence is invalid")
        if (
            evidence.get("schema") != SPORT_REQUEST_EVIDENCE_SCHEMA
            or evidence.get("scope") != "bridge_process"
        ):
            raise ControlProtocolError("bridge request evidence contract is invalid")

        count_names = (
            "published_count",
            "stop_count",
            "move_count",
            "zero_move_count",
            "nonzero_move_count",
            "malformed_move_count",
            "action_count",
            "other_count",
            "motion_run_id",
            "motion_run_nonzero_move_count",
        )
        counts: Dict[str, int] = {}
        for name in count_names:
            value = evidence.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= SPORT_REQUEST_EVIDENCE_MAX_COUNT
            ):
                raise ControlProtocolError("bridge request evidence count is invalid")
            counts[name] = value
        classified = min(
            SPORT_REQUEST_EVIDENCE_MAX_COUNT,
            counts["stop_count"]
            + counts["move_count"]
            + counts["action_count"]
            + counts["other_count"],
        )
        moves = min(
            SPORT_REQUEST_EVIDENCE_MAX_COUNT,
            counts["zero_move_count"]
            + counts["nonzero_move_count"]
            + counts["malformed_move_count"],
        )
        if counts["published_count"] != classified or counts["move_count"] != moves:
            raise ControlProtocolError("bridge request evidence counts are inconsistent")

        last_api_id = evidence.get("last_api_id")
        last_age = evidence.get("last_publish_age_ms")
        if counts["published_count"] == 0:
            if last_api_id is not None or last_age is not None:
                raise ControlProtocolError("empty bridge request evidence is inconsistent")
        elif (
            isinstance(last_api_id, bool)
            or not isinstance(last_api_id, int)
            or not 0 <= last_api_id <= 65_535
            or isinstance(last_age, bool)
            or not isinstance(last_age, int)
            or not 0 <= last_age <= SPORT_REQUEST_EVIDENCE_MAX_COUNT
        ):
            raise ControlProtocolError("bridge request evidence last request is invalid")
        if counts["published_count"]:
            if (
                (last_api_id == API_STOP_MOVE and counts["stop_count"] == 0)
                or (last_api_id == API_MOVE and counts["move_count"] == 0)
                or (
                    last_api_id in SAFE_ACTION_API_IDS.values()
                    and counts["action_count"] == 0
                )
                or (
                    last_api_id not in {
                        API_STOP_MOVE,
                        API_MOVE,
                        *SAFE_ACTION_API_IDS.values(),
                    }
                    and counts["other_count"] == 0
                )
            ):
                raise ControlProtocolError(
                    "bridge request evidence last request is inconsistent"
                )

        velocity_bounds = {
            "max_abs_linear_x": 0.30,
            "max_abs_linear_y": 0.20,
            "max_abs_angular_z": 0.50,
            "motion_run_max_abs_linear_x": 0.30,
            "motion_run_max_abs_linear_y": 0.20,
            "motion_run_max_abs_angular_z": 0.50,
        }
        velocities: Dict[str, float] = {}
        for name, upper in velocity_bounds.items():
            value = evidence.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= upper
            ):
                raise ControlProtocolError("bridge request evidence velocity is invalid")
            velocities[name] = float(value)
        if counts["nonzero_move_count"] == 0 and any(velocities.values()):
            raise ControlProtocolError("bridge request evidence velocity is inconsistent")
        motion_run_active = evidence.get("motion_run_active")
        if not isinstance(motion_run_active, bool):
            raise ControlProtocolError("bridge request evidence motion run is invalid")
        run_id = counts["motion_run_id"]
        run_count = counts["motion_run_nonzero_move_count"]
        run_velocities = (
            velocities["motion_run_max_abs_linear_x"],
            velocities["motion_run_max_abs_linear_y"],
            velocities["motion_run_max_abs_angular_z"],
        )
        if (
            run_id > counts["nonzero_move_count"]
            or run_count > counts["nonzero_move_count"]
            or (run_id == 0 and (motion_run_active or run_count != 0 or any(run_velocities)))
            or (run_id > 0 and (run_count == 0 or not any(run_velocities)))
            or any(
                run_velocity > velocities[cumulative_name]
                for run_velocity, cumulative_name in zip(
                    run_velocities,
                    (
                        "max_abs_linear_x",
                        "max_abs_linear_y",
                        "max_abs_angular_z",
                    ),
                )
            )
        ):
            raise ControlProtocolError("bridge request evidence motion run is inconsistent")

        return {
            "schema": SPORT_REQUEST_EVIDENCE_SCHEMA,
            "scope": "bridge_process",
            **counts,
            "last_api_id": last_api_id,
            "last_publish_age_ms": last_age,
            **velocities,
            "motion_run_active": motion_run_active,
        }

    @staticmethod
    def status_sport_mode_state(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate optional raw SportModeState data without gating on its values."""

        state = payload.get("sport_mode_state")
        if state is None:
            return {}
        expected = {
            "topic",
            "mode",
            "gait_type",
            "velocity",
            "error_code",
            "age_ms",
            "stale_after_ms",
            "fresh",
        }
        if not isinstance(state, Mapping) or set(state) != expected:
            raise ControlProtocolError("bridge SportModeState is invalid")
        if state.get("topic") not in SPORT_MODE_STATE_TOPICS:
            raise ControlProtocolError("bridge SportModeState topic is invalid")
        fresh = state.get("fresh")
        age_ms = state.get("age_ms")
        stale_after_ms = state.get("stale_after_ms")
        if not isinstance(fresh, bool):
            raise ControlProtocolError("bridge SportModeState freshness is invalid")
        if (
            isinstance(stale_after_ms, bool)
            or not isinstance(stale_after_ms, int)
            or not 200 <= stale_after_ms <= 1_000
        ):
            raise ControlProtocolError("bridge SportModeState freshness is invalid")
        if age_ms is None:
            if fresh or any(
                state.get(name) is not None
                for name in ("mode", "gait_type", "velocity", "error_code")
            ):
                raise ControlProtocolError("bridge SportModeState is inconsistent")
        elif (
            isinstance(age_ms, bool)
            or not isinstance(age_ms, int)
            or not 0 <= age_ms <= SPORT_MODE_STATE_MAX_AGE_MS
        ):
            raise ControlProtocolError("bridge SportModeState age is invalid")

        values_visible = age_ms is not None and age_ms <= stale_after_ms
        if fresh is not values_visible:
            raise ControlProtocolError("bridge SportModeState freshness is inconsistent")
        if not values_visible:
            if any(
                state.get(name) is not None
                for name in ("mode", "gait_type", "velocity", "error_code")
            ):
                raise ControlProtocolError("stale bridge SportModeState is not hidden")
            return {
                "topic": state["topic"],
                "mode": None,
                "gait_type": None,
                "velocity": None,
                "error_code": None,
                "age_ms": age_ms,
                "stale_after_ms": stale_after_ms,
                "fresh": False,
            }

        integers = {
            "mode": 255,
            "gait_type": 255,
            "error_code": SPORT_MODE_STATE_MAX_ERROR_CODE,
        }
        projected: Dict[str, Any] = {}
        for name, maximum in integers.items():
            value = state.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= maximum
            ):
                raise ControlProtocolError("bridge SportModeState value is invalid")
            projected[name] = value
        velocity = state.get("velocity")
        if not isinstance(velocity, list) or len(velocity) != 3:
            raise ControlProtocolError("bridge SportModeState velocity is invalid")
        safe_velocity: List[float] = []
        for value in velocity:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or abs(float(value)) > SPORT_MODE_STATE_MAX_ABS_VELOCITY
            ):
                raise ControlProtocolError("bridge SportModeState velocity is invalid")
            safe_velocity.append(round(float(value), 6))
        return {
            "topic": state["topic"],
            "mode": projected["mode"],
            "gait_type": projected["gait_type"],
            "velocity": safe_velocity,
            "error_code": projected["error_code"],
            "age_ms": age_ms,
            "stale_after_ms": stale_after_ms,
            "fresh": True,
        }

    def status_callback(self, message: String) -> None:
        key = self.bridge_key
        if key is None:
            self.set_unready("signed bridge key is not configured")
            return
        try:
            payload = decode_signed(
                message.data,
                key,
                max_age_s=max(1.0, self.status_timeout_s * 2.0),
            )
            bridge_ready, lowstate_ready, bridge_epoch = self.status_readiness(
                payload,
                lowstate_timeout_s=self.lowstate_timeout_s,
                expected_bare_sport_publishers=self.expected_bare_sport_publishers,
            )
            telemetry = self.status_telemetry(payload)
            request_evidence = self.status_request_evidence(payload)
            sport_mode_state = self.status_sport_mode_state(payload)
            command_ack = self.status_command_ack(payload)
        except (ControlProtocolError, TypeError, ValueError) as exc:
            self.set_unready(f"rejected bridge status: {exc}")
            return

        now = time.monotonic()
        available = bridge_ready and lowstate_ready
        status = dict(payload)
        status["telemetry"] = telemetry
        status["request_evidence"] = request_evidence
        if sport_mode_state:
            status["sport_mode_state"] = sport_mode_state
        if command_ack:
            status["command_ack"] = command_ack
        status.update(
            {
                "authenticated": True,
                "connected": available,
                "available": available,
                "message": (
                    "signed Go2 bridge ready"
                    if available
                    else str(payload.get("last_error") or "Go2 bridge is not ready")
                ),
            }
        )
        with self.operation_lock:
            with self.transport_lock:
                previous_epoch = self.bridge_epoch
                retired_epoch = bool(
                    previous_epoch
                    and bridge_epoch != previous_epoch
                    and bridge_epoch in self._retired_bridge_epochs
                )
            if retired_epoch:
                # A delayed authenticated UDP status from an earlier Bridge
                # must not roll the active epoch backwards and make all later
                # command envelopes invalid at the running Bridge.
                self.set_unready("rejected retired bridge epoch")
                return
            with self.transport_lock:
                if previous_epoch and previous_epoch != bridge_epoch:
                    if previous_epoch not in self._retired_bridge_epochs:
                        self._retired_bridge_epochs.append(previous_epoch)
                        self._retired_bridge_epochs = self._retired_bridge_epochs[-16:]
                    self._datagram_sync_epoch = ""
                    self._datagram_sync_required = True
                    self._datagram_sync_pending = None
                self.bridge_epoch = bridge_epoch
                self.status_received = now
                self.status = status
            if previous_epoch and previous_epoch != bridge_epoch:
                # Revoke the old lease and publish with the newly observed epoch.
                self.set_readiness(bridge_ready=False, lowstate_ready=False)
            if self.transport_mode == CONTROL_TRANSPORT_UDP:
                with self.transport_lock:
                    pending = self._datagram_sync_pending
                    acknowledged = bool(
                        pending is not None
                        and pending[0] == bridge_epoch
                        and command_ack.get("source_id") == self.source_id
                        and command_ack.get("seq") == pending[1]
                        and command_ack.get("type") == "stop"
                    )
                    if acknowledged:
                        self._datagram_sync_epoch = bridge_epoch
                        self._datagram_sync_required = False
                        self._datagram_sync_pending = None
                    synchronized = (
                        not self._datagram_sync_required
                        and self._datagram_sync_epoch == bridge_epoch
                    )
                if not synchronized:
                    # Stop is the only Bridge command allowed to take ownership
                    # from a previous dashboard source.  It never creates a
                    # lease, arms control, holds deadman, or resumes motion.
                    # Keep readiness revoked until a later authenticated status
                    # acknowledges this exact source, sequence and stop type.
                    with self.transport_lock:
                        self.status = {
                            **self.status,
                            "ready": False,
                            "connected": False,
                            "available": False,
                            "message": "signed Go2 bridge command handoff waiting",
                        }
                    self.set_readiness(bridge_ready=False, lowstate_ready=False)
                    with self.transport_lock:
                        pending = self._datagram_sync_pending
                        should_send = (
                            pending is None
                            or pending[0] != bridge_epoch
                            or now - pending[2] >= 0.50
                        )
                    if should_send:
                        sent = self._publish_outputs_result(
                            [
                                {
                                    "type": "stop",
                                    "reason": "dashboard_transport_synchronized",
                                    "velocity": {
                                        "vx": 0.0,
                                        "vy": 0.0,
                                        "wz": 0.0,
                                    },
                                    "created_at": now,
                                }
                            ]
                        )
                        with self.transport_lock:
                            self._datagram_sync_required = True
                            self._datagram_sync_pending = (
                                (bridge_epoch, self.bridge_seq, now) if sent else None
                            )
                    return
            self.set_readiness(
                bridge_ready=bridge_ready,
                lowstate_ready=lowstate_ready,
            )

    @staticmethod
    def status_telemetry(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate the optional bounded telemetry projection on signed status."""

        telemetry = payload.get("telemetry")
        if telemetry is None:
            return {}
        if not isinstance(telemetry, Mapping) or set(telemetry) - {"battery", "joints"}:
            raise ControlProtocolError("bridge telemetry is invalid")
        battery = telemetry.get("battery")
        projected_battery: Dict[str, float | int] = {}
        if battery is not None:
            if not isinstance(battery, Mapping) or set(battery) - {
                "battery_soc",
                "battery_current_ma",
                "power_v",
                "power_a",
            }:
                raise ControlProtocolError("bridge battery telemetry is invalid")
            bounds = {
                "battery_soc": (0.0, 100.0),
                "battery_current_ma": (-100_000.0, 100_000.0),
                "power_v": (0.0, 100.0),
                "power_a": (-100.0, 100.0),
            }
            for key, value in battery.items():
                lower, upper = bounds[key]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not lower <= float(value) <= upper
                ):
                    raise ControlProtocolError("bridge battery telemetry is invalid")
                projected_battery[key] = (
                    int(value)
                    if key.endswith(("soc", "_ma"))
                    else round(float(value), 3)
                )

        joints = telemetry.get("joints")
        projected_joints: Dict[str, Any] = {}
        if joints is not None:
            if not isinstance(joints, Mapping) or set(joints) - {
                "position_rad",
                "imu_rpy_rad",
                "seq",
            }:
                raise ControlProtocolError("bridge joint telemetry is invalid")
            positions = joints.get("position_rad")
            sequence = joints.get("seq")
            if (
                not isinstance(positions, list)
                or len(positions) != len(GO2_JOINT_ORDER)
                or isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or not 0 <= sequence < 2_147_483_647
            ):
                raise ControlProtocolError("bridge joint telemetry is invalid")
            safe_positions: List[float] = []
            for joint_name, value in zip(GO2_JOINT_ORDER, positions):
                lower, upper = GO2_JOINT_LIMITS[joint_name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not lower <= float(value) <= upper
                ):
                    raise ControlProtocolError("bridge joint telemetry is invalid")
                safe_positions.append(round(float(value), 6))
            imu_rpy = joints.get("imu_rpy_rad")
            safe_imu: List[float] | None = None
            if imu_rpy is not None:
                if (
                    not isinstance(imu_rpy, list)
                    or len(imu_rpy) != 3
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                        for value in imu_rpy
                    )
                ):
                    raise ControlProtocolError("bridge joint telemetry is invalid")
                safe_imu = [round(float(value), 6) for value in imu_rpy]
            projected_joints = {
                "position_rad": safe_positions,
                "imu_rpy_rad": safe_imu,
                "seq": sequence,
            }

        projected: Dict[str, Any] = {}
        if projected_battery:
            projected["battery"] = projected_battery
        if projected_joints:
            projected["joints"] = projected_joints
        return projected

    def joint_state_snapshot(self) -> Dict[str, Any] | None:
        """Project fresh authenticated bridge joints for the read-only model."""

        now = time.monotonic()
        with self.transport_lock:
            status = dict(self.status)
            received = self.status_received
        status_age = max(0.0, now - received) if received > 0.0 else None
        lowstate_age_ms = status.get("lowstate_age_ms")
        telemetry = status.get("telemetry")
        joints = telemetry.get("joints") if isinstance(telemetry, Mapping) else None
        fresh = (
            status.get("authenticated") is True
            and status_age is not None
            and status_age <= self.status_timeout_s
            and not isinstance(lowstate_age_ms, bool)
            and isinstance(lowstate_age_ms, (int, float))
            and math.isfinite(float(lowstate_age_ms))
            and 0.0 <= float(lowstate_age_ms) <= self.lowstate_timeout_s * 1_000.0
            and isinstance(joints, Mapping)
        )
        if not fresh:
            return None
        age_s = max(status_age, float(lowstate_age_ms) / 1_000.0)
        return go2_joint_state_payload(
            topic="bridge://go2/lowstate/joints",
            type_name="unitree_go/msg/LowState",
            positions=joints.get("position_rad"),
            updated_at=now - age_s,
            now=now,
            stale_after_s=self.lowstate_timeout_s,
            seq=int(joints.get("seq", 0)),
            source_order="unitree_lowstate",
            imu_rpy_rad=joints.get("imu_rpy_rad"),
        )

    def battery_sensor_snapshot(self) -> Dict[str, Any] | None:
        """Project fresh authenticated bridge battery data as one sensor."""

        now = time.monotonic()
        with self.transport_lock:
            status = dict(self.status)
            received = self.status_received
        status_age = max(0.0, now - received) if received > 0.0 else None
        lowstate_age_ms = status.get("lowstate_age_ms")
        telemetry = status.get("telemetry")
        battery = (
            telemetry.get("battery") if isinstance(telemetry, Mapping) else None
        )
        fresh = (
            status.get("authenticated") is True
            and status_age is not None
            and status_age <= self.status_timeout_s
            and not isinstance(lowstate_age_ms, bool)
            and isinstance(lowstate_age_ms, (int, float))
            and math.isfinite(float(lowstate_age_ms))
            and 0.0
            <= float(lowstate_age_ms)
            <= self.lowstate_timeout_s * 1_000.0
            and isinstance(battery, Mapping)
            and "battery_soc" in battery
        )
        if not fresh:
            return None
        age_s = max(status_age, float(lowstate_age_ms) / 1_000.0)
        return {
            "topic": "bridge://go2/lowstate/battery",
            "type": "unitree_go/msg/LowState",
            "category": "battery",
            "state": "ok",
            "age_s": round(age_s, 3),
            "hz": None,
            "samples": 1,
            "values": dict(battery),
            "transport": self.transport_mode,
        }

    def set_readiness(
        self,
        *,
        bridge_ready: bool,
        lowstate_ready: bool,
    ) -> None:
        with self.operation_lock:
            try:
                self.manager.set_readiness(
                    bridge_ready=bridge_ready,
                    lowstate_ready=lowstate_ready,
                )
            except ControlClosed:
                return
            self.flush_outputs()

    def set_unready(self, message: str) -> None:
        with self.operation_lock:
            with self.transport_lock:
                if self.transport_mode == CONTROL_TRANSPORT_UDP:
                    self._datagram_sync_required = True
                    self._datagram_sync_epoch = ""
                    self._datagram_sync_pending = None
                self.status_received = 0.0
                self.status = {
                    "state": "error",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "authenticated": False,
                    "message": str(message)[:240],
                }
            self.set_readiness(bridge_ready=False, lowstate_ready=False)

    def update_staleness_locked(self, now: float) -> bool:
        """Revoke readiness when the authenticated status receipt is stale.

        The caller owns ``operation_lock`` so navigation reconciliation can run
        immediately before this operation and before any manager output drains.
        """

        with self.transport_lock:
            status_received = self.status_received
            stale = (
                status_received <= 0.0
                or now - status_received > self.status_timeout_s
            )
            if stale and status_received > 0.0:
                if self.transport_mode == CONTROL_TRANSPORT_UDP:
                    self._datagram_sync_required = True
                    self._datagram_sync_epoch = ""
                    self._datagram_sync_pending = None
                self.status = {
                    **self.status,
                    "state": "stale",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "message": "signed Go2 bridge status is stale",
                }
                self.status_received = 0.0
        if stale:
            self.set_readiness(bridge_ready=False, lowstate_ready=False)
        return stale

    def manager_tick_locked(self) -> List[Dict[str, Any]]:
        """Advance manager timers without applying navigation policy."""

        try:
            return self.manager.tick()
        except ControlClosed:
            return []

    @staticmethod
    def bridge_envelope(
        output: Dict[str, Any],
        *,
        source_id: str,
        sequence: int,
        bridge_epoch: str,
    ) -> Dict[str, Any]:
        """Translate one manager output into the watchdog's narrow contract."""

        kind = output.get("type")
        envelope: Dict[str, Any] = {
            "type": kind,
            "source_id": source_id,
            "seq": sequence,
            "bridge_epoch": bridge_epoch,
        }
        if kind == "drive":
            velocity = output.get("velocity")
            if not isinstance(velocity, dict):
                raise ValueError("drive output has no velocity")
            values = {
                "linear_x": velocity.get("vx"),
                "linear_y": velocity.get("vy"),
                "angular_z": velocity.get("wz"),
            }
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in values.values()
            ):
                raise ValueError("drive output velocity is invalid")
            envelope.update(
                {
                    "deadman": True,
                    **{name: float(value) for name, value in values.items()},
                }
            )
            return envelope
        if kind == "stop":
            envelope["reason"] = str(output.get("reason", "dashboard stop"))[:160]
            return envelope
        if kind == "action":
            action_name = output.get("action")
            if not isinstance(action_name, str) or not action_name:
                raise ValueError("action output has no action name")
            envelope["action_id"] = action_name
            return envelope
        raise ValueError("unknown control manager output")

    def _publish_outputs_result(
        self,
        outputs: List[Dict[str, Any]],
        *,
        allow_shutdown: bool = False,
    ) -> bool:
        if not outputs:
            return True
        with self.transport_lock:
            if self.shutdown_started and not allow_shutdown:
                return False
            publisher = self.command_publisher
            key = self.bridge_key
            bridge_epoch = self.bridge_epoch
            if publisher is None or key is None or not bridge_epoch:
                return False
            try:
                for output in outputs:
                    self.bridge_seq += 1
                    envelope = self.bridge_envelope(
                        output,
                        source_id=self.source_id,
                        sequence=self.bridge_seq,
                        bridge_epoch=bridge_epoch,
                    )
                    message = String()
                    message.data = encode_signed(envelope, key)
                    publisher.publish(message)
                return True
            except (ControlProtocolError, TypeError, ValueError) as exc:
                self.status = {
                    "state": "error",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "message": f"control command publish rejected: {exc}",
                }
                try:
                    self.manager.set_readiness(
                        bridge_ready=False,
                        lowstate_ready=False,
                    )
                except ControlClosed:
                    pass
                return False
            except Exception as exc:
                self.status = {
                    "state": "error",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "message": f"control command transport failed: {exc}",
                }
                try:
                    self.manager.set_readiness(
                        bridge_ready=False,
                        lowstate_ready=False,
                    )
                except ControlClosed:
                    pass
                return False

    def publish_outputs(
        self,
        outputs: List[Dict[str, Any]],
        *,
        allow_shutdown: bool = False,
    ) -> None:
        self._publish_outputs_result(outputs, allow_shutdown=allow_shutdown)

    def flush_outputs(self) -> None:
        with self.operation_lock:
            self.publish_outputs(self.manager.drain_outputs())

    def raw_snapshot(self) -> Dict[str, Any]:
        """Return manager and signed-transport state without target/Nav overlays."""

        with self.operation_lock:
            snapshot = self.manager.snapshot()
            self.flush_outputs()
            snapshot = self.manager.snapshot()
            with self.transport_lock:
                bridge = dict(self.status)
                received = self.status_received
                transport_configured = bool(
                    self.bridge_key is not None
                    and self.command_publisher is not None
                    and self.status_subscription is not None
                    and self.timer is not None
                    and (
                        self.transport_mode != CONTROL_TRANSPORT_UDP
                        or (
                            self._datagram_endpoint is not None
                            and self._datagram_thread is not None
                            and self._datagram_thread.is_alive()
                        )
                    )
                )
        bridge["transport"] = self.transport_mode
        bridge["status_age_s"] = (
            None
            if received <= 0.0
            else round(max(0.0, time.monotonic() - received), 3)
        )
        snapshot["bridge"] = bridge
        snapshot["transport_configured"] = transport_configured
        return snapshot

    def stop_for_target_change(self) -> None:
        """Latch and publish the existing target-change software stop."""

        with self.operation_lock:
            try:
                self.manager.emergency_stop("robot_target_changed")
            except ControlClosed:
                pass
            self.flush_outputs()

    def shutdown(self) -> None:
        """Close once and publish the manager's final signed stop."""

        endpoint: ConnectedControlDatagram | None = None
        receiver: threading.Thread | None = None
        with self.operation_lock:
            with self.transport_lock:
                if self.shutdown_started:
                    return
                self.shutdown_started = True
                self.manager.close()
                outputs = self.manager.drain_outputs()
                self.publish_outputs(outputs, allow_shutdown=True)
                self._datagram_stop.set()
                endpoint = self._datagram_endpoint
                receiver = self._datagram_thread
                self._datagram_endpoint = None
        if endpoint is not None:
            endpoint.close()
        if receiver is not None and receiver is not threading.current_thread():
            receiver.join(timeout=0.5)


__all__ = [
    "CONTROL_COMMAND_TOPIC",
    "CONTROL_STATUS_TOPIC",
    "ControlTransport",
]
