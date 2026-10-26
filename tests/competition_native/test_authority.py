from dataclasses import replace
import unittest

from robot_dashboard.mission_routes.competition_native.authority import Command, CommandBoundary
from robot_dashboard.mission_routes.competition_native.contracts import ConstraintRequest
from .helpers import Rig


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.scope = Rig().scope
        self.gate = CommandBoundary(self.scope, owners=("mission", "safety"))
        self.seq = 0
        self.req = 0

    def constrain(self, mode="RELEASE", owner="mission", now=0):
        self.req += 1
        request = ConstraintRequest(self.scope, str(self.req), mode, "test", sequence=self.req)
        self.assertTrue(self.gate.apply_constraint(owner, request, now))
        return request

    def command(self, *, now=0, receipt=None, **kwargs):
        self.seq += 1
        cmd = Command(self.scope, self.seq, now if receipt is None else receipt, (0.7, -0.3, 0.4))
        return self.gate.evaluate(cmd, now=now, goal_scope=self.scope, goal_receipt_s=now,
                                  inputs_fresh=True, **kwargs)

    def test_all_owners_release_required_and_hold_has_no_expiry_open(self):
        self.constrain()
        self.assertEqual(self.command()[1], "HOLD")
        self.constrain(owner="safety")
        self.assertEqual(self.command()[1], "TRACKING")
        self.constrain("HOLD", now=1)
        self.assertEqual(self.command(now=100)[1], "HOLD")

    def test_precedence_estop_collision_hold_terrain_tracking(self):
        self.constrain()
        self.constrain(owner="safety")
        self.assertEqual(self.command(estop=True, collision=True, terrain_caps=(0, 0, 0))[1], "ESTOP")
        self.assertEqual(self.command(collision=True)[1], "COLLISION")
        self.assertEqual(self.command(terrain_caps=(0.2, 0.1, 0.3)), ((0.2, -0.1, 0.3), "TERRAIN_CAP"))
        self.constrain("HOLD")
        self.assertEqual(self.command(terrain_caps=(0.2, 0.1, 0.3))[0], (0, 0, 0))

    def test_release_never_replays_held_command(self):
        self.constrain("HOLD")
        self.constrain(owner="safety")
        cmd = Command(self.scope, 1, 0, (1, 0, 0))
        self.assertEqual(self.gate.evaluate(cmd, now=0)[0], (0, 0, 0))
        self.constrain(now=0.1)
        result = self.gate.evaluate(cmd, now=0.1, goal_scope=self.scope, goal_receipt_s=0.1, inputs_fresh=True)
        self.assertEqual(result[0], (0, 0, 0))
        self.seq = 1
        self.assertEqual(self.command(now=0.1)[1], "TRACKING")

    def test_quarter_second_ttl_boundary_is_distinct_from_fixture_gap(self):
        self.constrain()
        self.constrain(owner="safety")
        self.assertEqual(self.command(now=0.25, receipt=0)[1], "TRACKING")
        self.assertEqual(self.command(now=0.250001, receipt=0)[0], (0, 0, 0))

    def test_release_without_current_goal_or_new_generation_command_is_zero(self):
        self.constrain()
        self.constrain(owner="safety")
        cmd = Command(replace(self.scope, goal_generation=2), 1, 0, (1, 0, 0))
        self.assertEqual(self.gate.evaluate(cmd, now=0, inputs_fresh=True)[0], (0, 0, 0))
        cmd = replace(cmd, scope=self.scope, sequence=2)
        self.assertEqual(self.gate.evaluate(cmd, now=0, inputs_fresh=True)[0], (0, 0, 0))

    def test_duplicate_release_does_not_reset_command_barrier(self):
        request = self.constrain()
        self.constrain(owner="safety")
        self.command(now=0.1)
        self.assertTrue(self.gate.apply_constraint("mission", request, 0.2))
        self.assertEqual(self.gate.release_time, 0)

    def test_reconnect_requires_new_boundary(self):
        self.constrain()
        self.constrain(owner="safety")
        self.gate.retire()
        self.assertFalse(self.gate.apply_constraint("mission", ConstraintRequest(self.scope, "new", "RELEASE", "test"), 1))
        self.assertEqual(self.command(now=1)[0], (0, 0, 0))

    def test_unknown_owner_and_generation_revoke_release(self):
        self.constrain()
        self.constrain(owner="safety")
        req = ConstraintRequest(replace(self.scope, goal_generation=2), "bad", "RELEASE", "test")
        self.assertFalse(self.gate.apply_constraint("mission", req, 0))
        self.assertEqual(self.command()[0], (0, 0, 0))

    def test_late_release_cannot_override_newer_hold(self):
        self.constrain(owner="safety")
        hold = ConstraintRequest(self.scope, "new-hold", "HOLD", "stop", sequence=10)
        release = ConstraintRequest(self.scope, "late-release", "RELEASE", "old", sequence=9)
        self.assertTrue(self.gate.apply_constraint("mission", hold, 1))
        self.assertFalse(self.gate.apply_constraint("mission", release, 1.1))
        self.assertEqual(self.command(now=1.1)[1], "HOLD")
