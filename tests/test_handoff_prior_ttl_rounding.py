"""Exact TTL boundary must use the same monotonic arithmetic as admission."""
import copy
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_navigation_operator_prior_handoff as handoff_fixture
from robot_dashboard.application import operational_navigation
from robot_dashboard.relocalization import handoff_policy


class PriorTTLBoundaryTests(unittest.TestCase):
    def setUp(self):
        fixture = handoff_fixture.ConditionalHandoffTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        confirmed = fixture.confirm(True)
        fixture.h.finish_stop(confirmed['handoff_id'])
        fixture.h.manager.preflight(fixture.h.map_id, fixture.h.revision)
        self.fixture = fixture
        self.geometry = copy.deepcopy(fixture.h.manager.selected['seed_geometry'])
        self.bundle = fixture.h.manager.selected

    def validate_at(self, accepted, expiry, deadline, now=128.0):
        proof = self.geometry['handoff']
        proof['observation_started_monotonic_s'] = 7.
        proof['operator_prior_resolution']['accepted_monotonic_s'] = accepted
        proof['operator_prior_resolution']['expires_monotonic_s'] = expiry
        proof['expires_monotonic_s'] = deadline
        with patch.object(handoff_policy, 'time', SimpleNamespace(monotonic=lambda: now)):
            handoff_policy.validate_handoff(self.geometry, self.bundle)

    def test_generated_exact_ttl_can_round_up_in_subtraction(self):
        for accepted, expected_expiry, now, deadline in (
                (127.99999999999999, 248., 128., 200.),
                (8.000000000000016, 128.00000000000003, 8.5, 100.)):
            with self.subTest(accepted=accepted):
                expiry = accepted + 120.
                self.assertEqual(expiry, expected_expiry)
                self.assertEqual(expiry - accepted, 120.00000000000001)
                self.validate_at(accepted, expiry, deadline, now)

    def test_future_overlong_and_outliving_handoff_remain_blocked(self):
        accepted = 127.99999999999999
        expiry = accepted + 120.
        cases = [
            ('one_ulp_over', accepted, math.nextafter(expiry, math.inf), 200., 128.),
            ('accepted_future', 129., 249., 200., 128.),
            ('deadline_after_prior', 90., 210., 211., 128.),
            ('nonfinite_expiry', accepted, math.inf, 200., 128.),
            ('nan_expiry', accepted, math.nan, 200., 128.),
            ('negative_inf_expiry', accepted, -math.inf, 200., 128.),
            ('nan_accepted', math.nan, expiry, 200., 128.),
            ('infinite_accepted', math.inf, expiry, 200., 128.),
            ('negative_inf_accepted', -math.inf, expiry, 200., 128.),
            ('bool_accepted', True, expiry, 200., 128.),
            ('bool_expiry', accepted, True, 200., 128.),
            ('equal_expiry', accepted, accepted, 200., 128.),
        ]
        for name, start, end, deadline, now in cases:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'INITIAL_GEOMETRY_PROVENANCE_REQUIRED'):
                self.validate_at(start, end, deadline, now)
        with self.assertRaisesRegex(ValueError, 'HANDOFF_EXPIRED'):
            self.validate_at(accepted, expiry, 128., 128.)

    def test_real_preflight_accepts_the_producer_rounded_deadline(self):
        fixture = self.fixture
        proof = fixture.h.manager.selected['seed_geometry']['handoff']
        accepted = 127.99999999999999
        started = 126.
        proof['observation_started_monotonic_s'] = started
        fixture.h.manager._handoffs[proof['handoff_id']]['session_started'] = started
        with fixture.h.session._lock:
            fixture.h.session._handoff_receipts[proof['handoff_id']]['started'] = started
        proof['operator_prior_resolution']['accepted_monotonic_s'] = accepted
        proof['operator_prior_resolution']['expires_monotonic_s'] = accepted + 120.
        proof['expires_monotonic_s'] = 200.
        clock = SimpleNamespace(monotonic=lambda: 128.)
        with patch.object(handoff_policy, 'time', clock), patch.object(operational_navigation, 'time', clock):
            fixture.h.manager.preflight(fixture.h.map_id, fixture.h.revision)

if __name__ == '__main__':
    unittest.main()
