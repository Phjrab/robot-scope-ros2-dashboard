import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    SPEC = importlib.util.spec_from_file_location(
        "robot_scope_acceptance", SCRIPTS / "robot_scope_acceptance.py"
    )
    assert SPEC and SPEC.loader
    acceptance = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = acceptance
    SPEC.loader.exec_module(acceptance)
finally:
    sys.path.remove(str(SCRIPTS))


@dataclass(frozen=True)
class FakeDoctorCheck:
    id: str
    status: str
    required: bool
    summary: str


class FakeDoctor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self):
        return [
            FakeDoctorCheck("platform.os", "pass", True, "Ubuntu 22.04 is supported"),
            FakeDoctorCheck("go2.interface", "warn", False, "Go2 hardware is offline"),
        ]


class FakeCommands:
    def __init__(self):
        self.commands = []

    def __call__(self, command, **_kwargs):
        self.commands.append(tuple(str(item) for item in command))
        if "rev-parse" in command:
            return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")
        if "show" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                "LoadState=loaded\nUnitFileState=disabled\nActiveState=active\n"
                "SubState=running\nResult=success\nNRestarts=0\n",
                "",
            )
        return subprocess.CompletedProcess(command, 1, "", "")


def healthy_responses():
    topics = []
    for name, hz, age, jitter in (
        ("/lowstate", 100.0, 0.01, 2.0),
        ("/lidar_points", 10.0, 0.05, 8.0),
        ("/velodyne_points", 8.0, 0.05, 10.0),
        ("/Odometry", 20.0, 0.02, 4.0),
    ):
        topics.append(
            {
                "name": name,
                "publishers": 1,
                "hz": hz,
                "age_s": age,
                "jitter_ms": jitter,
            }
        )
    return {
        "/api/v1/health": {
            "agent_ready": True,
            "ros_interface_ready": True,
            "robot_target_connected": True,
            "target_matches_startup": True,
            "robot_online": True,
            "ros_distro": "humble",
            "rmw": "rmw_cyclonedds_cpp",
            "ros_domain_id": "0",
            "ros_transport": {
                "mode": "go2_interface",
                "interface_ready": True,
                "interface": "eno1",
                "dds_uri_configured": True,
                "cyclonedds_configured": True,
            },
        },
        "/api/v1/control": {
            "control": {
                "bridge": {
                    "authenticated": True,
                    "ready": True,
                    "status_age_s": 0.05,
                    "lowstate_age_ms": 10.0,
                    "sport_subscribers": 1,
                    "own_sport_publishers": 1,
                    "foreign_named_sport_publishers": 0,
                    "bare_unitree_sport_publishers": 9,
                    "expected_bare_sport_publishers": 9,
                    "total_sport_publishers": 10,
                    "lowstate_publishers": 1,
                }
            }
        },
        "/api/v1/navigation": {
            "pipeline": {"state": "running"},
            "readiness": {"scan": True, "odometry": True, "tf": True},
            "localization_health": {
                "state": "READY",
                "reason_code": "HEALTHY",
                "metrics": {
                    "cloud_frequency_hz": 8.0,
                    "cloud_age_s": 0.05,
                    "odometry_frequency_hz": 20.0,
                    "odometry_age_s": 0.02,
                    "tf_age_s": 0.02,
                    "fresh_sequence_count": 3,
                },
            },
        },
        "/api/v1/mapping/control": {"pipeline": {"state": "running"}},
        "/api/v1/datasets/capture": {
            "free_bytes": 8 * 1024 * 1024 * 1024,
            "minimum_free_bytes": 5 * 1024 * 1024 * 1024,
            "session_quota_bytes": 20 * 1024 * 1024 * 1024,
        },
        "/api/v1/saved-maps": {
            "maps": [{"id": "a" * 24, "format": "map-server-pgm"}]
        },
        "/api/v1/system/service": {"systemd": {"active_state": "active"}},
        "/api/v1/control/bridge-service": {
            "systemd": {"active_state": "active"}
        },
        "/api/v1/topics": {"topics": topics},
    }


class RobotScopeAcceptanceTests(unittest.TestCase):
    def make_runner(self, base: Path, responses=None):
        project = base / "project"
        project.mkdir()
        (project / "robot_dashboard").mkdir()
        (project / "scripts").mkdir()
        (project / "scripts" / "robot_scope_doctor.py").write_text(
            "# fixture\n", encoding="utf-8"
        )
        commands = FakeCommands()
        payloads = responses if responses is not None else healthy_responses()

        def fetch(endpoint):
            if endpoint not in acceptance.READ_ONLY_ENDPOINTS:
                raise AssertionError("non-allowlisted endpoint")
            return payloads[endpoint]

        runner = acceptance.AcceptanceRunner(
            project_dir=project,
            report_dir=project / "runtime" / "reports",
            fetch_json=fetch,
            command_runner=commands,
            which=lambda name: f"/usr/bin/{name}" if name in {"git", "systemctl"} else None,
            doctor_factory=FakeDoctor,
            now=lambda: "2026-08-23T00:00:00.000Z",
        )
        return runner, commands

    def test_read_only_collection_uses_only_fixed_gets_and_safe_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner, commands = self.make_runner(Path(temporary))
            runner.prepare_report_directory()
            commit = runner.collect_read_only()
            self.assertEqual(commit, "a" * 40)
            self.assertTrue(runner.checks)
            self.assertNotIn("FAIL", {item.status for item in runner.checks})
            for command in commands.commands:
                joined = " ".join(command)
                self.assertTrue("rev-parse HEAD" in joined or "systemctl show" in joined)
                self.assertNotRegex(joined, r"\b(start|stop|restart|enable|disable)\b")

    def test_report_is_private_bounded_and_contains_no_secret_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner, _commands = self.make_runner(Path(temporary))
            runner.prepare_report_directory()
            commit = runner.collect_read_only()
            runner.add_supervised_results(selected_scenario=None, selected_status=None)
            report = runner.report(commit=commit, supervised_requested=False)
            json_path, markdown_path = runner.write_report(report)
            self.assertEqual(stat.S_IMODE(runner.report_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(json_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(markdown_path.stat().st_mode), 0o600)
            encoded = json_path.read_text(encoding="utf-8")
            self.assertNotIn("bridge_key", encoded.casefold())
            self.assertNotIn("authorization", encoded.casefold())
            decoded = json.loads(encoded)
            self.assertEqual(decoded["schema"], acceptance.SCHEMA)
            self.assertFalse(decoded["script_hardware_side_effects"])
            self.assertEqual(len(decoded["checks"]), len(runner.checks))

    def test_supervised_record_requires_every_explicit_confirmation(self):
        parser = acceptance.build_parser()
        incomplete = parser.parse_args(
            [
                "--allow-supervised-motion",
                "--supervised-scenario",
                "supervised.manual_short_stop",
                "--supervised-result",
                "PASS",
            ]
        )
        with self.assertRaisesRegex(ValueError, "every supervised"):
            acceptance.validate_supervised_args(incomplete)
        complete = parser.parse_args(
            [
                "--allow-supervised-motion",
                "--confirm-estop-ready",
                "--confirm-clear-area",
                "--confirm-low-speed-limits",
                "--confirm-operator-present",
                "--supervised-scenario",
                "supervised.manual_short_stop",
                "--supervised-result",
                "PASS",
            ]
        )
        acceptance.validate_supervised_args(complete)

    def test_supervised_mode_records_one_fixed_scenario_and_never_drives(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner, commands = self.make_runner(Path(temporary))
            runner.add_supervised_results(
                selected_scenario="supervised.browser_disconnect_watchdog",
                selected_status="FAIL",
            )
            selected = [item for item in runner.checks if item.status == "FAIL"]
            self.assertEqual([item.id for item in selected], ["supervised.browser_disconnect_watchdog"])
            self.assertTrue(selected[0].manual_action)
            self.assertEqual(commands.commands, [])
            self.assertTrue(
                all(
                    item.status == "NOT_RUN"
                    for item in runner.checks
                    if item.id != "supervised.browser_disconnect_watchdog"
                )
            )

    def test_unsafe_control_cardinality_is_fail_not_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/control"]["control"]["bridge"][
                "foreign_named_sport_publishers"
            ] = 1
            runner, _commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_control()
            self.assertEqual(runner.checks[-1].status, "FAIL")

    def test_missing_hardware_is_blocked_without_cached_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/health"]["robot_online"] = False
            responses["/api/v1/topics"] = {"topics": []}
            runner, _commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_health()
            runner._collect_topics()
            self.assertEqual(runner.checks[0].status, "BLOCKED")
            self.assertTrue(all(item.status == "BLOCKED" for item in runner.checks[2:]))

    def test_loopback_client_rejects_non_allowlisted_endpoint_and_bad_port(self):
        with self.assertRaises(ValueError):
            acceptance.LocalDashboardClient(0)
        client = acceptance.LocalDashboardClient(8088)
        with self.assertRaises(ValueError):
            client.fetch("/api/v1/control/arm")

    def test_runner_rejects_a_non_repository_project_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "Robot Scope checkout"):
                acceptance.AcceptanceRunner(project_dir=Path(temporary))

    def test_runner_rejects_an_alternate_report_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            (project / "robot_dashboard").mkdir(parents=True)
            (project / "scripts").mkdir()
            (project / "scripts" / "robot_scope_doctor.py").write_text(
                "# fixture\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "fixed runtime report root"):
                acceptance.AcceptanceRunner(
                    project_dir=project,
                    report_dir=base / "outside",
                )

    def test_source_has_no_shell_or_mutating_http_method(self):
        source = (SCRIPTS / "robot_scope_acceptance.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("subprocess.Popen", source)
        self.assertNotIn('method="POST"', source)
        self.assertNotRegex(source, r'urlopen\([^\n]+data=')
        self.assertEqual(acceptance.FIXED_DASHBOARD_HOST, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
