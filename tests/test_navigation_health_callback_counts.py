"""Runtime envelope parsing must not invent unreported sensor counts."""
import json
import time
import unittest
from types import SimpleNamespace

from test_localization_gateway_generation import payload
from test_ros_navigation_gateway import gateway
from robot_dashboard.localization_health import classify_localization_health


REPORTED_COUNTS = ('input_points', 'accepted_points', 'translation_jump_count', 'heading_jump_count')


class RuntimeReportedCountTests(unittest.TestCase):
    def send(self, navigation, value):
        navigation._navigation_runtime_health_callback(SimpleNamespace(data=json.dumps(value)))

    def test_missing_counts_stay_unknown_and_do_not_change_readiness_policy(self):
        navigation = gateway()
        for sequence in (1, 2, 3):
            value = payload(sequence)
            value.update(localized=True, odom_to_base_age_s=.02, map_to_odom_age_s=.02,
                         odometry_frequency_hz=100.)
            for key in REPORTED_COUNTS:
                value.pop(key, None)
            self.send(navigation, value)
        health = navigation._navigation_runtime_health_snapshot(time.monotonic())
        self.assertIsNone(health['error'])
        for key in REPORTED_COUNTS:
            with self.subTest(key=key):
                self.assertIsNone(health[key])
        self.assertEqual(health['fresh_sequence_count'], 3)
        metrics = navigation._localization_metrics(health, time.monotonic())
        old_metrics = {**metrics, **dict.fromkeys(REPORTED_COUNTS, 0)}
        def classify(value):
            return classify_localization_health(value, active=True, localized=True,
                thresholds=navigation._health_thresholds, rate_policy=navigation._rate_policy)
        self.assertEqual(classify(metrics), classify(old_metrics))
        self.assertNotEqual(classify(metrics)['state'], 'READY')

    def test_reported_zero_is_preserved_and_fresh_sequence_is_still_owned_by_gateway(self):
        navigation = gateway(); value = payload(1)
        value.update(dict.fromkeys(REPORTED_COUNTS, 0))
        self.send(navigation, value)
        health = navigation._navigation_runtime_health_snapshot(time.monotonic())
        self.assertIsNone(health['error'])
        for key in REPORTED_COUNTS:
            self.assertIs(type(health[key]), int)
            self.assertEqual(health[key], 0)
        self.assertEqual(health['fresh_sequence_count'], 1)

    def test_null_invalid_and_inconsistent_counts_are_not_coerced_to_valid_reports(self):
        for key in REPORTED_COUNTS:
            for invalid in (None, True, '0', .5, -1):
                navigation = gateway(); value = payload(1)
                value.update(translation_jump_count=0, heading_jump_count=0)
                value[key] = invalid
                with self.subTest(key=key, invalid=invalid):
                    self.send(navigation, value)
                    health = navigation._navigation_runtime_health_snapshot(time.monotonic())
                    self.assertIsNotNone(health.get('error'))
                    self.assertFalse(health['fresh'])
                    metrics = navigation._localization_metrics(health, time.monotonic())
                    self.assertTrue(all(metrics[name] is None for name in REPORTED_COUNTS))

    def test_missing_input_does_not_admit_a_positive_accepted_count(self):
        navigation = gateway(); value = payload(1); value.pop('input_points')
        self.send(navigation, value)
        self.assertIsNotNone(navigation._navigation_runtime_health.get('error'))
        self.assertEqual(navigation._navigation_runtime_health_received, 0.)


if __name__ == '__main__':
    unittest.main()
