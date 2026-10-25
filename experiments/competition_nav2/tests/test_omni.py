# ruff: noqa: E402
"""Negative gate and independent kinematic checks for the explicit Omni revision."""

import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import Boundary, Command, LIMITS, propagate
from omni import OmniBoundary, OmniCommand, OMNI_ZERO, propagate_omni, swept_omni
from configure import candidate
from d0_adapter import load_fixture, input_path


class OmniTests(unittest.TestCase):
    def gate(self):
        gate = OmniBoundary()
        gate.sensor(0.0, 0.0)
        gate.set_hold(False, 0.0)
        return gate

    def test_body_lateral_uses_current_yaw(self):
        result = propagate_omni((2, 3, math.pi / 2), 0, 0.08, 0, 0.5)
        self.assertAlmostEqual(result[0], 1.96)
        self.assertAlmostEqual(result[1], 3.0)

    def test_twist_integral_matches_independent_midpoint_integration(self):
        pose = (0.2, 0.6, 1.1)
        vx, vy, w, dt = 0.12, -0.07, 0.5, 0.7
        result = propagate_omni(pose, vx, vy, w, dt)
        n = 10000
        x, y, yaw = pose
        for i in range(n):
            mid = yaw + w * dt * (i + 0.5) / n
            x += (vx * math.cos(mid) - vy * math.sin(mid)) * dt / n
            y += (vx * math.sin(mid) + vy * math.cos(mid)) * dt / n
        self.assertAlmostEqual(result[0], x, places=9)
        self.assertAlmostEqual(result[1], y, places=9)
        self.assertEqual(propagate_omni(pose, vx, 0, w, dt), propagate(pose, vx, w, dt))

    def test_sweep_bounds_include_lateral_corner_motion(self):
        samples = swept_omni((0, 0, 1), 0.16, 0.08, 0.6, 0.1, 0.54)
        for a, b in zip(samples, samples[1:]):
            self.assertLessEqual(
                math.dist(a[:2], b[:2]) + 0.54 * abs(a[2] - b[2]), 0.005 + 1e-9
            )

    def test_hold_epoch_and_fresh_release_cover_lateral(self):
        gate = self.gate()
        cmd = OmniCommand(1, gate.epoch, 0.01, 0.01, 0.1, 0.2, 0.08)
        self.assertTrue(gate.accept(cmd, 0.01))
        self.assertGreater(gate.step(0.01, 0.05)[1], 0)
        gate.set_hold(True, 0.02)
        self.assertEqual(gate.output, OMNI_ZERO)
        gate.set_hold(False, 0.03)
        self.assertFalse(gate.accept(cmd, 0.04))
        self.assertEqual(gate.step(0.04, 0.05), OMNI_ZERO)
        self.assertIsNone(gate.command)

    def test_sensor_stale_latches_three_axis_zero_even_after_new_scan(self):
        gate = self.gate()
        self.assertTrue(
            gate.accept(OmniCommand(1, gate.epoch, 0.01, 0.01, 0.1, 0.1, 0.08), 0.01)
        )
        self.assertNotEqual(gate.step(0.01, 0.05), OMNI_ZERO)
        self.assertEqual(gate.step(0.251, 0.05), OMNI_ZERO)
        gate.sensor(0.26, 0)
        self.assertFalse(
            gate.accept(OmniCommand(2, gate.epoch, 0.27, 0.27, 0.1, 0, 0.08), 0.27)
        )
        self.assertEqual(gate.step(0.27, 0.05), OMNI_ZERO)
        self.assertEqual(gate.fault, "SENSOR_STALE")

    def test_old_source_with_fresh_receipt_does_not_refresh_lateral_command(self):
        gate = self.gate()
        gate.sensor(0.3, 0)
        self.assertFalse(
            gate.accept(OmniCommand(1, gate.epoch, 0.01, 0.3, 0, 0, 0.08), 0.3)
        )
        self.assertEqual(gate.step(0.3, 0.05), OMNI_ZERO)

    def test_out_of_bound_nonfinite_and_wrong_model_latch(self):
        for cmd in [
            OmniCommand(1, 1, 0.01, 0.01, 0, 0, 0.081),
            OmniCommand(1, 1, 0.01, 0.01, 0.18, 0, 0.08),
            OmniCommand(1, 1, 0.01, 0.01, 0, 0, math.nan),
            Command(1, 1, 0.01, 0.01, 0.1, 0),
        ]:
            gate = self.gate()
            self.assertFalse(gate.accept(cmd, 0.01))
            self.assertIsNotNone(gate.fault)
            self.assertEqual(gate.output, OMNI_ZERO)

    def test_vector_slew_and_immediate_native_stop(self):
        gate = self.gate()
        previous = OMNI_ZERO
        for i in range(1, 9):
            now = i * 0.02
            self.assertTrue(
                gate.accept(OmniCommand(i, gate.epoch, now, now, 0.16, 0.6, 0.08), now)
            )
            out = gate.step(now, 0.02)
            self.assertLessEqual(
                math.dist(out[:2], previous[:2]), LIMITS["a"] * 0.02 + 1e-12
            )
            self.assertLessEqual(math.hypot(*out[:2]), LIMITS["v"])
            self.assertLessEqual(
                abs(out[2] - previous[2]), LIMITS["alpha"] * 0.02 + 1e-12
            )
            previous = out
        self.assertTrue(
            gate.accept(OmniCommand(9, gate.epoch, 0.18, 0.18, 0, 0, 0), 0.18)
        )
        self.assertEqual(gate.step(0.18, 0.02), OMNI_ZERO)
        self.assertEqual(Boundary().output, (0, 0))

    def test_native_lattice_matches_grid_and_keeps_scene_and_body(self):
        fixture = load_fixture(input_path("feasible1"))
        baseline = candidate("mppi", fixture=fixture)
        omni = candidate("mppi", "omni_lattice", fixture)
        for name in (
            "global_costmap",
            "local_costmap",
            "behavior_server",
            "bt_navigator",
        ):
            self.assertEqual(omni[name], baseline[name])
        primitive = json.loads((ROOT / "config/omni-2cm-primitives.json").read_text())
        meta = primitive["lattice_metadata"]
        self.assertEqual(meta["grid_resolution"], fixture["resolution_m"])
        self.assertEqual(meta["motion_model"], "omni")
        self.assertEqual(len(meta["heading_angles"]), meta["num_of_headings"])
        self.assertEqual(len(primitive["primitives"]), meta["number_of_trajectories"])
        north = meta["heading_angles"].index(math.pi / 2)
        ends = {
            tuple(p["poses"][-1][:2])
            for p in primitive["primitives"]
            if p["start_angle_index"] == north and p["end_angle_index"] == north
        }
        # Costmap resolution alone is insufficient: translation must reach
        # neighboring cells without forcing a 10 cm jump over a narrow passage.
        self.assertTrue({(0.02, 0), (-0.02, 0), (0, 0.02)} <= ends)
        for p in primitive["primitives"]:
            for axis in p["poses"][-1][:2]:
                self.assertAlmostEqual(axis / 0.02, round(axis / 0.02), places=4)
            self.assertAlmostEqual(
                p["poses"][-1][2], meta["heading_angles"][p["end_angle_index"]]
            )
        follow = omni["controller_server"]["ros__parameters"]["FollowPath"]
        self.assertEqual(follow["motion_model"], "Omni")
        self.assertLessEqual(
            math.hypot(follow["vx_max"], follow["vy_max"]), LIMITS["v"]
        )
