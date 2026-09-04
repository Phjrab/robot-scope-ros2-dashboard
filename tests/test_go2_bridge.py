import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from robot_dashboard.control import ACTION_GUARD_S, SAFE_ACTIONS
from robot_dashboard.go2_bridge import (
    API_MOVE,
    API_STOP_MOVE,
    BridgeCommandError,
    Go2BridgeCore,
    SAFE_ACTION_API_IDS,
    SAFE_ACTION_GUARD_S,
    SPORT_REQUEST_EVIDENCE_MAX_COUNT,
    SPORT_REQUEST_EVIDENCE_SCHEMA,
    SPORT_MODE_STATE_MAX_ERROR_CODE,
    SPORT_MODE_STATE_TOPICS,
    SportModeStateObservation,
    SportRequest,
    SportRequestEvidence,
    classify_sport_request_publishers,
)


class Go2BridgeCoreTests(unittest.TestCase):
    def setUp(self):
        self.core = Go2BridgeCore()
        self.now = 10.0

    def command(self, kind="drive", seq=1, **values):
        payload = {
            "type": kind,
            "source_id": "dashboard-a",
            "seq": seq,
            "bridge_epoch": self.core.bridge_epoch,
        }
        payload.update(values)
        return payload

    def tick(
        self,
        advance=0.0,
        age=0.01,
        subscribers=1,
        publishers=1,
        sport_publishers=1,
    ):
        self.now += advance
        return self.core.tick(
            now=self.now,
            lowstate_age_s=age,
            sport_subscribers=subscribers,
            sport_publishers=sport_publishers,
            lowstate_publishers=publishers,
        )

    def test_dashboard_and_watchdog_action_allowlists_match(self):
        self.assertEqual(SAFE_ACTION_API_IDS, SAFE_ACTIONS)
        self.assertEqual(SAFE_ACTION_GUARD_S, ACTION_GUARD_S)

    def test_bridge_keeps_ros_context_alive_for_shutdown_stop(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "robot_dashboard"
            / "go2_control_bridge.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        rendered = ast.unparse(main)
        self.assertIn("signal_handler_options=SignalHandlerOptions.NO", rendered)
        self.assertLess(rendered.index("node.stop_safely()"), rendered.index("rclpy.shutdown()"))

        bridge = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Go2ControlBridge"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in bridge.body
            if isinstance(node, ast.FunctionDef)
        }
        for method in ("_command_callback", "_tick", "stop_safely"):
            self.assertIn("with self._operation_lock", methods[method])
        self.assertLess(
            methods["stop_safely"].index("self._closing = True"),
            methods["stop_safely"].index("self._publish_request"),
        )
        self.assertLess(
            methods["stop_safely"].index("self._timer.cancel()"),
            methods["stop_safely"].index("self._publish_request"),
        )
        self.assertIn("if SignalHandlerOptions is None", rendered)
        self.assertIn("datagram_config=datagram_config", rendered)

    def test_wireless_transport_reuses_signed_bridge_without_relaying_dds(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "robot_dashboard"
            / "go2_control_bridge.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ConnectedControlDatagram", source)
        self.assertIn("self._accept_command(message)", source)
        self.assertIn("DatagramStringPublisher(endpoint)", source)
        self.assertNotIn("/api/sport/response", source)
        self.assertNotIn("create_generic", source)

        tree = ast.parse(source)
        bridge = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Go2ControlBridge"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in bridge.body
            if isinstance(node, ast.FunctionDef)
        }
        publish_status = methods["_publish_status"]
        receive_commands = methods["_receive_datagram_commands"]
        self.assertIn("except (ControlDatagramError, OSError)", publish_status)
        self.assertIn("self._core.force_stop", publish_status)
        self.assertIn("except OSError", receive_commands)
        self.assertIn("continue", receive_commands)

    def test_request_evidence_is_bridge_owned_and_records_after_publish(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "robot_dashboard"
            / "go2_control_bridge.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        bridge = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Go2ControlBridge"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in bridge.body
            if isinstance(node, ast.FunctionDef)
        }
        publish_request = methods["_publish_request"]
        self.assertLess(
            publish_request.index("self._sport_publisher.publish(message)"),
            publish_request.index("self._request_evidence.record"),
        )
        self.assertIn(
            "'request_evidence': self._request_evidence.snapshot(now=now)",
            methods["_publish_status"],
        )

        evidence_source = ast.unparse(
            next(
                node
                for node in ast.parse(
                    (
                        Path(__file__).resolve().parents[1]
                        / "robot_dashboard"
                        / "go2_bridge.py"
                    ).read_text(encoding="utf-8")
                ).body
                if isinstance(node, ast.ClassDef)
                and node.name == "SportRequestEvidence"
            )
        )
        for forbidden in (
            "create_publisher",
            "create_subscription",
            "ControlManager",
            "deadman",
            "lease",
            "rclpy",
        ):
            self.assertNotIn(forbidden, evidence_source)

    def test_sport_mode_state_observation_is_bounded_fresh_and_read_only(self):
        observation = SportModeStateObservation(
            topic="/sportmodestate",
            stale_after_s=0.5,
        )
        waiting = observation.snapshot(now=10.0)
        self.assertEqual(waiting["topic"], "/sportmodestate")
        self.assertFalse(waiting["fresh"])
        self.assertIsNone(waiting["age_ms"])
        self.assertIsNone(waiting["mode"])

        observation.observe(
            SimpleNamespace(
                mode=5,
                gait_type=3,
                # Foxy materializes fixed float arrays as numpy.float32 values.
                velocity=[np.float32(0.1051234), np.float32(-0.02), np.float32(0.0)],
                error_code=SPORT_MODE_STATE_MAX_ERROR_CODE,
            ),
            now=10.0,
        )
        fresh = observation.snapshot(now=10.125)
        self.assertEqual(
            fresh,
            {
                "topic": "/sportmodestate",
                "mode": 5,
                "gait_type": 3,
                "velocity": [0.105123, -0.02, 0.0],
                "error_code": SPORT_MODE_STATE_MAX_ERROR_CODE,
                "age_ms": 125,
                "stale_after_ms": 500,
                "fresh": True,
            },
        )

        boundary = observation.snapshot(now=10.5)
        self.assertTrue(boundary["fresh"])
        self.assertEqual(boundary["age_ms"], 500)

        over_boundary = observation.snapshot(now=10.5004)
        self.assertFalse(over_boundary["fresh"])
        self.assertEqual(over_boundary["age_ms"], 501)
        self.assertIsNone(over_boundary["mode"])

        stale = observation.snapshot(now=10.501)
        self.assertFalse(stale["fresh"])
        self.assertEqual(stale["age_ms"], 501)
        for field in ("mode", "gait_type", "velocity", "error_code"):
            self.assertIsNone(stale[field])

        observation_source = ast.unparse(
            next(
                node
                for node in ast.parse(
                    (
                        Path(__file__).resolve().parents[1]
                        / "robot_dashboard"
                        / "go2_bridge.py"
                    ).read_text(encoding="utf-8")
                ).body
                if isinstance(node, ast.ClassDef)
                and node.name == "SportModeStateObservation"
            )
        )
        for forbidden in (
            "create_publisher",
            "create_subscription",
            "ControlManager",
            "submit_drive",
            "SportRequest",
            "deadman",
            "lease",
        ):
            self.assertNotIn(forbidden, observation_source)

    def test_sport_mode_state_rejects_invalid_topic_values_and_time(self):
        with self.assertRaisesRegex(ValueError, "topic is not allowlisted"):
            SportModeStateObservation(topic="/other", stale_after_s=0.5)
        self.assertEqual(
            SPORT_MODE_STATE_TOPICS,
            ("/sportmodestate", "/lf/sportmodestate"),
        )
        observation = SportModeStateObservation(
            topic="/lf/sportmodestate",
            stale_after_s=0.5,
        )
        valid = {
            "mode": 1,
            "gait_type": 2,
            "velocity": [0.0, 0.0, 0.0],
            "error_code": 0,
        }
        for changes in (
            {"mode": True},
            {"gait_type": 256},
            {"velocity": [0.0, 0.0]},
            {"velocity": [0.0, float("nan"), 0.0]},
            {"velocity": [20.001, 0.0, 0.0]},
            {"error_code": SPORT_MODE_STATE_MAX_ERROR_CODE + 1},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                observation.observe(
                    SimpleNamespace(**{**valid, **changes}),
                    now=10.0,
                )
        with self.assertRaisesRegex(ValueError, "observation time"):
            observation.observe(SimpleNamespace(**valid), now=float("nan"))

    def test_control_bridge_subscribes_to_one_configured_sport_state_alias_only(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "robot_dashboard" / "go2_control_bridge.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        bridge = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Go2ControlBridge"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in bridge.body
            if isinstance(node, ast.FunctionDef)
        }
        constructor = methods["__init__"]
        callback = methods["_sport_mode_state_callback"]
        self.assertIn("control.get('sport_mode_state_topic'", constructor)
        self.assertIn("SportModeStateObservation", constructor)
        self.assertIn("self.create_subscription(SportModeState", constructor)
        self.assertIn("self._sport_mode_state.observe", callback)
        self.assertNotIn("self._core", callback)
        self.assertNotIn("_publish_request", callback)
        self.assertIn(
            "'sport_mode_state': self._sport_mode_state.snapshot(now=now)",
            methods["_publish_status"],
        )

        profile = json.loads(
            (root / "config" / "go2.json").read_text(encoding="utf-8")
        )
        self.assertIn(
            profile["control"]["sport_mode_state_topic"],
            SPORT_MODE_STATE_TOPICS,
        )

    def test_request_evidence_is_bounded_and_classifies_published_requests(self):
        evidence = SportRequestEvidence()
        empty = evidence.snapshot(now=10.0)
        self.assertEqual(empty["schema"], SPORT_REQUEST_EVIDENCE_SCHEMA)
        self.assertEqual(empty["scope"], "bridge_process")
        self.assertEqual(empty["published_count"], 0)
        self.assertIsNone(empty["last_api_id"])
        self.assertIsNone(empty["last_publish_age_ms"])

        zero_time = SportRequestEvidence()
        zero_time.record(SportRequest(API_STOP_MOVE), now=0.0)
        self.assertEqual(zero_time.snapshot(now=0.0)["last_publish_age_ms"], 0)

        evidence.record(SportRequest(API_STOP_MOVE), now=10.0)
        evidence.record(
            SportRequest(API_MOVE, '{"x":0.0,"y":0.0,"z":0.0}'),
            now=10.1,
        )
        evidence.record(
            SportRequest(API_MOVE, '{"x":-0.03,"y":0.02,"z":-0.04}'),
            now=10.2,
        )
        evidence.record(
            SportRequest(SAFE_ACTION_API_IDS["balance_stand"]),
            now=10.3,
        )
        snapshot = evidence.snapshot(now=10.35)
        self.assertEqual(snapshot["published_count"], 4)
        self.assertEqual(snapshot["stop_count"], 1)
        self.assertEqual(snapshot["move_count"], 2)
        self.assertEqual(snapshot["zero_move_count"], 1)
        self.assertEqual(snapshot["nonzero_move_count"], 1)
        self.assertEqual(snapshot["malformed_move_count"], 0)
        self.assertEqual(snapshot["action_count"], 1)
        self.assertEqual(snapshot["other_count"], 0)
        self.assertEqual(snapshot["last_api_id"], SAFE_ACTION_API_IDS["balance_stand"])
        self.assertEqual(snapshot["last_publish_age_ms"], 50)
        self.assertEqual(snapshot["max_abs_linear_x"], 0.03)
        self.assertEqual(snapshot["max_abs_linear_y"], 0.02)
        self.assertEqual(snapshot["max_abs_angular_z"], 0.04)
        self.assertEqual(snapshot["motion_run_id"], 1)
        self.assertFalse(snapshot["motion_run_active"])
        self.assertEqual(snapshot["motion_run_nonzero_move_count"], 1)
        self.assertEqual(snapshot["motion_run_max_abs_linear_x"], 0.03)
        self.assertEqual(snapshot["motion_run_max_abs_linear_y"], 0.02)
        self.assertEqual(snapshot["motion_run_max_abs_angular_z"], 0.04)

        tiny = SportRequestEvidence()
        tiny.record(
            SportRequest(API_MOVE, '{"x":1e-12,"y":0.0,"z":0.0}'),
            now=10.0,
        )
        tiny_snapshot = tiny.snapshot(now=10.0)
        self.assertEqual(tiny_snapshot["nonzero_move_count"], 1)
        self.assertEqual(tiny_snapshot["max_abs_linear_x"], 1e-12)

        evidence.record(SportRequest(API_MOVE, "invalid"), now=10.4)
        evidence.record(
            SportRequest(API_MOVE, '{"x":0.31,"y":0.0,"z":0.0}'),
            now=10.45,
        )
        evidence.record(SportRequest(65_000), now=10.5)
        rejected = evidence.snapshot(now=10.5)
        self.assertEqual(rejected["malformed_move_count"], 2)
        self.assertEqual(rejected["other_count"], 1)
        self.assertEqual(
            SportRequestEvidence._increment(SPORT_REQUEST_EVIDENCE_MAX_COUNT),
            SPORT_REQUEST_EVIDENCE_MAX_COUNT,
        )

    def test_startup_and_watchdog_publish_stop(self):
        requests = self.tick()
        self.assertEqual(requests[0].api_id, API_STOP_MOVE)
        self.core.accept(
            self.command(
                deadman=True,
                linear_x=0.2,
                linear_y=-0.1,
                angular_z=0.3,
            ),
            now=self.now,
        )
        requests = self.tick(0.199)
        self.assertEqual(requests[-1].api_id, API_MOVE)
        self.assertIn('"x":0.2', requests[-1].parameter)
        requests = self.tick(0.002)
        self.assertEqual(requests[-1].api_id, API_STOP_MOVE)

    def test_command_watchdog_is_capped_at_200_ms(self):
        core = Go2BridgeCore(command_timeout_s=99)
        self.assertEqual(core.command_timeout_s, 0.20)
        snapshot = core.snapshot(
            now=self.now,
            lowstate_age_s=0.01,
            lowstate_publishers=1,
            sport_subscribers=1,
            sport_publishers=1,
        )
        self.assertEqual(snapshot["limits"]["command_timeout_ms"], 200)

    def test_signed_transport_age_is_subtracted_from_watchdog(self):
        self.core.accept(
            self.command(
                deadman=True,
                linear_x=0.1,
                linear_y=0.0,
                angular_z=0.0,
            ),
            now=self.now,
            transport_age_s=0.19,
        )
        self.assertEqual(self.tick()[-1].api_id, API_MOVE)
        self.assertEqual(self.tick(0.011)[-1].api_id, API_STOP_MOVE)
        stale_core = Go2BridgeCore()
        with self.assertRaises(BridgeCommandError):
            stale_core.accept(
                {
                    **self.command(),
                    "bridge_epoch": stale_core.bridge_epoch,
                    "deadman": True,
                    "linear_x": 0.1,
                    "linear_y": 0.0,
                    "angular_z": 0.0,
                },
                now=self.now,
                transport_age_s=0.201,
            )

    def test_zero_axis_deadman_stream_stays_fresh_until_frames_stop(self):
        self.tick()  # consume the bridge's startup StopMove
        for seq in range(1, 61):
            self.now += 0.05
            self.core.accept(
                self.command(
                    seq=seq,
                    deadman=True,
                    linear_x=0.0,
                    linear_y=0.0,
                    angular_z=0.0,
                ),
                now=self.now,
                transport_age_s=0.01,
            )
            requests = self.tick()
            self.assertEqual([request.api_id for request in requests], [API_MOVE])
            self.assertEqual(requests[0].parameter, '{"x":0.0,"y":0.0,"z":0.0}')

        snapshot = self.core.snapshot(
            now=self.now,
            lowstate_age_s=0.01,
            lowstate_publishers=1,
            sport_subscribers=1,
            sport_publishers=1,
        )
        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["state"], "idle")

        # Zero velocity does not weaken the independent bridge watchdog.
        self.assertEqual(self.tick(0.201)[-1].api_id, API_STOP_MOVE)

    def test_bridge_rechecks_hard_limits_and_telemetry(self):
        self.core.accept(
            self.command(
                deadman=True,
                linear_x=99,
                linear_y=-99,
                angular_z=99,
            ),
            now=self.now,
        )
        request = self.tick()[-1]
        self.assertIn('"x":0.3', request.parameter)
        self.assertIn('"y":-0.2', request.parameter)
        self.assertIn('"z":0.5', request.parameter)
        request = self.tick(0.05, age=0.6)[-1]
        self.assertEqual(request.api_id, API_STOP_MOVE)

    def test_deadman_release_stop_and_replay_rejected(self):
        self.core.accept(
            self.command(
                deadman=True,
                linear_x=0.1,
                linear_y=0,
                angular_z=0,
            ),
            now=self.now,
        )
        self.tick()
        self.core.accept(self.command(seq=2, deadman=False), now=self.now)
        self.assertEqual(self.tick()[-1].api_id, API_STOP_MOVE)
        with self.assertRaises(BridgeCommandError):
            self.core.accept(self.command(seq=2, deadman=False), now=self.now)

    def test_bridge_epoch_rejects_commands_from_an_earlier_instance(self):
        command = self.command(
            deadman=True,
            linear_x=0.1,
            linear_y=0,
            angular_z=0,
        )
        self.core.accept(command, now=self.now)

        restarted = Go2BridgeCore()
        self.assertNotEqual(restarted.bridge_epoch, self.core.bridge_epoch)
        with self.assertRaisesRegex(BridgeCommandError, "epoch"):
            restarted.accept(command, now=self.now)

        command.pop("bridge_epoch")
        with self.assertRaisesRegex(BridgeCommandError, "epoch"):
            self.core.accept(command, now=self.now)

    def test_ready_requires_exactly_one_robot_graph_endpoint(self):
        for publishers, subscribers, sport_publishers, expected in (
            (1, 1, 1, True),
            (0, 1, 1, False),
            (2, 1, 1, False),
            (1, 0, 1, False),
            (1, 2, 1, False),
            (1, 1, 0, False),
            (1, 1, 2, False),
        ):
            with self.subTest(
                publishers=publishers,
                subscribers=subscribers,
                sport_publishers=sport_publishers,
            ):
                snapshot = self.core.snapshot(
                    now=self.now,
                    lowstate_age_s=0.01,
                    lowstate_publishers=publishers,
                    sport_subscribers=subscribers,
                    sport_publishers=sport_publishers,
                )
                self.assertEqual(snapshot["ready"], expected)
                self.assertEqual(snapshot["lowstate_publishers"], publishers)
                self.assertEqual(snapshot["sport_subscribers"], subscribers)
                self.assertEqual(snapshot["sport_publishers"], sport_publishers)
                self.assertIs(type(snapshot["sport_publishers"]), int)
                self.assertEqual(snapshot["bridge_epoch"], self.core.bridge_epoch)

        for publishers, subscribers, sport_publishers in (
            (0, 1, 1),
            (2, 1, 1),
            (1, 0, 1),
            (1, 2, 1),
            (1, 1, 0),
            (1, 1, 2),
        ):
            with self.subTest(
                rejects_drive_publishers=publishers,
                rejects_drive_subscribers=subscribers,
                rejects_drive_sport_publishers=sport_publishers,
            ):
                core = Go2BridgeCore()
                core.accept(
                    {
                        "type": "drive",
                        "source_id": "dashboard-a",
                        "seq": 1,
                        "bridge_epoch": core.bridge_epoch,
                        "deadman": True,
                        "linear_x": 0.1,
                        "linear_y": 0,
                        "angular_z": 0,
                    },
                    now=self.now,
                )
                requests = core.tick(
                    now=self.now,
                    lowstate_age_s=0.01,
                    lowstate_publishers=publishers,
                    sport_subscribers=subscribers,
                    sport_publishers=sport_publishers,
                )
                self.assertNotIn(API_MOVE, [request.api_id for request in requests])
                self.assertEqual(requests[-1].api_id, API_STOP_MOVE)

    def test_go2_bare_dds_baseline_does_not_hide_named_competitors(self):
        core = Go2BridgeCore(expected_bare_sport_publishers=10)
        ready = core.snapshot(
            now=self.now,
            lowstate_age_s=0.01,
            lowstate_publishers=1,
            sport_subscribers=1,
            sport_publishers=11,
            own_sport_publishers=1,
            foreign_named_sport_publishers=0,
            bare_unitree_sport_publishers=10,
        )
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["sport_publishers"], 11)
        self.assertEqual(ready["own_sport_publishers"], 1)
        self.assertEqual(ready["bare_unitree_sport_publishers"], 10)
        self.assertEqual(ready["expected_bare_sport_publishers"], 10)

        for values in (
            {
                "sport_publishers": 12,
                "own_sport_publishers": 1,
                "foreign_named_sport_publishers": 1,
                "bare_unitree_sport_publishers": 10,
            },
            {
                "sport_publishers": 10,
                "own_sport_publishers": 0,
                "foreign_named_sport_publishers": 0,
                "bare_unitree_sport_publishers": 10,
            },
            {
                "sport_publishers": 10,
                "own_sport_publishers": 1,
                "foreign_named_sport_publishers": 0,
                "bare_unitree_sport_publishers": 9,
            },
            {
                "sport_publishers": 11,
                "own_sport_publishers": 1,
                "foreign_named_sport_publishers": 0,
                "bare_unitree_sport_publishers": 9,
            },
        ):
            with self.subTest(values=values):
                self.assertFalse(
                    core.snapshot(
                        now=self.now,
                        lowstate_age_s=0.01,
                        lowstate_publishers=1,
                        sport_subscribers=1,
                        **values,
                    )["ready"]
                )

    def test_sport_publisher_endpoint_classification_fails_unknown_named_closed(self):
        bare = SimpleNamespace(
            node_name="_CREATED_BY_BARE_DDS_APP_",
            node_namespace="_CREATED_BY_BARE_DDS_APP_",
        )
        own = SimpleNamespace(
            node_name="robot_scope_go2_control_bridge",
            node_namespace="/",
        )
        foreign = SimpleNamespace(node_name="test_teleop", node_namespace="/")
        incomplete = SimpleNamespace(node_name=None, node_namespace=None)
        counts = classify_sport_request_publishers(
            [*([bare] * 9), own, foreign, incomplete],
            own_node_name="robot_scope_go2_control_bridge",
            own_node_namespace="/",
        )
        self.assertEqual(
            counts,
            {
                "sport_publishers": 12,
                "own_sport_publishers": 1,
                "foreign_named_sport_publishers": 2,
                "bare_unitree_sport_publishers": 9,
            },
        )

    def test_expected_bare_sport_publisher_count_is_strictly_validated(self):
        for invalid in (True, -1, 65, 9.0, "9"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    Go2BridgeCore(expected_bare_sport_publishers=invalid)

    def test_allowlisted_action_stops_first(self):
        self.tick()
        self.core.accept(
            self.command(kind="action", action_id="hello"),
            now=self.now,
        )
        self.assertEqual(self.tick()[0].api_id, API_STOP_MOVE)
        action = self.tick(0.11)[-1]
        self.assertEqual(action.api_id, SAFE_ACTION_API_IDS["hello"])
        with self.assertRaises(BridgeCommandError):
            self.core.accept(
                self.command(kind="action", seq=2, action_id="front_flip"),
                now=self.now,
            )

    def test_inflight_drive_cannot_cancel_pending_action(self):
        self.tick()
        self.core.accept(
            self.command(kind="action", action_id="hello"),
            now=self.now,
        )
        self.core.accept(
            self.command(
                seq=2,
                deadman=True,
                linear_x=0.1,
                linear_y=0,
                angular_z=0,
            ),
            now=self.now + 0.05,
        )
        action = self.tick(0.11)[-1]
        self.assertEqual(action.api_id, SAFE_ACTION_API_IDS["hello"])

    def test_action_guard_suppresses_idle_stop_but_not_telemetry_stop(self):
        self.tick()
        self.core.accept(
            self.command(kind="action", action_id="hello"),
            now=self.now,
        )
        self.assertEqual(self.tick()[0].api_id, API_STOP_MOVE)
        self.assertEqual(self.tick(0.11)[-1].api_id, SAFE_ACTION_API_IDS["hello"])
        self.assertEqual(self.tick(0.39), [])
        guarded = self.core.snapshot(
            now=self.now,
            lowstate_age_s=0.01,
            lowstate_publishers=1,
            sport_subscribers=1,
            sport_publishers=1,
        )
        self.assertTrue(guarded["action_guard"]["active"])
        self.assertFalse(guarded["ready"])
        self.assertEqual(self.tick(0.01, age=0.6)[-1].api_id, API_STOP_MOVE)

    def test_competing_sources_and_stop_takeover(self):
        self.core.accept(
            self.command(
                deadman=True,
                linear_x=0.1,
                linear_y=0,
                angular_z=0,
            ),
            now=self.now,
        )
        other = {
            "type": "drive",
            "source_id": "dashboard-b",
            "seq": 1,
            "bridge_epoch": self.core.bridge_epoch,
            "deadman": True,
            "linear_x": 0.1,
            "linear_y": 0,
            "angular_z": 0,
        }
        with self.assertRaises(BridgeCommandError):
            self.core.accept(other, now=self.now)
        other.update({"type": "stop", "reason": "emergency", "seq": 2})
        self.core.accept(other, now=self.now)
        self.assertEqual(self.tick()[-1].api_id, API_STOP_MOVE)


if __name__ == "__main__":
    unittest.main()
