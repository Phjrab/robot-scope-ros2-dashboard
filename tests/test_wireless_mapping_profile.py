import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.mapping_jobs import (
    WIRED_MAPPING_PROFILE,
    WIRELESS_MAPPING_PROFILE,
    MappingJobManager,
)


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "scripts" / "check_wireless_mapping_preflight.py"
SPEC = importlib.util.spec_from_file_location(
    "wireless_mapping_preflight", PREFLIGHT_PATH
)
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
assert SPEC.loader is not None
SPEC.loader.exec_module(preflight)
REMOTE_HELPER_PATH = ROOT / "scripts" / "robot_scope_wireless_mapping_ssh_command.py"
REMOTE_SPEC = importlib.util.spec_from_file_location(
    "wireless_mapping_remote_helper", REMOTE_HELPER_PATH
)
remote_helper = importlib.util.module_from_spec(REMOTE_SPEC)
assert REMOTE_SPEC.loader is not None
REMOTE_SPEC.loader.exec_module(remote_helper)


def completed(argv, returncode=0, stdout=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.identity = root / "identity"
        self.known_hosts = root / "known_hosts"
        for path in (self.identity, self.known_hosts):
            path.write_text("fixture", encoding="utf-8")
            path.chmod(0o600)
        self.environment = {
            preflight.SSH_IDENTITY_ENV: str(self.identity),
            preflight.SSH_KNOWN_HOSTS_ENV: str(self.known_hosts),
        }
        self.proc = root / "proc"
        (self.proc / "sys/net/core").mkdir(parents=True)
        (self.proc / "sys/net/core/rmem_max").write_text("8388608\n", encoding="ascii")

    def runner(self, argv, **_kwargs):
        values = tuple(argv)
        if values[0] == preflight.SYSTEMCTL:
            return completed(
                values,
                stdout=(
                    "LoadState=loaded\nActiveState=active\nSubState=exited\n"
                    "Result=success\nExecMainStatus=0\n"
                ),
            )
        if values[:2] == (preflight.IP, "-j"):
            return completed(
                values,
                stdout='[{"addr_info":[{"local":"192.168.50.10","prefixlen":24}]}]',
            )
        if values[0] == preflight.PING:
            return completed(values)
        if values[0] == preflight.TIMEDATECTL:
            return completed(values, stdout="yes\n")
        if values[0] == preflight.SSH:
            action = values[-1]
            if action == "clock-status":
                return completed(values, stdout="yes\n")
            if action.endswith("-status"):
                return completed(
                    values,
                    stdout="LoadState=loaded\nActiveState=active\nSubState=running\n",
                )
            if action == "relay-health":
                return completed(
                    values,
                    stdout=(
                        "[Robot Scope wireless XT16 relay] periodic captured=10 accepted=10 "
                        "forwarded=10 bytes=5680 send_errors=0\n"
                        "[Robot Scope wireless XT16 relay] periodic captured=20 accepted=20 "
                        "forwarded=20 bytes=11360 send_errors=0\n"
                    ),
                )
        raise AssertionError(values)


class WirelessMappingProfileTests(unittest.TestCase):
    def test_host_and_remote_health_preflights_are_fixed_and_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            preflight.check_host(
                fixture.environment,
                runner=fixture.runner,
                proc_root=fixture.proc,
            )
            preflight.check_relay_health(fixture.environment, runner=fixture.runner)
            preflight.check_remote_service(
                "imu", fixture.environment, runner=fixture.runner
            )
            self.assertEqual(
                preflight._parser().parse_args(["--stage", "relay-service"]).stage,
                "relay-service",
            )

    def test_relay_health_fails_when_sequence_does_not_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))

            def stale_runner(argv, **kwargs):
                result = fixture.runner(argv, **kwargs)
                if tuple(argv)[-1] == "relay-health":
                    result.stdout = result.stdout.replace("accepted=20", "accepted=10")
                return result

            with self.assertRaisesRegex(preflight.PreflightError, "XT16 PACKETS STALE"):
                preflight.check_relay_health(fixture.environment, runner=stale_runner)

    def test_remote_health_filters_journal_noise_and_returns_last_two_metrics(self):
        metric = (
            "[Robot Scope wireless XT16 relay] periodic captured={count} "
            "accepted={count} forwarded={count} bytes={bytes} send_errors=0 "
            "seq_lost=0 seq_duplicate=0 seq_reordered=0 "
            "last_accepted_age_s=0.001 last_forwarded_age_s=0.001 "
            "rejected=0(none)"
        )
        first = metric.format(count=10, bytes=5680)
        second = metric.format(count=20, bytes=11360)
        third = metric.format(count=30, bytes=17040)
        output = "\n".join((first, "systemd warning", second, third))
        self.assertEqual(
            remote_helper._relay_health_lines(output),
            (second, third),
        )
        self.assertIsNone(remote_helper._relay_health_lines("systemd warning"))

    def test_private_ssh_material_is_mandatory(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.identity.chmod(0o644)
            with self.assertRaisesRegex(preflight.PreflightError, "PREFLIGHT BLOCKED"):
                preflight.ssh_files(fixture.environment)

    def test_subprocess_timeout_is_bounded_and_fails_closed(self):
        def timeout_runner(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(("fixed",), 1.0)

        result = preflight._run(("/fixed",), runner=timeout_runner)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "")

    def test_subprocess_interrupt_is_bounded_without_traceback(self):
        def interrupted_runner(*_args, **_kwargs):
            raise KeyboardInterrupt

        result = preflight._run(("/fixed",), runner=interrupted_runner)
        self.assertEqual(result.returncode, 130)
        self.assertEqual(result.stdout, "")

    def test_conflicting_navigation_process_blocks_host_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            process = fixture.proc / "4242"
            process.mkdir()
            (process / "cmdline").write_bytes(
                b"/opt/ros/humble/lib/nav2_controller/controller_server\0"
            )
            with self.assertRaisesRegex(preflight.PreflightError, "PREFLIGHT BLOCKED"):
                preflight.check_host(
                    fixture.environment,
                    runner=fixture.runner,
                    proc_root=fixture.proc,
                )

    def test_mapping_host_allows_only_the_dashboard_preview_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            preview = fixture.proc / "4242"
            preview.mkdir()
            (preview / "cmdline").write_bytes(
                b"/usr/bin/hesai_ros_driver_node\0"
                b"/home/operator/start_wireless_xt16_preview_humble.sh\0"
            )
            preflight.check_host(
                fixture.environment,
                runner=fixture.runner,
                proc_root=fixture.proc,
                allow_preview_processes=True,
            )
            navigation = fixture.proc / "4343"
            navigation.mkdir()
            (navigation / "cmdline").write_bytes(
                b"/opt/ros/humble/lib/nav2_controller/controller_server\0"
            )
            with self.assertRaisesRegex(preflight.PreflightError, "PREFLIGHT BLOCKED"):
                preflight.check_host(
                    fixture.environment,
                    runner=fixture.runner,
                    proc_root=fixture.proc,
                    allow_preview_processes=True,
                )

    def test_missing_firewall_unit_blocks_before_sensor_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))

            def failed_firewall(argv, **kwargs):
                if tuple(argv)[0] == preflight.SYSTEMCTL:
                    return completed(argv, returncode=1)
                return fixture.runner(argv, **kwargs)

            with self.assertRaisesRegex(preflight.PreflightError, "PREFLIGHT BLOCKED"):
                preflight.check_host(
                    fixture.environment,
                    runner=failed_firewall,
                    proc_root=fixture.proc,
                )

    def test_all_browser_failure_reasons_are_bounded(self):
        self.assertEqual(
            set(preflight.EXIT_REASONS.values()),
            {
                "WIRELESS XT16 RELAY OFFLINE",
                "XT16 PACKETS STALE",
                "HESAI DRIVER WAITING",
                "WIRELESS IMU UNAUTHENTICATED",
                "IMU STALE",
                "CLOCK NOT SYNCHRONIZED",
                "CLOUD BRIDGE STALE",
                "FAST-LIO NOT READY",
                "WIRELESS MAPPING PREFLIGHT BLOCKED",
            },
        )

    def test_preview_and_mapping_launchers_have_separate_transactional_ownership(self):
        preview = (
            ROOT / "scripts" / "start_wireless_xt16_preview_humble.sh"
        ).read_text()
        mapping = (ROOT / "scripts" / "start_wireless_mapping_humble.sh").read_text()
        preview_order = (
            "--service relay --action ensure-started",
            "run_hesai_driver_wireless_humble.sh",
            "run_xt16_cloud_bridge_humble.sh",
        )
        mapping_order = (
            "--stage host-with-preview",
            "--stage preview",
            "--service imu --action ensure-started",
            "run_wireless_imu_receiver_humble.sh",
            'check_xt16_lidar_ready.py" --stage imu',
            "run_hesai_fastlio_wireless_humble.sh",
        )
        for source, order in ((preview, preview_order), (mapping, mapping_order)):
            offsets = [source.index(value) for value in order]
            self.assertEqual(offsets, sorted(offsets))
            self.assertIn(
                "for ((index=${#LOCAL_PIDS[@]} - 1; index >= 0; index--))",
                source,
            )
            self.assertIn('/usr/bin/setsid -- "$command"', source)
            self.assertIn('kill "-$signal" -- "-${LOCAL_PIDS[$index]}"', source)
            for forbidden in ("ros2 bag", "nav2", "control_arm", "mapping/save", "sudo "):
                self.assertNotIn(forbidden, source)
        service_check = preview.index("--stage relay-service")
        hesai_start = preview.index("run_hesai_driver_wireless_humble.sh")
        health_check = preview.index("--stage relay;", hesai_start)
        cloud_start = preview.index("run_xt16_cloud_bridge_humble.sh")
        self.assertLess(service_check, hesai_start)
        self.assertLess(hesai_start, health_check)
        self.assertLess(health_check, cloud_start)
        self.assertIn("post-bind reports", preview)
        self.assertNotIn("run_hesai_fastlio_wireless_humble.sh", preview)
        self.assertNotIn("--service imu", preview)
        self.assertIn("--stage preview", preview)
        self.assertNotIn("--stage bridge", preview)
        self.assertNotIn("run_hesai_driver_wireless_humble.sh", mapping)
        self.assertNotIn("run_xt16_cloud_bridge_humble.sh", mapping)
        self.assertNotIn("--stage bridge", mapping)
        self.assertNotIn("--service relay --action stop", mapping)

        # ensure-started reports "existing" for a relay that was already
        # active.  Only an exact "started" result grants preview cleanup
        # ownership, so an existing appliance relay cannot be stopped here.
        self.assertIn("REMOTE_RELAY_STARTED=0", preview)
        self.assertIn(
            '[[ "$relay_state" == "started" ]] && REMOTE_RELAY_STARTED=1',
            preview,
        )
        self.assertEqual(preview.count("REMOTE_RELAY_STARTED=1"), 1)
        self.assertIn(
            'if [[ "$REMOTE_RELAY_STARTED" -eq 1 ]]; then\n'
            "    remote_lifecycle --service relay --action stop",
            preview,
        )

    def test_remote_forced_command_and_sudoers_are_exact(self):
        helper = (
            ROOT / "scripts" / "robot_scope_wireless_mapping_ssh_command.py"
        ).read_text()
        sudoers = (
            ROOT / "deploy" / "robot-scope-wireless-mapping-remote.sudoers.example"
        ).read_text()
        for service in (
            "robot-scope-xt16-wireless-relay.service",
            "robot-scope-wireless-imu-sender.service",
            "robot-scope-wireless-odom-sender.service",
        ):
            self.assertIn(service, helper)
            self.assertIn(service, sudoers)
        self.assertIn('"--since=-15s"', helper)
        self.assertIn('"32"', helper)
        self.assertIn("--since\\=-15s -n 32", sudoers)
        self.assertIn("_relay_health_lines", helper)
        for forbidden in (
            '"restart"',
            '"enable"',
            '"disable"',
            "systemctl --no-block restart",
            "systemctl --no-block enable",
            "systemctl --no-block disable",
            "systemctl *",
            "shell=True",
        ):
            self.assertNotIn(forbidden, helper + sudoers)

    def test_wired_profile_remains_default_and_wireless_is_explicit(self):
        app_source = (ROOT / "robot_dashboard" / "app.py").read_text()
        runner = (ROOT / "scripts" / "run_go2_humble.sh").read_text()
        manager = (ROOT / "robot_dashboard" / "mapping_jobs.py").read_text()
        self.assertIn("default=WIRED_MAPPING_PROFILE", app_source)
        self.assertIn("${ROBOT_SCOPE_MAPPING_PROFILE:-go2-xt16-wired}", runner)
        self.assertIn("mapping_profile in {", manager)
        self.assertIn("WIRELESS_MAPPING_PROFILE,", manager)
        self.assertIn("COMPETITION_FASTLIO_MAPPING_PROFILE,", manager)
        self.assertIn("start_wireless_mapping_humble.sh", manager)
        self.assertIn("start_wireless_xt16_preview_humble.sh", manager)
        self.assertIn("start_hesai_mapping_humble.sh", manager)
        self.assertIn("start_xt16_preview_humble.sh", manager)

        environment = (ROOT / "deploy" / "robot-scope.env.example").read_text()
        self.assertIn("ROBOT_SCOPE_MAPPING_PROFILE=go2-xt16-wired", environment)
        self.assertIn("ROBOT_SCOPE_WIRELESS_MAPPING_SSH_IDENTITY=", environment)
        self.assertIn("ROBOT_SCOPE_WIRELESS_MAPPING_SSH_KNOWN_HOSTS=", environment)

        with tempfile.TemporaryDirectory() as temporary:
            wired = MappingJobManager.for_robot_scope(
                project_dir=ROOT,
                output_dir=Path(temporary) / "wired",
                mapping_profile=WIRED_MAPPING_PROFILE,
                enable_preview=True,
                save_commands={},
            )
            wireless = MappingJobManager.for_robot_scope(
                project_dir=ROOT,
                output_dir=Path(temporary) / "wireless",
                mapping_profile=WIRELESS_MAPPING_PROFILE,
                enable_preview=True,
                save_commands={},
            )
            self.assertEqual(
                wired.start_command.argv[0],
                str(ROOT / "scripts/start_hesai_mapping_humble.sh"),
            )
            self.assertIsNotNone(wired.preview_command)
            self.assertEqual(
                wireless.start_command.argv[0],
                str(ROOT / "scripts/start_wireless_mapping_humble.sh"),
            )
            self.assertIsNotNone(wireless.preview_command)
            self.assertEqual(
                wireless.preview_command.argv[0],
                str(ROOT / "scripts/start_wireless_xt16_preview_humble.sh"),
            )
            self.assertEqual(wireless.failure_exit_reasons[68], "FAST-LIO NOT READY")

    def test_wireless_hesai_runner_uses_only_wireless_config(self):
        source = (ROOT / "scripts" / "run_hesai_driver_wireless_humble.sh").read_text()
        self.assertIn("config/hesai_xt16_wireless.yaml", source)
        self.assertNotIn('config/hesai_xt16.yaml"', source)

    def test_wireless_ros_graph_is_pinned_without_weakening_wired_preflight(self):
        setup = (ROOT / "scripts" / "setup_wireless_mapping_ros2_humble.sh").read_text()
        fastlio = (
            ROOT / "scripts" / "run_hesai_fastlio_wireless_humble.sh"
        ).read_text()
        wired = (ROOT / "scripts" / "run_hesai_fastlio_humble.sh").read_text()
        for value in ("eno1", "192.168.50.10/24", "SocketReceiveBufferSize"):
            self.assertIn(value, setup)
        self.assertIn('ROBOT_SCOPE_GO2_INTERFACE="eno1"', fastlio)
        self.assertIn('ROBOT_SCOPE_GO2_INTERFACE_CIDR="192.168.50.10/24"', fastlio)
        self.assertIn("192.168.123.99/24", wired)
        self.assertNotIn("192.168.50.10/24", wired)


if __name__ == "__main__":
    unittest.main()
