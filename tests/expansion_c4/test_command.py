from dataclasses import replace
import unittest

from robot_dashboard.obstacle_runtime_adapter.command import Binding, RawCommand, Constraint, CommandGate, MockCommandSink


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.binding = Binding("goal-1", 1, "lease-1", "epoch-1", "map/r1/tf1", "local-clock")
        self.sink = MockCommandSink()
        self.gate = CommandGate(self.sink, self.binding)
        self.raw = RawCommand(1, self.binding, 100, 200, (.3, .1, -.2))
        self.clear = Constraint(1, 1, self.binding, 100, 200, "CLEAR")

    def test_stop_required_writes_zero_and_hold(self):
        self.assertEqual(self.gate.apply(self.raw, self.clear, now_ns=100).velocity, self.raw.velocity)
        c = replace(self.clear, sequence=2, command_sequence=2, severity="STOP_REQUIRED")
        result = self.gate.apply(replace(self.raw, sequence=2), c, now_ns=110)
        self.assertEqual(self.sink.current.velocity, (0., 0., 0.))
        self.assertTrue(result.hold)
        self.assertEqual(result.reason, "STOP_REQUIRED")

    def test_global_stop_estop_lease_priority_and_no_clearance_release(self):
        for authority, reason in (({"global_stop": True}, "GLOBAL_STOP"), ({"estop": True}, "ESTOP"),
                                  ({"lease_active": False}, "LEASE_CANCELED")):
            gate = CommandGate(MockCommandSink(), self.binding)
            gate.set_authority(**authority)
            gate.set_authority()  # No implicit unlatch from a default/late message.
            self.assertEqual(gate.apply(self.raw, self.clear, now_ns=100).reason, reason)
            self.assertFalse(gate.resume(self.clear, acknowledged_stop_revision=gate.stop_revision, now_ns=100))

    def test_duplicate_and_reordered_commands_zero_previous_motion(self):
        self.gate.apply(self.raw, self.clear, now_ns=100)
        result = self.gate.apply(self.raw, replace(self.clear, sequence=2), now_ns=110)
        self.assertTrue(result.hold)
        self.assertEqual(self.gate.rejected, 1)
        self.assertEqual(self.sink.current.velocity, (0., 0., 0.))

    def test_ttl_future_goal_generation_lease_clock_and_epoch_mismatch(self):
        variants = [{"goal_id": "goal-2"}, {"generation": 2}, {"lease_id": "lease-2"},
                    {"source_epoch": "epoch-2"}, {"clock_id": "foreign"}, {"frame_key": "other-map"}]
        for v in variants:
            with self.subTest(v=v):
                result = self.gate.apply(replace(self.raw, binding=replace(self.binding, **v)), self.clear, now_ns=100)
                self.assertTrue(result.hold)
        for raw in (replace(self.raw, expires_ns=100), replace(self.raw, issued_ns=120),
                    replace(self.raw, expires_ns=10**12), replace(self.raw, velocity=(float("nan"), 0, 0))):
            self.assertTrue(self.gate.apply(raw, self.clear, now_ns=100).hold)
        for c in (replace(self.clear, valid_until_ns=100), replace(self.clear, valid_from_ns=101),
                  replace(self.clear, command_sequence=2), replace(self.clear, binding=replace(self.binding, generation=2))):
            self.assertTrue(self.gate.apply(self.raw, c, now_ns=100).hold)

    def test_late_clearance_cannot_undo_stop_and_explicit_resume_never_replays(self):
        self.gate.apply(self.raw, replace(self.clear, severity="STOP_REQUIRED"), now_ns=100)
        revision = self.gate.stop_revision
        self.assertFalse(self.gate.resume(self.clear, acknowledged_stop_revision=revision, now_ns=110))
        fresh = replace(self.clear, sequence=2)
        self.assertFalse(self.gate.resume(fresh, acknowledged_stop_revision=revision-1, now_ns=110))
        self.assertTrue(self.gate.resume(fresh, acknowledged_stop_revision=revision, now_ns=110))
        self.assertEqual(self.sink.current.velocity, (0., 0., 0.))
        self.assertFalse(self.gate.resume(fresh, acknowledged_stop_revision=revision, now_ns=110))
        self.assertFalse(self.gate.apply(replace(self.raw, sequence=2), replace(fresh, sequence=3, command_sequence=2), now_ns=120).hold)

    def test_clear_without_resume_stays_latched(self):
        self.gate.apply(self.raw, replace(self.clear, severity="STOP_REQUIRED"), now_ns=100)
        result = self.gate.apply(replace(self.raw, sequence=2), replace(self.clear, sequence=2, command_sequence=2), now_ns=110)
        self.assertEqual(result.reason, "COLLISION_STOP_LATCHED")

    def test_unknown_is_zero_caution_scales_and_cannot_accelerate(self):
        scaled = replace(self.clear, severity="CAUTION", speed_scale=.5)
        self.assertEqual(self.gate.apply(self.raw, scaled, now_ns=100).velocity, (.15, .05, -.1))
        bad = replace(scaled, sequence=2, command_sequence=2, speed_scale=2.)
        self.assertTrue(self.gate.apply(replace(self.raw, sequence=2), bad, now_ns=110).hold)
        unknown = replace(scaled, sequence=3, command_sequence=3, severity="UNKNOWN")
        self.assertEqual(self.gate.apply(replace(self.raw, sequence=3), unknown, now_ns=120).reason, "UNKNOWN")

    def test_browser_disconnected_watchdog_zero_and_bounded_history(self):
        self.gate.apply(self.raw, self.clear, now_ns=100)
        self.assertFalse(self.gate.tick(now_ns=199).hold)
        self.assertEqual(self.gate.tick(now_ns=200).velocity, (0., 0., 0.))
        for n in range(100):
            self.gate.tick(now_ns=300+n)
        self.assertLessEqual(len(self.sink.history), 32)

    def test_wrong_sink_forbidden(self):
        with self.assertRaises(TypeError):
            CommandGate(object(), self.binding)
