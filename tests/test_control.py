import json
import math
import unittest

from robot_dashboard.control import (
    ClientFrameClock,
    SAFE_ACTIONS,
    CommandValidationError,
    ControlClosed,
    ControlDisabled,
    ControlManager,
    ControlNotReady,
    EmergencyStopLatched,
    LeaseBindingError,
    LeaseBusy,
    LeaseInvalid,
    SequenceError,
)


BINDING = "websocket-session-a"


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class ControlManagerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.profile = {
            "name": "Unitree Go2",
            "control": {
                "enabled": True,
                "bridge_stale_after_s": 1.0,
                "lowstate_stale_after_s": 0.5,
                "linear_slew_mps2": 0.75,
                "angular_slew_rps2": 1.5,
            },
        }
        self.env = {"ROBOT_SCOPE_CONTROL_ENABLED": "true"}

    def manager(self, *, profile=None, env=None):
        return ControlManager(
            self.profile if profile is None else profile,
            environ=self.env if env is None else env,
            clock=self.clock,
            token_factory=lambda: "test-token-that-is-long-enough",
        )

    def ready_manager(self):
        manager = self.manager()
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        return manager

    def leased(self, input_source="keyboard"):
        manager = self.ready_manager()
        result = manager.acquire_lease(input_source)
        token = result["token"]
        manager.bind_lease(token, BINDING)
        return manager, token

    def drive(self, manager, token, seq=0, **overrides):
        values = {
            "vx": 1.0,
            "vy": 0.0,
            "wz": 0.0,
            "speed_scale": 1.0,
            "deadman": True,
        }
        values.update(overrides)
        return manager.submit_drive(token, BINDING, seq, **values)

    def test_control_requires_both_profile_and_startup_opt_in(self):
        profile_off = {"control": {"enabled": False}}
        manager = self.manager(profile=profile_off)
        self.assertFalse(manager.snapshot()["enabled"])
        self.assertFalse(manager.snapshot()["configured"])
        with self.assertRaises(ControlDisabled):
            manager.acquire_lease("keyboard")

        env_off = dict(self.env, ROBOT_SCOPE_CONTROL_ENABLED="false")
        manager = self.manager(env=env_off)
        self.assertFalse(manager.snapshot()["enabled"])

        manager = self.manager(env={"ROBOT_SCOPE_CONTROL_ENABLED": "true"})
        self.assertTrue(manager.snapshot()["enabled"])
        self.assertTrue(manager.snapshot()["configured"])
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        self.assertTrue(manager.acquire_lease("keyboard")["lease"]["active"])

    def test_only_one_bound_lease_is_allowed(self):
        manager = self.ready_manager()
        lease = manager.acquire_lease("gamepad")
        token = lease["token"]
        with self.assertRaises(LeaseBusy):
            manager.acquire_lease("keyboard")
        self.assertEqual(manager.bind_lease(token, BINDING)["input_source"], "gamepad")
        self.assertTrue(manager.bind_lease(token, BINDING)["bound"])
        with self.assertRaises(LeaseBindingError):
            manager.bind_lease(token, "another-session")
        with self.assertRaises(LeaseBindingError):
            manager.submit_drive(
                token,
                "another-session",
                0,
                vx=0,
                vy=0,
                wz=0,
                deadman=True,
            )

    def test_lease_must_be_bound_before_commands(self):
        manager = self.ready_manager()
        token = manager.acquire_lease("keyboard")["token"]
        with self.assertRaises(LeaseBindingError):
            manager.heartbeat(token, BINDING, 0)

    def test_sequence_is_strictly_increasing_across_message_types(self):
        manager, token = self.leased()
        manager.heartbeat(token, BINDING, 4)
        with self.assertRaises(SequenceError):
            self.drive(manager, token, seq=4)
        with self.assertRaises(SequenceError):
            self.drive(manager, token, seq=3)
        self.drive(manager, token, seq=5)
        self.drive(manager, token, seq=6, vx=0, deadman=False)
        with self.assertRaises(SequenceError):
            manager.request_action(token, BINDING, 6, "hello", confirm=True)

    def test_client_frame_clock_rejects_websocket_backlog(self):
        guard = ClientFrameClock(100_000.0, 200_000.0)
        self.assertEqual(guard.validate(100_050.0, 200_050.0), 0.0)
        with self.assertRaises(CommandValidationError):
            guard.validate(100_100.0, 200_500.1)
        backlog = ClientFrameClock(100_000.0, 202_000.0)
        with self.assertRaises(CommandValidationError):
            backlog.validate(100_050.0, 202_300.1)
        with self.assertRaises(CommandValidationError):
            guard.validate(101_000.0, 200_100.0)
        for invalid in (True, "100", math.nan, math.inf, -1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(CommandValidationError):
                    guard.validate(invalid, 200_100.0)

    def test_axes_are_finite_normalized_and_speed_is_server_clamped(self):
        manager, token = self.leased()
        for bad in (math.nan, math.inf, -math.inf, 1.0001, -1.0001, True, "bad", "0.5"):
            with self.subTest(bad=bad):
                with self.assertRaises(CommandValidationError):
                    self.drive(manager, token, seq=manager.snapshot()["lease"]["last_seq"] + 1, vx=bad)

        seq = manager.snapshot()["lease"]["last_seq"] + 1
        accepted = self.drive(
            manager,
            token,
            seq=seq,
            vx=1.0,
            vy=-1.0,
            wz=1.0,
            speed_scale=99,
        )
        self.assertEqual(accepted["speed_scale"], 1.0)
        output = manager.tick()[-1]
        self.assertEqual(output["type"], "drive")
        self.assertLessEqual(abs(output["velocity"]["vx"]), 0.30)
        self.assertLessEqual(abs(output["velocity"]["vy"]), 0.20)
        self.assertLessEqual(abs(output["velocity"]["wz"]), 0.50)

        self.clock.advance(0.01)
        accepted = self.drive(manager, token, seq=seq + 1, speed_scale=-5)
        self.assertEqual(accepted["speed_scale"], 0.10)

    def test_tick_coalesces_drive_and_applies_slew_limit(self):
        manager, token = self.leased()
        self.drive(manager, token, seq=0, vx=1.0)
        self.drive(manager, token, seq=1, vx=-1.0)
        first = manager.tick()
        drives = [item for item in first if item["type"] == "drive"]
        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]["seq"], 1)
        self.assertAlmostEqual(drives[0]["velocity"]["vx"], -0.015)

        self.clock.advance(0.1)
        second = manager.tick()[0]
        self.assertAlmostEqual(second["velocity"]["vx"], -0.09)

    def test_snapshot_reports_only_the_last_manager_output(self):
        manager, token = self.leased()
        zero = {
            "source": None,
            "deadman": False,
            "linear_x": 0.0,
            "linear_y": 0.0,
            "angular_z": 0.0,
        }
        self.assertEqual(manager.snapshot()["command"], zero)

        self.drive(manager, token, seq=0, vx=1.0, vy=-1.0, wz=1.0)
        # An accepted intent is not advertised as a manager output before tick.
        self.assertEqual(manager.snapshot()["command"], zero)
        emitted = manager.tick()[-1]
        self.assertEqual(
            manager.snapshot()["command"],
            {
                "source": "keyboard",
                "deadman": True,
                "linear_x": emitted["velocity"]["vx"],
                "linear_y": emitted["velocity"]["vy"],
                "angular_z": emitted["velocity"]["wz"],
            },
        )

        manager.release_lease(token, BINDING)
        self.assertEqual(
            manager.snapshot()["command"],
            {**zero, "source": "keyboard"},
        )

    def test_snapshot_command_is_exact_zero_after_watchdog(self):
        manager, token = self.leased()
        self.drive(manager, token)
        manager.tick()
        self.clock.advance(0.20)
        snapshot = manager.snapshot()
        self.assertFalse(snapshot["lease"]["active"])
        self.assertEqual(
            snapshot["command"],
            {
                "source": "keyboard",
                "deadman": False,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
        )

    def test_command_timeout_boundary_bypasses_ramp(self):
        manager, token = self.leased()
        self.drive(manager, token)
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.clock.advance(0.199999)
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.clock.advance(0.000001)
        output = manager.tick()
        self.assertEqual(output[-1]["type"], "stop")
        self.assertEqual(output[-1]["reason"], "command_timeout")
        self.assertEqual(output[-1]["velocity"], {"vx": 0.0, "vy": 0.0, "wz": 0.0})
        self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_client_frame_age_is_subtracted_from_drive_watchdog(self):
        manager, token = self.leased()
        self.drive(manager, token, client_age_s=0.19)
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.clock.advance(0.01)
        output = manager.tick()
        self.assertEqual(output[-1]["type"], "stop")
        self.assertEqual(output[-1]["reason"], "command_timeout")
        self.assertFalse(manager.snapshot()["lease"]["active"])
        with self.assertRaises(LeaseInvalid):
            self.drive(manager, token, seq=1)

    def test_fresh_frame_cannot_replace_an_expired_drive_before_tick(self):
        manager, token = self.leased()
        self.drive(manager, token, seq=0)
        manager.tick()
        self.clock.advance(0.201)
        with self.assertRaises(LeaseInvalid):
            self.drive(manager, token, seq=1)
        output = manager.drain_outputs()
        self.assertEqual(output[-1]["reason"], "command_timeout")
        self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_heartbeat_does_not_sustain_an_old_drive_command(self):
        manager, token = self.leased()
        self.drive(manager, token, seq=0)
        manager.tick()
        self.clock.advance(0.20)
        with self.assertRaises(LeaseInvalid):
            manager.heartbeat(token, BINDING, 1)
        output = manager.drain_outputs()
        self.assertEqual(output[-1]["type"], "stop")
        self.assertEqual(output[-1]["reason"], "command_timeout")
        self.assertFalse(manager.snapshot()["lease"]["active"])
        with self.assertRaises(LeaseInvalid):
            manager.heartbeat(token, BINDING, 2)

    def test_zero_axis_deadman_stream_and_heartbeats_stay_armed(self):
        manager, token = self.leased()
        frame_clock = ClientFrameClock(100_000.0, 200_000.0)
        seq = -1

        # Reproduce Shift-only input for three seconds. The browser sends a
        # heartbeat instead of a twist once per second; the manager's 50 ms
        # tick may keep forwarding the most recent zero drive during that one
        # skipped frame without extending the browser command deadline.
        for step in range(1, 61):
            self.clock.advance(0.05)
            if step % 5 == 0:
                manager.set_readiness(bridge_ready=True, lowstate_ready=True)
            seq += 1
            client_time_ms = 100_000.0 + step * 50.0
            server_time_ms = 200_010.0 + step * 50.0
            frame_age_s = max(
                0.0,
                frame_clock.validate(client_time_ms, server_time_ms) / 1_000.0,
            )
            if step % 20 == 0:
                manager.heartbeat(token, BINDING, seq)
            else:
                manager.submit_drive(
                    token,
                    BINDING,
                    seq,
                    vx=0.0,
                    vy=0.0,
                    wz=0.0,
                    deadman=True,
                    client_age_s=frame_age_s,
                )
            outputs = manager.tick()
            self.assertTrue(manager.snapshot()["lease"]["active"])
            drives = [output for output in outputs if output["type"] == "drive"]
            self.assertEqual(len(drives), 1)
            self.assertEqual(drives[0]["velocity"], {"vx": 0.0, "vy": 0.0, "wz": 0.0})
            self.assertTrue(manager.snapshot()["command"]["deadman"])

        # A real frame loss still fails closed at the unchanged 200 ms limit.
        self.clock.advance(0.20)
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        self.assertEqual(manager.tick()[-1]["reason"], "command_timeout")
        self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_lease_expires_without_heartbeat_and_stops(self):
        manager, token = self.leased()
        self.drive(manager, token)
        manager.tick()
        self.clock.advance(2.001)
        output = manager.tick()
        self.assertEqual(output[-1]["reason"], "lease_expired")
        self.assertFalse(manager.snapshot()["lease"]["active"])
        with self.assertRaises(LeaseInvalid):
            manager.heartbeat(token, BINDING, 1)

    def test_unbound_lease_has_four_second_bind_ttl_and_bind_resets_heartbeat(self):
        manager = self.ready_manager()
        token = manager.acquire_lease("keyboard")["token"]

        # The old shared 2 s timeout could expire a lease while the browser was
        # still completing the server's allowed 3 s WebSocket bind handshake.
        self.clock.advance(2.001)
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        bound = manager.bind_lease(token, BINDING)
        self.assertTrue(bound["active"])
        self.assertEqual(bound["heartbeat_age_s"], 0.0)

        self.clock.advance(1.999)
        self.assertTrue(manager.snapshot()["lease"]["active"])
        self.clock.advance(0.001)
        self.assertFalse(manager.snapshot()["lease"]["active"])
        self.assertEqual(manager.drain_outputs()[-1]["reason"], "lease_expired")

    def test_unbound_lease_expires_at_bind_ttl_boundary(self):
        manager = self.ready_manager()
        manager.acquire_lease("keyboard")
        self.clock.advance(3.999)
        self.assertTrue(manager.snapshot()["lease"]["active"])
        self.clock.advance(0.001)
        self.assertFalse(manager.snapshot()["lease"]["active"])
        self.assertEqual(manager.drain_outputs()[-1]["reason"], "lease_expired")

    def test_readiness_loss_revokes_lease_and_stops(self):
        manager, token = self.leased()
        self.drive(manager, token)
        manager.tick()
        manager.note_lowstate(False)
        output = manager.drain_outputs()
        self.assertEqual(output[-1]["reason"], "lowstate_not_ready")
        self.assertFalse(manager.snapshot()["lease"]["active"])

        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        token = manager.acquire_lease("keyboard")["token"]
        manager.bind_lease(token, BINDING)
        self.clock.advance(0.501)
        output = manager.tick()
        self.assertEqual(output[-1]["reason"], "readiness_stale")

    def test_estop_wins_race_latches_and_old_lease_cannot_resume(self):
        manager, token = self.leased()
        self.drive(manager, token)
        manager.emergency_stop("red_button")
        output = manager.drain_outputs()
        self.assertEqual(output[-1]["type"], "stop")
        self.assertEqual(output[-1]["reason"], "emergency_stop")
        self.assertTrue(manager.snapshot()["estop"]["latched"])
        with self.assertRaises(EmergencyStopLatched):
            self.drive(manager, token, seq=1)
        with self.assertRaises(EmergencyStopLatched):
            manager.acquire_lease("keyboard")

    def test_estop_clear_requires_confirm_freshness_and_new_lease(self):
        manager, old_token = self.leased()
        manager.emergency_stop()
        with self.assertRaises(CommandValidationError):
            manager.clear_emergency_stop(confirm=False)
        manager.note_lowstate(False)
        with self.assertRaises(ControlNotReady):
            manager.clear_emergency_stop(confirm=True)

        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        cleared = manager.clear_emergency_stop(confirm=True)
        self.assertFalse(cleared["estop"]["latched"])
        self.assertFalse(cleared["lease"]["active"])
        with self.assertRaises(LeaseInvalid):
            manager.bind_lease(old_token, BINDING)
        new_token = manager.acquire_lease("keyboard")["token"]
        self.assertNotEqual(new_token, "")

    def test_duplicate_estop_clear_does_not_revoke_a_new_lease(self):
        manager, _ = self.leased()
        manager.emergency_stop()
        manager.clear_emergency_stop(confirm=True)
        token = manager.acquire_lease("keyboard")["token"]
        manager.bind_lease(token, BINDING)
        self.drive(manager, token, seq=0)

        duplicate = manager.clear_emergency_stop(confirm=True)
        self.assertTrue(duplicate["lease"]["active"])
        self.assertEqual(duplicate["lease"]["last_seq"], 0)
        self.assertFalse(duplicate["estop"]["latched"])
        self.assertEqual(manager.tick()[-1]["type"], "drive")

    def test_actions_are_strictly_allowlisted_and_risky_ones_confirmed(self):
        manager, token = self.leased()
        expected = {
            "balance_stand": 1002,
            "stand_up": 1004,
            "stand_down": 1005,
            "recovery_stand": 1006,
            "sit": 1009,
            "rise_sit": 1010,
            "hello": 1016,
            "stretch": 1017,
            "content": 1020,
            "scrape": 1029,
            "heart": 1036,
            "static_walk": 1061,
            "economic_gait": 1063,
            "free_walk": 2045,
        }
        self.assertEqual(SAFE_ACTIONS, expected)
        with self.assertRaises(CommandValidationError):
            manager.request_action(token, BINDING, 0, "hello")
        with self.assertRaises(CommandValidationError):
            manager.request_action(token, BINDING, 0, "flip")
        with self.assertRaises(CommandValidationError):
            manager.request_action(token, BINDING, 0, 1001)  # damp
        accepted = manager.request_action(token, BINDING, 0, "hello", confirm=True)
        self.assertEqual(accepted["action"], "hello")
        self.assertTrue(accepted["lease_released"])
        output = manager.tick()
        self.assertEqual([item["type"] for item in output], ["stop", "action"])
        self.assertFalse(manager.snapshot()["lease"]["active"])
        with self.assertRaises(LeaseInvalid):
            manager.request_action(token, BINDING, 1, "sit", confirm=True)

    def test_action_requires_released_deadman_and_emits_stop_first(self):
        manager, token = self.leased()
        self.drive(manager, token, seq=0)
        with self.assertRaises(CommandValidationError):
            manager.request_action(token, BINDING, 1, "hello", confirm=True)
        manager.submit_drive(
            token,
            BINDING,
            1,
            vx=0,
            vy=0,
            wz=0,
            deadman=False,
        )
        manager.drain_outputs()
        manager.request_action(token, BINDING, 2, "hello", confirm=True)
        output = manager.tick()
        self.assertEqual([item["type"] for item in output], ["stop", "action"])
        self.assertEqual(output[0]["reason"], "action_prepare")
        self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_action_guard_blocks_rearm_until_conservative_window_expires(self):
        manager, token = self.leased()
        manager.request_action(token, BINDING, 0, "hello", confirm=True)
        snapshot = manager.snapshot()
        self.assertTrue(snapshot["action_guard"]["active"])
        self.assertEqual(snapshot["action_guard"]["action"], "hello")
        self.assertFalse(snapshot["ready"])
        with self.assertRaises(ControlNotReady):
            manager.acquire_lease("keyboard")
        self.clock.advance(8.0)
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        new_lease = manager.acquire_lease("keyboard")
        self.assertTrue(new_lease["lease"]["active"])

    def test_snapshot_is_json_safe_and_never_exposes_token_or_binding(self):
        manager, token = self.leased()
        snapshot = manager.snapshot()
        encoded = json.dumps(snapshot, allow_nan=False)
        self.assertNotIn(token, encoded)
        self.assertNotIn(BINDING, encoded)
        self.assertNotIn("token", snapshot["lease"])
        self.assertEqual(snapshot["input_sources"], ["gamepad", "keyboard"])

    def test_deadman_release_and_manual_release_stop_immediately(self):
        manager, token = self.leased()
        self.drive(manager, token, seq=0)
        manager.tick()
        self.drive(manager, token, seq=1, deadman=False)
        output = manager.drain_outputs()
        self.assertEqual(output[-1]["reason"], "deadman_released")
        self.assertEqual(output[-1]["velocity"]["vx"], 0.0)

        manager.release_lease(token, BINDING)
        output = manager.drain_outputs()
        self.assertEqual(output[-1]["reason"], "lease_released")

    def test_profile_can_only_lower_limits_and_allowlisted_actions(self):
        profile = {
            "control": {
                "enabled": True,
                "max_linear_x": 9,
                "max_linear_y": 0.08,
                "max_angular_z": 0.25,
                "default_speed_scale": 0.4,
                "bridge_status_timeout_s": 0.75,
                "telemetry_timeout_s": 0.5,
                "max_linear_accel": 0.8,
                "max_lateral_accel": 0.3,
                "max_angular_accel": 1.2,
                "allowed_actions": ["hello", "flip", "sit"],
            }
        }
        manager = self.manager(profile=profile)
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        token = manager.acquire_lease("keyboard")["token"]
        manager.bind_lease(token, BINDING)
        snapshot = manager.snapshot()
        self.assertEqual(snapshot["limits"]["vx_mps"], 0.30)
        self.assertEqual(snapshot["limits"]["vy_mps"], 0.08)
        self.assertEqual(snapshot["limits"]["wz_rps"], 0.25)
        self.assertEqual(snapshot["limits"]["default_speed_scale"], 0.4)
        self.assertEqual([action["id"] for action in snapshot["actions"]], ["hello", "sit"])
        with self.assertRaises(CommandValidationError):
            manager.request_action(token, BINDING, 0, "balance_stand")

    def test_unbound_lease_can_be_released_before_websocket_connects(self):
        manager = self.ready_manager()
        token = manager.acquire_lease("keyboard")["token"]
        manager.release_lease(token)
        self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_close_is_idempotent_and_fail_closed(self):
        manager, token = self.leased()
        self.drive(manager, token)
        manager.tick()
        manager.close()
        manager.close()
        outputs = manager.drain_outputs()
        stops = [item for item in outputs if item["reason"] == "manager_closed"]
        self.assertEqual(len(stops), 1)
        self.assertTrue(manager.snapshot()["closed"])
        with self.assertRaises(ControlClosed):
            manager.tick()


if __name__ == "__main__":
    unittest.main()
