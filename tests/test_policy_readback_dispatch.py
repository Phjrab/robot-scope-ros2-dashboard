"""SOFTWARE_TEST: partial async dispatch through the production observer."""
from types import SimpleNamespace as NS
import unittest

from robot_dashboard.ros.policy_readback import PARAMETERS, RosPolicyReadback


class DispatchHarness:
    def __init__(self, *, fail_at=None, completed_positions=()):
        self.now = 10.0
        self.fail_at = fail_at
        self.completed_positions = set(completed_positions)
        self.attempts = []
        self.futures = []
        self.max_pending = 0
        self.observer = RosPolicyReadback(NS(), clock=lambda: self.now)
        self.observer._authorities = lambda: {name: "a" * 48 for name in PARAMETERS}
        self.observer._declarations = (0, self.observer._authorities(),
            {name: frozenset(keys) for name, keys in PARAMETERS.items()})
        self.observer._param_type = NS(Request=NS)
        self.observer._state_type = NS(Request=NS)
        self.observer._clients = {
            name: (self.client(name, "parameters", index * 2 + 1),
                   self.client(name, "state", index * 2 + 2))
            for index, name in enumerate(PARAMETERS)
        }

    def pending(self):
        return sum(not future.done() for future in self.futures)

    def client(self, name, kind, position):
        harness = self

        class Future:
            def __init__(self, value):
                self.value = value
                self.completed = position in harness.completed_positions
                self.cancel_calls = 0

            def done(self):
                return self.completed or self.cancel_calls > 0

            def result(self):
                return self.value

            def cancel(self):
                self.cancel_calls += 1

        class Client:
            def service_is_ready(self):
                return True

            def call_async(self, request):
                harness.attempts.append((name, kind, request))
                if harness.fail_at == position:
                    raise RuntimeError("private dispatch failure must not be exported")
                value = (NS(values=[NS(type=4, string_value="fixture") for _ in PARAMETERS[name]])
                         if kind == "parameters" else NS(current_state=NS(id=3)))
                future = Future(value)
                harness.futures.append(future)
                harness.max_pending = max(harness.max_pending, harness.pending())
                return future

        return Client()


class ReadbackDispatchTests(unittest.TestCase):
    def test_failure_at_each_dispatch_cancels_all_earlier_pending_requests(self):
        for fail_at in range(1, 11):
            with self.subTest(fail_at=fail_at):
                harness = DispatchHarness(fail_at=fail_at)
                harness.observer.tick()
                self.assertEqual(len(harness.attempts), fail_at)
                self.assertEqual(len(harness.futures), fail_at - 1)
                self.assertEqual(harness.pending(), 0)
                self.assertTrue(all(future.cancel_calls == 1 for future in harness.futures))
                self.assertIsNone(harness.observer._batch)
                evidence = harness.observer.snapshot()
                self.assertEqual(evidence["reason"], "POLICY_READBACK_FAILED")
                self.assertEqual(evidence["status"], "unavailable")
                self.assertEqual(evidence["parameters"], {})

    def test_repeated_dispatch_failure_is_bounded_and_healthy_retry_completes(self):
        harness = DispatchHarness(fail_at=10)
        for _ in range(5):
            harness.observer.tick()
            self.assertEqual(harness.pending(), 0)
            self.assertIsNone(harness.observer._batch)
        self.assertEqual(len(harness.attempts), 50)
        self.assertEqual(len(harness.futures), 45)
        self.assertLessEqual(harness.max_pending, 10)

        harness.fail_at = None
        harness.observer.tick()
        self.assertEqual(len(harness.attempts), 60)
        self.assertEqual(harness.pending(), 10)
        for _ in range(3):
            harness.observer.snapshot()
            harness.observer.tick()
        self.assertEqual(len(harness.attempts), 60)
        for future in harness.futures[-10:]:
            future.completed = True
        harness.now += 0.25
        harness.observer.tick()
        evidence = harness.observer.snapshot()
        self.assertEqual(evidence["status"], "current")
        self.assertEqual(evidence["sequence"], 1)
        self.assertIsNone(evidence["reason"])
        self.assertEqual(set(evidence["parameters"]), set(PARAMETERS))
        self.assertEqual(harness.pending(), 0)
        self.assertEqual(harness.max_pending, 10)
        self.assertEqual(len(harness.attempts), 60)
        for name, kind, request in harness.attempts:
            if kind == "parameters":
                self.assertEqual(request.names, list(PARAMETERS[name]))
            else:
                self.assertEqual(vars(request), {})

    def test_dispatch_cleanup_only_cancels_pending_owned_futures(self):
        harness = DispatchHarness(fail_at=4, completed_positions={1})
        harness.observer.tick()
        self.assertEqual([future.cancel_calls for future in harness.futures], [0, 1, 1])
        self.assertEqual(harness.pending(), 0)
        self.assertIsNone(harness.observer._batch)


if __name__ == "__main__":
    unittest.main()
