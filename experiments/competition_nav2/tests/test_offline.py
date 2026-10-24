# Standalone unittest discovery requires the explicit path bootstrap below.
# ruff: noqa: E402
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from configure import candidate, validate_config
from core import (
    Boundary,
    Command,
    FOOTPRINT,
    LIMITS,
    clearance,
    intersects,
    polygon,
    propagate,
    rectangle,
    swept_poses,
)
from fixtures import World, cases, digest
from preflight import isolated_errors
from validate import validate_record, validate_directory
from matrix import plan
from native_runner import plugin_library_names


class BoundaryTests(unittest.TestCase):
    def ready(self, now=1.0):
        b = Boundary()
        b.sensor(now, 0.0)
        b.set_hold(False, now)
        b.accept(Command(0, b.epoch, now, now, 0.18, 0.6), now)
        return b

    def test_initial_hold_is_exact_zero(self):
        self.assertEqual(Boundary().step(1.0, 0.05), (0.0, 0.0))

    def test_release_requires_new_command(self):
        b = Boundary()
        self.assertFalse(b.accept(Command(1, 0, 1.0, 1.0, 0.1, 0.1), 1.0))
        b.sensor(1.0, 0.0)
        b.set_hold(False, 1.0)
        self.assertEqual(b.step(1.0, 0.05), (0.0, 0.0))

    def test_speed_acceleration_limits_shared(self):
        b = self.ready()
        self.assertEqual(b.step(1.0, 0.05), (0.015, 0.06))
        for i in range(20):
            now = 1.0 + i * 0.05
            b.sensor(now, 0.0)
            b.accept(Command(i + 1, b.epoch, now, now, 10.0, -10.0), now)
            v, w = b.step(now, 0.05)
            self.assertLessEqual(v, LIMITS["v"])
            self.assertLessEqual(abs(w), LIMITS["w"])

    def test_hold_clears_immediately(self):
        b = self.ready()
        self.assertNotEqual(b.step(1.0, 0.05), (0.0, 0.0))
        b.set_hold(True, 1.01)
        self.assertEqual(b.output, (0.0, 0.0))
        self.assertIsNone(b.command)

    def test_old_epoch_and_pre_release_source_rejected(self):
        b = self.ready()
        old = b.epoch
        b.set_hold(True, 1.1)
        b.set_hold(False, 1.2)
        b.sensor(1.2, 0.0)
        self.assertFalse(b.accept(Command(2, old, 1.21, 1.21, 0.1, 0.1), 1.21))
        self.assertFalse(b.accept(Command(3, b.epoch, 1.19, 1.21, 0.1, 0.1), 1.21))
        self.assertEqual(b.step(1.21, 0.05), (0.0, 0.0))

    def test_replay_sequence_rejected(self):
        b = self.ready()
        self.assertFalse(b.accept(Command(0, b.epoch, 1.01, 1.01, 0.1, 0.1), 1.01))

    def test_command_receipt_ttl_stops(self):
        b = self.ready()
        b.sensor(1.26, 0.0)
        self.assertEqual(b.step(1.26, 0.05), (0.0, 0.0))
        self.assertEqual(b.reason, "COMMAND_TTL")

    def test_delayed_source_not_refreshed_by_receipt(self):
        b = self.ready()
        self.assertFalse(b.accept(Command(1, b.epoch, 1.01, 1.5, 0.1, 0.0), 1.5))

    def test_future_source_rejected(self):
        b = self.ready()
        self.assertFalse(b.accept(Command(1, b.epoch, 2.0, 1.0, 0.1, 0.0), 1.0))

    def test_stale_sensor_latched_no_auto_resume(self):
        b = self.ready()
        self.assertEqual(b.step(1.31, 0.05), (0.0, 0.0))
        self.assertEqual(b.fault, "SENSOR_STALE")
        b.sensor(1.32, 0.0)
        b.set_hold(False, 1.32)
        self.assertFalse(b.accept(Command(2, b.epoch, 1.32, 1.32, 0.1, 0.0), 1.32))

    def test_sensor_source_age_plus_receipt_age(self):
        b = self.ready()
        b.sensor(1.0, 0.2)
        self.assertEqual(b.step(1.11, 0.05), (0.0, 0.0))
        self.assertEqual(b.fault, "SENSOR_STALE")

    def test_nonfinite_faults(self):
        for value in (math.nan, math.inf, -math.inf):
            b = self.ready()
            self.assertFalse(b.accept(Command(1, b.epoch, 1.0, 1.0, value, 0.0), 1.0))
            self.assertEqual(b.step(1.0, 0.05), (0.0, 0.0))

    def test_clock_reset_fault(self):
        b = self.ready()
        b.step(1.0, 0.05)
        b.step(0.9, 0.05)
        self.assertEqual(b.fault, "CLOCK_RESET")

    def test_hold_blocks_recovery_commands(self):
        b = self.ready()
        b.set_hold(True, 1.1)
        for i in range(10):
            now = 1.1 + i * 0.05
            b.sensor(now, 0.0)
            self.assertFalse(b.accept(Command(i + 1, b.epoch, now, now, 0.0, 0.6), now))
            self.assertEqual(b.step(now, 0.05), (0.0, 0.0))


class GeometryTests(unittest.TestCase):
    def test_sat_detects_edge_crossing_without_inside_vertices(self):
        self.assertTrue(
            intersects(rectangle(-1.0, -0.1, 1.0, 0.1), rectangle(-0.1, -1.0, 0.1, 1.0))
        )

    def test_clearance_touch_and_separation(self):
        a = rectangle(0.0, 0.0, 1.0, 1.0)
        self.assertEqual(clearance(a, rectangle(1.0, 0.0, 2.0, 1.0)), 0.0)
        self.assertAlmostEqual(clearance(a, rectangle(2.0, 0.0, 3.0, 1.0)), 1.0)

    def test_sweep_finds_contact_between_endpoints(self):
        obstacle = rectangle(-0.02, -0.02, 0.02, 0.02)
        poses = swept_poses((-1.0, 0.0, 0.0), 2.0, 0.0, 1.0)
        self.assertFalse(intersects(polygon(poses[0]), obstacle))
        self.assertFalse(intersects(polygon(poses[-1]), obstacle))
        self.assertTrue(any(intersects(polygon(p), obstacle) for p in poses))

    def test_turn_sweep_resolution_and_exact_propagation(self):
        poses = swept_poses((0.0, 0.0, 0.0), 0.18, 0.6, 0.1)
        self.assertEqual(poses[-1], propagate((0.0, 0.0, 0.0), 0.18, 0.6, 0.1))
        for a, b in zip(poses, poses[1:]):
            self.assertLessEqual(
                max(math.dist(u, v) for u, v in zip(polygon(a), polygon(b))), 0.005001
            )


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = {f["scenario"]: f for f in cases()}
        cls.world = World(cls.fixtures["empty"])

    def test_required_scenarios_and_no_moved_central_cone(self):
        self.assertEqual(len(self.fixtures), 12)
        self.assertEqual(
            self.fixtures["central_cone_failure"]["obstacles"][0]["polygon"],
            rectangle(5.86, 2.87, 6.12, 3.13),
        )
        for f in self.fixtures.values():
            self.assertEqual(f["start"], [5.99, 1.65, math.pi / 2])
            self.assertEqual(f["goal"], [5.99, 4.35, math.pi / 2])
            self.assertEqual(f["footprint"], [list(p) for p in FOOTPRINT])

    def test_deterministic_fixture(self):
        self.assertEqual(digest(cases()), digest(cases()))

    def test_terrain_is_blocked(self):
        self.assertTrue(self.world.occupied(3.3, 3.0))
        for zone in self.world.geometry.zones():
            if zone["type"] in ("RAMP", "STAIRS"):
                x, y = [
                    sum(p[i] for p in zone["polygon"]) / len(zone["polygon"])
                    for i in (0, 1)
                ]
                self.assertTrue(self.world.occupied(x, y))

    def test_start_goal_free_and_outside_blocked(self):
        self.assertFalse(self.world.collision(self.fixtures["empty"]["start"], 0.0))
        self.assertFalse(self.world.collision(self.fixtures["empty"]["goal"], 0.0))
        self.assertTrue(self.world.occupied(-1.0, 1.0))
        self.assertTrue(self.world.collision((8.0, 3.0, 0.0), 0.0))

    def test_hidden_cone_not_in_static_map(self):
        cone = World(self.fixtures["central_cone_failure"])
        self.assertTrue((cone.static == self.world.static).all())
        self.assertTrue(cone.collision((5.99, 3.0, math.pi / 2), 0.0))
        self.assertFalse(self.world.collision((5.99, 3.0, math.pi / 2), 0.0))

    def test_scan_first_hit_and_late_appearance(self):
        late = World(self.fixtures["late_obstacle"])
        pose = self.fixtures["empty"]["start"]
        self.assertEqual(late.scan(pose, 1.0), self.world.scan(pose, 1.0))
        self.assertLess(late.scan(pose, 2.0)[180], self.world.scan(pose, 2.0)[180])

    def test_parking_intrusion_preserved_and_optional_permission(self):
        blocked = World(self.fixtures["parking_forbidden"])
        pose = (6.4, 3.0, 0.0)
        self.assertFalse(self.world.boundary_violation(pose))
        self.assertTrue(blocked.boundary_violation(pose))

    def test_map_export_identical_between_controller_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            a = self.world.write_map(Path(directory) / "a")
            b = World(self.fixtures["single_cone"]).write_map(Path(directory) / "b")
            self.assertEqual(a, b)


class ConfigIsolationEvidenceTests(unittest.TestCase):
    def test_plugin_export_library_name_can_differ_from_package(self):
        plugin = "nav2_mppi_controller::MPPIController"
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "mppic.xml").write_text(
                '<class_libraries><library path="mppi_controller"><class type="'
                + plugin
                + '"/></library></class_libraries>'
            )
            self.assertEqual(
                plugin_library_names(directory, plugin), {"libmppi_controller.so"}
            )
            with self.assertRaisesRegex(RuntimeError, "export missing"):
                plugin_library_names(directory, "fake::Controller")

    def test_native_launch_refuses_host_before_ros_import(self):
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location(
            "c3_launch", ROOT / "launch/native.launch.py"
        )
        launch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launch)
        with patch(
            "preflight.require_isolated", side_effect=RuntimeError("NOT_ISOLATED")
        ):
            with self.assertRaisesRegex(RuntimeError, "NOT_ISOLATED"):
                launch.generate_launch_description()

    def test_matrix_contains_matched_repeats_without_execution_claim(self):
        rows = plan()
        self.assertEqual(len(rows), 144)
        self.assertTrue(all(row["status"] == "NOT_RUN" for row in rows))
        for scenario in {row["scenario"] for row in rows}:
            for variant in ("baseline", "tuned"):
                for repeat in range(3):
                    group = [
                        r
                        for r in rows
                        if (r["scenario"], r["variant"], r["repeat"])
                        == (scenario, variant, repeat)
                    ]
                    self.assertEqual({r["controller"] for r in group}, {"rpp", "mppi"})

    def test_all_candidates_lint_and_fair_shared_inputs(self):
        for variant in ("baseline", "tuned"):
            aa = []
            for controller in ("rpp", "mppi"):
                cfg = candidate(controller, variant)
                self.assertEqual(validate_config(cfg, controller), [])
                cfg["controller_server"]["ros__parameters"].pop("FollowPath")
                aa.append(cfg)
            self.assertEqual(*aa)

    def test_original_mppi_period_error_is_rejected(self):
        cfg = candidate("mppi")
        cfg["controller_server"]["ros__parameters"]["controller_frequency"] = 10.0
        self.assertIn(
            "Humble MPPI model_dt must equal controller period",
            validate_config(cfg, "mppi"),
        )

    def test_bad_profile_is_rejected(self):
        cfg = candidate("mppi")
        cfg["controller_server"]["ros__parameters"]["odom_topic"] = (
            "/utlidar/robot_odom"
        )
        self.assertTrue(validate_config(cfg, "mppi"))

    def test_host_localhost_environment_is_insufficient(self):
        probe = {
            "network_interfaces": ["eth0", "lo"],
            "os_release": 'ID=ubuntu\nVERSION_ID="22.04"',
        }
        env = {
            "ROS_DISTRO": "humble",
            "ROS_LOCALHOST_ONLY": "1",
            "ROS_DOMAIN_ID": "193",
            "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        }
        self.assertTrue(isolated_errors(probe, env, False))
        probe["network_interfaces"] = ["lo"]
        self.assertEqual(isolated_errors(probe, env, True), [])
        env["ROS_DISCOVERY_SERVER"] = "untrusted"
        self.assertTrue(isolated_errors(probe, env, True))

    def test_offline_or_not_run_can_never_pass_native(self):
        self.assertTrue(
            validate_record(dict(backend="surrogate/offline", status="PASS"))
        )
        self.assertTrue(
            validate_record(dict(backend="nav2_native_sim", status="NOT_RUN"))
        )

    def test_native_name_alone_insufficient(self):
        fake = dict(
            backend="nav2_native_sim",
            status="NATIVE_RECORDED",
            controller="mppi",
            parameters={"FollowPath.plugin": "nav2_mppi_controller::MPPIController"},
        )
        errors = validate_record(fake)
        self.assertIn("native binary/version provenance missing", errors)
        self.assertIn("actual action terminal result missing", errors)

    def test_missing_delayed_probe_rejected_without_crash(self):
        fake = dict(
            backend="nav2_native_sim",
            status="NATIVE_RECORDED",
            scenario="hold_release_delayed",
            delayed_command_probe=None,
        )
        self.assertIn(
            "delayed nonzero rejection not demonstrated", validate_record(fake)
        )

    def test_missing_files_reject_even_declared_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "result.json").write_text(
                json.dumps(dict(backend="nav2_native_sim", status="NATIVE_RECORDED"))
            )
            self.assertEqual(validate_directory(directory)["status"], "FAIL")

    def test_bt_contains_real_actions(self):
        tree = ET.parse(ROOT / "config/replan.xml")
        self.assertIsNotNone(tree.find(".//ComputePathToPose"))
        self.assertIsNotNone(tree.find(".//FollowPath"))
        self.assertIsNotNone(tree.find(".//Spin"))


if __name__ == "__main__":
    unittest.main()
