"""Offline numerical and storage acceptance. All sensor data here is SYNTHETIC."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile

import numpy as np

from robot_dashboard.offline_slam.core import (
    Settings,
    encoded,
    optimize,
    pose,
    preview,
    project,
    register,
    validate_session,
)
from robot_dashboard.offline_slam.demo import fixture
from robot_dashboard.offline_slam.maps import ray_cells, rebuild
from robot_dashboard.offline_slam.record import Recorder, recover
from robot_dashboard.offline_slam.server import create_app
from robot_dashboard.offline_slam.store import Store


class NumericalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.settings = Settings(search_radius=1.2, min_separation=10)
        cls.result = optimize(cls.data, cls.settings)

    def test_real_optimization_closes_synthetic_loop_without_mutating_inputs(self):
        self.assertEqual(self.data, fixture())
        result = self.result
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertGreater(result["metrics"]["accepted_loops"], 0)
        self.assertLess(
            result["metrics"]["final_cost"], result["metrics"]["initial_cost"]
        )
        self.assertLess(result["metrics"]["endpoint_gap_after_m"], 0.04)
        np.testing.assert_array_equal(
            result["poses_before"][0], result["poses_after"][0]
        )
        # Same sampled landmark at first/last frames must align after correction.
        clouds = [np.asarray(f["points"]) for f in self.data["keyframes"]]
        before = np.sqrt(
            np.mean(
                (project(clouds[-1], np.array(result["poses_before"][-1])) - clouds[0])
                ** 2
            )
        )
        after = np.sqrt(
            np.mean(
                (project(clouds[-1], np.array(result["poses_after"][-1])) - clouds[0])
                ** 2
            )
        )
        self.assertLess(after, before * 0.2)

    def test_correlated_information_whitening_convention(self):
        # Production weights are diagonal; ensure exported matrices match residual scale.
        for edge in self.result["edges"]:
            info = np.array(edge["information"])
            self.assertTrue(np.all(np.linalg.eigvalsh(info) > 0))
            root = np.linalg.cholesky(info).T
            e = np.arange(6) * 0.1
            self.assertAlmostEqual(
                float(np.linalg.norm(root @ e) ** 2), float(e @ info @ e)
            )

    def test_loop_absence_not_reported_as_success(self):
        result = optimize(self.data, Settings(min_separation=399))
        self.assertEqual(result["state"], "NO_LOOP")
        self.assertNotIn("poses_after", result)

    def test_false_correspondences_and_degenerate_geometry_rejected(self):
        rng = np.random.default_rng(4)
        source = rng.normal(size=(100, 3))
        value, metrics = register(source, source + 20, np.eye(4), self.settings)
        self.assertIsNone(value)
        line = np.column_stack([np.arange(100) * 0.01, np.zeros(100), np.zeros(100)])
        value, metrics = register(line, line, np.eye(4), self.settings)
        self.assertIsNone(value)
        self.assertEqual(metrics["reason"], "DEGENERATE_GEOMETRY")

    def test_validation_rejects_bad_time_nan_rotation_and_settings(self):
        invalid = deepcopy(self.data)
        invalid["provenance"] = []
        with self.assertRaises(ValueError):
            validate_session(invalid)
        invalid = deepcopy(self.data)
        invalid.pop("sensor_origin_body")
        with self.assertRaises(ValueError):
            validate_session(invalid)
        for mutate in [
            lambda d: d["keyframes"][1].update(stamp_ns=d["keyframes"][0]["stamp_ns"]),
            lambda d: d["keyframes"][0]["points"][0].__setitem__(0, float("nan")),
            lambda d: d["keyframes"][0]["T_parent_body"][0].__setitem__(0, 2),
        ]:
            data = deepcopy(self.data)
            mutate(data)
            with self.assertRaises(ValueError):
                validate_session(data)
        for s in [
            Settings(min_separation=3.5),
            Settings(resolution=0),
            Settings(max_height=0),
            Settings(search_radius=float("nan")),
        ]:
            with self.assertRaises(ValueError):
                s.validate()

    def test_3d_transform_and_exact_stamp_recording(self):
        recorder = Recorder("fixture-calibration")
        points = np.random.default_rng(1).uniform(-1, 1, (100, 3))
        for k in range(3):
            t = pose(np.array([k, 0, 0.1 * k, 0.1 * k, 0, 0.2 * k]))
            recorder.add("cloud", k + 1, project(points, t), "camera_init")
            self.assertEqual(len(recorder.data["keyframes"]), k)
            recorder.add("pose", k + 1, t, "camera_init", "body")
        self.assertEqual(len(recorder.data["keyframes"]), 3)
        # Voxel selection removes duplicates, but every retained point must still
        # be in the original local frame, including nonzero roll and pitch.
        from scipy.spatial import cKDTree

        distances = cKDTree(points).query(recorder.data["keyframes"][2]["points"])[0]
        self.assertLess(float(distances.max()), 1e-12)
        with self.assertRaises(ValueError):
            recorder.add("cloud", 99, points, "map")
        validate_session(recorder.data)

    def test_maps_and_preview_are_rebuilt_from_corrected_poses(self):
        assets = rebuild(self.data, self.result)
        self.assertIn(b"DATA binary\n", assets["optimized.pcd"])
        self.assertTrue(assets["map.pgm"].startswith(b"P5\n"))
        self.assertIn(b"image: map.pgm", assets["map.yaml"])
        self.assertEqual(list(ray_cells((0, 0), (2, 2))), [(0, 0), (1, 1), (2, 2)])
        comp = preview(self.data, self.result)
        self.assertEqual(comp["revision"], self.result["revision"])
        self.assertLessEqual(len(comp["after"]), 16000)
        self.assertNotEqual(comp["before"], comp["after"])

    def test_journal_recovery_preserves_only_complete_keyframes(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = Path(temp) / "run.partial.jsonl"
            recorder = Recorder("original-calibration", journal=journal)
            points = np.random.default_rng(1).uniform(-2, 2, (80, 3))
            for k in range(3):
                t = pose(np.array([k, 0, 0, 0, 0, 0]))
                recorder.add(
                    "cloud", (k + 1) * 1_000_000_000, project(points, t), "camera_init"
                )
                recorder.add("pose", (k + 1) * 1_000_000_000, t, "camera_init", "body")
            with journal.open("ab") as handle:
                handle.write(b'{"interrupted":')
            out = Path(temp) / "recovered.json"
            recover(journal, out)
            data = json.loads(out.read_bytes())
            self.assertEqual(data["keyframes"], recorder.data["keyframes"])
            self.assertEqual(data["calibration_id"], "original-calibration")
            with self.assertRaises(FileExistsError):
                recover(journal, out)
            with self.assertRaisesRegex(ValueError, "SOURCE_TIME_RESET"):
                recorder.add("pose", 1, np.eye(4), "camera_init", "body")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "offline")
        self.data = fixture()
        self.job = self.store.import_session(encoded(self.data))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_subprocess_to_immutable_export_and_hashes(self):
        identifier = self.job["id"]
        self.store.start(
            identifier,
            Settings(search_radius=1.2, min_separation=10),
            self.job["source_revision"],
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = self.store.status(identifier)
            if job["state"] != "RUNNING":
                break
            time.sleep(0.1)
        self.assertEqual(job["state"], "SUCCEEDED", job)
        with self.assertRaises(ValueError):
            self.store.save(identifier, "0" * 64)
        self.store.save(identifier, job["revision"])
        path = self.store.export(identifier, job["revision"])
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertFalse(manifest["navigation_validated"])
            for name, sha in manifest["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), sha)
            self.assertEqual(json.loads(archive.read("session.json")), self.data)
        before = path.read_bytes()
        self.store.save(identifier, job["revision"])
        self.assertEqual(before, path.read_bytes())
        with self.assertRaises(ValueError):
            self.store.start(identifier, Settings(), self.job["source_revision"])

    def test_revision_paths_cancel_and_restart(self):
        for value in ["../bad", "a" * 31, "a" * 32]:
            with self.assertRaises(ValueError):
                self.store.status(value)
        with self.assertRaises(ValueError):
            self.store.start(self.job["id"], Settings(), "0" * 64)
        self.store.start(self.job["id"], Settings(), self.job["source_revision"])
        self.assertEqual(self.store.cancel(self.job["id"])["state"], "CANCELLED")
        with self.assertRaises(ValueError):
            Store(self.store.root)
        self.store.close()
        other = Store(self.store.root)
        try:
            self.assertEqual(other.status(self.job["id"])["state"], "CANCELLED")
        finally:
            other.close()

    def test_old_run_result_cannot_replace_new_attempt(self):
        identifier = self.job["id"]
        first = self.store.start(identifier, Settings(), self.job["source_revision"])
        self.store.cancel(identifier)
        second = self.store.start(
            identifier, Settings(min_separation=399), self.job["source_revision"]
        )
        self.assertNotEqual(first["run_id"], second["run_id"])
        old = self.store.directory(identifier) / first["run_id"] / "result.json"
        old.write_bytes(encoded(dict(state="SUCCEEDED", revision="0" * 64)))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = self.store.status(identifier)
            if current["state"] != "RUNNING":
                break
            time.sleep(0.05)
        self.assertEqual(current["state"], "NO_LOOP")
        self.assertNotIn("revision", current)

    def test_timeout_rejects_save(self):
        identifier = self.job["id"]
        self.store.start(identifier, Settings(), self.job["source_revision"])
        self.store.started -= 601
        self.assertEqual(self.store.status(identifier)["state"], "TIMED_OUT")
        with self.assertRaises(ValueError):
            self.store.save(identifier, "0" * 64)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(self.temp.name)

    async def asyncTearDown(self):
        self.app.state.store.close()
        self.temp.cleanup()

    async def request(self, method, path, body=None, origin="http://testserver"):
        messages = []
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return dict(
                    type="http.request", body=encoded(body or {}), more_body=False
                )
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
        if origin:
            headers.append((b"origin", origin.encode()))
        await self.app(
            dict(
                type="http",
                asgi={"version": "3.0", "spec_version": "2.4"},
                http_version="1.1",
                method=method,
                scheme="http",
                path=path,
                raw_path=path.encode(),
                query_string=b"",
                root_path="",
                server=("testserver", 80),
                client=("127.0.0.1", 1000),
                headers=headers,
            ),
            receive,
            send,
        )
        status = next(
            x["status"] for x in messages if x["type"] == "http.response.start"
        )
        raw = b"".join(
            x.get("body", b"") for x in messages if x["type"] == "http.response.body"
        )
        return status, json.loads(raw)

    async def test_import_read_and_origin_boundary(self):
        for origin in [None, "http://attacker.example", "null"]:
            status, _ = await self.request("POST", "/api/sessions", fixture(), origin)
            self.assertEqual(status, 403)
        status, job = await self.request("POST", "/api/sessions", fixture())
        self.assertEqual(status, 201)
        status, comparison = await self.request(
            "GET", f'/api/sessions/{job["id"]}/comparison'
        )
        self.assertEqual(status, 200)
        self.assertEqual(comparison["before"], comparison["after"])
        status, _ = await self.request(
            "POST",
            f'/api/sessions/{job["id"]}/optimize',
            {"expected_revision": job["source_revision"], "settings": {"shell": "bad"}},
        )
        self.assertEqual(status, 422)
        status, _ = await self.request(
            "POST", f'/api/sessions/{job["id"]}/save', {"revision": "0" * 64}
        )
        self.assertEqual(status, 422)


if __name__ == "__main__":
    unittest.main()
