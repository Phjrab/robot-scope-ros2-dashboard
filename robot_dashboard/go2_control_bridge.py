"""Standalone ROS 2 watchdog bridge for Unitree Go2 sport requests.

The web process never publishes the sport request topic directly. It sends
signed, allowlisted commands to this separate process. If browser or web
process updates stop, the 200 ms command-age limit plus the next 50 ms timer
cycle dispatches StopMove nominally within 250 ms.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
try:
    from rclpy.signals import SignalHandlerOptions
except ImportError:  # ROS 2 Foxy has no SignalHandlerOptions.
    SignalHandlerOptions = None  # type: ignore[assignment]
from std_msgs.msg import String
from unitree_api.msg import Request
from unitree_go.msg import LowState
try:
    from unitree_go.msg import SportModeState
except ImportError:  # Preserve operation with an older Unitree message package.
    SportModeState = None  # type: ignore[assignment]

from .control_protocol import (
    ControlProtocolError,
    decode_signed,
    encode_signed,
    shared_key,
)
from .control_datagram import (
    CONTROL_TRANSPORT_ROS,
    CONTROL_TRANSPORT_UDP,
    ConnectedControlDatagram,
    ControlDatagramConfig,
    ControlDatagramError,
    DatagramStringPublisher,
    control_transport_mode,
)
from .go2_bridge import (
    API_STOP_MOVE,
    BridgeCommandError,
    Go2BridgeCore,
    SPORT_MODE_STATE_TOPICS,
    SportModeStateObservation,
    SportRequest,
    SportRequestEvidence,
    classify_sport_request_publishers,
    runtime_release_commit,
)
from .serializers import (
    extract_go2_battery,
    extract_go2_imu_rpy,
    extract_go2_joint_positions,
)


COMMAND_TOPIC = "/robot_scope/control/command"
STATUS_TOPIC = "/robot_scope/control/status"
SPORT_REQUEST_TOPIC = "/api/sport/request"
LOWSTATE_TOPICS = ("/lowstate", "/lf/lowstate")


class Go2ControlBridge(Node):
    def __init__(
        self,
        profile: dict[str, Any],
        key: bytes,
        *,
        datagram_config: ControlDatagramConfig | None = None,
    ) -> None:
        super().__init__("robot_scope_go2_control_bridge")
        control = profile.get("control", {})
        configured_lowstate = str(control.get("lowstate_topic", "/lowstate"))
        if configured_lowstate not in LOWSTATE_TOPICS:
            raise ValueError("control.lowstate_topic is not allowlisted")
        self._lowstate_topic = configured_lowstate
        configured_sport_mode_state = str(
            control.get("sport_mode_state_topic", "/sportmodestate")
        )
        if configured_sport_mode_state not in SPORT_MODE_STATE_TOPICS:
            raise ValueError("control.sport_mode_state_topic is not allowlisted")
        self._key = key
        self._core = Go2BridgeCore(
            max_linear_x=control.get("max_linear_x", 0.30),
            max_linear_y=control.get("max_linear_y", 0.20),
            max_angular_z=control.get("max_angular_z", 0.50),
            command_timeout_s=control.get("bridge_command_timeout_s", 0.20),
            telemetry_timeout_s=control.get("telemetry_timeout_s", 0.50),
            source_timeout_s=control.get("lease_timeout_s", 2.0),
            expected_bare_sport_publishers=control.get(
                "expected_bare_sport_publishers", 0
            ),
        )
        self._sport_mode_state = SportModeStateObservation(
            topic=configured_sport_mode_state,
            stale_after_s=self._core.telemetry_timeout_s,
        )
        self._sport_mode_state_invalid = False
        self._callback_group = MutuallyExclusiveCallbackGroup()
        self._last_lowstate = 0.0
        self._lowstate_battery: dict[str, Any] = {}
        self._lowstate_joints: dict[str, Any] = {}
        self._lowstate_seq = 0
        self._last_status = 0.0
        self._status_update_requested = False
        self._closing = False
        # ROS callbacks run in executor threads while signal-driven shutdown
        # runs in the main thread. Serialize every core mutation and sport
        # publish so no in-flight MOVE can appear after the final StopMove.
        self._operation_lock = threading.RLock()
        self._datagram_endpoint: ConnectedControlDatagram | None = None
        self._datagram_stop = threading.Event()
        self._datagram_thread: threading.Thread | None = None
        self._command_transport_failed = False
        self._status_transport_failed = False
        self._request_evidence = SportRequestEvidence()
        self._release_commit = runtime_release_commit()

        reliable = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        best_effort = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._sport_publisher = self.create_publisher(
            Request,
            SPORT_REQUEST_TOPIC,
            reliable,
            callback_group=self._callback_group,
        )
        if datagram_config is None:
            self._status_publisher = self.create_publisher(
                String,
                STATUS_TOPIC,
                reliable,
                callback_group=self._callback_group,
            )
            self._command_subscription = self.create_subscription(
                String,
                COMMAND_TOPIC,
                self._command_callback,
                reliable,
                callback_group=self._callback_group,
            )
        else:
            endpoint = ConnectedControlDatagram(datagram_config)
            receiver = threading.Thread(
                target=self._receive_datagram_commands,
                args=(endpoint,),
                name="control-datagram-command",
                daemon=True,
            )
            self._datagram_endpoint = endpoint
            self._datagram_thread = receiver
            self._status_publisher = DatagramStringPublisher(endpoint)
            self._command_subscription = endpoint
        self._lowstate_subscription = (
            self.create_subscription(
                LowState,
                self._lowstate_topic,
                self._lowstate_callback,
                best_effort,
                callback_group=self._callback_group,
            )
        )
        self._sport_mode_state_subscription = (
            self.create_subscription(
                SportModeState,
                self._sport_mode_state.topic,
                self._sport_mode_state_callback,
                best_effort,
                callback_group=self._callback_group,
            )
            if SportModeState is not None
            else None
        )
        if SportModeState is None:
            self.get_logger().warning(
                "Unitree SportModeState message is unavailable; status will remain waiting"
            )
        self._timer = self.create_timer(
            0.05,
            self._tick,
            callback_group=self._callback_group,
        )
        self.get_logger().info(
            "Go2 control watchdog ready; waiting for exactly one "
            f"{self._lowstate_topic} publisher, one bridge-owned sport publisher, "
            "no foreign named sport publishers, "
            f"{self._core.expected_bare_sport_publishers} trusted bare Unitree "
            "sport publishers, and one sport subscriber"
        )
        if self._datagram_thread is not None:
            self._datagram_thread.start()

    def _receive_datagram_commands(
        self, endpoint: ConnectedControlDatagram
    ) -> None:
        while not self._datagram_stop.is_set():
            try:
                encoded = endpoint.receive_text()
            except ControlDatagramError as exc:
                with self._operation_lock:
                    if not self._closing:
                        self._core.force_stop(f"rejected command datagram: {exc}")
                self.get_logger().warning(str(exc))
                continue
            except OSError as exc:
                if self._datagram_stop.is_set():
                    return
                with self._operation_lock:
                    if not self._closing:
                        self._core.force_stop("command datagram failed")
                if not self._command_transport_failed:
                    self.get_logger().error(f"command datagram failed: {exc}")
                self._command_transport_failed = True
                if self._datagram_stop.wait(0.2):
                    return
                continue
            if encoded is None:
                continue
            if self._command_transport_failed:
                self.get_logger().info("command datagram transport recovered")
                self._command_transport_failed = False
            message = String()
            message.data = encoded
            self._command_callback(message)

    def _lowstate_callback(self, message: LowState) -> None:
        self._last_lowstate = time.monotonic()
        positions = extract_go2_joint_positions(
            message,
            "unitree_go/msg/LowState",
        )
        imu_rpy = extract_go2_imu_rpy(message, "unitree_go/msg/LowState")
        self._lowstate_seq = (self._lowstate_seq + 1) % 2_147_483_647
        self._lowstate_joints = (
            {
                "position_rad": positions,
                "imu_rpy_rad": imu_rpy,
                "seq": self._lowstate_seq,
            }
            if positions is not None
            else {}
        )
        self._lowstate_battery = extract_go2_battery(
            message,
            "unitree_go/msg/LowState",
        )

    def _sport_mode_state_callback(self, message: Any) -> None:
        try:
            self._sport_mode_state.observe(message, now=time.monotonic())
        except (TypeError, ValueError) as exc:
            if not self._sport_mode_state_invalid:
                self.get_logger().warning(f"rejected SportModeState sample: {exc}")
            self._sport_mode_state_invalid = True
            return
        self._sport_mode_state_invalid = False

    def _command_callback(self, message: String) -> None:
        with self._operation_lock:
            if self._closing:
                return
            self._accept_command(message)

    def _accept_command(self, message: String) -> None:
        now = time.monotonic()
        try:
            payload = decode_signed(message.data, self._key, max_age_s=1.5)
            issued_at_ms = payload.get("issued_at_ms")
            transport_age_s = max(
                0.0,
                time.time() - float(issued_at_ms) / 1_000.0,
            )
            self._core.accept(
                payload,
                now=now,
                transport_age_s=transport_age_s,
            )
            # Publish signed acceptance on the next existing 50 ms tick while
            # commands are arriving. Idle status retains the 250 ms cadence;
            # command selection and watchdog timing are unchanged.
            self._status_update_requested = True
        except (ControlProtocolError, BridgeCommandError, TypeError, ValueError) as exc:
            self._core.force_stop(f"rejected command: {exc}")
            self.get_logger().warning(str(exc))

    def _environment(
        self, now: float
    ) -> tuple[float | None, int, int, int, int, int, int]:
        lowstate_age = (
            None if self._last_lowstate <= 0 else max(0.0, now - self._last_lowstate)
        )
        # One explicitly configured alias avoids collapsing publishers from
        # two different global LowState topics into a false single-robot view.
        lowstate_publishers = self.count_publishers(self._lowstate_topic)
        subscribers = self.count_subscribers(SPORT_REQUEST_TOPIC)
        publisher_counts = classify_sport_request_publishers(
            self.get_publishers_info_by_topic(SPORT_REQUEST_TOPIC),
            own_node_name=self.get_name(),
            own_node_namespace=self.get_namespace(),
        )
        return (
            lowstate_age,
            lowstate_publishers,
            subscribers,
            publisher_counts["sport_publishers"],
            publisher_counts["own_sport_publishers"],
            publisher_counts["foreign_named_sport_publishers"],
            publisher_counts["bare_unitree_sport_publishers"],
        )

    def _publish_request(self, request: SportRequest) -> None:
        message = Request()
        message.header.identity.api_id = int(request.api_id)
        message.parameter = request.parameter
        self._sport_publisher.publish(message)
        self._request_evidence.record(request, now=time.monotonic())

    def _publish_status(
        self,
        now: float,
        lowstate_age: float | None,
        lowstate_publishers: int,
        sport_subscribers: int,
        sport_publishers: int,
        own_sport_publishers: int,
        foreign_named_sport_publishers: int,
        bare_unitree_sport_publishers: int,
    ) -> None:
        snapshot = self._core.snapshot(
            now=now,
            lowstate_age_s=lowstate_age,
            lowstate_publishers=lowstate_publishers,
            sport_subscribers=sport_subscribers,
            sport_publishers=sport_publishers,
            own_sport_publishers=own_sport_publishers,
            foreign_named_sport_publishers=foreign_named_sport_publishers,
            bare_unitree_sport_publishers=bare_unitree_sport_publishers,
        )
        snapshot.update(
            {
                "type": "bridge_status",
                "bridge_pid": os.getpid(),
                "command_topic": COMMAND_TOPIC,
                "request_topic": SPORT_REQUEST_TOPIC,
                "release_commit": self._release_commit,
                "lowstate_topic": self._lowstate_topic,
                "sport_mode_state": self._sport_mode_state.snapshot(now=now),
                "motion_observation": self._sport_mode_state.motion_snapshot(
                    now=now,
                    producer_generation=self._core.bridge_epoch,
                    release_commit=self._release_commit,
                ),
                "request_evidence": self._request_evidence.snapshot(now=now),
                "telemetry": {
                    "battery": dict(self._lowstate_battery),
                    "joints": dict(self._lowstate_joints),
                },
            }
        )
        message = String()
        message.data = encode_signed(snapshot, self._key)
        try:
            self._status_publisher.publish(message)
        except (ControlDatagramError, OSError) as exc:
            # Loss of the management Wi-Fi must not terminate the local ROS
            # watchdog. Force a StopMove for the next tick and keep retrying the
            # bounded status envelope on the same fixed socket.
            self._core.force_stop("bridge status transport failed")
            if not self._status_transport_failed:
                self.get_logger().error(f"bridge status transport failed: {exc}")
            self._status_transport_failed = True
            return
        if self._status_transport_failed:
            self.get_logger().info("bridge status transport recovered")
            self._status_transport_failed = False

    def _tick(self) -> None:
        with self._operation_lock:
            if self._closing:
                return
            self._tick_locked()

    def _tick_locked(self) -> None:
        now = time.monotonic()
        (
            lowstate_age,
            lowstate_publishers,
            sport_subscribers,
            sport_publishers,
            own_sport_publishers,
            foreign_named_sport_publishers,
            bare_unitree_sport_publishers,
        ) = self._environment(now)
        for request in self._core.tick(
            now=now,
            lowstate_age_s=lowstate_age,
            lowstate_publishers=lowstate_publishers,
            sport_subscribers=sport_subscribers,
            sport_publishers=sport_publishers,
            own_sport_publishers=own_sport_publishers,
            foreign_named_sport_publishers=foreign_named_sport_publishers,
            bare_unitree_sport_publishers=bare_unitree_sport_publishers,
        ):
            self._publish_request(request)
        if self._status_update_requested or now - self._last_status >= 0.25:
            self._publish_status(
                now,
                lowstate_age,
                lowstate_publishers,
                sport_subscribers,
                sport_publishers,
                own_sport_publishers,
                foreign_named_sport_publishers,
                bare_unitree_sport_publishers,
            )
            self._last_status = now
            self._status_update_requested = False

    def stop_safely(self) -> None:
        endpoint: ConnectedControlDatagram | None = None
        receiver: threading.Thread | None = None
        with self._operation_lock:
            if self._closing:
                return
            self._closing = True
            self._timer.cancel()
            self._core.force_stop("bridge shutdown")
            for _ in range(3):
                try:
                    self._publish_request(
                        SportRequest(API_STOP_MOVE, "", "shutdown")
                    )
                except Exception as exc:
                    self.get_logger().error(
                        f"StopMove publish failed during shutdown: {exc}"
                    )
                time.sleep(0.04)
            self._datagram_stop.set()
            endpoint = self._datagram_endpoint
            receiver = self._datagram_thread
            self._datagram_endpoint = None
        if endpoint is not None:
            endpoint.close()
        if receiver is not None and receiver is not threading.current_thread():
            receiver.join(timeout=0.5)


def load_profile(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read control profile: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("control profile must be a JSON object")
    return value


def acquire_process_lock() -> Any:
    configured = os.environ.get("ROBOT_SCOPE_CONTROL_LOCK_FILE", "")
    path = Path(configured).expanduser() if configured else Path(
        f"/tmp/robot-scope-go2-control-{os.getuid()}.lock"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another Go2 control bridge is already running") from exc
    return handle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Robot Scope standalone Go2 control watchdog bridge"
    )
    parser.add_argument("--profile", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = load_profile(args.profile)
    control = profile.get("control", {})
    if not isinstance(control, dict) or not bool(control.get("enabled", False)):
        raise SystemExit("control is disabled in the selected profile")
    if os.environ.get("ROBOT_SCOPE_CONTROL_ENABLED") != "1":
        raise SystemExit("ROBOT_SCOPE_CONTROL_ENABLED=1 is required")
    try:
        key = shared_key(os.environ.get("ROBOT_SCOPE_CONTROL_BRIDGE_KEY", ""))
        process_lock = acquire_process_lock()
        transport_mode = control_transport_mode(os.environ)
        datagram_config = (
            ControlDatagramConfig.from_environment(os.environ)
            if transport_mode == CONTROL_TRANSPORT_UDP
            else None
        )
        if transport_mode not in {CONTROL_TRANSPORT_ROS, CONTROL_TRANSPORT_UDP}:
            raise ControlDatagramError("control transport is invalid")
    except (ControlProtocolError, ControlDatagramError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc

    # rclpy's default SIGINT handler shuts the ROS context down before
    # ``executor.spin()`` returns.  That makes the shutdown StopMove publishes
    # fail with "publisher's context is invalid".  Keep the context alive,
    # interrupt the spin ourselves, then publish the final stops before calling
    # ``rclpy.shutdown()``.
    shutdown_requested = False

    def request_shutdown(_signum: int, _frame: Any) -> None:
        nonlocal shutdown_requested
        if shutdown_requested:
            return
        shutdown_requested = True
        raise KeyboardInterrupt

    if SignalHandlerOptions is None:
        rclpy.init(args=None)
    else:
        rclpy.init(args=None, signal_handler_options=SignalHandlerOptions.NO)
    previous_sigint = signal.signal(signal.SIGINT, request_shutdown)
    previous_sigterm = signal.signal(signal.SIGTERM, request_shutdown)
    node: Go2ControlBridge | None = None
    executor: MultiThreadedExecutor | None = None
    try:
        node = Go2ControlBridge(profile, key, datagram_config=datagram_config)
        executor = MultiThreadedExecutor(num_threads=2)
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.stop_safely()
        if executor is not None:
            try:
                executor.shutdown(timeout_sec=1.0)
            except Exception:
                pass
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        process_lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Robot Scope control bridge failed: {exc}", file=sys.stderr)
        raise
