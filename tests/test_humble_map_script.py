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
        self.assertGreaterEqual(len(source_indexes), 5)
        for source_index in source_indexes:
            previous = max(index for index in toggles if index < source_index)
            following = min(index for index in toggles if index > source_index)
            self.assertEqual(toggles[previous], "set +u")
            self.assertEqual(toggles[following], "set -u")

    def test_job_ros_names_cannot_start_with_a_digit(self):
        self.assertIn('JOB_TOKEN="job_$(', self.script)
        self.assertIn('MAP_TOPIC="/robot_scope/conversion/${JOB_TOKEN}/map"', self.script)

    def test_long_running_ros_nodes_are_started_without_ros2_run_wrappers(self):
        self.assertIn('"$PCD2PGM_EXEC" --ros-args', self.script)
        self.assertIn('35s "$MAP_SAVER_EXEC"', self.script)
        self.assertNotIn("ros2 run pcd2pgm", self.script)
        self.assertNotIn("ros2 run nav2_map_server", self.script)


if __name__ == "__main__":
    unittest.main()
