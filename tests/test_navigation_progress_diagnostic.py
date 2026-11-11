"""Robot-free diagnostic checks; a reproduced product defect is not a pass."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import reproduce_navigation_progress as diagnostic
from test_goal_precision import message


class NavigationProgressDiagnosticTests(unittest.TestCase):
    def test_small_legitimate_goal_is_not_discarded_by_distance_cutoff(self):
        nav, result = diagnostic.sequence(
            [.0416856, .030, .015, .008], [100, 100.2, 100.4, 100.6], snapshot_at=100.7)
        self.assertEqual(result["initial_distance_m"], .042)
        self.assertEqual(result["health"], "READY")
        self.assertGreater(result["display_fraction_formula"], .8)
        self.assertGreater(nav._navigation_goal_progress["last_progress_at"], 100.4)

    def test_large_oscillation_does_not_restart_stall_deadline(self):
        nav = diagnostic.gateway()
        diagnostic.Fixture._prepare_active_goal(nav)
        for index in range(32):
            diagnostic.feedback(nav, .838 + (.060 if index % 2 else 0), 100 + index * .1)
        self.assertEqual(nav._navigation_goal_progress["last_progress_at"], 100)
        self.assertEqual(diagnostic.snapshot(nav, 103.1)["reason"], "GOAL_PROGRESS_TOO_LOW")

    def test_generation_and_goal_id_each_reject_stale_feedback(self):
        nav, _ = diagnostic.sequence([.838], [100])
        generation = nav._navigation_goal_generation
        goal_id = nav._navigation["goal"]["goal_id"]
        for supplied_generation, supplied_id in [(generation - 1, goal_id), (generation, "old")]:
            with self.subTest(generation=supplied_generation, goal_id=supplied_id):
                before = copy.deepcopy((nav._navigation, nav._navigation_goal_progress))
                diagnostic.feedback(nav, .001, 100.1, supplied_generation, supplied_id)
                self.assertEqual((nav._navigation, nav._navigation_goal_progress), before)

    def test_fresh_matching_plan_alone_is_not_feedback_consumption(self):
        nav = diagnostic.gateway()
        diagnostic.Fixture._prepare_active_goal(nav)
        nav._navigation["goal"]["state"] = "idle"
        diagnostic.new_goal(nav, 100)
        diagnostic.feedback(nav, .838, 100.1)
        before = copy.deepcopy(nav._navigation_goal_progress)
        endpoint = message(100.2, x=.801)
        with patch.object(nav, "_goal_precision_clock", return_value=100_200_000_000), patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic", return_value=100.2
        ):
            nav._goal_precision_plan_callback(SimpleNamespace(header=endpoint.header, poses=[endpoint]))
        self.assertEqual(nav._goal_precision.plan["request_error"]["xy_m"], 0)
        self.assertEqual(nav._goal_precision.plan["association"], "OBSERVED_DURING_GOAL_NO_ACTION_UUID")
        self.assertEqual(nav._navigation_goal_progress, before)

    def test_partial_reproduction_and_broken_controls_never_exit_success(self):
        broken = dict(display_fraction_formula=0, health="DEGRADED", reason="GOAL_PROGRESS_TOO_LOW")
        normal = dict(display_fraction_formula=.4, health="READY", reason="HEALTHY")
        names = ["small_positive_then_approach", "restart_small_positive_then_approach",
                 "accepted_goal_with_matching_plan"]
        for reproduced_name in names:
            with self.subTest(reproduced_name=reproduced_name):
                cases = {name: broken if name == reproduced_name else normal for name in names}
                result, code, reproduced = diagnostic.diagnostic_verdict(cases, True)
                self.assertEqual((result, code, reproduced), ("PARTIALLY_REPRODUCED", 1, [reproduced_name]))
        cases = dict.fromkeys(names, broken)
        self.assertEqual(diagnostic.diagnostic_verdict(cases, True)[:2], ("REPRODUCED", 1))
        self.assertEqual(diagnostic.diagnostic_verdict(cases, False)[:2], ("INCONCLUSIVE", 2))
        cases = dict.fromkeys(names, normal)
        self.assertEqual(diagnostic.diagnostic_verdict(cases, True), ("NOT_REPRODUCED", 0, []))
        self.assertEqual(diagnostic.diagnostic_verdict(cases, False)[:2], ("INCONCLUSIVE", 2))


if __name__ == "__main__":
    unittest.main()
