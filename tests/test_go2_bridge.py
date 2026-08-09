import unittest

from robot_dashboard.control import ACTION_GUARD_S, SAFE_ACTIONS
from robot_dashboard.go2_bridge import (
    API_MOVE,
    API_STOP_MOVE,
    BridgeCommandError,
    Go2BridgeCore,
    SAFE_ACTION_API_IDS,
    SAFE_ACTION_GUARD_S,
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
