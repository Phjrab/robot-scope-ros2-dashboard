"""SOFTWARE_TEST: immutable input validation and opt-in native config contracts."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import yaml

from robot_dashboard.navigation_collision_mask import CollisionMaskError, write_collision_mask
from robot_dashboard.navigation_collision_profile import (
    BINDING_SCHEMA, MASK_TOPIC, load_collision_mask, make_collision_profile,
    mask_binding, parse_mask_binding,
)
from test_navigation_collision_mask import annotations, build, geometry


ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "config" / "robot_scope_collision_replan.xml"


class VerifiedCollisionArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.artifact = build(geometry(occupancy=bytes([0, 255, 100] + [0] * 61)))
        self.output = self.root / "mask"
        write_collision_mask(self.artifact, self.output)

    def tearDown(self):
        if self.output.exists() and not self.output.is_symlink():
            os.chmod(self.output, 0o700)
        self.tmp.cleanup()

    def load(self, **kwargs):
        return load_collision_mask(self.output, expected_digest=kwargs.get("digest", self.artifact.digest))

    def mutate(self, name, payload):
        target = self.output / name
        target.chmod(0o600)
        target.write_bytes(payload)

    def test_roundtrip_rebuild_preserves_source_bytes_and_pins(self):
        loaded = self.load()
        self.assertEqual(loaded, self.artifact)
        self.assertEqual(loaded.source_occupancy[:3], bytes([0, 255, 100]))
        self.assertEqual(loaded.mask[:3], bytes([0, 100, 100]))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o500)

    def test_every_payload_tamper_rejects(self):
        for name, payload in self.artifact.files():
            with self.subTest(name=name):
                self.mutate(name, payload + b"x")
                with self.assertRaises(CollisionMaskError):
                    self.load()
                self.mutate(name, payload)

    def test_rehashed_forged_mask_still_fails_semantic_reconstruction(self):
        manifest = json.loads(self.artifact.manifest)
        forged = bytes(64)
        self.mutate("mask.occupancy.bin", forged)
        manifest["files"]["mask.occupancy.bin"]["sha256"] = hashlib.sha256(forged).hexdigest()
        manifest.pop("artifact_digest")
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        manifest["artifact_digest"] = digest
        self.mutate("manifest.json", json.dumps(manifest).encode())
        with self.assertRaises(CollisionMaskError):
            self.load(digest=digest)

    def test_expected_digest_mandatory_and_exact(self):
        for digest in (None, "", "f" * 64, True, "a" * 65):
            with self.subTest(digest=digest), self.assertRaises(CollisionMaskError):
                self.load(digest=digest)

    def test_symlink_directory_and_file_rejected(self):
        link = self.root / "link"
        link.symlink_to(self.output, target_is_directory=True)
        with self.assertRaises(CollisionMaskError):
            load_collision_mask(link, expected_digest=self.artifact.digest)
        self.output.chmod(0o700)
        target = self.output / "mask.occupancy.bin"
        target.unlink()
        external = self.root / "external"
        external.write_bytes(self.artifact.mask)
        target.symlink_to(external)
        with self.assertRaises(CollisionMaskError):
            self.load()

    def test_nonregular_input_rejected_without_blocking(self):
        self.output.chmod(0o700)
        target = self.output / "mask.occupancy.bin"
        target.unlink()
        os.mkfifo(target)
        with self.assertRaises(CollisionMaskError):
            self.load()

    def test_duplicate_json_nonfinite_and_bad_geometry_reject(self):
        for payload in (b'{"artifact_digest":"x","artifact_digest":"y"}', b'{"x":NaN}',
                        b'{"x":Infinity}', b'[]'):
            self.mutate("manifest.json", payload)
            with self.assertRaises(CollisionMaskError):
                self.load()
        manifest = json.loads(self.artifact.manifest)
        for key, value in (("width", True), ("width", 2**31), ("height", 0),
                           ("resolution", -1), ("origin", [0, 0])):
            altered = deepcopy(manifest)
            altered["geometry"][key] = value
            self.mutate("manifest.json", json.dumps(altered).encode())
            with self.assertRaises(CollisionMaskError):
                self.load()

    def test_rotated_offline_artifact_is_loaded_without_silent_rotation(self):
        artifact = build(geometry(origin=(3.0, -2.0, 0.25)))
        path = self.root / "rotated"
        write_collision_mask(artifact, path)
        try:
            self.assertEqual(load_collision_mask(path, expected_digest=artifact.digest), artifact)
        finally:
            path.chmod(0o700)


class CollisionProfileTests(unittest.TestCase):
    def setUp(self):
        self.base = yaml.safe_load((ROOT / "config" / "nav2_params_go2_humble.yaml").read_text())
        self.artifact = build(geometry())

    def profile(self, **kwargs):
        values = dict(robot_radius_m=.22, footprint_padding_m=.01, bt_xml_path=BT)
        values.update(kwargs)
        return make_collision_profile(self.base, self.artifact, **values)

    def test_opt_in_copy_binds_two_native_layers_unknown_circle_and_bt(self):
        original = deepcopy(self.base)
        profile = self.profile()
        self.assertEqual(self.base, original)
        params = profile["parameters"]
        for name in ("global_costmap", "local_costmap"):
            values = params[name][name]["ros__parameters"]
            self.assertEqual(values["plugins"][-2:], ["policy_layer", "inflation_layer"])
            self.assertTrue(values["track_unknown_space"])
            self.assertTrue(values["use_maximum"])
            self.assertEqual(values["unknown_cost_value"], 255)
            self.assertEqual(values["lethal_cost_threshold"], 100)
            self.assertTrue(values["trinary_costmap"])
            self.assertEqual(values["policy_layer"]["map_topic"], MASK_TOPIC)
            self.assertFalse(values["policy_layer"]["footprint_clearing_enabled"])
            self.assertTrue(values["policy_layer"]["map_subscribe_transient_local"])
            self.assertEqual(values["robot_radius"], .22)
            self.assertEqual(values["footprint_padding"], .01)
            self.assertGreaterEqual(values["inflation_layer"]["inflation_radius"], .23 + values["resolution"])
        planner = params["planner_server"]["ros__parameters"]["GridBased"]
        self.assertFalse(planner["allow_unknown"])
        self.assertEqual(planner["tolerance"], 0.0)
        controller = params["controller_server"]["ros__parameters"]["FollowPath"]
        self.assertTrue(controller["use_collision_detection"])
        self.assertNotIn("primary_controller", controller)
        self.assertEqual(params["bt_navigator"]["ros__parameters"]["default_nav_to_pose_bt_xml"], str(BT))
        self.assertFalse(profile["manifest"]["runtime_policy_enforced"])
        self.assertEqual(profile["manifest"]["native_ingestion_evidence"], "not_provided")

    def test_no_radius_padding_fallback_and_polygon_rejected(self):
        for radius, padding in ((0, 0), (.22, -.1), (True, .01), (.22, True),
                                (float("nan"), 0), (.22, float("inf")), (3, .01), (2**4096, .01)):
            with self.subTest(radius=radius, padding=padding), self.assertRaises(CollisionMaskError):
                self.profile(robot_radius_m=radius, footprint_padding_m=padding)
        self.base["global_costmap"]["global_costmap"]["ros__parameters"]["footprint"] = "[[1,1],[1,-1],[-1,-1]]"
        with self.assertRaises(CollisionMaskError):
            self.profile()

    def test_native_rotated_or_nonmap_frame_refused(self):
        for change in ({"origin": (0, 0, .1)}, {"frame_id": "odom"}):
            self.artifact = build(geometry(**change))
            with self.assertRaises(CollisionMaskError):
                self.profile()

    def test_unknown_plugin_and_existing_filter_refused(self):
        for key, value in (("plugins", ["my_layer", "inflation_layer"]), ("filters", ["anything"])):
            self.setUp()
            self.base["local_costmap"]["local_costmap"]["ros__parameters"][key] = value
            with self.assertRaises(CollisionMaskError):
                self.profile()

    def test_profile_digest_is_deterministic_and_pins_radius_and_annotations(self):
        first = self.profile()["manifest"]["profile_digest"]
        self.assertEqual(first, self.profile()["manifest"]["profile_digest"])
        self.assertNotEqual(first, self.profile(robot_radius_m=.3)["manifest"]["profile_digest"])
        grid = geometry()
        self.artifact = build(grid, annotations(grid, [(1.1, 1.1), (2.1, 1.1), (1.1, 2.1)]))
        self.assertNotEqual(first, self.profile()["manifest"]["profile_digest"])

    def test_only_shipped_tree_and_fixed_replan_actions(self):
        with self.assertRaises(CollisionMaskError):
            self.profile(bt_xml_path=ROOT / "AGENTS.md")
        tree = ET.fromstring(BT.read_text())
        actions = [item.tag for item in tree.iter()]
        self.assertIn("ComputePathToPose", actions)
        self.assertIn("FollowPath", actions)
        self.assertNotIn("ClearEntireCostmap", actions)
        self.assertNotIn("RecoveryNode", actions)


class MaskBindingTests(unittest.TestCase):
    def setUp(self):
        self.value = mask_binding(build(geometry()), incarnation="a" * 32, sequence=1)

    def test_exact_publication_binding_and_no_enforcement_claim(self):
        self.assertEqual(parse_mask_binding(json.dumps(self.value)), self.value)
        self.assertEqual(self.value["schema"], BINDING_SCHEMA)
        self.assertFalse(self.value["runtime_policy_enforced"])

    def test_malformed_forged_true_and_unbounded_remote_fields_reject(self):
        for key, value in (("runtime_policy_enforced", True), ("sequence", True), ("sequence", 0),
                           ("sequence", 2**63), ("topic", "/map"), ("incarnation", "bad"),
                           ("frame_id", "x" * 129), ("artifact_digest", "bad"),
                           ("map_family", {}), ("evidence_kind", "native_verified"), ("secret", "/private")):
            altered = {**self.value, key: value}
            with self.subTest(key=key), self.assertRaises(CollisionMaskError):
                parse_mask_binding(json.dumps(altered))
        with self.assertRaises(CollisionMaskError):
            parse_mask_binding("x" * 4097)


if __name__ == "__main__":
    unittest.main()
