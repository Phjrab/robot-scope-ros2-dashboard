import unittest
from pathlib import Path


class AppConfigurationTests(unittest.TestCase):
    def test_mapping_catalog_limit_is_the_single_saver_limit_source(self):
        source = (
            Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        ).read_text(encoding="utf-8")
        output_ready = source.index("requested_output_dir.mkdir")
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

    def test_xt16_preview_requires_go2_profile_opt_in_and_ready_interface(self):
        source = (
            Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('AGENT.profile.get("xt16_preview")', source)
        self.assertIn('os.environ.get("ROBOT_SCOPE_DDS_INTERFACE_READY") == "1"', source)
        self.assertIn("MAPPING_JOBS.start_preview", source)


if __name__ == "__main__":
    unittest.main()
