import importlib
import importlib.machinery
import importlib.util
import json
import math
import queue
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock


def _install_ros_stubs():
    class CallbackGroup:
        pass

    class QoSProfile:
        def __init__(self, **kwargs):
            self.history = kwargs.get("history")
            self.depth = kwargs.get("depth")
            self.reliability = kwargs.get("reliability")
            self.durability = kwargs.get("durability")

    class HistoryPolicy:
        KEEP_LAST = "keep_last"

    class ReliabilityPolicy:
        RELIABLE = "reliable"

    class DurabilityPolicy:
        VOLATILE = "volatile"

    class String:
        def __init__(self):
            self.data = ""

    rclpy = types.ModuleType("rclpy")
    rclpy.__spec__ = importlib.machinery.ModuleSpec("rclpy", loader=None)
    callback_groups = types.ModuleType("rclpy.callback_groups")
    callback_groups.MutuallyExclusiveCallbackGroup = CallbackGroup
    qos = types.ModuleType("rclpy.qos")
    qos.DurabilityPolicy = DurabilityPolicy
    qos.HistoryPolicy = HistoryPolicy
    qos.QoSProfile = QoSProfile
    qos.ReliabilityPolicy = ReliabilityPolicy
    std_msgs = types.ModuleType("std_msgs")
    std_msgs.__path__ = []
    std_msgs_msg = types.ModuleType("std_msgs.msg")
    std_msgs_msg.String = String
    sys.modules.update(
        {
            "rclpy": rclpy,
            "rclpy.callback_groups": callback_groups,
            "rclpy.qos": qos,
            "std_msgs": std_msgs,
            "std_msgs.msg": std_msgs_msg,
        }
    )


existing_rclpy = sys.modules.get("rclpy")
if existing_rclpy is not None and not getattr(existing_rclpy, "__file__", None):
    # Another offline ROS test may already have installed a deliberately small
    # stub. Replace it with this test's QoS-aware stub and reload the component
    # so full-suite order cannot weaken the endpoint/QoS assertions below.
    _RCLPY_AVAILABLE = False
else:
    try:
        _RCLPY_AVAILABLE = importlib.util.find_spec("rclpy") is not None
    except (ImportError, ValueError):
        _RCLPY_AVAILABLE = False

if not _RCLPY_AVAILABLE:
    _install_ros_stubs()

import robot_dashboard.ros.control_transport as control_transport_module


if not _RCLPY_AVAILABLE:
    control_transport_module = importlib.reload(control_transport_module)

from robot_dashboard.control import ControlDisabled
from robot_dashboard.control_protocol import ControlProtocolError, decode_signed, encode_signed


ControlTransport = control_transport_module.ControlTransport
CONTROL_COMMAND_TOPIC = control_transport_module.CONTROL_COMMAND_TOPIC
CONTROL_STATUS_TOPIC = control_transport_module.CONTROL_STATUS_TOPIC
String = control_transport_module.String

KEY = "k" * 32
ROOT = Path(__file__).resolve().parents[1]


class FakePublisher:
    def __init__(self):
        self.messages = []
        self.failure = None

    def publish(self, message):
        if self.failure is not None:
            raise self.failure
        self.messages.append(message)


class FakeNode:
    def __init__(self):
        self.publisher = FakePublisher()
        self.publisher_calls = []
        self.subscription_calls = []
        self.timer_calls = []

    def create_publisher(self, message_type, topic, qos, *, callback_group):
        self.publisher_calls.append((message_type, topic, qos, callback_group))
        return self.publisher

    def create_subscription(
        self,
        message_type,
        topic,
        callback,
        qos,
        *,
        callback_group,
    ):
        subscription = object()
        self.subscription_calls.append(
            (message_type, topic, callback, qos, callback_group, subscription)
        )
        return subscription

    def create_timer(self, interval, callback, *, callback_group):
        timer = object()
        self.timer_calls.append((interval, callback, callback_group, timer))
        return timer


class FakeDatagramEndpoint:
    instances = []

    def __init__(self, config):
        self.config = config
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = False
        self.__class__.instances.append(self)

    def send_text(self, value):
        if self.closed:
            raise OSError("closed")
        self.sent.append(value)

    def receive_text(self):
        if self.closed:
            raise OSError("closed")
        try:
            value = self.incoming.get(timeout=0.02)
        except queue.Empty:
            return None
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed = True


class ControlTransportTests(unittest.TestCase):
    def profile(self, **control_overrides):
        control = {
            "enabled": True,
            "bridge_status_timeout_s": 0.75,
            "telemetry_timeout_s": 0.50,
            "expected_bare_sport_publishers": 0,
        }
        control.update(control_overrides)
        return {"name": "Unitree Go2", "robot_type": "go2", "control": control}

    def transport(self, **control_overrides):
        return ControlTransport(
            self.profile(**control_overrides),
            environ={
                "ROBOT_SCOPE_CONTROL_ENABLED": "1",
                "ROBOT_SCOPE_CONTROL_BRIDGE_KEY": KEY,
            },
        )

    @staticmethod
    def status_payload(epoch="e" * 32, **overrides):
        payload = {
            "type": "bridge_status",
            "ready": True,
            "sport_subscribers": 1,
            "sport_publishers": 1,
            "own_sport_publishers": 1,
            "foreign_named_sport_publishers": 0,
            "bare_unitree_sport_publishers": 0,
            "expected_bare_sport_publishers": 0,
            "lowstate_publishers": 1,
            "bridge_epoch": epoch,
            "lowstate_age_ms": 10.0,
            "last_error": "",
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def request_evidence(**overrides):
        evidence = {
            "schema": "robot-scope.sport-request-evidence.v1",
            "scope": "bridge_process",
            "published_count": 2,
            "stop_count": 1,
            "move_count": 1,
            "zero_move_count": 1,
            "nonzero_move_count": 0,
            "malformed_move_count": 0,
            "action_count": 0,
            "other_count": 0,
            "last_api_id": 1008,
            "last_publish_age_ms": 20,
            "max_abs_linear_x": 0.0,
            "max_abs_linear_y": 0.0,
            "max_abs_angular_z": 0.0,
            "motion_run_id": 0,
            "motion_run_active": False,
            "motion_run_nonzero_move_count": 0,
            "motion_run_max_abs_linear_x": 0.0,
            "motion_run_max_abs_linear_y": 0.0,
            "motion_run_max_abs_angular_z": 0.0,
        }
        evidence.update(overrides)
        return evidence

    @staticmethod
    def sport_mode_state(**overrides):
        state = {
            "topic": "/sportmodestate",
            "mode": 5,
            "gait_type": 3,
            "velocity": [0.105, 0.0, -0.01],
            "error_code": 0,
            "age_ms": 25,
            "stale_after_ms": 500,
            "fresh": True,
        }
        state.update(overrides)
        return state

    def send_status(self, transport, epoch="e" * 32, **overrides):
        message = String()
        message.data = encode_signed(self.status_payload(epoch, **overrides), KEY)
        transport.status_callback(message)

    def ready_setup(self):
        transport = self.transport()
        node = FakeNode()
        timer_callback = lambda: None
        transport.setup(node, timer_callback)
        self.send_status(transport)
        return transport, node, timer_callback

    def test_setup_uses_only_fixed_signed_topics_qos_group_and_timer_callback(self):
        transport = self.transport()
        node = FakeNode()
        calls = []

        def facade_tick():
            calls.append("tick")

        transport.setup(node, facade_tick)

        self.assertEqual(node.publisher_calls[0][1], CONTROL_COMMAND_TOPIC)
        self.assertEqual(node.subscription_calls[0][1], CONTROL_STATUS_TOPIC)
        self.assertIs(node.subscription_calls[0][2].__self__, transport)
        self.assertEqual(node.timer_calls[0][0], 0.05)
        self.assertIs(node.timer_calls[0][1], facade_tick)
        self.assertIs(node.publisher_calls[0][3], node.subscription_calls[0][4])
        self.assertIs(node.publisher_calls[0][3], node.timer_calls[0][2])
        self.assertEqual(node.publisher_calls[0][2].depth, 10)
        node.timer_calls[0][1]()
        self.assertEqual(calls, ["tick"])

    def test_udp_setup_uses_no_ros_command_topics_and_accepts_only_signed_status(self):
        transport = ControlTransport(
            self.profile(),
            environ={
                "ROBOT_SCOPE_CONTROL_ENABLED": "1",
                "ROBOT_SCOPE_CONTROL_BRIDGE_KEY": KEY,
                "ROBOT_SCOPE_CONTROL_TRANSPORT": "udp",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST": "192.168.50.10",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST": "192.168.50.30",
            },
        )
        node = FakeNode()
        FakeDatagramEndpoint.instances.clear()
        with mock.patch.object(
            control_transport_module,
            "ConnectedControlDatagram",
            FakeDatagramEndpoint,
        ):
            transport.setup(node, lambda: None)
            endpoint = FakeDatagramEndpoint.instances[-1]
            endpoint.incoming.put(
                encode_signed(self.status_payload(), KEY)
            )
            deadline = time.monotonic() + 0.5
            while not transport.status.get("authenticated"):
                if time.monotonic() >= deadline:
                    self.fail("signed datagram status was not accepted")
                time.sleep(0.01)

            self.assertEqual(node.publisher_calls, [])
            self.assertEqual(node.subscription_calls, [])
            self.assertEqual(len(node.timer_calls), 1)
            self.assertTrue(transport.raw_snapshot()["transport_configured"])
            self.assertEqual(transport.raw_snapshot()["bridge"]["transport"], "udp")
            transport.shutdown()

        self.assertTrue(endpoint.closed)
        self.assertTrue(endpoint.sent)
        self.assertEqual(decode_signed(endpoint.sent[-1], KEY)["type"], "stop")
        self.assertFalse(
            any(
                thread.name == "control-datagram-status" and thread.is_alive()
                for thread in threading.enumerate()
            )
        )

    def test_udp_receiver_survives_transient_network_error_and_recovers_status(self):
        transport = ControlTransport(
            self.profile(),
            environ={
                "ROBOT_SCOPE_CONTROL_ENABLED": "1",
                "ROBOT_SCOPE_CONTROL_BRIDGE_KEY": KEY,
                "ROBOT_SCOPE_CONTROL_TRANSPORT": "udp",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST": "192.168.50.10",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST": "192.168.50.30",
            },
        )
        FakeDatagramEndpoint.instances.clear()
        with mock.patch.object(
            control_transport_module,
            "ConnectedControlDatagram",
            FakeDatagramEndpoint,
        ):
            transport.setup(FakeNode(), lambda: None)
            endpoint = FakeDatagramEndpoint.instances[-1]
            endpoint.incoming.put(OSError("network unreachable"))
            deadline = time.monotonic() + 0.5
            while transport.status.get("state") != "error":
                if time.monotonic() >= deadline:
                    self.fail("transient datagram error was not observed")
                time.sleep(0.01)

            endpoint.incoming.put(encode_signed(self.status_payload(), KEY))
            deadline = time.monotonic() + 1.0
            while not transport.status.get("authenticated"):
                if time.monotonic() >= deadline:
                    self.fail("signed status did not recover on the existing socket")
                time.sleep(0.01)

            self.assertTrue(transport.raw_snapshot()["transport_configured"])
            self.assertTrue(transport._datagram_thread.is_alive())
            transport.shutdown()

    def test_blank_key_and_invalid_expected_publisher_baseline_fail_closed(self):
        transport = ControlTransport(
            self.profile(),
            environ={"ROBOT_SCOPE_CONTROL_ENABLED": "1"},
        )
        self.assertIsNone(transport.bridge_key)
        self.assertEqual(transport.status["state"], "not_configured")
        self.assertFalse(transport.manager.snapshot()["ready"])
        with self.assertRaisesRegex(ValueError, "from 0 to 64"):
            self.transport(expected_bare_sport_publishers=True)

    def test_target_policy_is_facade_bound_and_defaults_fail_closed(self):
        transport = self.transport()
        self.assertFalse(transport.go2_target())
        with self.assertRaisesRegex(ControlDisabled, "not bound"):
            transport.ensure_target()

        calls = []
        transport.bind_target_policy(
            lambda: calls.append("ensure"),
            lambda: True,
        )
        transport.ensure_target()
        self.assertEqual(calls, ["ensure"])
        self.assertTrue(transport.go2_target())

        transport.bind_target_policy(lambda: None, lambda: 1 / 0)
        self.assertFalse(transport.go2_target())
        with self.assertRaisesRegex(ValueError, "must be callable"):
            transport.bind_target_policy(None, lambda: True)

    def test_status_readiness_rechecks_cardinality_lowstate_and_profile_baseline(self):
        payload = self.status_payload(
            sport_publishers=10,
            bare_unitree_sport_publishers=9,
            expected_bare_sport_publishers=9,
        )
        self.assertEqual(
            ControlTransport.status_readiness(
                payload,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=9,
            )[:2],
            (True, True),
        )
        foreign = dict(
            payload,
            foreign_named_sport_publishers=1,
            sport_publishers=11,
        )
        self.assertFalse(
            ControlTransport.status_readiness(
                foreign,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=9,
            )[0]
        )
        stale_lowstate = dict(payload, lowstate_age_ms=500.001)
        self.assertFalse(
            ControlTransport.status_readiness(
                stale_lowstate,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=9,
            )[1]
        )
        with self.assertRaisesRegex(ControlProtocolError, "does not match profile"):
            ControlTransport.status_readiness(
                payload,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=8,
            )

    def test_signed_request_evidence_is_validated_projected_and_fail_closed(self):
        evidence = self.request_evidence()
        payload = self.status_payload(request_evidence=evidence)
        self.assertTrue(
            ControlTransport.status_readiness(
                payload,
                lowstate_timeout_s=0.5,
            )[0]
        )
        self.assertEqual(
            ControlTransport.status_request_evidence(payload),
            evidence,
        )
        motion_evidence = self.request_evidence(
            published_count=3,
            move_count=2,
            nonzero_move_count=1,
            max_abs_linear_x=0.03,
            motion_run_id=1,
            motion_run_active=True,
            motion_run_nonzero_move_count=1,
            motion_run_max_abs_linear_x=0.03,
        )
        self.assertEqual(
            ControlTransport.status_request_evidence(
                self.status_payload(request_evidence=motion_evidence)
            ),
            motion_evidence,
        )

        transport = self.transport()
        self.send_status(transport, request_evidence=evidence)
        self.assertEqual(
            transport.raw_snapshot()["bridge"]["request_evidence"],
            evidence,
        )

        for invalid in (
            {**evidence, "private": "not-allowed"},
            {**evidence, "published_count": 3},
            {**evidence, "move_count": 2},
            {**evidence, "last_publish_age_ms": -1},
            {**evidence, "last_api_id": 65_000},
            {**evidence, "last_api_id": 1003, "stop_count": 0},
            {**evidence, "max_abs_linear_x": 0.300001},
            {**evidence, "nonzero_move_count": 0, "max_abs_linear_x": 0.01},
            {**evidence, "motion_run_active": 0},
            {**evidence, "motion_run_id": 1},
            {
                **evidence,
                "motion_run_id": 1,
                "motion_run_nonzero_move_count": 1,
                "motion_run_max_abs_linear_x": 0.01,
            },
            {**motion_evidence, "motion_run_id": 2},
            {
                **motion_evidence,
                "motion_run_max_abs_linear_x": 0.04,
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ControlProtocolError):
                    ControlTransport.status_request_evidence(
                        self.status_payload(request_evidence=invalid)
                    )

        malformed = self.request_evidence(
            published_count=3,
            move_count=2,
            malformed_move_count=1,
        )
        unsafe = self.status_payload(request_evidence=malformed)
        self.assertFalse(
            ControlTransport.status_readiness(
                unsafe,
                lowstate_timeout_s=0.5,
            )[0]
        )

    def test_request_evidence_remains_optional_for_rolling_deployment(self):
        payload = self.status_payload()
        self.assertEqual(ControlTransport.status_request_evidence(payload), {})
        self.assertTrue(
            ControlTransport.status_readiness(
                payload,
                lowstate_timeout_s=0.5,
            )[0]
        )

    def test_sport_mode_state_is_optional_bounded_and_not_a_safety_gate(self):
        payload = self.status_payload()
        self.assertEqual(ControlTransport.status_sport_mode_state(payload), {})

        raw = self.sport_mode_state(error_code=4_294_967_295)
        payload = self.status_payload(sport_mode_state=raw)
        self.assertEqual(ControlTransport.status_sport_mode_state(payload), raw)
        self.assertTrue(
            ControlTransport.status_readiness(
                payload,
                lowstate_timeout_s=0.5,
            )[0]
        )

        transport = self.transport()
        self.send_status(transport, sport_mode_state=raw)
        self.assertTrue(transport.manager.snapshot()["ready"])
        self.assertEqual(
            transport.raw_snapshot()["bridge"]["sport_mode_state"],
            raw,
        )

        stale = self.sport_mode_state(
            mode=None,
            gait_type=None,
            velocity=None,
            error_code=None,
            age_ms=501,
            fresh=False,
        )
        self.assertEqual(
            ControlTransport.status_sport_mode_state(
                self.status_payload(sport_mode_state=stale)
            ),
            stale,
        )
        self.assertTrue(
            ControlTransport.status_readiness(
                self.status_payload(sport_mode_state=stale),
                lowstate_timeout_s=0.5,
            )[0]
        )

    def test_sport_mode_state_contract_rejects_malformed_or_stale_values(self):
        valid = self.sport_mode_state()
        invalid_states = (
            {**valid, "private": 1},
            {**valid, "topic": "/other"},
            {**valid, "mode": True},
            {**valid, "gait_type": 256},
            {**valid, "velocity": [0.0, 0.0]},
            {**valid, "velocity": [20.001, 0.0, 0.0]},
            {**valid, "velocity": [0.0, math.nan, 0.0]},
            {**valid, "error_code": 4_294_967_296},
            {**valid, "age_ms": -1},
            {**valid, "stale_after_ms": 1_001},
            {**valid, "fresh": False},
            {
                **valid,
                "age_ms": 501,
                "fresh": False,
            },
        )
        for state in invalid_states:
            with self.subTest(state=state), self.assertRaises(ControlProtocolError):
                ControlTransport.status_sport_mode_state(
                    self.status_payload(sport_mode_state=state)
                )

    def test_signed_fresh_battery_telemetry_is_projected_without_motion_readiness(self):
        transport = self.transport(expected_bare_sport_publishers=9)
        self.send_status(
            transport,
            ready=False,
            sport_publishers=10,
            bare_unitree_sport_publishers=9,
            expected_bare_sport_publishers=9,
            lowstate_age_ms=25.0,
            telemetry={
                "battery": {
                    "battery_soc": 72,
                    "battery_current_ma": -950,
                    "power_v": 28.7654,
                    "power_a": 1.2345,
                }
            },
        )

        self.assertFalse(transport.manager.snapshot()["ready"])
        sensor = transport.battery_sensor_snapshot()
        self.assertIsNotNone(sensor)
        self.assertEqual(sensor["topic"], "bridge://go2/lowstate/battery")
        self.assertEqual(sensor["category"], "battery")
        self.assertEqual(
            sensor["values"],
            {
                "battery_soc": 72,
                "battery_current_ma": -950,
                "power_v": 28.765,
                "power_a": 1.234,
            },
        )

    def test_bridge_battery_telemetry_rejects_invalid_values_and_expires(self):
        transport = self.transport()
        invalid_values = (
            {"battery_soc": 101},
            {"battery_soc": True},
            {"battery_soc": 50, "unexpected": 1},
        )
        for battery in invalid_values:
            with self.subTest(battery=battery):
                self.send_status(transport, telemetry={"battery": battery})
                self.assertFalse(transport.status.get("authenticated", False))
                self.assertIsNone(transport.battery_sensor_snapshot())
        with self.assertRaisesRegex(
            ControlProtocolError,
            "battery telemetry is invalid",
        ):
            ControlTransport.status_telemetry(
                {"telemetry": {"battery": {"battery_soc": math.nan}}}
            )

        self.send_status(
            transport,
            telemetry={"battery": {"battery_soc": 50}},
        )
        self.assertIsNotNone(transport.battery_sensor_snapshot())
        transport.status_received = (
            time.monotonic() - transport.status_timeout_s - 0.001
        )
        self.assertIsNone(transport.battery_sensor_snapshot())

        self.send_status(
            transport,
            lowstate_age_ms=transport.lowstate_timeout_s * 1_000.0 + 0.001,
            telemetry={"battery": {"battery_soc": 50}},
        )
        self.assertIsNone(transport.battery_sensor_snapshot())

    def test_signed_fresh_joint_telemetry_drives_only_the_read_only_model(self):
        transport = self.transport(expected_bare_sport_publishers=9)
        positions = [0.0, 0.5, -1.2] * 4
        self.send_status(
            transport,
            ready=False,
            sport_publishers=10,
            bare_unitree_sport_publishers=9,
            expected_bare_sport_publishers=9,
            lowstate_age_ms=25.0,
            telemetry={
                "joints": {
                    "position_rad": positions,
                    "imu_rpy_rad": [0.01, -0.02, 0.03],
                    "seq": 42,
                }
            },
        )

        self.assertFalse(transport.manager.snapshot()["ready"])
        snapshot = transport.joint_state_snapshot()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["state"], "ok")
        self.assertEqual(snapshot["topic"], "bridge://go2/lowstate/joints")
        self.assertEqual(snapshot["seq"], 42)
        self.assertEqual(snapshot["position_rad"], positions)
        self.assertEqual(snapshot["imu_rpy_rad"], [0.01, -0.02, 0.03])
        self.assertFalse(transport.manager.snapshot()["lease"]["active"])

    def test_bridge_joint_telemetry_rejects_partial_nonfinite_and_out_of_range(self):
        positions = [0.0, 0.5, -1.2] * 4
        invalid = (
            positions[:-1],
            [*positions[:-1], math.nan],
            [100.0, *positions[1:]],
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(
                    ControlProtocolError,
                    "joint telemetry is invalid",
                ):
                    ControlTransport.status_telemetry(
                        {
                            "telemetry": {
                                "joints": {
                                    "position_rad": candidate,
                                    "imu_rpy_rad": [0.0, 0.0, 0.0],
                                    "seq": 1,
                                }
                            }
                        }
                    )

    def test_epoch_rotation_revokes_lease_and_signs_stop_with_new_epoch(self):
        transport, node, _ = self.ready_setup()
        acquired = transport.manager.acquire_lease("keyboard")
        transport.manager.bind_lease(acquired["token"], "websocket-a")

        new_epoch = "n" * 32
        self.send_status(transport, new_epoch)

        self.assertFalse(transport.manager.snapshot()["lease"]["active"])
        self.assertEqual(transport.bridge_epoch, new_epoch)
        self.assertEqual(len(node.publisher.messages), 1)
        stop = decode_signed(node.publisher.messages[0].data, KEY)
        self.assertEqual(stop["type"], "stop")
        self.assertEqual(stop["bridge_epoch"], new_epoch)
        self.assertEqual(stop["reason"], "readiness_lost")

    def test_tampered_status_fails_closed_and_never_exposes_the_key(self):
        transport, node, _ = self.ready_setup()
        acquired = transport.manager.acquire_lease("keyboard")
        transport.manager.bind_lease(acquired["token"], "websocket-a")
        encoded = json.loads(encode_signed(self.status_payload(), KEY))
        encoded["ready"] = False
        message = String()
        message.data = json.dumps(encoded)

        transport.status_callback(message)

        snapshot = transport.raw_snapshot()
        self.assertFalse(snapshot["lease"]["active"])
        self.assertFalse(snapshot["bridge"]["authenticated"])
        self.assertIn("signature", snapshot["bridge"]["message"])
        self.assertNotIn(KEY, json.dumps(snapshot))
        self.assertEqual(
            decode_signed(node.publisher.messages[-1].data, KEY)["type"],
            "stop",
        )

    def test_stale_authenticated_status_revokes_lease_before_manager_tick(self):
        transport, node, _ = self.ready_setup()
        acquired = transport.manager.acquire_lease("keyboard")
        transport.manager.bind_lease(acquired["token"], "websocket-a")
        now = time.monotonic()
        transport.status_received = now - transport.status_timeout_s - 0.001

        with transport.operation_lock:
            self.assertTrue(transport.update_staleness_locked(now))
            outputs = transport.manager_tick_locked()
            transport.publish_outputs(outputs)

        self.assertFalse(transport.manager.snapshot()["lease"]["active"])
        self.assertEqual(transport.status["state"], "stale")
        self.assertEqual(
            decode_signed(node.publisher.messages[-1].data, KEY)["type"],
            "stop",
        )

    def test_bridge_envelope_is_narrow_finite_and_bounded(self):
        drive = ControlTransport.bridge_envelope(
            {
                "type": "drive",
                "velocity": {"vx": 0.1, "vy": -0.2, "wz": 0.3},
            },
            source_id="source-identifier",
            sequence=7,
            bridge_epoch="e" * 32,
        )
        self.assertEqual(
            {key: drive[key] for key in ("linear_x", "linear_y", "angular_z")},
            {"linear_x": 0.1, "linear_y": -0.2, "angular_z": 0.3},
        )
        self.assertIs(drive["deadman"], True)
        action = ControlTransport.bridge_envelope(
            {"type": "action", "action": "hello", "api_id": 1016},
            source_id="source-identifier",
            sequence=8,
            bridge_epoch="e" * 32,
        )
        self.assertEqual(action["action_id"], "hello")
        self.assertNotIn("api_id", action)
        stop = ControlTransport.bridge_envelope(
            {"type": "stop", "reason": "x" * 300},
            source_id="source-identifier",
            sequence=9,
            bridge_epoch="e" * 32,
        )
        self.assertEqual(len(stop["reason"]), 160)
        for velocity in (math.nan, True, "0.1"):
            with self.subTest(velocity=velocity):
                with self.assertRaises(ValueError):
                    ControlTransport.bridge_envelope(
                        {
                            "type": "drive",
                            "velocity": {"vx": velocity, "vy": 0.0, "wz": 0.0},
                        },
                        source_id="source-identifier",
                        sequence=10,
                        bridge_epoch="e" * 32,
                    )

    def test_publish_failure_revokes_readiness_and_queues_fail_closed_stop(self):
        transport, node, _ = self.ready_setup()
        acquired = transport.manager.acquire_lease("keyboard")
        transport.manager.bind_lease(acquired["token"], "websocket-a")
        transport.manager.submit_drive(
            acquired["token"],
            "websocket-a",
            0,
            vx=1.0,
            vy=0.0,
            wz=0.0,
            speed_scale=1.0,
            deadman=True,
            client_age_s=0.0,
        )
        outputs = transport.manager_tick_locked()
        node.publisher.failure = RuntimeError("publisher unavailable")

        transport.publish_outputs(outputs)

        self.assertFalse(transport.manager.snapshot()["lease"]["active"])
        self.assertEqual(transport.status["state"], "error")
        node.publisher.failure = None
        transport.flush_outputs()
        self.assertEqual(
            decode_signed(node.publisher.messages[-1].data, KEY)["type"],
            "stop",
        )

    def test_target_change_and_shutdown_publish_terminal_stops_exactly_once(self):
        transport, node, _ = self.ready_setup()
        acquired = transport.manager.acquire_lease("keyboard")
        transport.manager.bind_lease(acquired["token"], "websocket-a")

        transport.stop_for_target_change()

        snapshot = transport.manager.snapshot()
        self.assertTrue(snapshot["estop"]["latched"])
        self.assertEqual(snapshot["estop"]["reason"], "robot_target_changed")
        first_stop = decode_signed(node.publisher.messages[-1].data, KEY)
        self.assertEqual(first_stop["type"], "stop")
        self.assertEqual(first_stop["reason"], "emergency_stop")

        before_shutdown = len(node.publisher.messages)
        transport.shutdown()
        after_shutdown = len(node.publisher.messages)
        transport.shutdown()
        transport.publish_outputs([{"type": "stop", "reason": "late"}])

        self.assertEqual(after_shutdown, before_shutdown + 1)
        self.assertEqual(len(node.publisher.messages), after_shutdown)
        final_stop = decode_signed(node.publisher.messages[-1].data, KEY)
        self.assertEqual(final_stop["type"], "stop")
        self.assertEqual(final_stop["reason"], "manager_closed")
        self.assertTrue(transport.manager.snapshot()["closed"])

    def test_raw_snapshot_is_compatible_and_component_has_no_http_or_nav_dependency(self):
        transport, _, _ = self.ready_setup()
        snapshot = transport.raw_snapshot()
        self.assertTrue(snapshot["transport_configured"])
        self.assertTrue(snapshot["bridge"]["authenticated"])
        self.assertIsInstance(snapshot["bridge"]["status_age_s"], float)
        self.assertIn("lease", snapshot)
        source = (
            ROOT / "robot_dashboard" / "ros" / "control_transport.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("fastapi", source.lower())
        self.assertNotIn("navigation", "\n".join(
            line for line in source.splitlines() if line.lstrip().startswith(("from ", "import "))
        ).lower())


if __name__ == "__main__":
    unittest.main()
