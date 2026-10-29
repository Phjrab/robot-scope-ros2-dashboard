"""SOFTWARE_TEST: bounded production diagnostics, without ROS/native claims."""
from types import SimpleNamespace as NS
import unittest

from robot_dashboard.navigation_policy import POLICY_DIAGNOSTICS_SCHEMA, POLICY_ENDPOINTS
from robot_dashboard.ros.policy_readback import PARAMETERS, RosPolicyReadback


class Harness:
    def __init__(self):
        self.now = 10.0
        self.authority_duration = 0.0
        self.dispatch_duration = 0.0
        self.authority_failure = False
        self.ready = True
        self.fail_at = None
        self.requests = []
        self.futures = []
        self.observer = RosPolicyReadback(NS(), clock=lambda: self.now)
        self.observer._authorities = self.authorities
        self.observer._declarations = (0, {name: "a" * 48 for name in PARAMETERS},
            {name: frozenset(keys) for name, keys in PARAMETERS.items()})
        self.observer._param_type = NS(Request=NS)
        self.observer._state_type = NS(Request=NS)
        self.observer._clients = {name: (self.client(name, "parameters"), self.client(name, "state"))
                                  for name in PARAMETERS}

    def authorities(self):
        self.now += self.authority_duration
        if self.authority_failure:
            raise ValueError("POLICY_AUTHORITY_NOT_UNIQUE")
        return {name: "a" * 48 for name in PARAMETERS}

    def client(self, name, kind):
        harness = self

        class Future:
            def __init__(self):
                self.complete, self.is_cancelled, self.cancel_calls = False, False, 0

            def done(self):
                return self.complete or self.is_cancelled

            def cancelled(self):
                return self.is_cancelled

            def cancel(self):
                self.cancel_calls += 1
                self.is_cancelled = True

            def result(self):
                return (NS(values=[NS(type=4, string_value="fixture") for _ in PARAMETERS[name]])
                        if kind == "parameters" else NS(current_state=NS(id=3)))

        class Client:
            def service_is_ready(self):
                return harness.ready

            def call_async(self, request):
                harness.now += harness.dispatch_duration
                harness.requests.append((name, kind))
                if len(harness.requests) == harness.fail_at:
                    raise RuntimeError("private/path must never be exported")
                future = Future()
                harness.futures.append(future)
                return future

        return Client()


class ReadbackDiagnosticsTests(unittest.TestCase):
    def test_late_poll_of_completed_futures_still_times_out_without_cancelling(self):
        harness = Harness()
        harness.observer.tick()
        for future in harness.futures:
            future.complete = True
        harness.now += .501
        harness.observer.tick()
        value = harness.observer.snapshot()
        diagnostic = value["diagnostics"]
        self.assertEqual(value["reason"], "POLICY_READBACK_TIMEOUT")
        self.assertEqual(value["parameters"], {})
        self.assertEqual(diagnostic["schema"], POLICY_DIAGNOSTICS_SCHEMA)
        self.assertEqual(diagnostic["outcome"], "failed")
        self.assertAlmostEqual(diagnostic["batch_age_s"], .501)
        self.assertAlmostEqual(diagnostic["tick_gap_s"], .501)
        self.assertEqual(set(diagnostic["endpoints"]), set(POLICY_ENDPOINTS))
        for entry in diagnostic["endpoints"].values():
            self.assertEqual(entry, dict(dispatched=True, done=True, cancelled=False))
        self.assertTrue(all(future.cancel_calls == 0 for future in harness.futures))

    def test_pending_endpoint_is_named_before_cleanup_cancels_it(self):
        harness = Harness()
        harness.observer.tick()
        for future in harness.futures:
            future.complete = True
        harness.futures[3].complete = False
        harness.now += .501
        harness.observer.tick()
        endpoints = harness.observer.snapshot()["diagnostics"]["endpoints"]
        pending = {name for name, entry in endpoints.items() if entry["done"] is False}
        self.assertEqual(pending, {"/controller_server/get_state"})
        self.assertEqual(endpoints["/controller_server/get_state"],
                         dict(dispatched=True, done=False, cancelled=False))
        self.assertEqual([future.cancel_calls for future in harness.futures], [0, 0, 0, 1, 0, 0, 0, 0, 0, 0])
        self.assertTrue(harness.futures[3].cancelled())

    def test_partial_dispatch_records_missing_partner_and_fixed_ten_endpoints(self):
        harness = Harness()
        harness.fail_at = 4
        harness.observer.tick()
        value = harness.observer.snapshot()
        endpoints = value["diagnostics"]["endpoints"]
        self.assertEqual(len(endpoints), 10)
        self.assertEqual(sum(entry["dispatched"] for entry in endpoints.values()), 3)
        self.assertEqual(endpoints["/controller_server/get_parameters"],
                         dict(dispatched=True, done=False, cancelled=False))
        self.assertEqual(endpoints["/controller_server/get_state"],
                         dict(dispatched=False, done=None, cancelled=None))
        self.assertNotIn("private/path", repr(value))
        self.assertIsNone(harness.observer._batch)

    def test_authority_and_service_failures_have_no_dispatched_requests(self):
        for failure in ("authority", "service"):
            with self.subTest(failure=failure):
                harness = Harness()
                harness.authority_duration = .012
                harness.authority_failure = failure == "authority"
                harness.ready = failure != "service"
                harness.observer.tick()
                diagnostic = harness.observer.snapshot()["diagnostics"]
                self.assertAlmostEqual(diagnostic["authority_duration_s"], .012)
                self.assertIsNone(diagnostic["dispatch_duration_s"])
                self.assertIsNone(diagnostic["batch_age_s"])
                self.assertEqual(harness.requests, [])
                self.assertTrue(all(entry["dispatched"] is False for entry in diagnostic["endpoints"].values()))

    def test_timings_and_retained_attempt_age_do_not_rebase_policy_freshness(self):
        harness = Harness()
        harness.authority_duration = .03
        harness.dispatch_duration = .002
        harness.observer.tick()
        for future in harness.futures:
            future.complete = True
        harness.now = 10.25
        harness.authority_duration = .04
        harness.observer.tick()
        value = harness.observer.snapshot()
        diagnostic = value["diagnostics"]
        self.assertEqual(value["status"], "current")
        self.assertAlmostEqual(value["age_s"], .29)
        self.assertAlmostEqual(diagnostic["batch_age_s"], .29)
        self.assertAlmostEqual(diagnostic["tick_gap_s"], .25)
        self.assertAlmostEqual(diagnostic["authority_duration_s"], .04)
        self.assertAlmostEqual(diagnostic["dispatch_duration_s"], .02)
        self.assertEqual(diagnostic["attempt_sequence"], 1)
        harness.now = 10.75
        # GET only ages the retained record; it never schedules a fresh batch.
        self.assertEqual(harness.observer.snapshot()["status"], "current")
        harness.now += .001
        expired = harness.observer.snapshot()
        self.assertEqual(expired["status"], "stale")
        self.assertAlmostEqual(expired["diagnostics"]["age_s"], .461)
        self.assertEqual(len(harness.requests), 10)
        harness.observer.tick()
        self.assertEqual(harness.observer.snapshot()["diagnostics"]["attempt_sequence"], 1)

    def test_deadline_boundary_is_unchanged(self):
        for delay, expected in ((.5, "current"), (.500001, "unavailable")):
            with self.subTest(delay=delay):
                harness = Harness()
                harness.observer.tick()
                for future in harness.futures:
                    future.complete = True
                harness.now += delay
                harness.observer.tick()
                self.assertEqual(harness.observer.snapshot()["status"], expected)


if __name__ == "__main__":
    unittest.main()
