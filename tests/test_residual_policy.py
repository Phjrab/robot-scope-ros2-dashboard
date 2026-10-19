"""Stored residual policy checks; no registration or operational gate changes."""

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import json
import math
import unittest

from robot_dashboard.relocalization.residual_policy import (
    ORIGINAL_RESIDUAL_POLICY,
    PROVISIONAL_RESIDUAL_POLICY,
    evaluate_residual,
)


class ResidualPolicyTests(unittest.TestCase):
    def test_provisional_boundary_is_inclusive_without_rounding_or_epsilon(self):
        for value, expected in (
            (math.nextafter(0.10, -math.inf), True),
            (0.10, True),
            (math.nextafter(0.10, math.inf), False),
        ):
            with self.subTest(value=value):
                result = evaluate_residual(value, policy=PROVISIONAL_RESIDUAL_POLICY)
                self.assertEqual(result.rmse_m, value)
                self.assertIs(result.residual_passed, expected)

    def test_original_boundary_and_original_decision_are_preserved(self):
        for value, expected in (
            (math.nextafter(0.05, -math.inf), True),
            (0.05, True),
            (math.nextafter(0.05, math.inf), False),
        ):
            with self.subTest(value=value):
                original = evaluate_residual(value, policy=ORIGINAL_RESIDUAL_POLICY)
                provisional = evaluate_residual(value, policy=PROVISIONAL_RESIDUAL_POLICY)
                self.assertIs(original.residual_passed, expected)
                self.assertIs(provisional.original_residual_passed, expected)
                self.assertEqual(provisional.original_policy.max_rmse_m, 0.05)

    def test_stored_residual_pass_does_not_evaluate_overall_acceptance(self):
        stored_rmse = 0.07044731830991433
        result = evaluate_residual(stored_rmse, policy=PROVISIONAL_RESIDUAL_POLICY)
        self.assertEqual(result.rmse_m, stored_rmse)
        self.assertTrue(result.residual_passed)
        self.assertFalse(result.original_residual_passed)
        data = result.as_dict()
        self.assertFalse(data["overall_candidate_acceptance_evaluated"])
        self.assertIsNone(data["overall_candidate_accepted"])
        policy = data["policy"]
        self.assertEqual(policy["source_policy_id"], data["original_policy"]["policy_id"])
        self.assertNotEqual(policy["policy_id"], policy["source_policy_id"])
        self.assertEqual(policy["qualifier"], "PROVISIONAL_RESIDUAL_ONLY")
        self.assertTrue(policy["provisional"])
        self.assertTrue(policy["observation_only"])
        self.assertTrue(policy["no_accuracy_claim"])
        self.assertFalse(policy["accuracy_verified"])
        self.assertEqual(json.loads(json.dumps(data, allow_nan=False)), data)

    def test_zero_is_valid_but_invalid_residuals_are_rejected(self):
        self.assertTrue(evaluate_residual(0, policy=PROVISIONAL_RESIDUAL_POLICY).residual_passed)
        for invalid in (True, False, None, "0.10", [], {}, 0.1j,
                        -0.01, math.nan, math.inf, -math.inf, 10**1000):
            with self.subTest(value=repr(invalid)), self.assertRaises(ValueError):
                evaluate_residual(invalid, policy=PROVISIONAL_RESIDUAL_POLICY)

    def test_numeric_conversion_cannot_round_an_above_threshold_value_down(self):
        just_above = Fraction.from_float(0.10) + Fraction(1, 10**100)
        self.assertEqual(float(just_above), 0.10)
        with self.assertRaises(ValueError):
            evaluate_residual(just_above, policy=PROVISIONAL_RESIDUAL_POLICY)

    def test_only_metres_are_accepted_without_unit_conversion(self):
        self.assertTrue(evaluate_residual(0.10, policy=PROVISIONAL_RESIDUAL_POLICY, unit="m").residual_passed)
        self.assertFalse(evaluate_residual(10, policy=PROVISIONAL_RESIDUAL_POLICY, unit="m").residual_passed)
        for unit in ("cm", "mm", "M", "metres", "", None):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                evaluate_residual(10, policy=PROVISIONAL_RESIDUAL_POLICY, unit=unit)

    def test_fixed_policies_and_evaluation_are_immutable(self):
        result = evaluate_residual(0.10, policy=PROVISIONAL_RESIDUAL_POLICY)
        with self.assertRaises(FrozenInstanceError):
            PROVISIONAL_RESIDUAL_POLICY.max_rmse_m = 0.20
        with self.assertRaises(FrozenInstanceError):
            result.residual_passed = False
        changed = replace(PROVISIONAL_RESIDUAL_POLICY, max_rmse_m=0.20)
        with self.assertRaises(ValueError):
            evaluate_residual(0.15, policy=changed)
        data = result.as_dict()
        data["policy"]["max_rmse_m"] = 0.20
        self.assertEqual(result.policy.max_rmse_m, 0.10)
        with self.assertRaises(TypeError):
            evaluate_residual(0.10)


if __name__ == "__main__":
    unittest.main()
