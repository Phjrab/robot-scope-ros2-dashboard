from unittest.mock import Mock
import unittest

from robot_dashboard.navigation_operator import cancel_current_goal


class CancelOperatorTests(unittest.TestCase):
    def test_current_goal_id_is_pinned_without_automatic_retry(self):
        api = Mock(side_effect=[{'goal': {'state': 'active', 'goal_id': 'a' * 32}},
                                {'goal': {'state': 'canceling', 'goal_id': 'a' * 32}}])
        result = cancel_current_goal(api)
        self.assertTrue(result['requested'])
        self.assertFalse(result['measured_stop_confirmed'])
        self.assertEqual(api.call_args.args, ('POST', '/api/v1/navigation/cancel', {'goal_id': 'a' * 32}))

    def test_422_stale_conflict_and_transport_failure_are_not_success(self):
        for failure in ['HTTP 422', 'HTTP 409', 'transport unavailable']:
            api = Mock(side_effect=[{'goal': {'state': 'active', 'goal_id': 'b' * 32}}, RuntimeError(failure)])
            with self.assertRaisesRegex(RuntimeError, failure):
                cancel_current_goal(api)
            self.assertEqual(api.call_count, 2)

    def test_missing_id_idle_and_duplicate_terminal_do_not_cancel(self):
        for state in ['idle', 'succeeded', 'canceled', 'failed']:
            api = Mock(return_value={'goal': {'state': state, 'goal_id': 'a' * 32}})
            self.assertFalse(cancel_current_goal(api)['requested'])
            self.assertEqual(api.call_count, 1)
        api = Mock(return_value={'goal': {'state': 'active'}})
        with self.assertRaises(ValueError):
            cancel_current_goal(api)
        self.assertEqual(api.call_count, 1)
