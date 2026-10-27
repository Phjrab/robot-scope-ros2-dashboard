import unittest
from observation import Observer, Sample


class ObservationTests(unittest.TestCase):
    def test_predicted_stop_continues_without_command_or_restart(self):
        o = Observer(5)
        for t in range(5):
            r = o.step(Sample(t, predicted_collision=True))
            self.assertTrue(r['continue_observation'])
            self.assertFalse(r['restart_goal'])
            self.assertEqual(r['command_authority'], 'NONE')
        self.assertEqual(o.step(Sample(5))['terminal_reason'], 'OBSERVATION_TIMEOUT')

    def test_aborted_and_canceled_actions_are_observed_not_restarted(self):
        for status in ('ABORTED', 'CANCELED'):
            o = Observer(4)
            self.assertTrue(o.step(Sample(1, action_status=status))['continue_observation'])
            self.assertEqual(o.step(Sample(4, action_status=status))['terminal_reason'], 'OBSERVATION_TIMEOUT')

    def test_raw_contact_is_sticky_terminal(self):
        o = Observer(10)
        r = o.step(Sample(1, raw_contact=True))
        self.assertEqual(r['terminal_reason'], 'RAW_CONTACT')
        self.assertEqual(o.step(Sample(2, action_status='SUCCEEDED', goal_verified=True)), r)

    def test_padded_violation_not_contact_but_not_safety_pass(self):
        o = Observer(5)
        r = o.step(Sample(1, padded_violation=True))
        self.assertTrue(r['continue_observation'])
        self.assertEqual(r['safety_evaluation'], 'FAIL_PADDED_ENVELOPE')
        self.assertEqual(o.step(Sample(2, action_status='SUCCEEDED', goal_verified=True))['safety_evaluation'], 'FAIL_PADDED_ENVELOPE')

    def test_real_goal_terminates_but_not_navigation_acceptance(self):
        r = Observer(5).step(Sample(1, action_status='SUCCEEDED', goal_verified=True))
        self.assertEqual(r['terminal_reason'], 'GOAL_REACHED')
        self.assertFalse(r['navigation_accepted'])

    def test_unverified_goal_is_error(self):
        self.assertEqual(Observer(5).step(Sample(1, action_status='SUCCEEDED'))['terminal_reason'], 'GOAL_EVIDENCE_ERROR')

    def test_infrastructure_error_and_operator_cancel(self):
        for sample, reason in [(Sample(1, infrastructure_error='SENSOR_STALE'), 'INFRASTRUCTURE_ERROR'),
                               (Sample(1, cancelled_by_operator=True), 'OPERATOR_CANCEL')]:
            self.assertEqual(Observer(5).step(sample)['terminal_reason'], reason)

    def test_unknown_contact_remains_missing(self):
        o = Observer(5)
        o.step(Sample(0, raw_contact=None))
        self.assertEqual(o.step(Sample(5))['safety_evaluation'], 'INPUT_REQUIRED')

    def test_zero_motion_timeout_not_success(self):
        o = Observer(10)
        o.step(Sample(0))
        r = o.step(Sample(10))
        self.assertFalse(r['goal_reached'])
        self.assertFalse(r['navigation_accepted'])
        self.assertEqual(r['mean_sampled_translation_speed_mps'], 0)

    def test_speed_is_reported_not_forced(self):
        o = Observer(10)
        o.step(Sample(0, translation_speed_mps=.2))
        r = o.step(Sample(2, translation_speed_mps=.1))
        self.assertAlmostEqual(r['mean_sampled_translation_speed_mps'], .15)
        self.assertEqual(r['command_authority'], 'NONE')

    def test_invalid_clock_or_budget_rejected(self):
        for limit in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError): Observer(limit)
        o = Observer(5)
        o.step(Sample(2))
        for t in (1, 2, float('nan')):
            with self.assertRaises(ValueError): o.step(Sample(t))

    def test_omitted_contact_is_unknown(self):
        self.assertEqual(Observer(5).step(Sample(1))["safety_evaluation"], "INPUT_REQUIRED")

    def test_success_at_or_after_budget_times_out(self):
        for t in (5, 20):
            r = Observer(5).step(Sample(t, action_status="SUCCEEDED", goal_verified=True, raw_contact=False))
            self.assertEqual(r["terminal_reason"], "OBSERVATION_TIMEOUT")
            self.assertFalse(r["goal_reached"])

    def test_contact_precedes_success(self):
        r = Observer(5).step(Sample(1, raw_contact=True, action_status='SUCCEEDED', goal_verified=True))
        self.assertEqual(r['terminal_reason'], 'RAW_CONTACT')
        self.assertFalse(r['goal_reached'])


if __name__ == '__main__': unittest.main()
