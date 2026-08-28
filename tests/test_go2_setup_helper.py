from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup_go2_ros2_humble.sh"


class Go2SetupHelperTests(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_contract_is_platform_neutral_and_fail_closed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("jetson_orin_nano", source)
        self.assertIn("ROBOT_SCOPE_GO2_INTERFACE", source)
        self.assertIn("ROBOT_SCOPE_GO2_INTERFACE_CIDR", source)
        self.assertIn("ROBOT_SCOPE_UNITREE_SETUP", source)
        self.assertIn("ROBOT_SCOPE_WORKSPACE_ROOT", source)
        self.assertIn("rmw_cyclonedds_cpp", source)
        self.assertIn('SocketReceiveBufferSize max=\\"8 MiB\\"', source)
        self.assertNotIn("eval ", source)

    def test_runtime_runners_use_the_repository_helper(self) -> None:
        runner_names = (
            "run_go2_humble.sh",
            "run_go2_control_bridge_humble.sh",
            "run_go2_navigation_humble.sh",
            "run_static_map_humble.sh",
            "run_hesai_driver_humble.sh",
            "run_xt16_bridge_humble.sh",
            "save_hesai_map_humble.sh",
            "start_hesai_mapping_humble.sh",
        )
        for name in runner_names:
            with self.subTest(runner=name):
                source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
                self.assertIn("scripts/setup_go2_ros2_humble.sh", source)
                self.assertNotIn("$HOME/setup_go2_ros2_humble.sh", source)

    def test_missing_ros_setup_fails_when_sourced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = subprocess.run(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    'source "$1"',
                    "robot-scope-test",
                    str(SCRIPT),
                ],
                cwd=root,
                env={
                    "HOME": str(root),
                    "PATH": "/usr/bin:/bin",
                    "ROBOT_SCOPE_ROS_SETUP": str(root / "missing-ros.bash"),
                    "ROBOT_SCOPE_UNITREE_SETUP": str(root / "missing-unitree.bash"),
                },
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ROS 2 Humble setup is missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
