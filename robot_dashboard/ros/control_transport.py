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
        )
        return bridge_ready, lowstate_ready, bridge_epoch

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
        except (ControlProtocolError, TypeError, ValueError) as exc:
            self.set_unready(f"rejected bridge status: {exc}")
            return

        now = time.monotonic()
        available = bridge_ready and lowstate_ready
        status = dict(payload)
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
                self.bridge_epoch = bridge_epoch
                self.status_received = now
                self.status = status
            if previous_epoch and previous_epoch != bridge_epoch:
                # Revoke the old lease and publish with the newly observed epoch.
                self.set_readiness(bridge_ready=False, lowstate_ready=False)
            self.set_readiness(
                bridge_ready=bridge_ready,
                lowstate_ready=lowstate_ready,
            )

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

    def publish_outputs(
        self,
        outputs: List[Dict[str, Any]],
        *,
        allow_shutdown: bool = False,
    ) -> None:
        if not outputs:
            return
        with self.transport_lock:
            if self.shutdown_started and not allow_shutdown:
                return
            publisher = self.command_publisher
            key = self.bridge_key
            bridge_epoch = self.bridge_epoch
            if publisher is None or key is None or not bridge_epoch:
                return
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
