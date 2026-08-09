import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "robot_dashboard" / "static" / "assets"
CATALOG_PATH = ASSETS / "robot-model-catalog.json"
MODEL_CASES = {
    "turtlebot": {
        "directory": "turtlebot",
        "urdf": "generic-turtlebot.urdf",
        "asset": "generic-turtlebot-lite.json",
    },
    "so-101": {
        "directory": "so101",
        "urdf": "generic-so101.urdf",
        "asset": "generic-so101-lite.json",
    },
}


def load_builder():
    path = ROOT / "scripts" / "build_generic_robot_models.py"
    spec = importlib.util.spec_from_file_location("build_generic_robot_models", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generic model builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenericRobotAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.assets = {}
        cls.urdfs = {}
        for robot_type, case in MODEL_CASES.items():
            directory = ASSETS / case["directory"]
            cls.assets[robot_type] = json.loads(
                (directory / case["asset"]).read_text(encoding="utf-8")
            )
            cls.urdfs[robot_type] = ET.parse(directory / case["urdf"]).getroot()

    def test_catalog_maps_all_profiles_to_local_allowlisted_assets(self):
        self.assertEqual(self.catalog["schema"], "robot-scope.robot-model-catalog")
        self.assertEqual(self.catalog["version"], 1)
        self.assertEqual(set(self.catalog["models"]), {"go2", "turtlebot", "so-101"})
        for robot_type, entry in self.catalog["models"].items():
            self.assertEqual(entry["type"], robot_type)
            self.assertEqual(entry["renderer"], "triangle-skeleton")
            self.assertTrue(entry["asset_url"].startswith("/static/assets/"))
            self.assertNotIn("http://", entry["asset_url"])
            self.assertNotIn("https://", entry["asset_url"])
            asset_path = ROOT / "robot_dashboard" / "static" / entry["asset_url"].removeprefix("/static/")
            self.assertTrue(asset_path.is_file(), entry["asset_url"])
            if entry["urdf_url"]:
                urdf_path = ROOT / "robot_dashboard" / "static" / entry["urdf_url"].removeprefix("/static/")
                self.assertTrue(urdf_path.is_file(), entry["urdf_url"])
        for robot_type in MODEL_CASES:
            entry = self.catalog["models"][robot_type]
            self.assertEqual(entry["fidelity"], "generic-approximation")
            self.assertIn("generic", entry["notice"].lower())

    def test_generic_urdfs_are_local_primitive_only_mit_sources(self):
        for robot_type, robot in self.urdfs.items():
            with self.subTest(robot_type=robot_type):
                metadata = robot.find("robot_scope")
                self.assertIsNotNone(metadata)
                self.assertEqual(metadata.get("robot_type"), robot_type)
                self.assertEqual(metadata.get("fidelity"), "generic-approximation")
                self.assertIn("generic", metadata.get("notice", "").lower())
                self.assertFalse(robot.findall(".//mesh"), "external mesh references are forbidden")
                geometries = robot.findall(".//visual/geometry")
                self.assertTrue(geometries)
                for geometry in geometries:
                    primitives = [child.tag for child in geometry]
                    self.assertEqual(len(primitives), 1)
                    self.assertIn(primitives[0], {"box", "cylinder", "sphere"})

                link_names = {link.get("name") for link in robot.findall("link")}
                child_names = {joint.find("child").get("link") for joint in robot.findall("joint")}
                self.assertEqual(len(link_names - child_names), 1)

    def test_generated_assets_have_provenance_skeleton_and_valid_meshes(self):
        for robot_type, asset in self.assets.items():
            with self.subTest(robot_type=robot_type):
                self.assertEqual(asset["schema"], "robot-scope.robot-model-lite")
                self.assertEqual(asset["version"], 1)
                self.assertEqual(asset["units"], "meter")
                self.assertEqual(asset["up_axis"], "Z")
                self.assertEqual(asset["source"]["license"], "MIT")
                self.assertEqual(asset["source"]["license_file"], "/static/assets/LICENSE.txt")
                license_path = (
                    ROOT / "robot_dashboard" / "static"
                    / asset["source"]["license_file"].removeprefix("/static/")
                )
                self.assertTrue(license_path.is_file())
                self.assertIn("MIT License", license_path.read_text(encoding="utf-8"))
                self.assertEqual(asset["source"]["fidelity"], "generic-approximation")
                self.assertEqual(asset["model"]["robot_type"], robot_type)
                self.assertEqual(asset["model"]["fidelity"], "generic-approximation")
                self.assertIn("generic", asset["model"]["notice"].lower())
                self.assertTrue(asset["source"]["urdf_path"].endswith(".urdf"))

                skeleton = asset["skeleton"]
                link_names = {link["name"] for link in skeleton["links"]}
                self.assertIn(skeleton["root"], link_names)
                resolved = {skeleton["root"]}
                for joint in skeleton["joints"]:
                    self.assertIn(joint["parent"], resolved)
                    resolved.add(joint["child"])
                self.assertTrue(link_names <= resolved)
                self.assertEqual(
                    set(skeleton["default_joint_positions"]),
                    set(skeleton["joint_order"]),
                )

                counted_triangles = 0
                for mesh in asset["meshes"].values():
                    vertices = mesh["vertices_q"]
                    self.assertEqual(len(vertices) % 3, 0)
                    self.assertTrue(all(isinstance(value, int) for value in vertices))
                    self.assertTrue(all(math.isfinite(value) for value in vertices))
                    vertex_count = len(vertices) // 3
                    mesh_triangles = 0
                    for group in mesh["groups"]:
                        self.assertRegex(group["color"], r"^#[0-9a-f]{6}$")
                        self.assertEqual(len(group["indices"]) % 3, 0)
                        self.assertTrue(all(0 <= index < vertex_count for index in group["indices"]))
                        mesh_triangles += len(group["indices"]) // 3
                    self.assertEqual(mesh_triangles, mesh["statistics"]["triangles"])
                    counted_triangles += mesh_triangles
                self.assertEqual(counted_triangles, asset["model"]["asset_unique_triangles"])

    def test_committed_json_is_a_deterministic_urdf_build(self):
        for robot_type, case in MODEL_CASES.items():
            directory = ASSETS / case["directory"]
            source = directory / case["urdf"]
            committed = directory / case["asset"]
            with self.subTest(robot_type=robot_type), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "model.json"
                self.builder.build(source, output)
                self.assertEqual(output.read_bytes(), committed.read_bytes())

    def test_generic_assets_stay_lightweight(self):
        for robot_type, case in MODEL_CASES.items():
            path = ASSETS / case["directory"] / case["asset"]
            with self.subTest(robot_type=robot_type):
                self.assertLess(path.stat().st_size, 64 * 1024)


if __name__ == "__main__":
    unittest.main()
