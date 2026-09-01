import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from robot_dashboard.mapping_jobs import (
    COMPETITION_DIRECT_MAPPING_PROFILE,
    WIRED_MAPPING_PROFILE,
    WIRELESS_MAPPING_PROFILE,
    MappingJobManager,
)


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


preflight = load_script(
    "competition_direct_preflight", "check_competition_direct_preflight.py"
)
no_goal = load_script(
    "competition_no_goal_ready", "check_competition_no_goal_ready.py"
)


def completed(argv, returncode=0, stdout=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


class DirectFixture:
    def __init__(self, root: Path):
        self.proc = root / "proc"
        self.proc.mkdir()
        self.environment = {
            "ROBOT_SCOPE_MAPPING_PROFILE": preflight.PROFILE,
            "ROS_DISTRO": "humble",
            "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
            "ROBOT_SCOPE_GO2_INTERFACE": "eth0",
            "ROBOT_SCOPE_GO2_INTERFACE_CIDR": "192.168.123.99/24",
        }

    def runner(self, argv, **_kwargs):
        values = tuple(argv)
        if values[:2] == (preflight.IP, "-j"):
            return completed(
                values,
                stdout=(
                    '[{"addr_info":[{"local":"192.168.123.99",'
                    '"prefixlen":24}]}]'
                ),
            )
        if values[0] == preflight.PING:
            return completed(values)
        if values[:3] == ("/opt/ros/humble/bin/ros2", "topic", "info"):
            topic = values[3]
            message_type = preflight.NAVIGATION_TOPICS[topic]
            return completed(
                values,
                stdout=f"Type: {message_type}\nPublisher count: 1\n",
            )
        raise AssertionError(values)


class TrackCCompetitionDirectTests(unittest.TestCase):
    def test_profile_is_isolated_without_changing_existing_defaults(self):
        self.assertEqual(WIRED_MAPPING_PROFILE, "go2-xt16-wired")
        self.assertEqual(WIRELESS_MAPPING_PROFILE, "go2-xt16-wireless")
        self.assertEqual(COMPETITION_DIRECT_MAPPING_PROFILE, "competition-pdf-direct")

        app = (ROOT / "robot_dashboard" / "app.py").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "run_go2_humble.sh").read_text(
            encoding="utf-8"
        )
        environment = (ROOT / "deploy" / "robot-scope.env.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("default=WIRED_MAPPING_PROFILE", app)
        self.assertIn("${ROBOT_SCOPE_MAPPING_PROFILE:-go2-xt16-wired}", runner)
        self.assertIn("ROBOT_SCOPE_MAPPING_PROFILE=go2-xt16-wired", environment)

    def test_profile_routes_to_direct_wrappers_with_no_wireless_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = MappingJobManager.for_robot_scope(
                project_dir=ROOT,
                output_dir=Path(temporary),
                mapping_profile=COMPETITION_DIRECT_MAPPING_PROFILE,
                enable_preview=True,
                save_commands={},
            )
        self.assertEqual(
            manager.start_command.argv[0],
            str(ROOT / "scripts" / "start_competition_pdf_direct_mapping_humble.sh"),
        )
        self.assertIsNotNone(manager.preview_command)
        self.assertEqual(
            manager.preview_command.argv[0],
            str(ROOT / "scripts" / "start_competition_pdf_direct_preview_humble.sh"),
        )
        wrappers = "\n".join(
            (ROOT / "scripts" / filename).read_text(encoding="utf-8")
            for filename in (
                "setup_competition_pdf_direct_humble.sh",
                "start_competition_pdf_direct_mapping_humble.sh",
                "start_competition_pdf_direct_preview_humble.sh",
                "run_hesai_driver_competition_direct_humble.sh",
            )
        )
        self.assertNotIn("run_wireless_odom_receiver", wrappers)
        self.assertNotIn("run_wireless_odom_sender", wrappers)
        self.assertNotIn("wireless_mapping_remote_lifecycle", wrappers)
        self.assertIn("hesai_xt16_competition_direct.yaml", wrappers)
        self.assertIn("hesai_ros_driver_node", wrappers)
        self.assertNotIn("ros2 run hesai_ros_driver", wrappers)

        config = (
            ROOT / "config" / "hesai_xt16_competition_direct.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("device_ip_address: 192.168.123.20", config)
        self.assertIn("ros_send_point_cloud_topic: /lidar_points", config)
        self.assertIn("ros_frame_id: hesai_lidar", config)

    def test_navigation_branch_uses_direct_preflight_only(self):
        source = (ROOT / "scripts" / "run_go2_navigation_humble.sh").read_text(
            encoding="utf-8"
        )
        start = source.index("  competition-pdf-direct)")
        end = source.index("  go2-xt16-wireless)", start)
        branch = source[start:end]
        self.assertIn("setup_competition_pdf_direct_humble.sh", branch)
        self.assertIn("check_competition_direct_preflight.py", branch)
        self.assertNotIn("wireless_odom", branch)

    def test_direct_preflight_accepts_exact_direct_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DirectFixture(Path(temporary))
            preflight.check(
                "navigation",
                environment=fixture.environment,
                runner=fixture.runner,
                proc_root=fixture.proc,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_direct_preflight_rejects_foxy_and_wireless_transport(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DirectFixture(Path(temporary))
            foxy = dict(fixture.environment, ROS_DISTRO="foxy")
            with self.assertRaisesRegex(preflight.PreflightError, "Humble"):
                preflight.validate_environment(foxy)

            process = fixture.proc / "42"
            process.mkdir()
            (process / "cmdline").write_bytes(
                b"python3\0scripts/wireless_odom_receiver_humble.py\0"
            )
            with self.assertRaisesRegex(preflight.PreflightError, "wireless odometry"):
                preflight.check_no_wireless_odom_processes(fixture.proc)

    def test_no_goal_checker_requires_active_graph_and_quiet_motion_topics(self):
        environment = {
            "ROBOT_SCOPE_MAPPING_PROFILE": no_goal.PROFILE,
            "ROS_DISTRO": "humble",
        }

        def runner(argv, **_kwargs):
            values = tuple(argv)
            if values[1:3] == ("lifecycle", "get"):
                return completed(values, stdout="active [3]\n")
            if values[1:3] == ("topic", "info"):
                return completed(values, stdout="Publisher count: 1\n")
            if "tf2_echo" in values:
                return completed(values, returncode=124, stdout="Translation:\nRotation:\n")
            if values[:2] == (no_goal.TIMEOUT, "2"):
                return completed(values, returncode=124)
            raise AssertionError(values)

        no_goal.check(
            environment=environment,
            runner=runner,
            ros2="/opt/ros/humble/bin/ros2",
        )

        def motion_runner(argv, **kwargs):
            values = tuple(argv)
            result = runner(argv, **kwargs)
            if values[:2] == (no_goal.TIMEOUT, "2"):
                return completed(values, stdout="motion sample\n")
            return result

        with self.assertRaisesRegex(no_goal.NoGoalError, "unexpected output"):
            no_goal.check(
                environment=environment,
                runner=motion_runner,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_wireless_clock_guards_remain_exact(self):
        source = (ROOT / "scripts" / "wireless_odom_protocol.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAX_SOURCE_AGE_NS = 500_000_000", source)
        self.assertIn("MAX_FUTURE_SKEW_NS = 100_000_000", source)

    def test_runtime_artifacts_remain_ignored(self):
        ignored = subprocess.run(
            ["git", "check-ignore", "runtime/maps/probe.pcd", "runtime/maps/probe.yaml"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0, ignored.stderr)


if __name__ == "__main__":
    unittest.main()
