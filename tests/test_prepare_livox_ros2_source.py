import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_livox_ros2_source", ROOT / "scripts/prepare_livox_ros2_source.py")
assert SPEC and SPEC.loader
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


class LivoxSourcePreparationTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "pinned"
        source.mkdir()
        (source / ".git").mkdir()
        (source / ".git/config").write_text("preserve git metadata")
        (source / "package.xml").write_text("original ROS1 package")
        (source / "package_ROS2.xml").write_text("selected ROS2 package")
        (source / "launch_ROS2").mkdir()
        (source / "launch_ROS2/driver.py").write_text("selected launch")
        return source, root / "stage"

    def test_ros2_selection_and_rerun_preserve_original_pinned_clone(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, destination = self.fixture(Path(temporary).resolve())
            before = preparation.inventory(source)
            preparation.prepare(source, destination)
            self.assertEqual((source / "package.xml").read_text(), "original ROS1 package")
            self.assertEqual(preparation.inventory(source), before)
            self.assertEqual((destination / "package.xml").read_text(), "selected ROS2 package")
            self.assertEqual((destination / "launch/driver.py").read_text(), "selected launch")
            self.assertFalse((destination / ".git").exists())
            preparation.prepare(source, destination)
            self.assertEqual(preparation.inventory(source), before)

    def test_changed_stage_fails_without_discarding_unrelated_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, destination = self.fixture(Path(temporary).resolve())
            preparation.prepare(source, destination)
            marker = destination / "user-file"
            marker.write_text("preserve")
            with self.assertRaisesRegex(ValueError, "preserving it without reset"):
                preparation.prepare(source, destination)
            self.assertEqual(marker.read_text(), "preserve")
            self.assertEqual((source / "package.xml").read_text(), "original ROS1 package")

    def test_symlink_or_nested_destination_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, destination = self.fixture(Path(temporary).resolve())
            (source / "link").symlink_to(source / "package_ROS2.xml")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                preparation.prepare(source, destination)
            self.assertFalse(destination.exists())
            with self.assertRaisesRegex(ValueError, "separate"):
                preparation.prepare(source, source / "stage")


if __name__ == "__main__":
    unittest.main()
