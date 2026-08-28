import stat
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.saved_maps import prepare_private_map_root


class AppConfigurationTests(unittest.TestCase):
    def test_mapping_output_is_created_private_and_broad_existing_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            created = prepare_private_map_root(root / "maps")
            self.assertEqual(stat.S_IMODE(created.stat().st_mode), 0o700)

            broad = root / "broad-maps"
            broad.mkdir(mode=0o755)
            broad.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError, "group or others"):
                prepare_private_map_root(broad)

    def test_runners_keep_runtime_data_in_real_project_local_paths(self):
        root = Path(__file__).parents[1]
        for name in ("run_go2_humble.sh", "run_generic.sh"):
            source = (root / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn('RUNTIME_DIR="${ROBOT_SCOPE_RUNTIME_DIR:-$PROJECT_DIR/runtime}"', source)
            self.assertIn('DATASET_DIR="${ROBOT_SCOPE_DATASET_DIR:-$RUNTIME_DIR/datasets}"', source)
            self.assertIn('--source-selection-state "$SOURCE_SELECTION_STATE"', source)
            self.assertIn('--navigation-runtime-dir "$NAVIGATION_RUNTIME_DIR"', source)
            self.assertIn('--mapping-output-dir "$MAPS_DIR"', source)
            self.assertIn('--dataset-output-dir "$DATASET_DIR"', source)
            self.assertIn('ROS_LOG_DIR="${ROS_LOG_DIR:-$RUNTIME_DIR/logs/ros}"', source)
            self.assertIn('export ROS_LOG_DIR', source)

        ignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/runtime/", ignore)
        self.assertIn("/workspaces/", ignore)

    def test_mapping_catalog_limit_is_the_single_saver_limit_source(self):
        source = (
            Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        ).read_text(encoding="utf-8")
        output_ready = source.index("prepare_private_map_root(requested_output_dir)")
        catalog_ready = source.index("catalog = SavedMapCatalog.from_profile")
        manager_ready = source.index("manager = MappingJobManager.for_robot_scope")

        self.assertLess(output_ready, catalog_ready)
        self.assertLess(catalog_ready, manager_ready)
        catalog_block = source[catalog_ready:manager_ready]
        self.assertIn("additional_roots=[mapping_output_dir]", catalog_block)
        self.assertIn("managed_roots=[mapping_output_dir]", catalog_block)
        self.assertIn("map_file_limit = catalog.max_file_bytes", source)
        self.assertEqual(source.count("max_result_bytes=map_file_limit"), 2)
        self.assertNotIn("max_result_bytes=1024 * 1024 * 1024", source)

    def test_generic_runner_selects_the_supported_ros_pair(self):
        source = (
            Path(__file__).parents[1] / "scripts" / "run_generic.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('22.04) ROS_DISTRO_NAME="humble"', source)
        self.assertIn('24.04) ROS_DISTRO_NAME="jazzy"', source)
        self.assertIn('/opt/ros/$ROS_DISTRO_NAME/setup.bash', source)
        self.assertIn("humble|jazzy", source)

    def test_xt16_preview_requires_go2_profile_opt_in_and_ready_interface(self):
        source = (
            Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('RUNTIME.agent.profile.get("xt16_preview")', source)
        self.assertIn('os.environ.get("ROBOT_SCOPE_DDS_INTERFACE_READY") == "1"', source)
        self.assertIn("runtime.mapping.start_preview", source)

    def test_go2_dashboard_bounds_idle_pointcloud_processing_rate(self):
        profile = (
            Path(__file__).parents[1] / "config" / "go2.json"
        ).read_text(encoding="utf-8")
        self.assertIn('"pointcloud_frame_interval_s": 0.18', profile)


if __name__ == "__main__":
    unittest.main()
