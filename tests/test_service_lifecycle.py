import json
import subprocess
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

import robot_dashboard.service_lifecycle as lifecycle_module
from robot_dashboard.service_lifecycle import (
    COMMANDS,
    SERVICE_NAME,
    ServiceLifecycleBlocked,
    ServiceLifecycleBusy,
    ServiceLifecycleConfirmationRequired,
    ServiceLifecycleManager,
    ServiceLifecycleUnavailable,
)


def wait_for_state(
    manager: ServiceLifecycleManager,
    expected: set[str],
    *,
    timeout: float = 2.0,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.snapshot()
        operation = snapshot.get("operation") or {}
        if operation.get("state") in expected:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"lifecycle state did not reach {sorted(expected)}")


class ServiceLifecycleManagerTests(unittest.TestCase):
    @staticmethod
    def manager(**overrides):
        options = {
            "enabled": True,
            "executable_probe": lambda _path: True,
            "dispatch_delay_seconds": 0.25,
            "command_timeout_seconds": 0.5,
            "transition_timeout_seconds": 0.5,
        }
        options.update(overrides)
        return ServiceLifecycleManager(**options)

    def test_confirmation_mode_never_exposes_or_requires_credentials(self):
        manager = self.manager()
        rendered = json.dumps(manager.snapshot(), sort_keys=True)
        self.assertNotIn("token", rendered.casefold())
        self.assertTrue(manager.snapshot()["configured"])

    def test_only_two_fixed_shell_free_commands_can_be_dispatched(self):
        calls = []

        def runner(command, timeout_seconds):
            calls.append((command, timeout_seconds))
            return subprocess.CompletedProcess(command, 0, stdout="")

        for action in ("restart", "stop"):
            manager = self.manager(command_runner=runner)
            if action == "restart":
                manager.schedule_restart(confirmed=True)
            else:
                manager.schedule_stop(confirmed=True)
            snapshot = wait_for_state(manager, {"queued"})
            self.assertEqual(snapshot["operation"]["action"], action)
            self.assertEqual(snapshot["privilege"]["last_result"], "verified")

        self.assertEqual([item[0] for item in calls], [COMMANDS["restart"], COMMANDS["stop"]])
        for command, timeout_seconds in calls:
            self.assertEqual(command[0], "/usr/bin/sudo")
            self.assertEqual(command[1:4], ("-n", "/usr/bin/systemctl", "--no-block"))
            self.assertEqual(command[-1], SERVICE_NAME)
            self.assertEqual(timeout_seconds, 0.5)
            self.assertNotIn("reboot", command)
            self.assertNotIn("poweroff", command)

    def test_confirmation_enablement_busy_and_blockers_fail_closed(self):
        manager = self.manager(command_runner=lambda command, timeout: None)
        with self.assertRaises(ServiceLifecycleConfirmationRequired):
            manager.schedule_restart(confirmed=False)

        disabled = self.manager(enabled=False)
        with self.assertRaises(ServiceLifecycleUnavailable):
            disabled.schedule_stop(confirmed=True)

        blocked = self.manager(blocker_provider=lambda: ["manual_control_active"])
        with self.assertRaises(ServiceLifecycleBlocked) as raised:
            blocked.schedule_stop(confirmed=True)
        self.assertEqual(raised.exception.blockers, ("manual_control_active",))
        self.assertFalse(blocked.snapshot()["can_stop"])

        busy = self.manager(command_runner=lambda command, timeout: None)
        busy.schedule_restart(confirmed=True)
        with self.assertRaises(ServiceLifecycleBusy):
            busy.schedule_stop(confirmed=True)

    def test_dispatch_rechecks_activity_and_never_runs_after_new_blocker(self):
        blockers = []
        calls = []
        manager = self.manager(
            blocker_provider=lambda: list(blockers),
            command_runner=lambda command, timeout: calls.append(command),
        )
        manager.schedule_restart(confirmed=True)
        blockers.append("mapping_pipeline_active")
        snapshot = wait_for_state(manager, {"blocked"})
        self.assertEqual(calls, [])
        self.assertEqual(snapshot["operation"]["error"], "active_robot_work")
        self.assertIn("mapping_pipeline_active", snapshot["blockers"])

    def test_timeout_rejection_and_close_have_bounded_public_results(self):
        def timeout_runner(command, timeout_seconds):
            raise subprocess.TimeoutExpired(command, timeout_seconds, output="secret-output")

        timed_out = self.manager(command_runner=timeout_runner)
        timed_out.schedule_restart(confirmed=True)
        snapshot = wait_for_state(timed_out, {"failed"})
        self.assertEqual(snapshot["operation"]["error"], "dispatch_timeout")
        self.assertNotIn("secret-output", json.dumps(snapshot))

        rejected = self.manager(
            command_runner=lambda command, timeout: subprocess.CompletedProcess(
                command, 1, stdout="sudo private diagnostic"
            )
        )
        rejected.schedule_stop(confirmed=True)
        snapshot = wait_for_state(rejected, {"failed"})
        self.assertEqual(snapshot["operation"]["error"], "dispatch_rejected")
        self.assertEqual(snapshot["operation"]["exit_status"], 1)
        self.assertNotIn("private diagnostic", json.dumps(snapshot))

        cancelled = self.manager()
        cancelled.schedule_restart(confirmed=True)
        cancelled.close()
        snapshot = wait_for_state(cancelled, {"cancelled"})
        self.assertEqual(snapshot["operation"]["error"], "application_shutdown")

    def test_queued_transition_cannot_leave_the_manager_busy_forever(self):
        manager = self.manager(
            command_runner=lambda command, timeout: subprocess.CompletedProcess(
                command, 0, stdout=""
            )
        )
        manager.schedule_restart(confirmed=True)
        wait_for_state(manager, {"queued"})
        snapshot = wait_for_state(manager, {"failed"}, timeout=1.5)
        self.assertEqual(
            snapshot["operation"]["error"],
            "service_transition_not_observed",
        )
        self.assertFalse(snapshot["operation"]["state"] in {"scheduled", "queued"})

    def test_default_runner_sets_shell_false_noninteractive_and_minimal_environment(self):
        completed = subprocess.CompletedProcess(COMMANDS["restart"], 0, stdout="")
        with mock.patch.object(
            lifecycle_module.subprocess,
            "run",
            return_value=completed,
        ) as run:
            result = lifecycle_module._default_command_runner(COMMANDS["restart"], 3.0)
        self.assertIs(result, completed)
        args, kwargs = run.call_args
        self.assertEqual(args, (COMMANDS["restart"],))
        self.assertIs(kwargs["shell"], False)
        self.assertIs(kwargs["check"], False)
        self.assertEqual(kwargs["timeout"], 3.0)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(
            kwargs["env"],
            {
                "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )


class ServiceLifecycleEnvironmentTests(unittest.TestCase):
    def test_environment_requires_only_explicit_opt_in(self):
        disabled = ServiceLifecycleManager.from_environment({})
        self.assertFalse(disabled.snapshot()["enabled"])

        enabled = ServiceLifecycleManager.from_environment(
            {"ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED": "1"}
        )
        self.assertTrue(enabled.snapshot()["enabled"])
        self.assertTrue(enabled.snapshot()["configured"])

    def test_sudoers_example_allows_only_the_two_exact_dashboard_commands(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "deploy" / "robot-scope-service-lifecycle.sudoers.example"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/usr/bin/systemctl --no-block restart robot-scope.service,",
            source,
        )
        self.assertIn(
            "/usr/bin/systemctl --no-block stop robot-scope.service",
            source,
        )
        self.assertIn("NOPASSWD: ROBOT_SCOPE_SERVICE_LIFECYCLE", source)
        self.assertNotIn("systemctl *", source)
        for forbidden in ("reboot", "poweroff", "halt", "daemon-reload"):
            commands = "\n".join(
                line for line in source.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertNotIn(forbidden, commands)

        unit = (root / "deploy" / "robot-scope.service.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("EnvironmentFile=-/home/jetson_orin_nano/.config/robot-scope/control.env", unit)
        self.assertNotIn("ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED=0", unit)


if __name__ == "__main__":
    unittest.main()
