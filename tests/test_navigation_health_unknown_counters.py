"""Missing runtime observations stay unknown in public navigation health."""
import unittest

from test_ros_navigation_gateway import gateway


SENSOR_COUNTERS = (
    "translation_jump_count",
    "heading_jump_count",
    "input_points",
    "accepted_points",
    "fresh_sequence_count",
)


class SensorReportedCountersTests(unittest.TestCase):
    def test_active_navigation_without_telemetry_reports_unknown_counters(self):
        navigation = gateway()
        navigation._navigation["active"] = True

        snapshot = navigation.runtime_snapshot()

        health = snapshot["localization_health"]
        self.assertEqual(health["reason_code"], "TELEMETRY_MISSING")
        for key in SENSOR_COUNTERS:
            with self.subTest(key=key):
                self.assertIsNone(health["metrics"][key])
        self.assertEqual(health["metrics"]["costmap_clear_count"], 0)
        self.assertEqual(health["metrics"]["goal_startup_zero_feedback_count"], 0)
        self.assertEqual(health["metrics"]["goal_ignored_zero_feedback_count"], 0)

    def test_missing_null_and_invalid_counter_types_remain_unknown(self):
        navigation = gateway()
        missing = object()
        invalid_values = (missing, None, True, False, "0", "bad", 0., 1.5,
                          -1, float("nan"), float("inf"), [], {})
        for value in invalid_values:
            runtime_health = {} if value is missing else dict.fromkeys(SENSOR_COUNTERS, value)
            with self.subTest(value=value):
                metrics = navigation._localization_metrics(runtime_health, 100.)
                self.assertEqual({key: metrics[key] for key in SENSOR_COUNTERS},
                                 dict.fromkeys(SENSOR_COUNTERS))

    def test_observed_integer_zero_and_positive_counts_are_preserved(self):
        navigation = gateway()
        navigation._navigation_clear_count = 7
        for value in (0, 23):
            with self.subTest(value=value):
                metrics = navigation._localization_metrics(dict.fromkeys(SENSOR_COUNTERS, value), 100.)
                for key in SENSOR_COUNTERS:
                    self.assertIs(type(metrics[key]), int)
                    self.assertEqual(metrics[key], value)
                self.assertEqual(metrics["costmap_clear_count"], 7)


if __name__ == "__main__":
    unittest.main()
