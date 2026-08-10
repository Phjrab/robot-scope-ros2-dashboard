import subprocess
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "save_hesai_map_humble.sh"


class HumbleMapScriptTests(unittest.TestCase):
    def setUp(self):
        self.lines = SCRIPT.read_text(encoding="utf-8").splitlines()
        self.script = "\n".join(self.lines)

    def test_script_has_valid_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_generated_setup_files_are_sourced_without_nounset(self):
        toggles = {
            index: line.strip()
            for index, line in enumerate(self.lines)
            if line.strip() in {"set +u", "set -u"}
        }
        source_indexes = [
            index
            for index, line in enumerate(self.lines)
            if line.strip().startswith("source ")
        ]
        self.assertGreaterEqual(len(source_indexes), 1)
        for source_index in source_indexes:
            previous = max(index for index in toggles if index < source_index)
            following = min(index for index in toggles if index > source_index)
            self.assertEqual(toggles[previous], "set +u")
            self.assertEqual(toggles[following], "set -u")

    def test_repository_owned_saver_and_converter_are_fixed(self):
        self.assertIn('SAVE_SCRIPT="$PROJECT_DIR/scripts/save_map.py"', self.script)
        self.assertIn(
            'CONVERTER_SCRIPT="$PROJECT_DIR/scripts/convert_pcd_to_occupancy.py"',
            self.script,
        )
        self.assertNotIn("$HOME/ws/go2_3d/save_map.py", self.script)
        self.assertIn(
            'source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"',
            self.script,
        )

    def test_2d_conversion_has_no_external_ros_node_dependency(self):
        self.assertIn('"$PYTHON_BIN" "$CONVERTER_SCRIPT"', self.script)
        for forbidden in (
            "pcd2pgm",
            "map_saver_cli",
            "ros2 pkg prefix",
            "ros2 run",
            "ROS_LOCALHOST_ONLY",
        ):
            self.assertNotIn(forbidden, self.script)


if __name__ == "__main__":
    unittest.main()
