import ast
import math
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

from robot_dashboard.relocalization.collector import FixedCloudRegisteredCollector
from robot_dashboard.relocalization.manager import (
    LiveCollection,
    RelocalizationBusy,
    RelocalizationConflict,
    RelocalizationMapBundle,
    RelocalizationUnavailable,
    RelocalizationValidationError,
    StationaryRelocalizationManager,
    _compose_pose,
)
from robot_dashboard.relocalization.process_adapter import RegistrationProcessError


ROOT = Path(__file__).resolve().parents[1]
MAP_ID = "1" * 24
MAP_REVISION = "2" * 64
PCD_ID = "3" * 24
PCD_REVISION = "4" * 64


def points(count=600):
    return tuple(
        (1.0 + (index % 30) * 0.2, -3.0 + ((index // 30) % 20) * 0.2, (index % 5) * 0.2)
        for index in range(count)
    )


def write_pcd(path, cloud):
    header = (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
        f"COUNT 1 1 1\nWIDTH {len(cloud)}\nHEIGHT 1\nPOINTS {len(cloud)}\nDATA binary\n"
    ).encode("ascii")
    path.write_bytes(header + b"".join(struct.pack("<fff", *point) for point in cloud))


class Geometry:
    def __init__(self, *, contains=True, free=True):
        self._contains = contains
        self._free = free

    def contains(self, x, y):
        return self._contains and math.isfinite(x) and math.isfinite(y)

    def known_free(self, x, y, *, clearance_radius):
        return self._free and clearance_radius == 0.35


class FakeCollector:
    def __init__(self, collection=None, *, block=False, error=None):
        self.collection = collection or valid_collection()
        self.block = block
        self.error = error

    def collect(self, cancel_event):
        if self.error:
            raise self.error
        while self.block and not cancel_event.wait(0.01):
            pass
        if self.block:
            raise RelocalizationConflict("collection canceled")
        return self.collection


class FakeRegistration:
    def __init__(self, result=None, error=None, block=False):
        self.result = result or registration_result()
        self.error = error
        self.block = block
        self.calls = []

    def run(self, payload, *, cancel_event=None):
        self.calls.append(payload)
        if self.error:
            raise self.error
        while self.block and cancel_event is not None and not cancel_event.wait(0.01):
            pass
        if self.block:
            raise RegistrationProcessError("canceled")
        return self.result


def valid_collection(**updates):
    values = {
        "topic": "/cloud_registered",
        "frame_id": "camera_init",
        "duration_s": 2.5,
        "frame_stamps_ns": tuple(range(1, 26)),
        "raw_points": 15_000,
        "points": points(),
        "base_pose_odom": (0.2, 0.1, 0.05),
        "controller_translation_delta_m": 0.001,
        "controller_yaw_delta_rad": 0.001,
        "maximum_fastlio_twist_mps": 0.001,
        "maximum_imu_angular_rate_rps": 0.01,
        "publisher_count": 1,
    }
    values.update(updates)
    return LiveCollection(**values)


def safety(**updates):
    values = {
        "profile": "go2-xt16-wireless-competition-fastlio",
        "stationary": True,
        "control_disarmed": True,
        "control_lease_active": False,
        "navigation_lease_active": False,
        "deadman": False,
        "goal_idle": True,
        "mapping_active": False,
        "dataset_active": False,
        "physical_safety_ready": True,
        "source_topic": "/cloud_registered",
        "source_frame": "camera_init",
        "source_publishers": 1,
        "source_fresh": True,
        "source_qos_valid": True,
        "velocity": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
    }
    values.update(updates)
    return values


def request(**updates):
    value = {
        "map_id": MAP_ID,
        "map_revision": MAP_REVISION,
        "source_pcd_id": PCD_ID,
        "source_pcd_revision": PCD_REVISION,
        "seed": {
            "mode": "REGION",
            "x": 0.0,
            "y": 0.0,
            "yaw": 0.0,
            "radius_m": 3.0,
            "yaw_half_range": 1.57,
        },
    }
    value.update(updates)
    return value


def registration_result(*, confidence="HIGH", margin=0.2, candidates=1):
    results = []
    for rank in range(1, candidates + 1):
        results.append({
            "converged": True,
            "pose": {"x": 1.0 + rank * 0.1, "y": 2.0, "yaw": 0.1},
            "metrics": {
                "fitness": 0.02,
                "overlap_ratio": 0.8,
                "inlier_ratio": 0.8,
                "query_points": 600,
                "reference_points": 600,
                "runtime_ms": 20.0,
            },
            "confidence": confidence,
            "rank": rank,
            "ambiguity_margin": margin,
        })
    return {
        "schema": "robot-scope.relocalization-result.v1",
        "backend": "bounded-se2-icp",
        "results": results,
        "timing": {"preprocess_ms": 1.0, "coarse_ms": 2.0, "refine_ms": 3.0},
    }


class Harness:
    def __init__(self, testcase, *, geometry=None, annotations=None, collector=None, registration=None, current=True):
        self.temp = tempfile.TemporaryDirectory(prefix="robot-scope-d2-")
        testcase.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.geometry = geometry or Geometry()
        self.annotations = annotations or {"polygons": []}
        self.collector = collector or FakeCollector()
        self.registration = registration or FakeRegistration()
        self.current = current

        def snapshotter(map_id, map_revision, pcd_id, pcd_revision, destination):
            if (map_id, map_revision, pcd_id, pcd_revision) != (MAP_ID, MAP_REVISION, PCD_ID, PCD_REVISION):
                raise RelocalizationConflict("family mismatch")
            reference = destination / "reference.pcd"
            write_pcd(reference, points())
            return RelocalizationMapBundle(
                "5" * 24, "6" * 64, map_id, map_revision, pcd_id, pcd_revision,
                reference, 600, self.geometry, self.annotations,
            )

        self.manager = StationaryRelocalizationManager(
            self.root / "runtime",
            snapshotter=snapshotter,
            current_checker=lambda bundle: self.current,
            collector=self.collector,
            registration=self.registration,
            safety_provider=lambda: safety(),
        )
        testcase.addCleanup(self.manager.close)

    def run(self):
        started = self.manager.start(request())
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            result = self.manager.job(started["job_id"])
            if result["state"] in {"candidate_ready", "ambiguous", "rejected", "failed"}:
                return result
            time.sleep(0.01)
        self.manager.cancel(started["job_id"])
        self.fail("job did not settle")


class StationaryRelocalizationTests(unittest.TestCase):
    def test_candidate_job_pins_family_and_never_applies(self):
        harness = Harness(self)
        result = harness.run()
        self.assertEqual(result["state"], "candidate_ready")
        self.assertFalse(result["candidate_applied"])
        self.assertEqual(result["family_revision"], "6" * 64)
        self.assertEqual(result["collection"]["frames"], 25)
        self.assertEqual(set(result["preview_layers"]), {"reference", "current", "aligned"})
        self.assertEqual(harness.registration.calls[0]["reference_pcd"].split("/")[-1], "reference.pcd")

    def test_family_and_revision_mismatch_fail_closed(self):
        harness = Harness(self)
        bad = request(map_revision="7" * 64)
        started = harness.manager.start(bad)
        result = self._wait(harness.manager, started["job_id"])
        self.assertEqual(result["state"], "failed")
        self.assertIn("family mismatch", result["error"])

    def test_map_revision_change_after_registration_rejects(self):
        harness = Harness(self, current=False)
        result = harness.run()
        self.assertEqual(result["state"], "failed")
        self.assertIn("changed", result["error"])

    def test_occupied_unknown_clearance_and_keep_out_candidates_reject(self):
        cases = [
            (Geometry(contains=False), {"polygons": []}, "outside_occupancy_map"),
            (Geometry(free=False), {"polygons": []}, "footprint_not_known_free"),
            (Geometry(), {"polygons": [{"type": "KEEP_OUT", "vertices": [
                {"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 0.0}, {"x": 3.0, "y": 3.0}, {"x": 0.0, "y": 3.0},
            ]}]}, "keep_out"),
        ]
        for geometry, annotations, reason in cases:
            with self.subTest(reason=reason):
                result = Harness(self, geometry=geometry, annotations=annotations).run()
                self.assertEqual(result["state"], "rejected")
                self.assertIn(reason, result["candidates"][0]["reasons"])

    def test_slow_and_wait_zones_are_annotations_only(self):
        annotations = {"polygons": [
            {"type": kind, "vertices": [
                {"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 0.0}, {"x": 3.0, "y": 3.0}, {"x": 0.0, "y": 3.0},
            ]} for kind in ("SLOW_ZONE", "WAIT_ZONE")
        ]}
        result = Harness(self, annotations=annotations).run()
        self.assertEqual(result["state"], "candidate_ready")
        self.assertEqual(result["candidates"][0]["zones"], ["SLOW_ZONE", "WAIT_ZONE"])

    def test_motion_stale_source_conflict_and_insufficient_points_fail(self):
        cases = [
            valid_collection(controller_translation_delta_m=0.006),
            valid_collection(frame_stamps_ns=(1,) * 20),
            valid_collection(publisher_count=2),
            valid_collection(points=points(499)),
        ]
        for collection in cases:
            with self.subTest(collection=collection):
                result = Harness(self, collector=FakeCollector(collection)).run()
                self.assertEqual(result["state"], "failed")

    def test_preflight_unknown_or_nonzero_state_blocks_before_job(self):
        temp = tempfile.TemporaryDirectory(prefix="robot-scope-d2-preflight-")
        self.addCleanup(temp.cleanup)
        for unsafe in (
            safety(stationary=False),
            safety(velocity={"vx": 0.001, "vy": 0.0, "wz": 0.0}),
            safety(control_lease_active=True),
            safety(source_fresh=False),
            {},
        ):
            manager = StationaryRelocalizationManager(
                Path(temp.name) / secrets_name(),
                snapshotter=lambda *args: None,
                current_checker=lambda bundle: True,
                collector=FakeCollector(), registration=FakeRegistration(),
                safety_provider=lambda unsafe=unsafe: unsafe,
            )
            with self.assertRaises(RelocalizationUnavailable):
                manager.start(request())
            self.assertIsNone(manager.snapshot()["active"])

    def test_one_job_cancel_and_cleanup(self):
        harness = Harness(self, collector=FakeCollector(block=True))
        started = harness.manager.start(request())
        with self.assertRaises(RelocalizationBusy):
            harness.manager.start(request())
        canceled = harness.manager.cancel(started["job_id"])
        self.assertEqual(canceled["state"], "canceling")
        settled = self._wait(harness.manager, started["job_id"])
        self.assertEqual(settled["state"], "failed")
        self.assertIn("canceled", settled["error"])
        self.assertEqual(list((harness.root / "runtime").iterdir()), [])

    def test_process_timeout_crash_and_too_many_candidates_fail(self):
        for registration in (
            FakeRegistration(error=RegistrationProcessError("timed out")),
            FakeRegistration(error=RegistrationProcessError("process crashed")),
            FakeRegistration(result=registration_result(candidates=4)),
        ):
            with self.subTest(error=registration.error):
                result = Harness(self, registration=registration).run()
                self.assertEqual(result["state"], "failed")

    def test_spatially_separate_second_best_marks_ambiguity(self):
        ambiguous = registration_result(confidence="LOW", margin=0.01, candidates=2)
        ambiguous["results"][1]["pose"]["x"] += 1.0
        result = Harness(
            self,
            registration=FakeRegistration(ambiguous),
        ).run()
        self.assertEqual(result["state"], "ambiguous")
        self.assertEqual(result["candidates"][0]["state"], "AMBIGUOUS")

    def test_transform_convention_is_map_odom_times_odom_base(self):
        x, y, yaw = _compose_pose((1.0, 2.0, math.pi / 2), (2.0, 0.0, math.pi / 4))
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 4.0)
        self.assertAlmostEqual(yaw, 3 * math.pi / 4)

    def test_request_is_strict_and_global_search_disabled(self):
        harness = Harness(self)
        for candidate in (
            request(extra=True),
            request(seed={**request()["seed"], "mode": "NONE"}),
            request(source_pcd_id="outside/path"),
        ):
            with self.assertRaises(RelocalizationValidationError):
                harness.manager.start(candidate)

    def test_preview_is_bounded_path_free_and_unknown_layer_rejected(self):
        harness = Harness(self)
        result = harness.run()
        for layer, maximum in (("reference", 50_000), ("current", 30_000), ("aligned", 30_000)):
            preview = harness.manager.preview(result["job_id"], layer)
            self.assertLessEqual(preview["point_count"], maximum)
            self.assertEqual(preview["maximum_points"], maximum)
            self.assertNotIn("path", preview)
        with self.assertRaises(RelocalizationValidationError):
            harness.manager.preview(result["job_id"], "raw")

    def test_api_has_no_apply_endpoint_and_mutations_use_origin_guard(self):
        path = ROOT / "robot_dashboard" / "api" / "routers" / "relocalization.py"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("initialpose", source)
        self.assertNotIn("/apply", source)
        tree = ast.parse(source)
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
        for name in ("relocalization_start", "relocalization_cancel"):
            self.assertTrue(any(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "require_same_origin" for node in ast.walk(functions[name])
            ))

    def test_manager_has_no_control_or_navigation_mutation_dependency(self):
        source = (ROOT / "robot_dashboard" / "relocalization" / "manager.py").read_text(encoding="utf-8")
        for forbidden in ("acquire_lease", "arm(", "deadman(", "send_goal", "initialpose"):
            self.assertNotIn(forbidden, source)

    def test_fixed_collector_rejects_stale_reordered_and_publisher_conflict(self):
        base = points()
        packed = b"".join(struct.pack("<fff", *point) for point in base)
        for change in ("stale", "reordered", "publishers"):
            index = 0

            def cloud():
                nonlocal index
                index += 1
                return {
                    "seq": index,
                    "stamp_ns": 1 if change == "reordered" else index,
                    "topic": "/cloud_registered",
                    "frame_id": "camera_init",
                    "publisher_count": 2 if change == "publishers" else 1,
                    "fresh": change != "stale",
                    "qos_valid": True,
                    "source_points": len(base),
                    "points_bytes": packed,
                }

            collector = FixedCloudRegisteredCollector(
                cloud,
                lambda: {"fresh": True, "base_pose_odom": [0.0, 0.0, 0.0], "fastlio_twist_mps": 0.0, "imu_angular_rate_rps": 0.0},
                duration_s=0.1,
                poll_interval_s=0.001,
            )
            with self.subTest(change=change), self.assertRaises((RelocalizationConflict, RelocalizationUnavailable)):
                collector.collect(threading.Event())

    @staticmethod
    def _wait(manager, job_id):
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            job = manager.job(job_id)
            if job["state"] in {"candidate_ready", "ambiguous", "rejected", "failed"}:
                return job
            time.sleep(0.01)
        raise AssertionError("job did not settle")


def secrets_name():
    return f"runtime-{time.monotonic_ns()}"


if __name__ == "__main__":
    unittest.main()
