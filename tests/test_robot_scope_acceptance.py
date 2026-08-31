import contextlib
import importlib.util
import io
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
            "hostname": "external-orin",
            "platform": "aarch64",
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
        "/api/v1/cameras": {
            "sources": [
                {
                    "id": "go2_front",
                    "configured": True,
                    "live": True,
                    "state": "ok",
                    "fps": 15.0,
                    "age_s": 0.05,
                },
                {
                    "id": "realsense_color",
                    "configured": True,
                    "configured_robot_ip": "192.168.50.30",
                    "live": True,
                    "state": "ok",
                    "receive_fps": 15.0,
                    "last_complete_jpeg_age_s": 0.05,
                    "receive_bitrate_mbps": 6.5,
                    "restart_count": 0,
                    "relay_health": {
                        "state": "streaming",
                        "fps": 15.0,
                        "last_frame_age_s": 0.04,
                        "invalid_frames": 0,
                        "producer_generation": 1,
                        "wifi": {
                            "state": "LIVE",
                            "interface": "wlan0",
                            "rssi_dbm": -54.0,
                            "link_mbps": 433.3,
                            "quality": {
                                "rtt_p50_ms": 4.0,
                                "rtt_p95_ms": 9.0,
                                "rtt_p99_ms": 14.0,
                                "loss_percent": 0.0,
                                "minimum_throughput_mbps": 80.0,
                            },
                        },
                    },
                },
            ]
        },
        "/api/v1/perception/health": {
            "mode": "SHADOW",
            "state": "LIVE",
            "source_ip": "192.168.50.30",
            "last_success_age_s": 0.05,
            "motion_authority": False,
            "command_publishers": 0,
            "compute": {
                "cpu_percent": 32.0,
                "gpu_percent": 24.0,
                "ram_used_bytes": 4_000_000_000,
                "ram_total_bytes": 8_000_000_000,
                "temperature_c": 58.0,
                "throttling": False,
            },
        },
        "/api/v1/perception/latest": {
            "mode": "SHADOW",
            "transport_state": "LIVE",
            "results": [
                {
                    "task": "lane",
                    "model_id": "lane-v2",
                    "model_sha256": "b" * 64,
                    "backend": "onnx",
                    "result_status": "LIVE",
                    "last_receive_age": 0.05,
                    "clock_domain_verified": True,
                },
                {
                    "task": "object",
                    "model_id": "object-v2",
                    "model_sha256": "f" * 64,
                    "backend": "tensorrt",
                    "result_status": "LIVE",
                    "last_receive_age": 0.05,
                    "clock_domain_verified": True,
                },
                {
                    "task": "depth_summary",
                    "model_id": "depth-v2",
                    "model_sha256": "d" * 64,
                    "backend": "onnx",
                    "result_status": "LIVE",
                    "last_receive_age": 0.05,
                    "clock_domain_verified": True,
                },
            ],
        },
        "/api/v1/models": {
            "models": [
                {
                    "model_id": "lane-v1",
                    "task": "lane",
                    "onnx_sha256": "a" * 64,
                    "engine": {"sha256": "0" * 64},
                },
                {
                    "model_id": "lane-v2",
                    "task": "lane",
                    "onnx_sha256": "b" * 64,
                    "engine": {"sha256": "e" * 64},
                },
                {
                    "model_id": "object-v2",
                    "task": "object",
                    "onnx_sha256": "c" * 64,
                    "engine": {"sha256": "f" * 64},
                },
                {
                    "model_id": "depth-v2",
                    "task": "depth_summary",
                    "onnx_sha256": "d" * 64,
                    "engine": {"sha256": "1" * 64},
                },
            ],
            "active": {
                "lane": "lane-v2",
                "object": "object-v2",
                "depth_summary": "depth-v2",
            },
            "previous": {"lane": "lane-v1"},
        },
        "/api/v1/competition": {
            "operation_mode": "SHADOW",
            "requested_mode": "SHADOW",
            "locked": True,
            "motion_authority": "NONE",
            "lock_is_physical_safety": False,
        },
        "/api/v1/pointcloud/settings": {
            "max_points": 30_000,
            "all_points": False,
            "frame_interval_s": 0.18,
        },
    }


class RobotScopeAcceptanceTests(unittest.TestCase):
    def make_runner(self, base: Path, responses=None, *, mode="go2-nav"):
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
            mode=mode,
            report_dir=project / "runtime" / "reports",
            fetch_json=fetch,
            command_runner=commands,
            which=lambda name: f"/usr/bin/{name}" if name in {"git", "systemctl"} else None,
            doctor_factory=FakeDoctor,
            now=lambda: "2026-08-23T00:00:00.000Z",
        )
        return runner, commands

    def test_go2_control_accepts_fresh_signed_bridge_without_direct_ros(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/health"].update(
                {
                    "ros_interface_ready": False,
                    "robot_online": False,
                    "ros_transport": {
                        "mode": "offline_viewer",
                        "interface_ready": False,
                        "offline_viewer": True,
                    },
                }
            )
            responses["/api/v1/control"]["control"]["bridge"]["connected"] = True
            runner, _ = self.make_runner(
                Path(temporary), responses, mode="go2-control"
            )
            runner._responses = responses

            runner._collect_health()

            check = next(item for item in runner.checks if item.id == "runtime.go2_connection")
            self.assertEqual(check.status, "PASS")
            self.assertIn("signed LowState Bridge", check.observed)
            self.assertIn("link_contract=signed_bridge", check.evidence)

    def test_go2_nav_still_requires_direct_ros_interface(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/health"]["ros_interface_ready"] = False
            responses["/api/v1/health"]["robot_online"] = False
            responses["/api/v1/control"]["control"]["bridge"]["connected"] = True
            runner, _ = self.make_runner(Path(temporary), responses, mode="go2-nav")
            runner._responses = responses

            runner._collect_health()

            check = next(item for item in runner.checks if item.id == "runtime.go2_connection")
            self.assertEqual(check.status, "FAIL")
            self.assertIn("required ROS interface", check.observed)
            self.assertIn("link_contract=direct_ros", check.evidence)

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
            self.assertEqual(
                [item.id for item in selected],
                ["supervised.browser_disconnect_watchdog"],
            )
            self.assertTrue(selected[0].manual_action)
            self.assertEqual(commands.commands, [])
            self.assertTrue(
                all(
                    item.status == "NOT_RUN"
                    for item in runner.checks
                    if item.id != "supervised.browser_disconnect_watchdog"
                )
            )

    def test_wp07_scenario_allowlist_and_single_value_parsing(self):
        expected = {
            "supervised.robot_wifi_disconnect",
            "supervised.realsense_source_stall",
            "supervised.realsense_relay_restart",
            "supervised.perception_process_stop",
            "supervised.perception_result_freeze",
            "supervised.model_hash_mismatch",
            "supervised.model_activation_rollback",
            "supervised.preview_consumer_disconnect",
            "supervised.decimated_pointcloud_load",
            "supervised.raw_pointcloud_overload_abort",
            "supervised.dashboard_receiver_restart",
            "supervised.competition_lock_mutation_rejection",
        }
        self.assertTrue(expected.issubset(acceptance.SCENARIO_BY_ID))
        parser = acceptance.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "--supervised-scenario",
                        "supervised.robot_wifi_disconnect",
                        "--supervised-scenario",
                        "supervised.realsense_source_stall",
                    ]
                )
            with self.assertRaises(SystemExit):
                parser.parse_args(["--supervised-result", "UNVERIFIED"])

    def test_every_supervised_confirmation_is_individually_required(self):
        parser = acceptance.build_parser()
        flags = [
            "--allow-supervised-motion",
            "--confirm-estop-ready",
            "--confirm-clear-area",
            "--confirm-low-speed-limits",
            "--confirm-operator-present",
        ]
        for missing in flags:
            args = parser.parse_args(
                [
                    *(flag for flag in flags if flag != missing),
                    "--supervised-scenario",
                    "supervised.competition_lock_mutation_rejection",
                    "--supervised-result",
                    "NOT_RUN",
                ]
            )
            with self.subTest(missing=missing):
                with self.assertRaisesRegex(ValueError, "every supervised"):
                    acceptance.validate_supervised_args(args)

    def test_supervised_result_parses_only_the_four_fixed_statuses(self):
        parser = acceptance.build_parser()
        for status in acceptance.STATUSES:
            args = parser.parse_args(
                [
                    "--allow-supervised-motion",
                    "--confirm-estop-ready",
                    "--confirm-clear-area",
                    "--confirm-low-speed-limits",
                    "--confirm-operator-present",
                    "--supervised-scenario",
                    "supervised.robot_wifi_disconnect",
                    "--supervised-result",
                    status,
                ]
            )
            with self.subTest(status=status):
                acceptance.validate_supervised_args(args)
                self.assertEqual(args.supervised_result, status)

    def test_stale_perception_is_explicit_and_old_live_result_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/perception/latest"]["transport_state"] = "OFFLINE"
            for result in responses["/api/v1/perception/latest"]["results"]:
                result["result_status"] = "STALE"
                result["last_receive_age"] = 3.0
            runner, _commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_perception()
            freshness = next(
                item for item in runner.checks if item.id == "perception.result_freshness"
            )
            self.assertEqual(freshness.status, "PASS")
            self.assertIn("explicitly stale", freshness.observed)

            responses["/api/v1/perception/latest"]["transport_state"] = "LIVE"
            responses["/api/v1/perception/latest"]["results"][0]["result_status"] = "LIVE"
            unsafe_base = Path(temporary) / "unsafe"
            unsafe_base.mkdir()
            unsafe, _commands = self.make_runner(unsafe_base, responses)
            unsafe._responses = responses
            unsafe._collect_perception()
            unsafe_freshness = next(
                item for item in unsafe.checks if item.id == "perception.result_freshness"
            )
            self.assertEqual(unsafe_freshness.status, "FAIL")

    def test_stale_realsense_source_fails_without_reusing_last_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            source = responses["/api/v1/cameras"]["sources"][1]
            source["state"] = "stale"
            source["live"] = False
            source["relay_health"]["state"] = "stale"
            source["relay_health"]["last_frame_age_s"] = 5.0
            runner, _commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_camera_and_link()
            statuses = {item.id: item.status for item in runner.checks}
            self.assertEqual(statuses["camera.realsense_source"], "FAIL")
            self.assertEqual(statuses["camera.realsense_transport"], "FAIL")

    def test_model_hash_mismatch_fails_and_does_not_mutate_registry_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            original = json.dumps(responses["/api/v1/models"], sort_keys=True)
            responses["/api/v1/perception/latest"]["results"][0]["model_sha256"] = "f" * 64
            runner, commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_models()
            runtime = next(item for item in runner.checks if item.id == "models.runtime_match")
            self.assertEqual(runtime.status, "FAIL")
            self.assertEqual(json.dumps(responses["/api/v1/models"], sort_keys=True), original)
            self.assertEqual(commands.commands, [])

    def test_missing_active_model_result_is_blocked_not_inferred(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/perception/latest"]["results"] = responses[
                "/api/v1/perception/latest"
            ]["results"][:1]
            runner, _commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_models()
            runtime = next(
                item for item in runner.checks if item.id == "models.runtime_match"
            )
            self.assertEqual(runtime.status, "BLOCKED")
            self.assertIn("no runtime result", runtime.observed)

    def test_raw_and_oversized_pointcloud_never_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw_responses = healthy_responses()
            raw_responses["/api/v1/pointcloud/settings"] = {
                "max_points": None,
                "all_points": True,
                "frame_interval_s": 3.0,
            }
            raw, _commands = self.make_runner(Path(temporary), raw_responses)
            raw._responses = raw_responses
            raw._collect_pointcloud()
            raw_budget = next(
                item for item in raw.checks if item.id == "pointcloud.dashboard_budget"
            )
            self.assertEqual(raw_budget.status, "BLOCKED")

            overload_responses = healthy_responses()
            overload_responses["/api/v1/pointcloud/settings"]["max_points"] = 60_001
            overload_base = Path(temporary) / "overload"
            overload_base.mkdir()
            overload, _commands = self.make_runner(overload_base, overload_responses)
            overload._responses = overload_responses
            overload._collect_pointcloud()
            overload_budget = next(
                item for item in overload.checks if item.id == "pointcloud.dashboard_budget"
            )
            self.assertEqual(overload_budget.status, "FAIL")

    def test_wp07_redaction_and_arbitrary_selectors_are_rejected(self):
        self.assertEqual(
            acceptance.safe_text(
                "password=hunter2 from /private/runtime/result.json",
                fallback="redacted",
            ),
            "redacted",
        )
        parser = acceptance.build_parser()
        for option in ("--url", "--unit", "--topic", "--command", "--evidence"):
            with self.subTest(option=option):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args([option, "unsafe-value"])

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

    def test_missing_distributed_sources_are_blocked_not_passed(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = healthy_responses()
            responses["/api/v1/cameras"] = {"sources": []}
            responses["/api/v1/perception/health"] = {
                "mode": "SHADOW",
                "state": "OFFLINE",
                "source_ip": "192.168.50.30",
                "motion_authority": False,
            }
            responses["/api/v1/perception/latest"] = {
                "mode": "SHADOW",
                "transport_state": "OFFLINE",
                "results": [],
            }
            responses["/api/v1/models"] = {
                "models": [],
                "active": {},
                "previous": {},
            }
            runner, _commands = self.make_runner(Path(temporary), responses)
            runner._responses = responses
            runner._collect_camera_and_link()
            runner._collect_perception()
            runner._collect_models()
            runner._collect_pointcloud()
            hardware_ids = {
                "camera.realsense_source",
                "camera.realsense_transport",
                "network.robot_wifi",
                "network.quality_observation",
                "perception.runtime",
                "perception.result_freshness",
                "perception.clock_domain",
                "perception.compute_metrics",
                "models.registry_identity",
                "models.runtime_match",
                "pointcloud.robot_side_mode",
            }
            statuses = {item.id: item.status for item in runner.checks}
            self.assertEqual(set(statuses).intersection(hardware_ids), hardware_ids)
            self.assertTrue(all(statuses[check_id] == "BLOCKED" for check_id in hardware_ids))

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
