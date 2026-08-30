import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wp07AcceptanceContractTests(unittest.TestCase):
    def test_wp07_document_separates_ci_from_field_evidence(self):
        source = (ROOT / "docs" / "WP07_FAIL_CLOSED_ACCEPTANCE.md").read_text(
            encoding="utf-8"
        )
        for value in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
            self.assertIn(value, source)
        self.assertIn("robot was deliberately powered off", source)
        self.assertIn("none are inferred as `PASS`", source)
        self.assertIn("physical remote/E-stop always has priority", source)

    def test_wp07_document_keeps_runtime_safety_bounds_unchanged(self):
        source = (ROOT / "docs" / "WP07_FAIL_CLOSED_ACCEPTANCE.md").read_text(
            encoding="utf-8"
        )
        for invariant in (
            "runtime timeout",
            "speed limit",
            "graph cardinality",
            "lease rule",
            "Dataset reserve",
            "navigation freshness gate",
        ):
            self.assertIn(invariant, source)
        self.assertIn("does not authorize", source)

    def test_hardware_procedure_lists_every_new_fixed_scenario(self):
        procedure = (ROOT / "docs" / "HARDWARE_ACCEPTANCE.md").read_text(
            encoding="utf-8"
        )
        for scenario in (
            "supervised.robot_wifi_disconnect",
            "supervised.realsense_source_stall",
            "supervised.realsense_relay_restart",
            "supervised.perception_process_stop",
            "supervised.perception_result_freeze",
            "supervised.model_hash_mismatch",
            "supervised.model_activation_rollback",
            "supervised.preview_consumer_disconnect",
            "supervised.decimated_pointcloud_load",
            "supervised.raw_pointcloud_overload_abort",
            "supervised.dashboard_receiver_restart",
            "supervised.competition_lock_mutation_rejection",
        ):
            self.assertIn(scenario, procedure)


if __name__ == "__main__":
    unittest.main()
