import json
import math
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from robot_dashboard.relocalization.models import (
    RegistrationContractError,
    RegistrationRequest,
    RegistrationResultSet,
)
from robot_dashboard.relocalization.process_adapter import (
    OfflineRegistrationProcess,
    RegistrationBusy,
    RegistrationCanceled,
    RegistrationProcessError,
)
from robot_dashboard.relocalization.scoring import confidence_for


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ros2" / "robot_scope_registration"


def room_cloud():
    points = []
    for layer in range(5):
        z = -0.4 + layer * 0.2
        for step in range(121):
            value = -6.0 + step * 0.1
            points.extend(((value, -4.0, z), (value, 4.0, z), (-6.0, value * 2 / 3, z)))
            if step < 80:
                points.append((6.0, -4.0 + step * 0.1, z))
        for step in range(63):
            angle = step * 0.1
            points.append((2.1 + 0.35 * math.cos(angle), 1.2 + 0.35 * math.sin(angle), z))
    return points


def inverse_cloud(points, pose):
    x_pose, y_pose, yaw = pose
    cosine, sine = math.cos(yaw), math.sin(yaw)
    return [
        (
            cosine * (x - x_pose) + sine * (y - y_pose),
            -sine * (x - x_pose) + cosine * (y - y_pose),
            z,
        )
        for x, y, z in points
    ]


def l_corridor_cloud():
    points = []
    for layer in range(5):
        z = -0.4 + layer * 0.2
        for step in range(161):
            value = -8.0 + step * 0.1
            points.append((value, -2.5, z))
            if value <= 2.5:
                points.append((value, 2.5, z))
            points.append((2.5, value, z))
    return points


def pillar_cloud():
    points = []
    centers = ((-3.0, -2.0), (2.0, -1.0), (3.5, 2.5), (-1.0, 3.0))
    for layer in range(15):
        z = -1.4 + layer * 0.2
        for center_x, center_y in centers:
            for step in range(64):
                angle = step * 2 * math.pi / 64
                points.append((center_x + 0.4 * math.cos(angle), center_y + 0.4 * math.sin(angle), z))
    return points


def parallel_corridor_cloud(repeated=False):
    points = []
    for layer in range(5):
        z = -0.4 + layer * 0.2
        for step in range(181):
            x = -9.0 + step * 0.1
            points.extend(((x, -2.0, z), (x, 2.0, z)))
        if not repeated:
            for step in range(41):
                y = -2.0 + step * 0.1
                points.extend(((-9.0, y, z), (9.0, y, z)))
        else:
            for center in range(-8, 9, 2):
                for step in range(32):
                    angle = step * 2 * math.pi / 32
                    points.append((center + 0.25 * math.cos(angle), 0.25 * math.sin(angle), z))
    return points


def degraded_cloud(points, *, dropout=0.0, noise=0.0, outlier_ratio=0.0, partial=False):
    randomizer = random.Random(2048)
    selected = [point for point in points if not partial or point[0] >= -0.5]
    selected = [point for point in selected if randomizer.random() >= dropout]
    output = [
        tuple(value + randomizer.gauss(0.0, noise) for value in point)
        for point in selected
    ]
    for _ in range(int(len(output) * outlier_ratio)):
        output.append((randomizer.uniform(-15, 15), randomizer.uniform(-15, 15), randomizer.uniform(-1, 2)))
    return output


def write_pcd(path, points):
    header = (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\n"
        "TYPE F F F\nCOUNT 1 1 1\n"
        f"WIDTH {len(points)}\nHEIGHT 1\nPOINTS {len(points)}\nDATA binary\n"
    ).encode("ascii")
    path.write_bytes(header + b"".join(struct.pack("fff", *point) for point in points))


def request(reference, query, *, timeout_ms=15_000):
    return {
        "reference_pcd": str(reference),
        "query_pcd": str(query),
        "seed": {"x": 0.0, "y": 0.0, "yaw": 0.0, "radius_m": 0.8, "yaw_range_rad": 0.5},
        "limits": {
            "max_reference_points": 100_000,
            "max_query_points": 100_000,
            "timeout_ms": timeout_ms,
        },
    }


class OfflineRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("c++")
        if compiler is None:
            raise unittest.SkipTest("C++17 compiler is unavailable")
        cls.build = tempfile.TemporaryDirectory(prefix="robot-scope-registration-")
        cls.build_path = Path(cls.build.name)
        include = PACKAGE / "include"
        core = PACKAGE / "src" / "registration_core.cpp"
        cls.cli = cls.build_path / "robot_scope_offline_registration"
        cls.core_test = cls.build_path / "registration_core_test"
        common = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic", f"-I{include}", str(core)]
        subprocess.run(
            [*common, str(PACKAGE / "src" / "offline_registration_cli.cpp"), "-o", str(cls.cli)],
            check=True,
        )
        subprocess.run(
            [*common, str(PACKAGE / "test" / "registration_core_test.cpp"), "-o", str(cls.core_test)],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="robot-scope-registration-data-")
        self.root = Path(self.temporary.name)
        self.reference = self.root / "reference.pcd"
        self.query = self.root / "query.pcd"
        write_pcd(self.reference, room_cloud())
        write_pcd(self.query, inverse_cloud(room_cloud(), (0.4, -0.3, 0.2)))

    def tearDown(self):
        self.temporary.cleanup()

    def test_ros_independent_cpp_core_builds_and_recovers_known_transform(self):
        subprocess.run([str(self.core_test)], check=True, timeout=15)
        source = (PACKAGE / "src" / "registration_core.cpp").read_text(encoding="utf-8")
        self.assertNotIn("rclcpp", source)
        self.assertNotIn("sensor_msgs", source)

    def test_process_adapter_runs_fixed_argv_and_validates_ranked_result(self):
        adapter = OfflineRegistrationProcess(self.cli, [self.root])
        result = adapter.run(request(self.reference, self.query))
        best = result["results"][0]
        self.assertTrue(best["converged"])
        self.assertLess(math.hypot(best["pose"]["x"] - 0.4, best["pose"]["y"] + 0.3), 0.15)
        self.assertLess(abs(best["pose"]["yaw"] - 0.2), math.radians(5))
        self.assertIn(best["confidence"], {"HIGH", "MEDIUM", "LOW"})
        repeated = adapter.run(request(self.reference, self.query))
        self.assertEqual(
            [(item["pose"], item["confidence"], item["rank"]) for item in result["results"]],
            [(item["pose"], item["confidence"], item["rank"]) for item in repeated["results"]],
        )

    def test_bounded_json_cli_accepts_valid_input_and_rejects_malformed_json(self):
        command = [
            sys.executable,
            str(ROOT / "scripts" / "run_offline_registration.py"),
            "--executable", str(self.cli),
            "--allowed-root", str(self.root),
        ]
        valid = subprocess.run(
            command,
            input=json.dumps(request(self.reference, self.query)),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        RegistrationResultSet.parse(json.loads(valid.stdout))
        malformed = subprocess.run(
            command,
            input="{",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed.stdout, "")

    def test_distinct_synthetic_corpus_meets_translation_and_yaw_targets(self):
        cases = [
            (room_cloud(), (0.40, -0.30, 0.20), {}),
            (l_corridor_cloud(), (-0.35, 0.25, -0.18), {}),
            (pillar_cloud(), (0.30, 0.35, 0.22), {}),
            (room_cloud(), (0.0, 0.0, 0.25), {}),
            (room_cloud(), (0.45, -0.20, 0.0), {}),
            (room_cloud(), (-0.30, 0.30, -0.22), {"dropout": 0.30}),
            (room_cloud(), (0.35, 0.20, 0.18), {"dropout": 0.50}),
            (l_corridor_cloud(), (0.25, -0.25, 0.15), {"noise": 0.02}),
            (pillar_cloud(), (-0.25, -0.35, -0.17), {"outlier_ratio": 0.20}),
            (room_cloud(), (0.30, -0.25, 0.20), {"partial": True}),
        ]
        translation_errors = []
        yaw_errors = []
        for index, (reference_points, truth, degradation) in enumerate(cases):
            with self.subTest(index=index):
                reference = self.root / f"reference-{index}.pcd"
                query = self.root / f"query-{index}.pcd"
                write_pcd(reference, reference_points)
                transformed = inverse_cloud(reference_points, truth)
                write_pcd(query, degraded_cloud(transformed, **degradation))
                result = OfflineRegistrationProcess(self.cli, [self.root]).run(request(reference, query))
                best = result["results"][0]
                translation_errors.append(
                    math.hypot(best["pose"]["x"] - truth[0], best["pose"]["y"] - truth[1])
                )
                yaw_errors.append(
                    abs(math.atan2(math.sin(best["pose"]["yaw"] - truth[2]), math.cos(best["pose"]["yaw"] - truth[2])))
                )
        translation_errors.sort()
        yaw_errors.sort()
        median_index = len(cases) // 2
        p95_index = math.ceil(0.95 * len(cases)) - 1
        self.assertLessEqual(translation_errors[median_index], 0.15)
        self.assertLessEqual(translation_errors[p95_index], 0.30)
        self.assertLessEqual(math.degrees(yaw_errors[median_index]), 3.0)
        self.assertLessEqual(math.degrees(yaw_errors[p95_index]), 8.0)

    def test_symmetric_corridor_never_reports_false_high_confidence(self):
        reference_points = parallel_corridor_cloud(repeated=True)
        write_pcd(self.reference, reference_points)
        write_pcd(self.query, inverse_cloud(reference_points, (0.5, 0.0, 0.0)))
        result = OfflineRegistrationProcess(self.cli, [self.root]).run(request(self.reference, self.query))
        self.assertNotEqual(result["results"][0]["confidence"], "HIGH")

    def test_no_overlap_wrong_seed_and_z_offset_fail_closed(self):
        adapter = OfflineRegistrationProcess(self.cli, [self.root])
        no_overlap = [(x + 30.0, y + 30.0, z) for x, y, z in room_cloud()]
        write_pcd(self.query, no_overlap)
        with self.assertRaises(RegistrationProcessError):
            adapter.run(request(self.reference, self.query))
        wrong_seed = request(self.reference, self.reference)
        wrong_seed["seed"].update(x=50.0, y=50.0, radius_m=0.2, yaw_range_rad=0.1)
        with self.assertRaises(RegistrationProcessError):
            adapter.run(wrong_seed)
        write_pcd(self.query, [(x, y, z + 5.0) for x, y, z in room_cloud()])
        with self.assertRaises(RegistrationProcessError):
            adapter.run(request(self.reference, self.query))

    def test_request_rejects_unknown_nonfinite_and_unbounded_values(self):
        valid = request(self.reference, self.query)
        for mutate in (
            lambda value: value.update(output_path="/tmp/result"),
            lambda value: value["seed"].update(x=True),
            lambda value: value["seed"].update(yaw=float("nan")),
            lambda value: value["seed"].update(radius_m=11.0),
            lambda value: value["limits"].update(max_query_points=150_001),
            lambda value: value["limits"].update(timeout_ms=15_001),
        ):
            candidate = json.loads(json.dumps(valid))
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises((RegistrationContractError, ValueError)):
                RegistrationRequest.parse(candidate)

    def test_adapter_rejects_outside_symlink_ascii_and_malformed_pcd(self):
        adapter = OfflineRegistrationProcess(self.cli, [self.root])
        outside_dir = tempfile.TemporaryDirectory(prefix="robot-scope-registration-outside-")
        self.addCleanup(outside_dir.cleanup)
        outside = Path(outside_dir.name) / "outside.pcd"
        write_pcd(outside, room_cloud())
        symlink = self.root / "link.pcd"
        symlink.symlink_to(self.reference)
        ascii_pcd = self.root / "ascii.pcd"
        ascii_pcd.write_text("FIELDS x y z\nPOINTS 1\nDATA ascii\n0 0 0\n", encoding="ascii")
        for invalid in (outside, symlink, ascii_pcd):
            with self.subTest(invalid=invalid), self.assertRaises(RegistrationContractError):
                adapter.run(request(invalid, self.query))

    def test_result_contract_rejects_false_confidence_unknown_fields_and_nonfinite(self):
        valid = {
            "schema": "robot-scope.relocalization-result.v1",
            "backend": "bounded-se2-icp",
            "results": [{
                "converged": True,
                "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                "metrics": {
                    "fitness": 0.02, "overlap_ratio": 0.8, "inlier_ratio": 0.8,
                    "query_points": 600, "reference_points": 1000, "runtime_ms": 5.0,
                },
                "confidence": "HIGH", "rank": 1, "ambiguity_margin": 0.2,
            }],
            "timing": {"preprocess_ms": 1.0, "coarse_ms": 2.0, "refine_ms": 2.0},
        }
        RegistrationResultSet.parse(valid)
        for mutate in (
            lambda value: value.update(path="/tmp/leak"),
            lambda value: value["results"][0].update(confidence="HIGH", ambiguity_margin=0.0),
            lambda value: value["results"][0]["pose"].update(x=float("inf")),
        ):
            candidate = json.loads(json.dumps(valid))
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(RegistrationContractError):
                RegistrationResultSet.parse(candidate)

    def test_confidence_never_promotes_ambiguous_or_sparse_geometry(self):
        self.assertEqual(
            confidence_for(converged=True, query_points=800, overlap_ratio=0.9, fitness=0.01, ambiguity_margin=0.0),
            "LOW",
        )
        self.assertEqual(
            confidence_for(converged=True, query_points=499, overlap_ratio=0.9, fitness=0.01, ambiguity_margin=0.5),
            "REJECTED",
        )
        self.assertEqual(
            confidence_for(converged=False, query_points=800, overlap_ratio=0.9, fitness=0.01, ambiguity_margin=0.5),
            "REJECTED",
        )

    def test_timeout_kills_process_group_and_releases_single_job_slot(self):
        slow = self.root / "slow"
        slow.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
        slow.chmod(0o700)
        adapter = OfflineRegistrationProcess(slow, [self.root])
        with self.assertRaises(RegistrationProcessError):
            adapter.run(request(self.reference, self.query, timeout_ms=100))
        failing = self.root / "failing"
        failing.write_text("#!/bin/sh\necho failed >&2\nexit 2\n", encoding="utf-8")
        failing.chmod(0o700)
        with self.assertRaisesRegex(RegistrationProcessError, "failed"):
            OfflineRegistrationProcess(failing, [self.root]).run(request(self.reference, self.query))
        malformed = self.root / "malformed"
        malformed.write_text("#!/bin/sh\nprintf 'not-json\\n'\n", encoding="utf-8")
        malformed.chmod(0o700)
        with self.assertRaisesRegex(RegistrationProcessError, "invalid JSON"):
            OfflineRegistrationProcess(malformed, [self.root]).run(request(self.reference, self.query))

    def test_one_job_lock_fails_closed_without_starting_a_second_process(self):
        slow = self.root / "slow"
        slow.write_text("#!/bin/sh\nsleep 1\n", encoding="utf-8")
        slow.chmod(0o700)
        adapter = OfflineRegistrationProcess(slow, [self.root])
        errors = []

        def run_first():
            try:
                adapter.run(request(self.reference, self.query, timeout_ms=1500))
            except RegistrationProcessError as exc:
                errors.append(exc)

        thread = threading.Thread(target=run_first)
        thread.start()
        time.sleep(0.1)
        with self.assertRaises(RegistrationBusy):
            adapter.run(request(self.reference, self.query))
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)

    def test_cancel_event_terminates_owned_process_group(self):
        slow = self.root / "cancel-slow"
        slow.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
        slow.chmod(0o700)
        adapter = OfflineRegistrationProcess(slow, [self.root])
        cancel = threading.Event()
        timer = threading.Timer(0.05, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        started = time.monotonic()
        with self.assertRaises(RegistrationCanceled):
            adapter.run(request(self.reference, self.query), cancel_event=cancel)
        self.assertLess(time.monotonic() - started, 1.0)


if __name__ == "__main__":
    unittest.main()
