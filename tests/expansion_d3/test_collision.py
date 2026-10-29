import copy
import math
import unittest

import numpy as np

from robot_dashboard.collision_geometry_core import (
    Primitive,
    RobotGeometry,
    assess,
    clearance,
    official_go2,
    obstacle_primitives,
    plane_clearance,
    sweep_samples,
    transform,
)
from experiments.expansion_20261029.d3_collision_sim.fixtures import (
    frame,
    model,
    obstacle,
    oracle_circle_box,
    sensor_points,
    state,
)
from experiments.expansion_20261029.d3_collision_sim.observer import Observer


class GeometryTests(unittest.TestCase):
    def test_metric_axes_origin_and_joint_fk(self):
        xml = """<robot><link name="base"/><link name="leg"><collision>
          <origin xyz="1 0 0"/><geometry><sphere radius="0.1"/></geometry>
          </collision></link><joint name="j" type="revolute"><parent link="base"/>
          <child link="leg"/><origin xyz="0 1 0"/><axis xyz="0 0 1"/>
          <limit lower="-3.2" upper="3.2"/></joint></robot>"""
        g = RobotGeometry(xml, provenance="SYNTHETIC")
        p = g.fk(transform((2, 0, 0)), {"j": math.pi / 2})[0]
        np.testing.assert_allclose(p.pose[:3, 3], [2, 2, 0], atol=1e-12)
        with self.assertRaises(KeyError):
            g.fk(np.eye(4), {})
        with self.assertRaises(ValueError):
            g.fk(np.diag([100, 100, 100, 1]), {"j": 0})
        with self.assertRaises(ValueError):
            g.fk(np.eye(4), {"j": 4})

    def test_urdf_pin_and_dynamic_leg_envelope(self):
        g = official_go2(gait_margin=0.04)
        joints = {
            f"{leg}_{joint}_joint": q
            for leg in ("FL", "FR", "RL", "RR")
            for joint, q in [("hip", 0), ("thigh", 0.75), ("calf", -1.5)]
        }
        a = g.fk(transform((0, 0, 0.4)), joints)
        joints["FL_thigh_joint"] = 1.0
        b = g.fk(transform((0, 0, 0.4)), joints)
        self.assertEqual(len(a), 27)
        foot = next(p for p in a if p.name == "FL_foot/0")
        moved = next(p for p in b if p.name == "FL_foot/0")
        self.assertGreater(np.linalg.norm(foot.pose[:3, 3] - moved.pose[:3, 3]), 0.01)
        self.assertEqual(g.gait_margin, 0.04)
        self.assertTrue(g.unmodeled)
        self.assertNotEqual(official_go2().geometry_hash, g.geometry_hash)

    def test_mount_provenance_and_rejected_mesh(self):
        mount = Primitive("camera", "box", transform((0.7, 0, 0.2)), (0.2, 0.1, 0.1))
        g = RobotGeometry(
            '<robot><link name="base"/></robot>', provenance="synthetic", mounts=[mount]
        )
        p = g.fk(np.eye(4), {})[0]
        self.assertLess(
            clearance(
                p, Primitive("wall", "box", transform((0.8, 0, 0.2)), (0.1, 0.3, 0.3))
            ),
            0,
        )
        with self.assertRaises(ValueError):
            RobotGeometry(
                '<robot><link name="base"><collision><geometry><mesh filename="x" scale="1 1 1"/></geometry></collision></link></robot>',
                provenance="x",
            )

    def test_box_corner_sat_and_padding_not_double(self):
        a = Primitive("a", "box", np.eye(4), (2, 2, 2))
        b = Primitive("b", "box", transform((1.8, 1.8, 0), (0, 0, 0.2)), (2, 2, 2))
        self.assertLess(clearance(a, b), 0)
        o = obstacle((1, 0, 0.3), (0.3, 0.3, 0.3))
        o["uncertainty"]["bound_m"] = 0.02
        p = obstacle_primitives(frame([o]), uncertainty_in_extent=True)[0]
        self.assertEqual(p.size, (0.3, 0.3, 0.3))
        p = obstacle_primitives(frame([o]), uncertainty_in_extent=False)[0]
        np.testing.assert_allclose(p.size, [0.34] * 3)

    def test_capsule_box_and_sphere_distances(self):
        box = Primitive("box", "box", np.eye(4), (2, 2, 2))
        capsule = Primitive("leg", "capsule", transform((2, 0, 0)), (0.2, 3))
        self.assertAlmostEqual(clearance(box, capsule), 0.8, places=8)
        sphere = Primitive("foot", "sphere", transform((2, 0, 0)), (0.2,))
        self.assertAlmostEqual(clearance(box, sphere), 0.8)
        self.assertAlmostEqual(clearance(capsule, sphere), -0.4)

    def test_independent_oracle_random_rotations(self):
        rng = np.random.default_rng(9)
        for _ in range(80):
            xy = rng.uniform(-1, 1, 2)
            yaw = rng.uniform(-math.pi, math.pi)
            center = rng.uniform(-2, 2, 2)
            box = Primitive(
                "body", "box", transform((*xy, 0), (0, 0, yaw)), (0.716, 0.324, 10)
            )
            sphere = Primitive(
                "cone_cross_section", "sphere", transform((*center, 0)), (0.13,)
            )
            self.assertAlmostEqual(
                clearance(box, sphere),
                oracle_circle_box(center, 0.13, (*xy, yaw)),
                places=10,
            )

    def test_support_plane_slope(self):
        n = np.array([-0.2, 0, 1.0])
        n /= np.linalg.norm(n)
        p = Primitive("foot", "sphere", transform(n * 0.03), (0.03,), True)
        self.assertAlmostEqual(plane_clearance(p, n, 0), 0)
        self.assertGreater(plane_clearance(p, n, -1), 0.9)

    def test_invalid_dimensions_and_axis(self):
        for dims in [(0,), (-1,), (float("nan"),)]:
            with self.assertRaises(ValueError):
                Primitive("bad", "sphere", np.eye(4), dims)


class AssessmentTests(unittest.TestCase):
    def run_assess(self, s=None, f=None, path=None, **kwargs):
        return assess(
            model(),
            s or state(),
            f or frame(),
            path,
            now_stamp_ns=1_000_000_000,
            now_clock_domain="fixture-clock",
            **kwargs,
        )

    def test_empty_sparse_unknown_complete_fixture_clear(self):
        self.assertEqual(self.run_assess()["severity"], "UNKNOWN")
        self.assertEqual(
            self.run_assess(coverage="COMPLETE_SYNTHETIC")["severity"], "CLEAR"
        )

    def test_padded_and_unpadded_overlap_distinct(self):
        a = self.run_assess(f=frame([obstacle((0.51, 0, 0.3))]))
        self.assertEqual(a["severity"], "STOP_REQUIRED")
        self.assertFalse(a["unpadded_envelope"]["overlap"])
        self.assertTrue(a["padded_envelope"]["overlap"])
        self.assertAlmostEqual(
            a["unpadded_envelope"]["min_clearance"] - a["min_clearance"], 0.04
        )
        self.assertEqual(a["reason"], "PREDICTED_COLLISION")
        a = self.run_assess(f=frame([obstacle((0.2, 0, 0.3))]))
        self.assertEqual(a["reason"], "MODEL_OVERLAP")
        self.assertNotIn("CONTACT_CONFIRMED", str(a))

    def test_pure_rotation_sweep_hits_between_clear_endpoints(self):
        f = frame([obstacle((0.30, 0.30, 0.3), (0.03, 0.03, 0.1))])
        s = state()
        end = transform((0, 0, 0.3), (0, 0, math.pi / 2)).tolist()
        self.assertEqual(
            self.run_assess(f=f, coverage="COMPLETE_SYNTHETIC")["severity"], "CLEAR"
        )
        s2 = copy.deepcopy(s)
        s2["pose"] = end
        self.assertEqual(
            self.run_assess(s=s2, f=f, coverage="COMPLETE_SYNTHETIC")["severity"],
            "CLEAR",
        )
        p = {
            "ref": {"id": "rotation"},
            "poses": [{"time_s": 0, "pose": s["pose"]}, {"time_s": 2, "pose": end}],
        }
        a = self.run_assess(s=s, f=f, path=p)
        self.assertEqual(a["severity"], "STOP_REQUIRED")
        self.assertGreater(a["modeled_ttc"], 0)
        self.assertLessEqual(
            a["padded_envelope"]["sweep_displacement_bound_m"], 0.005 + 1e-12
        )
        self.assertGreater(a["padded_envelope"]["samples"], 100)

    def test_translation_sweep(self):
        p = {
            "ref": {"id": "translation"},
            "poses": [
                {"time_s": 0, "pose": state()["pose"]},
                {"time_s": 2, "pose": transform((2, 0, 0.3)).tolist()},
            ],
        }
        a = self.run_assess(f=frame([obstacle()]), path=p)
        self.assertEqual(a["severity"], "STOP_REQUIRED")
        self.assertIsNotNone(a["modeled_ttc"])

    def test_stale_joints_and_generation_clock_gates(self):
        for key, value in [
            ("joint_stamp_ns", "0"),
            ("calibration_known", False),
            ("pose_uncertainty_m", None),
        ]:
            s = state()
            s[key] = value
            a = self.run_assess(s=s)
            self.assertEqual(a["severity"], "UNKNOWN")
            self.assertIsNone(a["min_clearance"])
        for key, value in [
            ("frame_key", {"source_epoch": "other", "frame_id": "odom"}),
            ("clock_domain", "other"),
            ("map_binding", {"generation": 9}),
        ]:
            f = frame()
            f[key] = value
            self.assertEqual(self.run_assess(f=f)["severity"], "UNKNOWN")

    def test_obstacle_timeout_no_clearing_and_unknown_uncertainty(self):
        o = obstacle()
        for status in ("STALE", "OCCLUDED", "REJECTED"):
            o["state"] = status
            self.assertEqual(self.run_assess(f=frame([o]))["severity"], "UNKNOWN")
        o["state"] = "OBSERVED"
        o["uncertainty"] = None
        self.assertEqual(self.run_assess(f=frame([o]))["severity"], "UNKNOWN")

    def test_explicit_support_not_blanket_ground_removal(self):
        xml = '<robot><link name="base"><collision><origin xyz="0 0 .3"/><geometry><box size=".2 .2 .2"/></geometry></collision></link><link name="FL_foot"><collision><geometry><sphere radius=".03"/></geometry></collision></link><joint name="fixed" type="fixed"><parent link="base"/><child link="FL_foot"/><origin xyz="0 0 .03"/></joint></robot>'
        g = RobotGeometry(xml, provenance="SYNTHETIC")
        s = state()
        s["pose"] = np.eye(4).tolist()
        support = dict(
            id="floor",
            normal=[0, 0, 1],
            offset=0,
            patch_min=[-1, -1, -0.1],
            patch_max=[1, 1, 0.1],
            allowed_feet=["FL_foot/0"],
            penetration_tolerance_m=0.001,
            contact_tolerance_m=0.003,
        )
        a = assess(
            g,
            s,
            frame(),
            now_stamp_ns=1_000_000_000,
            now_clock_domain="fixture-clock",
            coverage="COMPLETE_SYNTHETIC",
            support_surfaces=[support],
        )
        self.assertEqual(a["severity"], "CLEAR")
        self.assertEqual(
            a["padded_envelope"]["support_pairs"], [["FL_foot/0", "floor"]]
        )
        a = assess(
            g,
            s,
            frame([obstacle((0, 0, 0.2), (0.1, 0.1, 0.4))]),
            now_stamp_ns=1_000_000_000,
            now_clock_domain="fixture-clock",
            support_surfaces=[support],
        )
        self.assertEqual(a["severity"], "STOP_REQUIRED")
        support["offset"] = 0.25
        a = assess(
            g,
            s,
            frame(),
            now_stamp_ns=1_000_000_000,
            now_clock_domain="fixture-clock",
            support_surfaces=[support],
        )
        self.assertEqual(a["severity"], "STOP_REQUIRED")

    def test_sample_budget_and_path_mismatch_fail_closed(self):
        path = [
            {"time_s": 0, "pose": np.eye(4)},
            {"time_s": 1, "pose": transform((100, 0, 0))},
        ]
        with self.assertRaises(ValueError):
            sweep_samples(path, 1, max_samples=20)
        a = self.run_assess(path={"ref": {}, "poses": path})
        self.assertEqual(a["severity"], "UNKNOWN")

    def test_gait_envelope_changes_assessment_without_changed_source(self):
        g = model(gait_margin=0.1)
        a = assess(
            g,
            state(),
            frame([obstacle((0.6, 0, 0.3))]),
            now_stamp_ns=1_000_000_000,
            now_clock_domain="fixture-clock",
        )
        self.assertEqual(a["severity"], "STOP_REQUIRED")
        self.assertEqual(
            a["padded_envelope"]["future_joints"], "HELD_CURRENT_NOT_GAIT_PREDICTION"
        )

    def test_constant_command_prediction_not_a_controller(self):
        from robot_dashboard.collision_geometry_core.assessment import (
            command_prediction,
        )

        path = command_prediction(
            np.eye(4), dict(linear_x_mps=1, angular_z_radps=1, horizon_s=1)
        )
        np.testing.assert_allclose(
            path[-1]["pose"][:2, 3], [math.sin(1), 1 - math.cos(1)]
        )
        a = self.run_assess(
            f=frame([obstacle()]),
            path={
                "ref": {"kind": "synthetic_command"},
                "command": dict(linear_x_mps=1, angular_z_radps=0, horizon_s=2),
            },
        )
        self.assertEqual(a["severity"], "STOP_REQUIRED")
        self.assertIsNotNone(a["padded_envelope"]["command_arc_approximation_bound_m"])
        with self.assertRaises(ValueError):
            command_prediction(
                np.eye(4), dict(linear_x_mps=1, angular_z_radps=1, horizon_s=100)
            )

    def test_hardened_input_bounds(self):
        for path in (
            [],
            [
                {"time_s": 0, "pose": state()["pose"]},
                {"time_s": -1, "pose": state()["pose"]},
            ],
        ):
            self.assertEqual(
                self.run_assess(path={"ref": {}, "poses": path})["severity"], "UNKNOWN"
            )
        s = state()
        s["joint_stamp_ns"] = "800000000"
        self.assertEqual(self.run_assess(s=s)["severity"], "UNKNOWN")
        s.pop("map_binding")
        self.assertEqual(self.run_assess(s=s)["severity"], "UNKNOWN")
        support = dict(
            id="floor",
            normal=[0, 0, 1],
            offset=0,
            patch_min=[-1, -1, -1],
            patch_max=[1, 1, 1],
            allowed_feet=[],
            penetration_tolerance_m=1,
            contact_tolerance_m=0.003,
        )
        self.assertEqual(
            self.run_assess(support_surfaces=[support])["severity"], "UNKNOWN"
        )

    def test_runtime_geometry_mutation_changes_identity(self):
        g = model()
        before = g.geometry_hash
        g.gait_margin = 0.1
        self.assertNotEqual(before, g.geometry_hash)
        before = g.geometry_hash
        g.links["base"][0].pose[0, 3] = 0.1
        self.assertNotEqual(before, g.geometry_hash)


class ObserverTests(unittest.TestCase):
    def test_predictive_stop_latched_observer_bounded(self):
        gate = Observer(10, 1)
        self.assertEqual(
            gate.step(0, (0.2, 0.3), {"severity": "CLEAR"})["command"], (0.2, 0.3)
        )
        self.assertTrue(
            gate.step(1, (0.2, 0), {"severity": "STOP_REQUIRED"})["observing"]
        )
        self.assertEqual(
            gate.step(1.5, (0.2, 0), {"severity": "CLEAR"})["command"], (0.0, 0.0)
        )
        self.assertEqual(
            gate.step(2, (0.2, 0), {"severity": "CLEAR"})["terminal"],
            "PREDICTIVE_STOP_OBSERVED",
        )
        self.assertFalse(gate.step(3, (0.2, 0), {"severity": "CLEAR"})["observing"])

    def test_distinct_terminal_causes(self):
        for flag, expected in [
            ("oracle_contact", "ACTUAL_SIM_GEOMETRY_CONTACT"),
            ("cancel", "CANCELED"),
            ("infrastructure_error", "INFRASTRUCTURE_FAILURE"),
        ]:
            result = Observer(10).step(
                0, (0.2, 0), {"severity": "CLEAR"}, **{flag: True}
            )
            self.assertEqual(result["terminal"], expected)
            self.assertEqual(result["command"], (0.0, 0.0))

    def test_observer_rejects_nonfinite_commands_and_negative_time(self):
        for command in ((float("nan"), 0), (float("inf"), 0), (0,)):
            with self.assertRaises(ValueError):
                Observer(1).step(0, command, {"severity": "CLEAR"})
        with self.assertRaises(ValueError):
            Observer(1).step(-0.1, (0, 0), {"severity": "CLEAR"})

    def test_sensor_occlusion_and_repeatability(self):
        visible = sensor_points([(1, 0, 0.13)])
        occluded = sensor_points([(1, 0, 0.13), (2, 0, 0.13)])
        np.testing.assert_array_equal(visible, occluded)
        np.testing.assert_array_equal(visible, sensor_points([(1, 0, 0.13)]))
        self.assertTrue(np.all(occluded[:, 0] < 1.2))


if __name__ == "__main__":
    unittest.main()
