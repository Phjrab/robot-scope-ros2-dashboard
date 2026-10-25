# ruff: noqa: E402
"""Pinned external-input contract, true sensor conformance and larger-body guards."""

import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import Boundary, Command, RADIUS, polygon
from configure import candidate, validate_config
from d0_adapter import (
    load_fixture,
    input_path,
    sensor_conformance,
    D0World,
    verify_bundle,
)
from fixtures import cases, World


class D0Tests(unittest.TestCase):
    def fixture(self, name="empty"):
        self.assertTrue(
            input_path(name).exists(),
            "materialize pinned source with prepare_d0.py before these tests",
        )
        return load_fixture(input_path(name))

    def test_all_six_sensor_probe_sets_use_original_sensor_and_dropout(self):
        for name in (
            "empty",
            "feasible1",
            "feasible2",
            "original_tight5",
            "blocked",
            "sensor_dropout",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    sensor_conformance(self.fixture(name))["status"], "PASS"
                )

    def test_truth_mutation_rejected_by_canonical_manifest(self):
        fixture = self.fixture()
        fixture["d0_bundle"]["truth"]["start"][0] += 0.01
        with self.assertRaises(ValueError):
            verify_bundle(fixture["d0_bundle"])

    def test_smaller_effective_body_is_not_accepted(self):
        fixture = self.fixture()
        fixture["effective_footprint"] = [list(p) for p in cases()[0]["footprint"]]
        with self.assertRaises(ValueError):
            D0World(fixture)

    def test_static_prior_has_no_hidden_cones_and_original_geometry_is_preserved(self):
        empty = D0World(self.fixture())
        tight = D0World(self.fixture("original_tight5"))
        self.assertTrue((empty.static == tight.static).all())
        self.assertFalse(empty.boundary_violation((0.5, 0.95, math.pi / 2)))
        self.assertTrue(empty.boundary_violation((0.5, 0.9, math.pi / 2)))
        self.assertTrue(tight.collision((0.18, 1.55, math.pi / 2), 0))
        self.assertGreater(empty.radius, RADIUS)

    def test_body_margin_config_and_sim_frame_contract(self):
        fixture = self.fixture()
        config = candidate("rpp", fixture=fixture)
        self.assertEqual(
            validate_config(config, "rpp", fixture["effective_footprint"]), []
        )
        for name in ("local_costmap", "global_costmap"):
            cm = config[name][name]["ros__parameters"]
            self.assertEqual(cm["footprint_padding"], 0.0)
            self.assertEqual(
                json.loads(cm["footprint"]),
                [list(p) for p in fixture["effective_footprint"]],
            )
            self.assertEqual(cm["resolution"], 0.02)
        self.assertEqual(
            fixture["footprint"],
            [[-0.405, -0.28], [0.405, -0.28], [0.405, 0.28], [-0.405, 0.28]],
        )
        self.assertIsNone(fixture["map_transform"])
        self.assertEqual(
            fixture["d0_source_commit"], "83f4ee8d6971d00ab31b2de0eeebf329542dd5d6"
        )

    def test_stricter_sensor_ttl_latches_and_cannot_be_relaxed(self):
        gate = Boundary(0.25)
        gate.sensor(0.0, 0.0)
        gate.set_hold(False, 0.0)
        gate.accept(Command(1, gate.epoch, 0.20, 0.20, 0.18, 0.0), 0.20)
        self.assertNotEqual(gate.step(0.20, 0.05), (0.0, 0.0))
        self.assertEqual(gate.step(0.251, 0.05), (0.0, 0.0))
        self.assertEqual(gate.fault, "SENSOR_STALE")
        with self.assertRaises(ValueError):
            Boundary(0.31)

    def test_existing_builtin_grid_and_body_unchanged(self):
        original = cases()[0]
        self.assertEqual(World(original).res, 0.04)
        self.assertEqual(polygon((0, 0, 0)), [tuple(p) for p in original["footprint"]])
        self.assertNotEqual(self.fixture()["footprint"], original["footprint"])

    def test_unprepared_external_fixture_path_rejected(self):
        with self.assertRaises(ValueError):
            load_fixture(Path("/tmp/foreign.truth.json"))


if __name__ == "__main__":
    unittest.main()
