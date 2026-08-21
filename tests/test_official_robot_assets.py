from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "robot_dashboard" / "static" / "assets"
CATALOG_PATH = ASSETS / "robot-model-catalog.json"
MODEL_CASES = {
    "turtlebot": {
        "directory": ASSETS / "turtlebot",
        "asset": "turtlebot3-burger-official-lite.json",
        "urdf": "source/turtlebot3_description/urdf/turtlebot3_burger.urdf",
        "repository": "https://github.com/ROBOTIS-GIT/turtlebot3",
        "commit": "90a68bd2e3c61c12966779da89d8eeaec82730e9",
        "mesh_count": 4,
        "required_joints": {"base_joint", "wheel_left_joint", "wheel_right_joint", "scan_joint"},
        "required_links": {"base_link", "wheel_left_link", "wheel_right_link", "base_scan"},
    },
}


def load_builder():
    path = ROOT / "scripts" / "build_official_robot_models.py"
    spec = importlib.util.spec_from_file_location("build_official_robot_models", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load official model builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OfficialRobotAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.assets = {
            robot_type: json.loads(
                (case["directory"] / case["asset"]).read_text(encoding="utf-8")
            )
            for robot_type, case in MODEL_CASES.items()
        }

    def test_catalog_selects_local_official_derived_assets(self):
        self.assertEqual(self.catalog["schema"], "robot-scope.robot-model-catalog")
        self.assertEqual(self.catalog["version"], 1)
        self.assertEqual(set(self.catalog["models"]), {"go2", "turtlebot"})
        for robot_type, case in MODEL_CASES.items():
            entry = self.catalog["models"][robot_type]
            self.assertEqual(entry["type"], robot_type)
            self.assertEqual(entry["renderer"], "triangle-skeleton")
            self.assertEqual(entry["fidelity"], "official-derived")
            self.assertNotIn("generic", entry["label"].lower())
            self.assertTrue(entry["asset_url"].startswith("/static/assets/"))
            self.assertTrue(entry["urdf_url"].startswith("/static/assets/"))
            self.assertNotIn("http://", entry["asset_url"])
            self.assertNotIn("https://", entry["asset_url"])
            asset_path = ROOT / "robot_dashboard/static" / entry["asset_url"].removeprefix("/static/")
            urdf_path = ROOT / "robot_dashboard/static" / entry["urdf_url"].removeprefix("/static/")
            self.assertEqual(asset_path, case["directory"] / case["asset"])
            self.assertEqual(urdf_path, case["directory"] / case["urdf"])
            self.assertTrue(asset_path.is_file())
            self.assertTrue(urdf_path.is_file())

    def test_pinned_upstream_manifests_verify_every_source_byte(self):
        for robot_type, case in MODEL_CASES.items():
            with self.subTest(robot_type=robot_type):
                manifest = json.loads(
                    (case["directory"] / "upstream-manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["schema"], "robot-scope.upstream-asset-manifest")
                self.assertEqual(manifest["repository"], case["repository"])
                self.assertEqual(manifest["commit"], case["commit"])
                self.assertEqual(manifest["license"], "Apache-2.0")
                for relative, expected in manifest["files"].items():
                    path = case["directory"] / relative
                    self.assertTrue(path.is_file(), relative)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
                license_text = (case["directory"] / "LICENSE.txt").read_text(encoding="utf-8")
                self.assertIn("Apache License", license_text)
                self.assertIn("Version 2.0", license_text)

    def test_actual_urdfs_resolve_all_visual_meshes(self):
        for robot_type, case in MODEL_CASES.items():
            with self.subTest(robot_type=robot_type):
                model_spec = self.builder.MODEL_SPECS[robot_type]
                robot = ET.parse(case["directory"] / case["urdf"]).getroot()
                self.assertEqual(robot.tag, "robot")
                self.assertIsNone(robot.find("robot_scope"))
                references = {
                    mesh.get("filename", "")
                    for mesh in robot.findall(".//visual/geometry/mesh")
                }
                self.assertEqual(len(references), case["mesh_count"])
                for reference in references:
                    self.assertTrue(self.builder.resolve_mesh(model_spec, reference).is_file())

    def test_generated_assets_preserve_provenance_skeleton_and_mesh_contract(self):
        for robot_type, case in MODEL_CASES.items():
            asset = self.assets[robot_type]
            with self.subTest(robot_type=robot_type):
                self.assertEqual(asset["schema"], "robot-scope.robot-model-lite")
                self.assertEqual(asset["version"], 1)
                self.assertEqual(asset["units"], "meter")
                self.assertEqual(asset["up_axis"], "Z")
                self.assertEqual(asset["source"]["repository"], case["repository"])
                self.assertEqual(asset["source"]["commit"], case["commit"])
                self.assertEqual(asset["source"]["license"], "Apache-2.0")
                self.assertEqual(asset["source"]["fidelity"], "official-derived")
                self.assertEqual(asset["model"]["robot_type"], robot_type)
                self.assertEqual(asset["model"]["fidelity"], "official-derived")
                self.assertIn("byte-for-byte", asset["source"]["modifications"])

                skeleton = asset["skeleton"]
                self.assertNotIn("${namespace}", json.dumps(skeleton))
                visual_link_names = {link["name"] for link in skeleton["links"]}
                joint_names = {joint["name"] for joint in skeleton["joints"]}
                self.assertTrue(case["required_links"] <= visual_link_names)
                self.assertTrue(case["required_joints"] <= joint_names)
                resolved = {skeleton["root"]}
                for joint in skeleton["joints"]:
                    self.assertIn(joint["parent"], resolved)
                    resolved.add(joint["child"])
                self.assertTrue(visual_link_names <= resolved)
                self.assertEqual(
                    set(skeleton["default_joint_positions"]),
                    set(skeleton["joint_order"]),
                )

                counted_triangles = 0
                for mesh in asset["meshes"].values():
                    vertices = mesh["vertices_q"]
                    self.assertEqual(len(vertices) % 3, 0)
                    self.assertTrue(all(isinstance(value, int) for value in vertices))
                    vertex_count = len(vertices) // 3
                    mesh_triangles = 0
                    for group in mesh["groups"]:
                        self.assertRegex(group["color"], r"^#[0-9a-f]{6}$")
                        self.assertEqual(len(group["indices"]) % 3, 0)
                        self.assertTrue(all(0 <= index < vertex_count for index in group["indices"]))
                        mesh_triangles += len(group["indices"]) // 3
                    self.assertEqual(mesh_triangles, mesh["statistics"]["triangles"])
                    self.assertLess(mesh_triangles, mesh["statistics"]["source_triangles"])
                    counted_triangles += mesh_triangles
                self.assertEqual(counted_triangles, asset["model"]["asset_unique_triangles"])

    def test_committed_json_is_a_deterministic_official_source_build(self):
        for robot_type, case in MODEL_CASES.items():
            with self.subTest(robot_type=robot_type), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "model.json"
                spec = replace(self.builder.MODEL_SPECS[robot_type], output=output)
                self.builder.build(spec)
                committed = case["directory"] / case["asset"]
                self.assertEqual(output.read_bytes(), committed.read_bytes())

    def test_browser_derivatives_stay_lightweight(self):
        limits = {"turtlebot": 64 * 1024}
        for robot_type, case in MODEL_CASES.items():
            with self.subTest(robot_type=robot_type):
                path = case["directory"] / case["asset"]
                self.assertLess(path.stat().st_size, limits[robot_type])

    def test_catalog_does_not_reference_removed_model_assets(self):
        self.assertNotIn("so-101", self.catalog["models"])
        self.assertFalse((ASSETS / "so101").exists())


if __name__ == "__main__":
    unittest.main()
