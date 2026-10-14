import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scripts.evaluate_recorded_se3 import qualified_inputs
from robot_dashboard.relocalization.experimental_se3 import ExperimentalSE3Error


class RecordedSE3InputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = {"schema": "robot-scope.recorded-se3-input.v1", "evidence_type": "recorded_real",
                         "provenance": {"calibration_verified": True, "clock_verified": True,
                                        "frames_connected_verified": True, "independent_collection_verified": True,
                                        "reference_contains_query": False, "transform_direction": "T_target_source",
                                        "query_registration_application_count": 1,
                                        "sensor_config_sha256": "a"*64, "calibration_sha256": "b"*64},
                         "seeds": [{"source": "operator_survey", "T_target_source": np.eye(4).tolist()}]}
        for role, session in (("reference", "reference-session"), ("query", "query-session")):
            file = self.root / (role + ".npy")
            np.save(file, np.random.default_rng(4 if role=="reference" else 5).uniform(-1, 1, (80, 3)))
            self.manifest[role] = {"session_id": session, "map_family_id": "nonoperational-test-family",
                                   "map_revision": "c"*64, "frame": "map", "path": file.name,
                                   "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "unit": "m",
                                   "kind": "REGISTERED_MAP" if role=="reference" else "REGISTERED_QUERY",
                                   "source_stamp_ns": None if role=="reference" else 123456789}

    def test_qualified_contract_loads_without_applying_transform(self):
        reference, query, seeds = qualified_inputs(self.manifest, self.root)
        np.testing.assert_array_equal(query.points, np.load(self.root / "query.npy"))
        self.assertEqual(query.stamp_ns, 123456789)
        np.testing.assert_array_equal(seeds[0], np.eye(4))

    def test_unknown_clock_calibration_same_session_raw_and_truth_seed_reject(self):
        mutations = [("provenance", "clock_verified", False), ("provenance", "calibration_verified", False),
                     ("provenance", "reference_contains_query", True),
                     ("provenance", "query_registration_application_count", 2),
                     ("query", "session_id", "reference-session"), ("query", "kind", "RAW_CLOUD"),
                     ("query", "map_revision", "d"*64), ("query", "source_stamp_ns", None)]
        for section, key, value in mutations:
            manifest = copy.deepcopy(self.manifest);manifest[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ExperimentalSE3Error):
                qualified_inputs(manifest, self.root)
        self.manifest["seeds"][0]["source"] = "ground_truth"
        with self.assertRaises(ExperimentalSE3Error):qualified_inputs(self.manifest, self.root)

    def test_identical_file_with_different_session_labels_rejects(self):
        self.manifest["query"]["sha256"] = self.manifest["reference"]["sha256"]
        with self.assertRaisesRegex(ExperimentalSE3Error, "byte-identical"):
            qualified_inputs(self.manifest, self.root)

    def test_hash_point_limit_and_nonfinite_data_fail_before_registration(self):
        self.manifest["query"]["sha256"] = "0"*64
        with self.assertRaisesRegex(ExperimentalSE3Error, "hash"):qualified_inputs(self.manifest, self.root)
        file = self.root / "query.npy"
        for points in (np.zeros((4001, 3)), np.full((80, 3), np.nan)):
            np.save(file, points);self.manifest["query"]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
            with self.assertRaises(ExperimentalSE3Error):qualified_inputs(self.manifest, self.root)
