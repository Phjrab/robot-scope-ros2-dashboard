import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "robot_dashboard/static/assets/go2/go2-official-lite.json"
LICENSE = ROOT / "robot_dashboard/static/assets/go2/LICENSE.txt"


class OfficialGo2AssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset = json.loads(ASSET.read_text(encoding="utf-8"))

    def test_provenance_and_budget(self):
        self.assertEqual(self.asset["schema"], "robot-scope.go2-official-lite")
        self.assertEqual(self.asset["source"]["license"], "BSD-3-Clause")
        self.assertEqual(
            self.asset["source"]["commit"],
            "f3772ce54c56ef2d34c6aee8100bc768896c7d19",
        )
        self.assertLess(ASSET.stat().st_size, 128 * 1024)
        self.assertIn("HangZhou YuShu TECHNOLOGY", LICENSE.read_text(encoding="utf-8"))

    def test_mesh_indices_and_statistics(self):
        asset_triangles = 0
        for mesh in self.asset["meshes"].values():
            vertex_count = len(mesh["vertices_q"]) // 3
            self.assertEqual(len(mesh["vertices_q"]) % 3, 0)
            triangles = 0
            for group in mesh["groups"]:
                self.assertEqual(len(group["indices"]) % 3, 0)
                self.assertTrue(all(0 <= index < vertex_count for index in group["indices"]))
                triangles += len(group["indices"]) // 3
            self.assertEqual(triangles, mesh["statistics"]["triangles"])
            asset_triangles += triangles
        self.assertEqual(asset_triangles, self.asset["model"]["asset_unique_triangles"])

    def test_official_urdf_skeleton_is_complete(self):
        skeleton = self.asset["skeleton"]
        link_names = {link["name"] for link in skeleton["links"]}
        joint_names = set(skeleton["joint_order"])
        self.assertEqual(len(link_names), 17)
        self.assertEqual(len(joint_names), 12)
        for leg in ("FR", "FL", "RR", "RL"):
            self.assertTrue({f"{leg}_hip", f"{leg}_thigh", f"{leg}_calf", f"{leg}_foot"} <= link_names)
            self.assertTrue({f"{leg}_hip_joint", f"{leg}_thigh_joint", f"{leg}_calf_joint"} <= joint_names)


if __name__ == "__main__":
    unittest.main()
