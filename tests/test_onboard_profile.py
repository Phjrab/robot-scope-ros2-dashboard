import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from robot_dashboard.connection_topology import connection_topology_for
from robot_dashboard.mapping_jobs import MappingJobManager
from robot_dashboard.navigation_jobs import NavigationJobManager
from robot_dashboard.onboard_profile import configure_onboard_profile


ROOT = Path(__file__).resolve().parents[1]


class OnboardProfileTests(unittest.TestCase):
    def test_explicit_profile_wires_direct_local_children_without_enabling_control(self):
        environment = {"ROBOT_SCOPE_CONTROL_ENABLED": "0"}
        path = configure_onboard_profile(
            "go2-onboard", "", project_dir=ROOT, environment=environment
        )
        self.assertEqual(path, str(ROOT / "config/go2-onboard.json"))
        self.assertEqual(environment["ROBOT_SCOPE_MAPPING_PROFILE"], "go2-onboard")
        self.assertEqual(environment["ROBOT_SCOPE_CONTROL_TRANSPORT"], "ros")
        self.assertEqual(environment["ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT"], "local")
        self.assertEqual(environment["ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE"], "local")
        self.assertNotIn("ROBOT_SCOPE_REALSENSE_PROFILE_CONTROL_ENABLED", environment)
        self.assertEqual(environment["ROBOT_SCOPE_GO2_INTERFACE"], "eth0")
        self.assertEqual(environment["ROBOT_SCOPE_GO2_INTERFACE_CIDR"], "192.168.123.18/24")
        self.assertEqual(environment["ROBOT_SCOPE_CONTROL_ENABLED"], "0")
        self.assertEqual(connection_topology_for("go2", "go2-onboard"), "onboard_local")
        self.assertEqual(connection_topology_for("go2", "go2-xt16-wired"), "direct_robot")
        self.assertEqual(connection_topology_for("go2", "go2-xt16-wireless"), "onboard_gateway")

    def test_onboard_refuses_conflicting_transport_distro_and_profile(self):
        conflicts = (
            {"ROBOT_SCOPE_MAPPING_PROFILE": "go2-xt16-wired"},
            {"ROBOT_SCOPE_CONTROL_TRANSPORT": "udp"},
            {"ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT": "ssh"},
            {"ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE": "ssh"},
            {"ROBOT_SCOPE_FASTLIO_DDS_MODE": "local"},
            {"ROS_DISTRO": "foxy"},
            {"ROS_LOCALHOST_ONLY": "1"},
            {"RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"},
        )
        for environment in conflicts:
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                configure_onboard_profile(
                    "go2-onboard", "", project_dir=ROOT, environment=environment
                )
        with self.assertRaises(ValueError):
            configure_onboard_profile(
                "go2-xt16-wired", "", project_dir=ROOT,
                environment={"ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard"},
            )

    def test_trusted_sensor_interface_override_is_preserved(self):
        environment = {
            "ROBOT_SCOPE_GO2_INTERFACE": "enp2s0",
            "ROBOT_SCOPE_GO2_INTERFACE_CIDR": "192.168.123.19/24",
        }
        configure_onboard_profile("go2-onboard", "", project_dir=ROOT, environment=environment)
        self.assertEqual(environment["ROBOT_SCOPE_GO2_INTERFACE"], "enp2s0")
        self.assertEqual(environment["ROBOT_SCOPE_CAMERA_INTERFACE"], "enp2s0")
        self.assertEqual(environment["ROBOT_SCOPE_GO2_INTERFACE_CIDR"], "192.168.123.19/24")

    def test_profile_keeps_existing_control_timeouts_and_sensor_extrinsics(self):
        wired = json.loads((ROOT / "config/go2.json").read_text())
        onboard = json.loads((ROOT / "config/go2-onboard.json").read_text())
        self.assertEqual(onboard["control"], wired["control"])
        self.assertEqual(onboard["navigation_health"], wired["navigation_health"])
        self.assertEqual(onboard["robot_pose_in_cloud_frames"], wired["robot_pose_in_cloud_frames"])

    def test_direct_xt16_preserves_the_sensor_calibration_and_pointcloud_contract(self):
        previous = yaml.safe_load((ROOT / "config/hesai_xt16_wireless.yaml").read_text())["lidar"][0]
        onboard = yaml.safe_load((ROOT / "config/hesai_xt16_onboard.yaml").read_text())["lidar"][0]
        self.assertEqual(onboard["driver"]["lidar_udp_type"]["correction_file_path"],
                         previous["driver"]["lidar_udp_type"]["correction_file_path"])
        self.assertFalse(onboard["driver"]["lidar_udp_type"]["use_ptc_connected"])
        self.assertEqual(onboard["driver"]["lidar_udp_type"]["device_ip_address"], "192.168.123.20")
        self.assertEqual(onboard["driver"]["lidar_udp_type"]["host_ip_address"], "192.168.123.18")
        self.assertEqual(onboard["driver"]["use_timestamp_type"], previous["driver"]["use_timestamp_type"])
        self.assertFalse(onboard["driver"]["transform_flag"])
        self.assertEqual(onboard["ros"], previous["ros"])

    def test_factories_use_local_direct_mapping_and_strict_controller_odometry(self):
        with tempfile.TemporaryDirectory() as directory:
            mapping = MappingJobManager.for_robot_scope(
                project_dir=ROOT, output_dir=Path(directory) / "maps",
                mapping_profile="go2-onboard", enable_preview=True, save_commands={},
            )
            navigation = NavigationJobManager.for_go2_humble(
                project_dir=ROOT, runtime_dir=Path(directory) / "navigation",
                map_snapshotter=lambda *_: None, navigation_profile="go2-onboard",
            )
            try:
                self.assertEqual(Path(mapping.start_command.argv[0]).name, "start_hesai_mapping_humble.sh")
                self.assertEqual(Path(mapping.preview_command.argv[0]).name, "start_xt16_preview_humble.sh")
                self.assertFalse(mapping.preview_auto_recovery_enabled)
                self.assertEqual(navigation.navigation_profile, "go2-onboard")
                self.assertEqual(navigation.controller_odom_mode, "strict_onboard")
                self.assertEqual(navigation.controller_odom_topic, "/utlidar/robot_odom")
            finally:
                navigation.close()
                mapping.close()

    def test_shell_contract_rejects_udp_before_ros_or_service_execution(self):
        script = ROOT / "scripts/apply_go2_onboard_contract.sh"
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", 'source "$1"', "test", str(script)],
            env={"PATH": "/usr/bin:/bin", "ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard",
                 "ROBOT_SCOPE_CONTROL_TRANSPORT": "udp"},
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires Humble", result.stderr)

    def test_dashboard_launcher_passes_onboard_profile_and_persistent_data_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "release"
            storage = root / "storage"
            (project / "scripts").mkdir(parents=True)
            (project / "config").mkdir()
            (project / ".venv/bin").mkdir(parents=True)
            python = project / ".venv/bin/python"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            ros_setup = root / "ros.bash"
            ros_setup.write_text("true\n")
            (project / "scripts/setup_go2_ros2_humble.sh").write_text("true\n")
            (project / "config/go2-onboard.json").write_text((ROOT / "config/go2-onboard.json").read_text())
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/run_go2_humble.sh")], env={
                    "PATH": "/usr/bin:/bin", "HOME": str(root),
                    "ROBOT_SCOPE_DIR": str(project), "ROBOT_SCOPE_ROS_SETUP": str(ros_setup),
                    "ROBOT_SCOPE_WORKSPACE_ROOT": str(storage / "workspaces"),
                    "ROBOT_SCOPE_RUNTIME_DIR": str(storage / "runtime"),
                    "ROBOT_SCOPE_STATE_DIR": str(storage / "state"),
                    "ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard",
                }, capture_output=True, text=True, check=False, timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = result.stdout.splitlines()
            for flag, expected in (
                ("--mapping-profile", "go2-onboard"),
                ("--profile", str(project / "config/go2-onboard.json")),
                ("--spatial-route-dir", str(storage / "state/spatial-routes")),
                ("--operator-event-dir", str(storage / "runtime/operator-events")),
                ("--navigation-runtime-dir", str(storage / "state/navigation")),
            ):
                self.assertEqual(arguments[arguments.index(flag) + 1], expected)

    def test_foreign_sensor_processes_are_refused_without_stopping_them(self):
        for launcher, expected in (
            ("start_xt16_preview_humble.sh", "refused duplicate Hesai driver"),
            ("start_hesai_mapping_humble.sh", "refused foreign FAST-LIO"),
        ):
            with self.subTest(launcher=launcher), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                scripts = root / "scripts"
                binaries = root / "bin"
                scripts.mkdir()
                binaries.mkdir()
                target = scripts / launcher
                target.write_text((ROOT / "scripts" / launcher).read_text())
                (scripts / "setup_go2_ros2_humble.sh").write_text("true\n")
                for name in ("run_hesai_driver_humble.sh", "run_xt16_bridge_humble.sh", "run_hesai_fastlio_humble.sh"):
                    runner = scripts / name
                    runner.write_text('#!/bin/sh\ntouch "$ROBOT_SCOPE_WORKSPACE_ROOT/launched"\n')
                    runner.chmod(0o755)
                for name, body in (("pgrep", "echo 4242"), ("stat", "echo 1001"), ("id", "echo 1000")):
                    binary = binaries / name
                    binary.write_text("#!/bin/sh\n" + body + "\n")
                    binary.chmod(0o755)
                result = subprocess.run(
                    ["bash", str(target)], env={
                        "PATH": f"{binaries}:/usr/bin:/bin", "HOME": str(root),
                        "ROBOT_SCOPE_WORKSPACE_ROOT": str(root),
                        "ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard",
                    }, capture_output=True, text=True, check=False, timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertFalse((root / "launched").exists())


if __name__ == "__main__":
    unittest.main()
