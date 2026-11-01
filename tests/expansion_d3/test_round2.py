import copy
import unittest

from robot_dashboard.collision_geometry_core import assess
from robot_dashboard.collision_geometry_core.contracts import c4_constraint
from experiments.expansion_20261029.d3_collision_sim.fixtures import (
    coverage_evidence,
    frame,
    model,
    state,
)


class Round2Tests(unittest.TestCase):
    def calculate(self, coverage=None, now=1_000_000_000):
        s = state()
        return assess(
            model(),
            s,
            frame(),
            now_stamp_ns=now,
            now_clock_domain=s["clock_domain"],
            coverage=coverage,
        )

    def test_empty_or_old_magic_label_is_not_coverage(self):
        for evidence in (None, "COMPLETE_SYNTHETIC", {}, {"complete_for_motion": True}):
            a = self.calculate(evidence)
            self.assertEqual(a["severity"], "UNKNOWN")
            self.assertEqual(
                a["freshness"]["coverage"]["status"], "MOTION_COVERAGE_NOT_QUALIFIED"
            )

    def test_limited_volume_clock_and_epoch_coverage(self):
        valid = coverage_evidence()
        self.assertEqual(self.calculate(valid)["severity"], "CLEAR")
        for key, value in [
            ("volume_max", [0, 0, 0]),
            ("source_epoch", "other"),
            ("clock_domain", "other"),
            ("valid_until_ns", "999999999"),
            ("source_refs", []),
            ("evidence_kind", "REPLAY"),
            ("horizon_s", -1),
        ]:
            bad = copy.deepcopy(valid)
            bad[key] = value
            self.assertEqual(self.calculate(bad)["severity"], "UNKNOWN")

    def test_source_interval_does_not_restart_ttl(self):
        a, b = self.calculate(now=1_000_000_000), self.calculate(now=1_100_000_000)
        self.assertEqual(a["schema_version"], "0.2")
        self.assertIsInstance(a["received_monotonic_ns"], str)
        self.assertEqual(a["validity_interval"], {})  # no host mapping invented
        self.assertEqual(
            a["freshness"]["source_validity_interval"],
            b["freshness"]["source_validity_interval"],
        )

    def test_advisory_is_explicit_and_does_not_call_consumer(self):
        seen = []
        a = self.calculate()
        result = c4_constraint(
            a,
            validate_canonical=lambda x: seen.append(x),
            consume=None,
            binding=None,
            command_sequence=1,
            enforcement_mode="ADVISORY_ONLY",
        )
        self.assertIsNone(result)
        self.assertEqual(seen, [a])
        with self.assertRaises(ValueError):
            c4_constraint(
                a,
                validate_canonical=lambda x: None,
                consume=None,
                binding=None,
                command_sequence=1,
                enforcement_mode="AUTO_DOWNGRADE",
            )


if __name__ == "__main__":
    unittest.main()
