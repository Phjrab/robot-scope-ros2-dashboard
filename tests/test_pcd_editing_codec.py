"""Synthetic full-source fixtures only; no robot or sensor-data dependency."""

import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.pcd_editing.geometry import PcdEditError, point_in_region, validate_regions
from robot_dashboard.pcd_editing.pcd import filter_pcd


def region(**overrides):
    value = {"kind": "visibility", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]], "z_min": 0, "z_max": 1}
    value.update(overrides)
    return value


def pcd_bytes(points, *, fields=None, width=None, viewpoint="1 2 3 0.5 0.5 0.5 0.5", count=True):
    if fields is None:
        fields = [("x", 4, "F", 1), ("y", 4, "F", 1), ("z", 4, "F", 1)]
    descriptors = []
    for name, size, kind, items in fields:
        dtype_code = {"F": "f", "I": "i", "U": "u"}[kind]
        base = np.dtype(f"<{dtype_code}{size}")
        descriptors.append((name, base) if items == 1 else (name, base, (items,)))
    records = np.array(points, dtype=np.dtype(descriptors))
    width = len(records) if width is None else width
    header = ["# synthetic test cloud", "VERSION 0.7", "FIELDS " + " ".join(item[0] for item in fields),
              "SIZE " + " ".join(str(item[1]) for item in fields), "TYPE " + " ".join(item[2] for item in fields)]
    if count:
        header.append("COUNT " + " ".join(str(item[3]) for item in fields))
    header.extend([f"WIDTH {width}", f"HEIGHT {len(records) // width}", f"VIEWPOINT {viewpoint}", f"POINTS {len(records)}", "DATA binary"])
    return ("\n".join(header) + "\n").encode("ascii") + records.tobytes(), records


def payload(path):
    header, body = path.read_bytes().split(b"DATA binary\n", 1)
    return header.decode("ascii"), body


class GeometryTests(unittest.TestCase):
    def test_defensive_normalization_is_json_safe(self):
        original = region()
        normalized = validate_regions([original])
        self.assertEqual(normalized[0]["selection"], "inside")
        original["polygon"][0][0] = 900
        self.assertEqual(normalized[0]["polygon"][0], [0, 0])
        json.dumps(normalized, allow_nan=False)

    def test_inclusive_edges_vertices_and_z_planes(self):
        for point in ([0, 0, 0], [1, 1, 1], [0.5, 0, 0.5], [0.5, 0.5, 1]):
            with self.subTest(point=point):
                self.assertTrue(point_in_region(point, region()))
        for point in ([-0.01, 0, 0], [0, 0, -0.01], [0.5, 0.5, 1.01]):
            self.assertFalse(point_in_region(point, region()))

    def test_outside_complements_xy_only_and_excludes_polygon_boundary(self):
        selected = region(selection="outside")
        for point, expected in (([2, 2, 0.5], True), ([1, 1, 0.5], False), ([2, 2, -1], False), ([2, 2, 2], False)):
            self.assertEqual(point_in_region(point, selected), expected)

    def test_scale_normalization_handles_huge_and_tiny_finite_coordinates(self):
        for scale in (1e-200, 1e200):
            selected = region(polygon=[[0, 0], [scale, 0], [scale, scale], [0, scale]])
            self.assertTrue(point_in_region([scale / 2, scale / 2, 0], selected))
            self.assertFalse(point_in_region([scale * 2, scale / 2, 0], selected))

    def test_concave_and_clockwise_polygons(self):
        polygon = [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]]
        for ordered in (polygon, polygon[::-1]):
            self.assertTrue(point_in_region([0.5, 1.5, 0], region(polygon=ordered)))
            self.assertFalse(point_in_region([1.5, 1.5, 0], region(polygon=ordered)))

    def test_invalid_polygons_and_region_shapes_are_rejected(self):
        invalid = [None, {}, region(extra=True), region(kind="nav2"), region(selection="all"),
                   region(z_min=2, z_max=1), region(z_min=True), region(z_max=math.inf),
                   region(polygon=[[0, 0], [1, 1]]), region(polygon=[[0, 0], [1, 1], [0, 0]]),
                   region(polygon=[[0, 0], [1, 1], [0, 1], [1, 0]]),
                   region(polygon=[[0, 0], [2, 0], [1, 0], [1, 1]]),
                   region(polygon=[[0, 0], [1, 0], [2, 0]]),
                   region(polygon=[[0, 0], [1, 0], [1, math.nan]]),
                   region(polygon=[[0, 0], [1, 0], [1, 1], [0, 0]])]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(PcdEditError):
                validate_regions([value])
        for value in ((), {}, [region()] * 101, [region(polygon=[[index, 0] for index in range(257)])]):
            with self.assertRaises(PcdEditError):
                validate_regions(value)

    def test_point_validation_rejects_nonfinite_and_boolean(self):
        for point in ([math.nan, 0, 0], [0, math.inf, 0], [True, 0, 0], [0, 0], "xyz"):
            with self.assertRaises(PcdEditError):
                point_in_region(point, region())

    def test_javascript_geometry_parity(self):
        node = os.environ.get("PCD_EDIT_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Set PCD_EDIT_NODE to run parity against the existing JavaScript editor")
        randomizer = random.Random(842)
        points = [[randomizer.uniform(-1, 3), randomizer.uniform(-1, 3), randomizer.choice([-1, 0, 0.5, 1, 2])] for _ in range(160)]
        points.extend([[0, 0, 0], [1, 1, 1], [0.5, 0, 0.5], [2, 2, 0], [1, 0.5, 1]])
        cases = [region(), region(selection="outside"),
                 region(kind="localization", polygon=[[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]]),
                 region(polygon=[[0, 0], [1, 1], [0, 1], [1, 0]]),
                 region(polygon=[[0, 0], [2, 0], [1, 0], [1, 1]]),
                 region(polygon=[[0, 0], [1e200, 0], [1e200, 1e200], [0, 1e200]]),
                 region(polygon=[[0, 0], [1e-200, 0], [1e-200, 1e-200], [0, 1e-200]])]
        core = Path(__file__).resolve().parents[1] / "robot_dashboard/static/features/map_editor3d/core.js"
        script = """
import { readFileSync } from 'node:fs';
const input = JSON.parse(readFileSync(0, 'utf8'));
const {validateRegion, pointInRegion} = await import('data:text/javascript;base64,' + readFileSync(input.core).toString('base64'));
console.log(JSON.stringify(input.cases.map(value => {
  try { const normalized = validateRegion(value); return {valid: true, normalized, points: input.points.map(p => pointInRegion(p, normalized))}; }
  catch { return {valid: false}; }
})));
"""
        run = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps({"core": str(core), "cases": cases, "points": points}), text=True, capture_output=True, check=True)
        javascript = json.loads(run.stdout)
        for value, expected in zip(cases, javascript):
            with self.subTest(value=value):
                try:
                    normalized = validate_regions([value])[0]
                except PcdEditError:
                    self.assertFalse(expected["valid"])
                else:
                    self.assertTrue(expected["valid"])
                    self.assertEqual(normalized, expected["normalized"])
                    self.assertEqual([point_in_region(point, normalized) for point in points], expected["points"])


class BinaryCodecTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.pcd"
        self.target = self.root / "new.pcd"
        self.data, self.records = pcd_bytes([(0, 0, 0), (0.5, 0.5, 0.5), (2, 2, 0.5), (2, 2, 2)])
        self.source.write_bytes(self.data)

    def tearDown(self):
        self.temporary.cleanup()

    def test_filters_entire_source_in_chunks_including_points_absent_from_preview(self):
        preview = self.records[[0, 3]]
        self.assertNotIn(0.5, preview["x"])
        result = filter_pcd(self.source, self.target, [region()], "visibility", chunk_points=1)
        header, body = payload(self.target)
        self.assertEqual(body, self.records[[2, 3]].tobytes())
        self.assertEqual(result["source_points"], 4)
        self.assertEqual(result["output_points"], 2)
        self.assertEqual(result["removed_points"], 2)
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(result["output_sha256"], hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertIn("WIDTH 2", header)
        self.assertIn("HEIGHT 1", header)
        self.assertIn("POINTS 2", header)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_preserves_all_types_multicount_fields_order_and_viewpoint(self):
        fields = [("descriptor", 2, "I", 3), ("z", 8, "F", 1), ("x", 8, "F", 1), ("rgb", 4, "U", 1), ("y", 8, "F", 1), ("label", 1, "U", 1), ("timestamp", 8, "U", 1)]
        data, records = pcd_bytes([([1, -2, 3], 0, 0, 0xFFFFFFFF, 0, 255, 2**63 + 41), ([4, 5, -6], 2, 3, 0xFF112233, 4, 7, 2**63 + 67)], fields=fields)
        self.source.write_bytes(data)
        result = filter_pcd(self.source, self.target, [region()], "visibility")
        header, body = payload(self.target)
        self.assertEqual(body, records[[1]].tobytes())
        self.assertIn("FIELDS descriptor z x rgb y label timestamp", header)
        self.assertIn("COUNT 3 1 1 1 1 1 1", header)
        self.assertIn("VIEWPOINT 1 2 3 0.5 0.5 0.5 0.5", header)
        self.assertEqual(result["fields"], [{"name": name, "size": size, "type": kind, "count": count} for name, size, kind, count in fields])

    def test_optional_count_defaults_to_one_and_organized_cloud_is_flattened(self):
        data, records = pcd_bytes([(0, 0, 0), (2, 2, 2), (3, 3, 3), (4, 4, 4)], count=False, width=2)
        self.source.write_bytes(data)
        filter_pcd(self.source, self.target, [region()], "visibility")
        header, body = payload(self.target)
        self.assertEqual(body, records[1:].tobytes())
        self.assertIn("WIDTH 3", header)
        self.assertIn("HEIGHT 1", header)
        self.assertNotIn("COUNT", header)

    def test_nonfinite_records_keep_original_nan_payload_and_other_field_bytes(self):
        data, records = pcd_bytes([(0, 0, 0), (math.nan, 0, 0), (2, math.inf, 0), (2, 2, -math.inf)])
        raw = bytearray(records.tobytes())
        # A quiet NaN with a distinctive payload; never reconstruct this float.
        raw[records.dtype.itemsize:records.dtype.itemsize + 4] = bytes.fromhex("3412c07f")
        header = data[:len(data) - records.nbytes]
        self.source.write_bytes(header + raw)
        result = filter_pcd(self.source, self.target, [region(selection="outside"), region()], "visibility", chunk_points=2)
        self.assertEqual(payload(self.target)[1], bytes(raw[records.dtype.itemsize:]))
        self.assertEqual(result["nonfinite_points_preserved"], 3)
        self.assertEqual(result["output_points"], 3)

    def test_only_selected_purpose_union_is_removed_and_keepout_is_annotation_only(self):
        regions = [region(), region(), region(kind="localization", selection="outside"), region(kind="keepout", z_max=100)]
        visibility = filter_pcd(self.source, self.target, regions, "visibility")
        self.assertEqual(visibility["removed_points"], 2)
        other = self.root / "localization.pcd"
        localization = filter_pcd(self.source, other, regions, "localization")
        self.assertEqual(localization["removed_points"], 1)
        self.assertEqual(payload(other)[1], self.records[[0, 1, 3]].tobytes())
        with self.assertRaises(PcdEditError):
            filter_pcd(self.source, self.root / "keepout.pcd", regions, "keepout")

    def test_no_regions_copies_records_without_mutating_source(self):
        result = filter_pcd(self.source, self.target, [], "visibility", chunk_points=3)
        self.assertEqual(payload(self.target)[1], self.records.tobytes())
        self.assertEqual(result["removed_points"], 0)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_existing_output_and_source_path_are_never_overwritten(self):
        self.target.write_bytes(b"existing result")
        for target in (self.target, self.source):
            with self.assertRaises(PcdEditError):
                filter_pcd(self.source, target, [region()], "visibility")
        self.assertEqual(self.target.read_bytes(), b"existing result")
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_empty_result_is_rejected_and_owned_partial_file_removed(self):
        with self.assertRaisesRegex(PcdEditError, "no points"):
            filter_pcd(self.source, self.target, [region(polygon=[[-1, -1], [3, -1], [3, 3], [-1, 3]], z_max=3)], "visibility")
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_failed_fsync_removes_only_new_output(self):
        with patch("robot_dashboard.pcd_editing.pcd.os.fsync", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(PcdEditError):
                filter_pcd(self.source, self.target, [], "visibility")
        self.assertFalse(self.target.exists())

    def test_cleanup_does_not_remove_replacement_owned_by_another_writer(self):
        def replace_then_fail(_descriptor):
            self.target.rename(self.root / "original-owned-output.pcd")
            self.target.write_bytes(b"another writer's file")
            raise OSError("synthetic replacement")

        with patch("robot_dashboard.pcd_editing.pcd.os.fsync", side_effect=replace_then_fail):
            with self.assertRaises(PcdEditError):
                filter_pcd(self.source, self.target, [], "visibility")
        self.assertEqual(self.target.read_bytes(), b"another writer's file")

    def test_dangling_symlink_target_is_not_followed(self):
        outside = self.root / "must-not-create.pcd"
        self.target.symlink_to(outside)
        with self.assertRaises(PcdEditError):
            filter_pcd(self.source, self.target, [], "visibility")
        self.assertTrue(self.target.is_symlink())
        self.assertFalse(outside.exists())

    def test_output_byte_limit_also_cleans_partial_file(self):
        with self.assertRaisesRegex(PcdEditError, "Edited PCD exceeds"):
            filter_pcd(self.source, self.target, [], "visibility", max_bytes=len(self.data))
        self.assertFalse(self.target.exists())

    def test_interrupted_filter_cleans_owned_partial_file(self):
        with patch("robot_dashboard.pcd_editing.pcd.os.fsync", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                filter_pcd(self.source, self.target, [], "visibility")
        self.assertFalse(self.target.exists())

    def test_source_change_during_filter_is_rejected_and_cleaned(self):
        from robot_dashboard.pcd_editing import pcd
        original = pcd._selection_mask

        def change_source(*args):
            with self.source.open("ab") as stream:
                stream.write(b"unexpected")
            return original(*args)

        with patch.object(pcd, "_selection_mask", side_effect=change_source):
            with self.assertRaisesRegex(PcdEditError, "changed"):
                filter_pcd(self.source, self.target, [region()], "visibility")
        self.assertFalse(self.target.exists())

    def test_limits_and_invalid_options_are_rejected_before_output(self):
        for options in ({"max_points": 3}, {"max_bytes": len(self.data) - 1}, {"chunk_points": 0}, {"max_points": True}, {"max_bytes": -1}):
            with self.subTest(options=options), self.assertRaises(PcdEditError):
                filter_pcd(self.source, self.target, [], "visibility", **options)
            self.assertFalse(self.target.exists())

    def test_malformed_binary_headers_and_payloads_are_rejected(self):
        corruptions = [
            self.data.replace(b"DATA binary", b"DATA ascii"),
            self.data.replace(b"DATA binary", b"DATA binary_compressed"),
            self.data.replace(b"POINTS 4", b"POINTS 5"),
            self.data.replace(b"WIDTH 4", b"WIDTH 2"),
            self.data.replace(b"HEIGHT 1", b"HEIGHT 0"),
            self.data.replace(b"COUNT 1 1 1", b"COUNT 1 1 2"),
            self.data.replace(b"COUNT 1 1 1", b"COUNT 1 1 0"),
            self.data.replace(b"SIZE 4 4 4", b"SIZE 4 4 3"),
            self.data.replace(b"TYPE F F F", b"TYPE F F X"),
            self.data.replace(b"SIZE 4 4 4", b"SIZE 4 4 2"),
            self.data.replace(b"FIELDS x y z", b"FIELDS x x z"),
            self.data.replace(b"FIELDS x y z", b"FIELDS x y intensity"),
            self.data.replace(b"TYPE F F F", b"TYPE F F"),
            self.data.replace(b"WIDTH 4", b"WIDTH -4"),
            self.data.replace(b"WIDTH 4", b"WIDTH 4\nWIDTH 4"),
            self.data.replace(b"VERSION 0.7", b"VERSION 0.6"),
            self.data.replace(b"POINTS 4\n", b""),
            self.data.replace(b"POINTS 4", b"POINTS 0"),
            self.data.replace(b"VIEWPOINT 1 2 3 0.5 0.5 0.5 0.5", b"VIEWPOINT 1 2 3 nan 0 0 0"),
            self.data.replace(b"VIEWPOINT 1 2 3 0.5 0.5 0.5 0.5", b"VIEWPOINT 1 2 3"),
            self.data.replace(b"COUNT 1 1 1", b"COUNT 1 1 18446744073709551616"),
            self.data[:-1], self.data + b"extra", b"#" * 65537, self.data.replace(b"VERSION", b"UNKNOWN"),
        ]
        for data in corruptions:
            with self.subTest(data=data[:180]):
                self.source.write_bytes(data)
                with self.assertRaises(PcdEditError):
                    filter_pcd(self.source, self.target, [], "visibility")
                self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
