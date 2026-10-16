"""Synthetic wire tests: no engine, sensor or end-to-end latency claims."""
from copy import deepcopy
import json
import unittest

from robot_dashboard.slam_sessions import SlamError
from robot_dashboard.slam_transport import SlamGeometryTransport


def frame():
    return dict(engine_id="visual_stereo", session_id="session", generation=1,
        map_epoch="epoch", frame_id="map", sequence=1,
        image={"stamp_ns": "1792026000123456789", "jpeg_base64": "AA=="},
        camera_pose={"stamp_ns": "1792026000123456789", "position": [1, 2, 3]},
        global_map=dict(points=[[1, 2, 3]], snapshot_id="1", map_epoch="epoch",
                        source_timestamp_ns="1792026000123456789", coordinate_frame="map"),
        trajectory=dict(points=[[0, 0, 0]], map_epoch="epoch", coordinate_frame="map"))


class SlamGeometryTransportTests(unittest.TestCase):
    def test_legacy_is_complete_and_has_no_protocol_fields(self):
        source = frame()
        transport = SlamGeometryTransport()
        for _ in range(2):
            self.assertEqual(json.loads(transport.encode(source)), source)

    def test_repeat_references_only_unchanged_layers_and_preserves_live_channels(self):
        source = frame()
        original = deepcopy(source)
        transport = SlamGeometryTransport(True)
        full = json.loads(transport.encode(source))
        repeat = json.loads(transport.encode(source))
        for name in ("global_map", "trajectory"):
            self.assertEqual(full["geometry_updates"]["layers"][name]["kind"], "full")
            self.assertEqual(repeat["geometry_updates"]["layers"][name],
                {"kind": "reference", "token": full["geometry_updates"]["layers"][name]["token"]})
            self.assertIsNone(repeat[name])
        for name in ("image", "camera_pose"):
            self.assertEqual(repeat[name], source[name])
        self.assertEqual(source, original)

    def test_coordinate_correction_with_same_stamp_count_and_id_sends_full(self):
        source = frame()
        transport = SlamGeometryTransport(True)
        first = json.loads(transport.encode(source))
        source["global_map"]["points"][0][0] = 42
        result = json.loads(transport.encode(source))
        self.assertEqual(result["global_map"]["points"], [[42, 2, 3]])
        self.assertEqual(result["geometry_updates"]["layers"]["global_map"]["kind"], "full")
        self.assertNotEqual(result["geometry_updates"]["layers"]["global_map"]["token"],
                            first["geometry_updates"]["layers"]["global_map"]["token"])
        self.assertEqual(result["geometry_updates"]["layers"]["trajectory"]["kind"], "reference")

    def test_unavailable_and_empty_layers_cannot_resurrect_old_geometry(self):
        source = frame()
        transport = SlamGeometryTransport(True)
        transport.encode(source)
        absent = json.loads(transport.encode({**source, "global_map": None}))
        self.assertNotIn("global_map", absent["geometry_updates"]["layers"])
        returned = json.loads(transport.encode(source))
        self.assertEqual(returned["geometry_updates"]["layers"]["global_map"]["kind"], "full")
        empty = deepcopy(source)
        empty["global_map"]["points"] = []
        self.assertEqual(json.loads(transport.encode(empty))["global_map"]["points"], [])

    def test_context_and_connection_reset_require_full_geometry(self):
        for name, value in [("engine_id", "other"), ("session_id", "other"),
                            ("generation", 2), ("map_epoch", "new"), ("frame_id", "other")]:
            with self.subTest(name=name):
                source = frame()
                transport = SlamGeometryTransport(True)
                transport.encode(source)
                changed = json.loads(transport.encode({**source, name: value}))
                self.assertEqual(changed["geometry_updates"]["layers"]["global_map"]["kind"], "full")
        transport.encode({"session_id": None})
        self.assertIsNotNone(json.loads(transport.encode(source))["global_map"])
        self.assertIsNotNone(json.loads(SlamGeometryTransport(True).encode(source))["global_map"])

    def test_consumers_and_returned_frames_do_not_mutate_reference_cache(self):
        a, b = SlamGeometryTransport(True), SlamGeometryTransport(True)
        source = frame()
        returned = json.loads(a.encode(source))
        returned["global_map"]["points"].clear()
        self.assertIsNone(json.loads(a.encode(source))["global_map"])
        self.assertIsNotNone(json.loads(b.encode(source))["global_map"])

    def test_invalid_json_and_wire_limit_still_rejected(self):
        for enabled in (False, True):
            for invalid in ({"value": float("nan")}, {"value": "x" * (8 * 1024**2)}):
                with self.subTest(enabled=enabled, nan=isinstance(invalid["value"], float)):
                    with self.assertRaises((ValueError, SlamError)):
                        SlamGeometryTransport(enabled).encode(invalid)


if __name__ == "__main__":
    unittest.main()
