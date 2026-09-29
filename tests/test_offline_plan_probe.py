"""Synthetic-only connectivity cases; no ROS planner or hardware transport."""

import unittest
from dataclasses import replace
from pathlib import Path

from robot_dashboard.offline_plan_probe import probe_connectivity
from robot_dashboard.saved_maps import NavigationMapSnapshot
from robot_dashboard.spatial_routes import ROBOT_RADIUS_M


FAMILY = {
    "family_id": "f" * 24,
    "family_revision": "1" * 64,
    "pcd_map_id": "p" * 24,
    "pcd_revision": "2" * 64,
    "occupancy_map_id": "m" * 24,
    "occupancy_revision": "3" * 64,
}


class OfflinePlanProbeTests(unittest.TestCase):
    def setUp(self):
        self.cells = bytearray([0] * (12 * 12))
        self.snapshot = NavigationMapSnapshot(
            map_id=FAMILY["occupancy_map_id"],
            revision=FAMILY["occupancy_revision"],
            name="synthetic-grid",
            frame_id="map",
            yaml_path=Path("unused.yaml"),
            image_path=Path("unused.pgm"),
            width=12,
            height=12,
            resolution=0.5,
            origin=(0.0, 0.0, 0.0),
            occupancy=bytes(self.cells),
            family_id=FAMILY["family_id"],
            family_revision=FAMILY["family_revision"],
            source_pcd_id=FAMILY["pcd_map_id"],
            source_pcd_revision=FAMILY["pcd_revision"],
            occupancy_map_id=FAMILY["occupancy_map_id"],
            occupancy_map_revision=FAMILY["occupancy_revision"],
        )

    def probe(self, **changes):
        inputs = dict(
            map_family=FAMILY,
            annotations={
                "map_id": FAMILY["occupancy_map_id"],
                "map_revision": FAMILY["occupancy_revision"],
                "annotation_revision": "4" * 64,
                "polygons": [],
            },
            start=(1.25, 1.25),
            goal=(4.25, 4.25),
            pose_age_s=0.1,
            max_pose_age_s=0.75,
            tf_authorities={"map_to_odom": 1, "odom_to_base": 1},
            robot_radius_m=ROBOT_RADIUS_M,
        )
        inputs.update(changes)
        return probe_connectivity(self.snapshot, **inputs)

    def test_reachable_is_diagnostic_only(self):
        result = self.probe()
        self.assertTrue(result["reachable"])
        self.assertEqual(result["reason"], "CONNECTED")
        self.assertFalse(result["actual_nav2_run"])
        self.assertEqual(result["engine"], "OFFLINE_GRID_CONNECTIVITY_NOT_NAV2")
        self.assertEqual(result["cell_count"], len(result["path_cells"]))
        for left, right in zip(result["path_cells"], result["path_cells"][1:]):
            self.assertEqual(abs(left[0] - right[0]) + abs(left[1] - right[1]), 1)

    def test_goal_occupied_unknown_and_outside_fail_closed(self):
        for value, reason in ((100, "GOAL_NOT_KNOWN_FREE"), (255, "GOAL_NOT_KNOWN_FREE")):
            with self.subTest(value=value):
                cells = bytearray(self.cells)
                cells[8 * 12 + 8] = value
                self.snapshot = replace(self.snapshot, occupancy=bytes(cells))
                self.assertEqual(self.probe()["reason"], reason)
        self.assertEqual(self.probe(goal=(20.0, 20.0))["reason"], "GOAL_OUTSIDE_MAP")

    def test_blocked_corridor_and_unknown_are_not_traversed(self):
        for value in (100, 255):
            with self.subTest(value=value):
                cells = bytearray(self.cells)
                for y in range(12):
                    cells[y * 12 + 6] = value
                self.snapshot = replace(self.snapshot, occupancy=bytes(cells))
                self.assertEqual(self.probe()["reason"], "NO_KNOWN_FREE_CONNECTION")

    def test_lineage_pose_and_tf_preflight(self):
        self.assertEqual(
            self.probe(map_family={**FAMILY, "pcd_revision": "9" * 64})["reason"],
            "MAP_LINEAGE_MISMATCH",
        )
        self.assertEqual(self.probe(pose_age_s=None)["reason"], "POSE_MISSING_OR_STALE")
        self.assertEqual(self.probe(pose_age_s=0.751)["reason"], "POSE_MISSING_OR_STALE")
        self.assertEqual(
            self.probe(annotations={"map_id": FAMILY["occupancy_map_id"], "map_revision": "9" * 64})["reason"],
            "ANNOTATION_MAP_REVISION_MISMATCH",
        )
        for count in (0, 2):
            with self.subTest(count=count):
                self.assertEqual(
                    self.probe(tf_authorities={"map_to_odom": count, "odom_to_base": 1})["reason"],
                    "TF_MISSING_OR_CONFLICTING",
                )

    def test_e1_keep_out_annotation_rejects_candidate(self):
        annotation = {
            "map_id": FAMILY["occupancy_map_id"],
            "map_revision": FAMILY["occupancy_revision"],
            "annotation_revision": "4" * 64,
            "polygons": [{
                "id": "k" * 24,
                "type": "KEEP_OUT",
                "name": "middle",
                "vertices": [
                    {"x": 2.0, "y": 0.0}, {"x": 3.0, "y": 0.0},
                    {"x": 3.0, "y": 6.0}, {"x": 2.0, "y": 6.0},
                ],
            }],
        }
        self.assertEqual(self.probe(annotations=annotation)["reason"], "E1_CONSTRAINT_REJECTED")


if __name__ == "__main__":
    unittest.main()
