import importlib.util
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "robot_scope_dashboard_service.py"
SUDOERS = ROOT / "deploy" / "robot-scope-service-lifecycle.sudoers.example"
SPEC = importlib.util.spec_from_file_location("dashboard_service_script", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class DashboardServiceScriptTests(unittest.TestCase):
    def test_help_and_invalid_actions_need_no_systemd(self):
        help_result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("start", help_result.stdout)
        invalid = subprocess.run(
            [sys.executable, str(SCRIPT), "enable"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(invalid.returncode, 2)

    def test_dry_run_uses_only_fixed_commands(self):
        expected = {
            "start": "/usr/bin/sudo -n /usr/bin/systemctl --no-block restart robot-scope.service",
            "restart": "/usr/bin/sudo -n /usr/bin/systemctl --no-block restart robot-scope.service",
            "stop": "/usr/bin/sudo -n /usr/bin/systemctl --no-block stop robot-scope.service",
            "status": "/usr/bin/systemctl show robot-scope.service --no-pager",
            "logs": "/usr/bin/journalctl --unit robot-scope.service --lines 150 --no-pager",
        }
        for action, fragment in expected.items():
            with self.subTest(action=action):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--dry-run", action],
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(fragment, result.stdout)

    def test_runner_is_shell_free_bounded_and_sanitized(self):
        with patch.object(module.subprocess, "run") as runner:
            runner.return_value = completed(module.MUTATION_COMMANDS["start"])
            result = module._run(module.MUTATION_COMMANDS["start"])
        self.assertEqual(result.returncode, 0)
        _, kwargs = runner.call_args
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 5.0)
        self.assertEqual(kwargs["env"], module.SAFE_ENVIRONMENT)

    def test_status_port_is_fixed_or_read_from_a_root_owned_regular_file(self):
        missing = unittest.mock.MagicMock()
        missing.exists.return_value = False
        with patch.object(module, "PORT_CONFIG_PATH", missing):
            self.assertEqual(module._status_port(), 8088)
        trusted = unittest.mock.MagicMock(
            st_mode=0o100644,
            st_uid=0,
            st_size=5,
        )
        configured = unittest.mock.MagicMock()
        configured.exists.return_value = True
        with patch.object(module, "PORT_CONFIG_PATH", configured), patch.object(
            module.os, "open", return_value=91
        ), patch.object(module.os, "fstat", return_value=trusted), patch.object(
            module.os, "read", return_value=b"18088\n"
        ), patch.object(module.os, "close"):
            self.assertEqual(module._status_port(), 18088)
        self.assertTrue(module.os.O_NONBLOCK)

    def test_dashboard_url_uses_the_server_address_from_ssh(self):
        with patch.dict(
            module.os.environ,
            {"SSH_CONNECTION": "192.168.0.10 53122 192.168.0.26 22"},
        ), patch.object(
            module, "_configured_dashboard_address", return_value=None
        ), patch.object(module, "_status_port", return_value=8088):
            self.assertEqual(module._dashboard_url(), "http://192.168.0.26:8088")

    def test_dashboard_url_prefers_root_owned_configured_address(self):
        trusted = unittest.mock.MagicMock(
            st_mode=0o100644,
            st_uid=0,
            st_size=14,
        )
        configured = unittest.mock.MagicMock()
        configured.exists.return_value = True
        with patch.object(
            module, "DASHBOARD_ADDRESS_CONFIG_PATH", configured
        ), patch.object(module.os, "open", return_value=92), patch.object(
            module.os, "fstat", return_value=trusted
        ), patch.object(
            module.os, "read", return_value=b"192.168.50.10\n"
        ), patch.object(module.os, "close"), patch.dict(
            module.os.environ,
            {"SSH_CONNECTION": "192.168.0.10 53122 192.168.0.26 22"},
        ), patch.object(module, "_status_port", return_value=8088):
            self.assertEqual(module._dashboard_url(), "http://192.168.50.10:8088")

    def test_dashboard_address_config_rejects_public_or_untrusted_files(self):
        configured = unittest.mock.MagicMock()
        configured.exists.return_value = True
        untrusted = unittest.mock.MagicMock(
            st_mode=0o100666,
            st_uid=0,
            st_size=12,
        )
        with patch.object(
            module, "DASHBOARD_ADDRESS_CONFIG_PATH", configured
        ), patch.object(module.os, "open", return_value=93), patch.object(
            module.os, "fstat", return_value=untrusted
        ), patch.object(module.os, "close"):
            with self.assertRaisesRegex(module.DashboardServiceError, "not trusted"):
                module._configured_dashboard_address()

        trusted = unittest.mock.MagicMock(
            st_mode=0o100644,
            st_uid=0,
            st_size=8,
        )
        with patch.object(
            module, "DASHBOARD_ADDRESS_CONFIG_PATH", configured
        ), patch.object(module.os, "open", return_value=94), patch.object(
            module.os, "fstat", return_value=trusted
        ), patch.object(
            module.os, "read", return_value=b"8.8.8.8\n"
        ), patch.object(module.os, "close"):
            with self.assertRaisesRegex(module.DashboardServiceError, "private host IPv4"):
                module._configured_dashboard_address()

    def test_blank_root_owned_address_config_keeps_automatic_selection(self):
        configured = unittest.mock.MagicMock()
        configured.exists.return_value = True
        trusted = unittest.mock.MagicMock(
            st_mode=0o100644,
            st_uid=0,
            st_size=1,
        )
        with patch.object(
            module, "DASHBOARD_ADDRESS_CONFIG_PATH", configured
        ), patch.object(module.os, "open", return_value=95), patch.object(
            module.os, "fstat", return_value=trusted
        ), patch.object(module.os, "read", return_value=b"\n"), patch.object(
            module.os, "close"
        ):
            self.assertIsNone(module._configured_dashboard_address())

    def test_active_status_prints_the_dashboard_url(self):
        active = {
            "Id": module.SERVICE,
            "LoadState": "loaded",
            "ActiveState": "active",
            "SubState": "running",
            "InvocationID": "current",
        }
        output = io.StringIO()
        with patch.object(module, "_snapshot", return_value=active), patch.object(
            module, "_dashboard_url", return_value="http://192.168.0.26:8088"
        ), redirect_stdout(output):
            self.assertEqual(module.execute("status"), 0)
        self.assertIn(
            "[Robot Scope] dashboard URL: http://192.168.0.26:8088",
            output.getvalue(),
        )

    def test_restart_requires_new_invocation_before_success(self):
        old = {
            "Id": module.SERVICE,
            "LoadState": "loaded",
            "ActiveState": "active",
            "SubState": "running",
            "InvocationID": "old",
        }
        new = dict(old, InvocationID="new")
        with patch.object(module, "_snapshot", side_effect=[old, old, new]), patch.object(
            module.time, "sleep"
        ):
            result = module._wait_for_active("old")
        self.assertEqual(result["InvocationID"], "new")

    def test_dispatch_timeout_is_an_unknown_transition_not_a_safe_retry(self):
        with patch.object(module, "_run", side_effect=subprocess.TimeoutExpired([], 5.0)):
            with self.assertRaisesRegex(module.TransitionTimeout, "without retrying"):
                module._dispatch("restart")

    def test_failed_stop_is_not_reported_as_cleanly_inactive(self):
        failed = {
            "Id": module.SERVICE,
            "LoadState": "loaded",
            "ActiveState": "failed",
            "SubState": "failed",
            "InvocationID": "failed-run",
        }
        with patch.object(module, "_snapshot", return_value=failed):
            with self.assertRaisesRegex(module.DashboardServiceError, "entered failed state"):
                module._wait_for_stopped()

    def test_start_while_activating_waits_without_dispatching_again(self):
        activating = {
            "Id": module.SERVICE,
            "LoadState": "loaded",
            "ActiveState": "activating",
            "SubState": "start",
            "InvocationID": "starting",
        }
        active = dict(activating, ActiveState="active", SubState="running")
        with patch.object(module, "_snapshot", return_value=activating), patch.object(
            module, "_wait_for_existing_start", return_value=active
        ), patch.object(module, "_wait_for_http_ready"), patch.object(
            module, "_dispatch"
        ) as dispatch, patch.object(
            module, "_mutation_lock"
        ) as lock:
            lock.return_value.__enter__.return_value = None
            self.assertEqual(module.execute("start"), 0)
        dispatch.assert_not_called()

    def test_http_readiness_waits_past_systemd_active(self):
        unavailable = unittest.mock.MagicMock()
        unavailable.status = 503
        ready = unittest.mock.MagicMock()
        ready.status = 200
        first = unittest.mock.MagicMock()
        first.getresponse.return_value = unavailable
        second = unittest.mock.MagicMock()
        second.getresponse.return_value = ready
        active = {
            "Id": module.SERVICE,
            "LoadState": "loaded",
            "ActiveState": "active",
            "SubState": "running",
            "InvocationID": "new",
        }
        with patch.object(
            module.http.client, "HTTPConnection", side_effect=[first, second]
        ), patch.object(module, "_snapshot", return_value=active), patch.object(
            module.time, "sleep"
        ):
            module._wait_for_http_ready()

    def test_active_robot_work_blocks_mutation(self):
        response = unittest.mock.MagicMock()
        response.status = 200
        response.read.return_value = (
            b'{"service":"robot-scope.service",'
            b'"blockers":["mapping_operation_active"],"operation":null}'
        )
        connection = unittest.mock.MagicMock()
        connection.getresponse.return_value = response
        with patch.object(module.http.client, "HTTPConnection", return_value=connection):
            with self.assertRaisesRegex(module.DashboardServiceError, "mapping_operation_active"):
                module._idle_preflight()
        connection.request.assert_called_once_with(
            "GET",
            module.STATUS_PATH,
            headers={"Accept": "application/json", "Host": "127.0.0.1:8088"},
        )
        connection.close.assert_called_once_with()

    def test_existing_web_lifecycle_operation_blocks_ssh_mutation(self):
        response = unittest.mock.MagicMock()
        response.status = 200
        response.read.return_value = (
            b'{"service":"robot-scope.service","blockers":[],'
            b'"operation":{"state":"dispatching"}}'
        )
        connection = unittest.mock.MagicMock()
        connection.getresponse.return_value = response
        with patch.object(module.http.client, "HTTPConnection", return_value=connection):
            with self.assertRaisesRegex(module.DashboardServiceError, "operation is active"):
                module._idle_preflight()

    def test_sudoers_is_exact_and_never_allows_the_helper(self):
        source = SUDOERS.read_text(encoding="utf-8")
        command_body = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for action in ("restart", "stop"):
            self.assertIn(
                f"/usr/bin/systemctl --no-block {action} robot-scope.service",
                command_body,
            )
        self.assertNotIn("--no-block start robot-scope.service", command_body)
        for forbidden in ("systemctl *", "robot-scope-dashboard *", "reboot", "poweroff"):
            self.assertNotIn(forbidden, command_body)

    def test_source_never_targets_control_robot_or_mapping_services(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("robot-scope-control-bridge.service", source)
        self.assertNotIn("robot-scope-xt16-relay.service", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("ros2 ", source)


if __name__ == "__main__":
    unittest.main()
