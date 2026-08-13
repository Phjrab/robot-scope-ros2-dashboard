import json
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import robot_dashboard.control_bridge_lifecycle as lifecycle_module
from robot_dashboard.control_bridge_lifecycle import (
    MUTATION_COMMANDS,
    SERVICE_NAME,
    STATUS_COMMAND,
    ControlBridgeLifecycleBlocked,
    ControlBridgeLifecycleBusy,
    ControlBridgeLifecycleConfirmationRequired,
    ControlBridgeLifecycleManager,
    ControlBridgeLifecycleUnavailable,
    collect_control_bridge_lifecycle_blockers,
    parse_systemd_show,
)


def systemd_output(
    active_state="inactive",
    sub_state="dead",
    *,
    invocation_id="",
    load_state="loaded",
    unit_file_state="disabled",
):
    return "\n".join(
        (
            f"ActiveState={active_state}",
            f"SubState={sub_state}",
            f"InvocationID={invocation_id}",
            f"LoadState={load_state}",
            f"UnitFileState={unit_file_state}",
            "",
        )
    )


class FakeSystemd:
    def __init__(self, active_state="inactive"):
        self._lock = threading.Lock()
        self.active_state = active_state
        self.invocation_id = "" if active_state != "active" else "a" * 32
        self.mutations = []

    def status(self, command, timeout_seconds):
        self.assert_status_command(command)
        with self._lock:
            active_state = self.active_state
            invocation_id = self.invocation_id
        sub_state = "running" if active_state == "active" else "dead"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=systemd_output(
                active_state,
                sub_state,
                invocation_id=invocation_id,
            ),
        )

    def mutate(self, command, timeout_seconds):
        with self._lock:
            self.mutations.append((command, timeout_seconds))
            if command == MUTATION_COMMANDS["start"]:
                self.active_state = "active"
                self.invocation_id = "b" * 32
            elif command == MUTATION_COMMANDS["stop"]:
                self.active_state = "inactive"
                self.invocation_id = ""
            else:  # pragma: no cover - makes an allowlist regression loud
                raise AssertionError(f"unexpected command: {command!r}")
        return subprocess.CompletedProcess(command, 0, stdout="")

    @staticmethod
    def assert_status_command(command):
        if command != STATUS_COMMAND:
            raise AssertionError(f"unexpected status command: {command!r}")


def wait_for_state(manager, expected, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.snapshot()
        operation = snapshot.get("operation") or {}
        if operation.get("state") in expected:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"operation did not reach {sorted(expected)}")


class ControlBridgeLifecycleManagerTests(unittest.TestCase):
    @staticmethod
    def manager(fake_systemd, **overrides):
        options = {
            "enabled": True,
            "executable_probe": lambda _path: True,
            "status_runner": fake_systemd.status,
            "mutation_runner": fake_systemd.mutate,
            "command_timeout_seconds": 0.5,
            "status_timeout_seconds": 0.1,
            "transition_timeout_seconds": 0.6,
            "poll_interval_seconds": 0.01,
        }
        options.update(overrides)
        return ControlBridgeLifecycleManager(**options)

    def test_status_parser_requires_loaded_unit_and_all_fixed_fields(self):
        parsed = parse_systemd_show(
            systemd_output(
                "active",
                "running",
                invocation_id="A" * 32,
                unit_file_state="enabled",
            )
        )
        self.assertTrue(parsed["available"])
        self.assertTrue(parsed["running"])
        self.assertEqual(parsed["load_state"], "loaded")
        self.assertEqual(parsed["unit_file_state"], "enabled")
        self.assertEqual(parsed["invocation_id"], "a" * 32)

        self.assertFalse(
            parse_systemd_show("ActiveState=inactive\nSubState=dead\n")["available"]
        )
        self.assertFalse(
            parse_systemd_show(
                systemd_output(load_state="not-found")
            )["available"]
        )
        rendered = json.dumps(parse_systemd_show("ActiveState=<secret>\n"))
        self.assertNotIn("secret", rendered)

    def test_only_fixed_absolute_start_and_stop_commands_are_dispatched(self):
        fake = FakeSystemd("inactive")
        manager = self.manager(fake)
        manager.schedule_start(confirmed=True)
        started = wait_for_state(manager, {"succeeded"})
        self.assertTrue(started["systemd"]["running"])
        self.assertEqual(fake.mutations, [(MUTATION_COMMANDS["start"], 0.5)])

        stopped_status_polls = 0

        def signed_status_fresh():
            nonlocal stopped_status_polls
            stopped_status_polls += 1
            return stopped_status_polls < 3

        manager = self.manager(fake, bridge_status_provider=signed_status_fresh)
        manager.schedule_stop(confirmed=True)
        stopped = wait_for_state(manager, {"succeeded"})
        self.assertFalse(stopped["systemd"]["running"])
        self.assertGreaterEqual(stopped_status_polls, 3)
        self.assertEqual(fake.mutations[-1], (MUTATION_COMMANDS["stop"], 0.5))

        for command in MUTATION_COMMANDS.values():
            self.assertEqual(command[0:3], ("/usr/bin/sudo", "-n", "/usr/bin/systemctl"))
            self.assertEqual(command[3], "--no-block")
            self.assertEqual(command[-1], SERVICE_NAME)
            self.assertNotIn("restart", command)
            self.assertNotIn("enable", command)

    def test_confirmation_opt_in_busy_and_preflight_fail_closed(self):
        fake = FakeSystemd("inactive")
        manager = self.manager(fake)
        with self.assertRaises(ControlBridgeLifecycleConfirmationRequired):
            manager.schedule_start(confirmed=False)

        disabled = self.manager(fake, enabled=False)
        with self.assertRaises(ControlBridgeLifecycleUnavailable):
            disabled.schedule_stop(confirmed=True)

        blocked = self.manager(
            fake,
            preflight_provider=lambda: {
                "start": ["manual_control_active"],
                "stop": ["manual_control_active"],
            },
        )
        with self.assertRaises(ControlBridgeLifecycleBlocked) as raised:
            blocked.schedule_start(confirmed=True)
        self.assertEqual(raised.exception.blockers, ("manual_control_active",))

        mutation_entered = threading.Event()
        release_mutation = threading.Event()

        def slow_mutation(command, timeout_seconds):
            mutation_entered.set()
            release_mutation.wait(1.0)
            return fake.mutate(command, timeout_seconds)

        busy = self.manager(fake, mutation_runner=slow_mutation)
        busy.schedule_start(confirmed=True)
        self.assertTrue(mutation_entered.wait(0.5))
        with self.assertRaises(ControlBridgeLifecycleBusy):
            busy.schedule_stop(confirmed=True)
        release_mutation.set()
        wait_for_state(busy, {"succeeded"})

    def test_systemd_unavailable_disables_and_rejects_both_mutations(self):
        fake = FakeSystemd("active")

        def unavailable(command, timeout_seconds):
            return subprocess.CompletedProcess(command, 1, stdout="private diagnostic")

        calls = []
        manager = self.manager(
            fake,
            status_runner=unavailable,
            mutation_runner=lambda command, timeout: calls.append(command),
        )
        snapshot = manager.snapshot()
        self.assertFalse(snapshot["systemd"]["available"])
        self.assertFalse(snapshot["can_start"])
        self.assertFalse(snapshot["can_stop"])
        with self.assertRaises(ControlBridgeLifecycleUnavailable):
            manager.schedule_start(confirmed=True)
        with self.assertRaises(ControlBridgeLifecycleUnavailable):
            manager.schedule_stop(confirmed=True)
        self.assertEqual(calls, [])

    def test_snapshot_and_schedule_status_reads_do_not_invert_locks(self):
        first_status_entered = threading.Event()
        release_first_status = threading.Event()
        status_calls = 0
        status_calls_lock = threading.Lock()

        def status_runner(command, timeout_seconds):
            nonlocal status_calls
            with status_calls_lock:
                status_calls += 1
                first = status_calls == 1
            if first:
                first_status_entered.set()
                release_first_status.wait(1.0)
            return subprocess.CompletedProcess(
                command, 0, stdout=systemd_output("inactive", "dead")
            )

        manager = ControlBridgeLifecycleManager(
            enabled=True,
            executable_probe=lambda _path: True,
            status_runner=status_runner,
            mutation_runner=lambda command, timeout: subprocess.CompletedProcess(
                command, 0, stdout=""
            ),
            command_timeout_seconds=0.5,
            status_timeout_seconds=0.1,
            transition_timeout_seconds=0.5,
            poll_interval_seconds=0.01,
        )
        errors = []
        snapshot_thread = threading.Thread(
            target=lambda: manager.snapshot(), name="snapshot-regression"
        )

        def schedule():
            try:
                manager.schedule_start(confirmed=True)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        schedule_thread = threading.Thread(target=schedule, name="schedule-regression")
        snapshot_thread.start()
        self.assertTrue(first_status_entered.wait(0.5))
        schedule_thread.start()
        release_first_status.set()
        snapshot_thread.join(0.75)
        schedule_thread.join(0.75)
        self.assertFalse(snapshot_thread.is_alive())
        self.assertFalse(schedule_thread.is_alive())
        self.assertEqual(errors, [])
        manager.close()

    def test_close_during_final_status_probe_never_dispatches_mutation(self):
        fake = FakeSystemd("inactive")
        final_probe_entered = threading.Event()
        release_final_probe = threading.Event()
        status_calls = 0

        def status_runner(command, timeout_seconds):
            nonlocal status_calls
            status_calls += 1
            # schedule_start performs one reservation status read, then the
            # worker repeats the probe immediately before dispatch.
            if status_calls == 2:
                final_probe_entered.set()
                release_final_probe.wait(1.0)
            return fake.status(command, timeout_seconds)

        manager = self.manager(fake, status_runner=status_runner)
        scheduling_errors = []

        def schedule():
            try:
                manager.schedule_start(confirmed=True)
            except Exception as exc:  # pragma: no cover - asserted below
                scheduling_errors.append(exc)

        scheduling_thread = threading.Thread(target=schedule)
        scheduling_thread.start()
        self.assertTrue(final_probe_entered.wait(0.5))
        manager.close()
        release_final_probe.set()
        scheduling_thread.join(0.75)
        self.assertFalse(scheduling_thread.is_alive())
        self.assertEqual(scheduling_errors, [])
        snapshot = wait_for_state(manager, {"cancelled"})
        self.assertEqual(snapshot["operation"]["error"], "application_shutdown")
        self.assertEqual(fake.mutations, [])

    def test_default_runners_are_shell_free_and_use_a_fixed_environment(self):
        status_completed = subprocess.CompletedProcess(
            STATUS_COMMAND, 0, stdout=systemd_output()
        )
        mutation_completed = subprocess.CompletedProcess(
            MUTATION_COMMANDS["start"], 0, stdout=""
        )
        with mock.patch.object(
            lifecycle_module.subprocess,
            "run",
            side_effect=[status_completed, mutation_completed],
        ) as run:
            lifecycle_module._default_status_runner(STATUS_COMMAND, 1.0)
            lifecycle_module._default_mutation_runner(
                MUTATION_COMMANDS["start"], 2.0
            )
        for call in run.call_args_list:
            _args, kwargs = call
            self.assertIs(kwargs["shell"], False)
            self.assertIs(kwargs["check"], False)
            self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(
                kwargs["env"],
                {
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                },
            )


class ControlBridgePreflightTests(unittest.TestCase):
    @staticmethod
    def blockers(**overrides):
        values = {
            "control": {
                "enabled": True,
                "configured": True,
                "transport_configured": True,
                "target_supported": True,
                "target_matches_startup": True,
                "restart_required": False,
                "lease": {"active": False, "input_source": None},
                "action_guard": {"active": False},
                "bridge": {"ready": False},
            },
            "navigation_runtime": {"active": False, "goal": {"state": "idle"}},
            "navigation_jobs": {"pipeline": {"state": "idle"}},
            "mapping_jobs": {
                "pipeline": {"state": "running"},
                "operation": {"state": "saving"},
            },
            "mapping_task_active": True,
            "dataset_capture_active": True,
            "dashboard_service_lifecycle_busy": False,
        }
        values.update(overrides)
        return collect_control_bridge_lifecycle_blockers(**values)

    def test_offline_bridge_mapping_and_capture_do_not_block_cleanup(self):
        blockers = self.blockers()
        self.assertEqual(blockers["stop"], [])
        self.assertNotIn("mapping_pipeline_active", blockers["start"])
        self.assertNotIn("dataset_capture_active", blockers["start"])

    def test_configuration_and_target_compatibility_block_only_start(self):
        control = {
            "enabled": False,
            "configured": False,
            "transport_configured": False,
            "target_supported": False,
            "target_matches_startup": False,
            "restart_required": True,
            "lease": {"active": False},
            "action_guard": {"active": False},
        }
        blockers = self.blockers(control=control)
        self.assertIn("control_not_configured", blockers["start"])
        self.assertIn("control_target_incompatible", blockers["start"])
        self.assertNotIn("control_not_configured", blockers["stop"])
        self.assertNotIn("control_target_incompatible", blockers["stop"])

    def test_lease_action_navigation_and_dashboard_transition_block_both(self):
        control = {
            "enabled": True,
            "configured": True,
            "transport_configured": True,
            "target_supported": True,
            "target_matches_startup": True,
            "lease": {"active": True, "input_source": "keyboard"},
            "action_guard": {"active": True},
        }
        blockers = self.blockers(
            control=control,
            navigation_runtime={"active": True, "goal": {"state": "active"}},
            navigation_jobs={"pipeline": {"state": "running"}},
            dashboard_service_lifecycle_busy=True,
        )
        for action in ("start", "stop"):
            self.assertIn("manual_control_active", blockers[action])
            self.assertIn("robot_action_active", blockers[action])
            self.assertIn("navigation_active", blockers[action])
            self.assertIn("dashboard_service_lifecycle_active", blockers[action])
            self.assertEqual(blockers[action].count("navigation_active"), 1)

    def test_missing_motion_snapshots_fail_closed(self):
        blockers = self.blockers(
            control=None,
            navigation_runtime=None,
            navigation_jobs=None,
            dashboard_service_lifecycle_busy=None,
        )
        for action in ("start", "stop"):
            self.assertIn("control_status_unavailable", blockers[action])
            self.assertIn("navigation_status_unavailable", blockers[action])
            self.assertIn(
                "dashboard_service_lifecycle_status_unavailable", blockers[action]
            )


class ControlBridgeLifecycleEnvironmentTests(unittest.TestCase):
    def test_independent_environment_opt_in(self):
        disabled = ControlBridgeLifecycleManager.from_environment({})
        self.assertFalse(disabled.snapshot()["enabled"])
        enabled = ControlBridgeLifecycleManager.from_environment(
            {"ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED": "1"}
        )
        self.assertTrue(enabled.snapshot()["enabled"])

    def test_sudoers_example_contains_only_exact_start_and_stop_rules(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "deploy"
            / "robot-scope-control-bridge-lifecycle.sudoers.example"
        ).read_text(encoding="utf-8")
        commands = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertIn(
            "/usr/bin/systemctl --no-block start robot-scope-control-bridge.service,",
            commands,
        )
        self.assertIn(
            "/usr/bin/systemctl --no-block stop robot-scope-control-bridge.service",
            commands,
        )
        self.assertIn("NOPASSWD: ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE", commands)
        for forbidden in ("systemctl *", " restart ", " enable ", " disable ", "daemon-reload"):
            self.assertNotIn(forbidden, commands)


if __name__ == "__main__":
    unittest.main()
