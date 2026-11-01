from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from tests.expansion_services.http_client import TestClient

from robot_dashboard.expansion_contracts import ContractError, CollisionAssessment
from robot_dashboard.expansion_contracts.fixtures import (
    envelope,
    request,
    source,
    obstacle,
)
from robot_dashboard.expansion_contracts.messages import IDENTITY
from robot_dashboard.expansion_services.catalogue import (
    CatalogueAdapter,
    ResolvedSource,
    Conflict,
    Busy,
    validate_dag,
)
from robot_dashboard.expansion_services.export import BundleStore, transform_masks
from robot_dashboard.expansion_services.jobs import FusionJobManager
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.pcd_editing.store import SourceAsset, _digest
from robot_dashboard.pcd_editing.pcd import _read_header
from experiments.expansion_20261029.c1_service_host.host import (
    write_synthetic_pcd,
    fixture_solver,
    create_test_host,
)


class Rig:
    def __init__(self, root, solver=fixture_solver, normals=True, **limits):
        self.root, self.resolved = Path(root), {}
        for index in (1, 2, 3):
            path = self.root / f"source-{index}.pcd"
            fields = write_synthetic_pcd(path, normals=normals, offset=index)
            d = replace(source(index, _digest(path)), point_schema=fields)
            self.resolved[d.map_id] = ResolvedSource(
                d, SourceAsset(d.map_id, d.revision, path, d.frame_id)
            )
        self.catalogue = CatalogueAdapter(
            lambda: list(self.resolved), lambda k: self.resolved[k]
        )
        self.store = BundleStore(self.root / "exports", self.catalogue, chunk_points=1)
        self.manager = FusionJobManager(self.catalogue, solver, self.store, **limits)

    def request(self, indices=(1, 2), request_id="fixture-request"):
        return request(
            [self.resolved[f"{i:024x}"].descriptor for i in indices], request_id
        )

    def wait(self, job_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.manager.status(job_id)
            if state["state"] not in {"RUNNING", "QUEUED"}:
                return state
            time.sleep(0.002)
        raise AssertionError("worker did not finish fixture")

    def solve_review(self, req=None):
        j = self.manager.enqueue(req or self.request())
        s = self.wait(j["job_id"])
        if s["state"] != "SOLVED_CANDIDATE":
            raise AssertionError(s)
        return self.manager.review(j["job_id"], s["proposal_revision"], True)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rigs = []

    def tearDown(self):
        for r in self.rigs:
            r.manager.close()
        self.temp.cleanup()

    def rig(self, **kwargs):
        r = Rig(self.temp.name, **kwargs)
        self.rigs.append(r)
        return r

    def test_full_export_normals_scalar_unknown_immutable_reload(self):
        def rotated(req, sources, cancel, progress, *, job_id):
            p = fixture_solver(req, sources, cancel, progress, job_id=job_id)
            t = [0.0, -1, 0, 4, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
            return replace(
                p,
                T_fused_source={
                    sources[0].descriptor.key: list(IDENTITY),
                    sources[1].descriptor.key: t,
                },
            )

        r = self.rig(solver=rotated)
        before = {k: _digest(s.asset.path) for k, s in r.resolved.items()}
        j = r.solve_review()
        with self.assertRaises(Conflict):
            r.manager.export(j["job_id"], "merged", 1)
        m = r.manager.export(j["job_id"], "merged", j["proposal_revision"])
        self.assertEqual(m["point_count"], 6)
        self.assertFalse(m["operational_installed"])
        self.assertIsNone(m["sources"][0]["mapping_session_id"])
        self.assertEqual(
            m["source_pcd_metadata"][0]["original_header"]["VIEWPOINT"],
            ["0", "0", "0", "1", "0", "0", "0"],
        )
        self.assertEqual(m["legacy_family"]["status"], "DEFERRED")
        with (r.store.root / m["id"] / "map.pcd").open("rb") as stream:
            _, _, dtype, count, _ = _read_header(
                stream, (r.store.root / m["id"] / "map.pcd").stat().st_size, 100
            )
            records = np.frombuffer(stream.read(), dtype=dtype)
        self.assertEqual(count, 6)
        np.testing.assert_allclose(records["normal_x"][3:], 0, atol=1e-7)
        np.testing.assert_allclose(records["normal_y"][3:], 1)
        np.testing.assert_allclose(records["intensity"], [10, 20, 30, 10, 20, 30])
        pixels = (
            (r.store.root / m["id"] / "occupancy.pgm").read_bytes().split(b"\n", 3)[3]
        )
        self.assertIn(205, pixels)
        self.assertNotIn(254, pixels)
        self.assertIsNone(m["occupancy"]["free_evidence"])
        self.assertEqual(
            before, {k: _digest(s.asset.path) for k, s in r.resolved.items()}
        )
        reloaded = r.store.reload(m["id"])
        self.assertEqual(_digest(reloaded.asset.path), reloaded.descriptor.sha256)
        with self.assertRaises(Conflict):
            r.manager.cancel(j["job_id"])
        path = r.store.root / m["id"] / "map.pcd"
        path.chmod(0o600)
        with path.open("ab") as stream:
            stream.write(b"bad")
        with self.assertRaises(Conflict):
            r.store.get(m["id"])

    def test_private_worker_copy_and_aggregate_byte_limit(self):
        captured = []

        def check(req, sources, cancel, progress, *, job_id):
            captured.extend(s.asset.path for s in sources)
            self.assertTrue(
                all(s.asset.path.stat().st_mode & 0o222 == 0 for s in sources)
            )
            return fixture_solver(req, sources, cancel, progress, job_id=job_id)

        r = self.rig(solver=check)
        j = r.manager.enqueue(r.request())
        self.assertEqual(r.wait(j["job_id"])["state"], "SOLVED_CANDIDATE")
        self.assertTrue(all(not p.exists() for p in captured))
        self.assertTrue(
            all(p != s.asset.path for p in captured for s in r.resolved.values())
        )
        r.manager.max_job_bytes = 1
        j = r.manager.enqueue(r.request(request_id="oversize-job"))
        self.assertEqual(r.wait(j["job_id"])["state"], "FAILED")

    def test_idempotence_bounded_worker_cancel_late_result_and_history(self):
        entered, release = threading.Event(), threading.Event()
        active, peak = 0, 0

        def slow(req, sources, cancel, progress, *, job_id):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            progress(0.5)
            entered.set()
            release.wait(2)
            active -= 1
            return fixture_solver(req, sources, cancel, progress, job_id=job_id)

        r = self.rig(solver=slow, max_queue=1, max_history=2)
        j = r.manager.enqueue(r.request())
        self.assertTrue(entered.wait(1))
        self.assertEqual(r.manager.enqueue(r.request())["job_id"], j["job_id"])
        with self.assertRaises(Conflict):
            r.manager.enqueue(replace(r.request(), options={"max_iterations": 11}))
        next_job = r.manager.enqueue(r.request(request_id="second"))
        with self.assertRaises(Busy):
            r.manager.enqueue(r.request(request_id="third"))
        self.assertEqual(r.manager.status(j["job_id"])["progress"], 0.5)
        r.manager.cancel(j["job_id"])
        release.set()
        self.assertEqual(r.wait(next_job["job_id"])["state"], "SOLVED_CANDIDATE")
        self.assertIsNone(r.manager.status(j["job_id"])["proposal"])
        self.assertEqual(peak, 1)
        r.wait(r.manager.enqueue(r.request(request_id="third"))["job_id"])
        self.assertEqual(len(r.manager._jobs), 2)
        self.assertEqual(len(r.manager._requests), 2)

    def test_drift_and_wrong_worker_pins_fail_closed(self):
        def drift(req, sources, cancel, progress, *, job_id):
            with sources[0].asset.path.open("ab") as stream:
                stream.write(b"changed")
            return fixture_solver(req, sources, cancel, progress, job_id=job_id)

        r = self.rig(solver=drift)
        j = r.manager.enqueue(r.request())
        self.assertEqual(r.wait(j["job_id"])["state"], "FAILED")
        self.assertIsNone(r.manager.status(j["job_id"])["proposal"])
        self.assertFalse(r.store.root.exists())

    def test_worker_cannot_mutate_owned_pins(self):
        def mutator(req, sources, cancel, progress, *, job_id):
            req.source_pins[req.anchor_source_key] = "f" * 64
            return fixture_solver(req, sources, cancel, progress, job_id=job_id)

        r = self.rig(solver=mutator)
        self.assertEqual(
            r.wait(r.manager.enqueue(r.request())["job_id"])["state"], "FAILED"
        )

    def test_wrong_solver_identity_rejected(self):
        def bad(req, sources, cancel, progress, *, job_id):
            return fixture_solver(req, sources, cancel, progress, job_id="f" * 24)

        r = self.rig(solver=bad)
        self.assertEqual(
            r.wait(r.manager.enqueue(r.request())["job_id"])["state"], "FAILED"
        )

    def test_revision_review_manual_and_rejection_fence(self):
        r = self.rig()
        j = r.manager.enqueue(r.request())
        s = r.wait(j["job_id"])
        with self.assertRaises(Conflict):
            r.manager.export(j["job_id"], "unreviewed", 1)
        rejected = r.manager.review(j["job_id"], 1, False)
        with self.assertRaises(Conflict):
            r.manager.export(j["job_id"], "rejected", 2)
        accepted = r.manager.review(
            j["job_id"],
            rejected["proposal_revision"],
            True,
            s["proposal"]["T_fused_source"],
        )
        self.assertFalse(accepted["review"]["registration_quality_validated"])
        with self.assertRaises(Conflict):
            r.manager.review(j["job_id"], 1, True)
        self.assertEqual(accepted["proposal_revision"], 3)

    def test_duplicate_export_and_crash_staging_leave_no_registration(self):
        r = self.rig()
        j = r.solve_review()
        with patch(
            "robot_dashboard.expansion_services.export._sync_directory",
            side_effect=OSError("injected crash"),
        ):
            with self.assertRaises(OSError):
                r.manager.export(j["job_id"], "crash", 2)
        self.assertEqual(list(r.store.root.glob(".stage-*")), [])
        self.assertEqual([p for p in r.store.root.iterdir() if len(p.name) == 24], [])
        m = r.manager.export(j["job_id"], "copy", 2)
        j2 = r.solve_review(r.request(request_id="retry"))
        with self.assertRaises(Conflict):
            r.manager.export(j2["job_id"], "copy", 2)
        self.assertEqual(r.store.get(m["id"])["name"], "copy")
        self.assertEqual(list(r.store.root.glob(".stage-*")), [])

    def test_durability_failure_after_rename_rolls_back_registration(self):
        r = self.rig()
        j = r.solve_review()
        from robot_dashboard.expansion_services.export import _sync_directory

        def fail_root(path):
            if path == r.store.root:
                raise OSError("injected root fsync failure")
            return _sync_directory(path)

        with patch(
            "robot_dashboard.expansion_services.export._sync_directory",
            side_effect=fail_root,
        ):
            with self.assertRaises(OSError):
                r.manager.export(j["job_id"], "durability", 2)
        self.assertEqual([p for p in r.store.root.iterdir() if len(p.name) == 24], [])
        self.assertEqual(r.manager.status(j["job_id"])["state"], "REVIEWED")

    def test_cancel_during_export_prevents_atomic_publish(self):
        r = self.rig()
        j = r.solve_review()
        original = r.store._merge

        def cancel_then_merge(*args):
            result = original(*args)
            r.manager.cancel(j["job_id"])
            return result

        with patch.object(r.store, "_merge", side_effect=cancel_then_merge):
            with self.assertRaises(Conflict):
                r.manager.export(j["job_id"], "canceled", 2)
        self.assertEqual([p for p in r.store.root.iterdir() if len(p.name) == 24], [])
        self.assertEqual(r.manager.status(j["job_id"])["state"], "CANCELED")

    def test_two_to_three_source_dag_cycle_duplicate_ancestor(self):
        r = self.rig()
        j = r.solve_review()
        first = r.manager.export(j["job_id"], "two", 2)
        fused = r.store.reload(first["id"])
        r.resolved[fused.descriptor.map_id] = fused
        third = r.resolved[f"{3:024x}"].descriptor
        req = request([fused.descriptor, third], "three")
        second_job = r.solve_review(req)
        second = r.manager.export(second_job["job_id"], "three", 2)
        self.assertEqual(second["point_count"], 9)
        self.assertEqual(len(second["provenance_dag"]), 4)
        with self.assertRaises(Conflict):
            r.catalogue.pinned(
                request(
                    [fused.descriptor, r.resolved[f"{1:024x}"].descriptor], "duplicate"
                )
            )
        with self.assertRaises(Conflict):
            validate_dag(
                [replace(fused, lineage={fused.descriptor.key: [fused.descriptor.key]})]
            )

    def test_schema_mismatch_and_source_drift_on_export(self):
        r = self.rig()
        j = r.solve_review()
        s = r.resolved[f"{2:024x}"]
        r.resolved[s.descriptor.map_id] = replace(
            s, descriptor=replace(s.descriptor, revision="f" * 64)
        )
        with self.assertRaises(Conflict):
            r.manager.export(j["job_id"], "changed", 2)
        r.resolved[s.descriptor.map_id] = s
        fields = write_synthetic_pcd(s.asset.path, normals=False)
        d = replace(s.descriptor, sha256=_digest(s.asset.path), point_schema=fields)
        r.resolved[d.map_id] = replace(s, descriptor=d)
        j2 = r.solve_review(r.request(request_id="schema"))
        with self.assertRaises(ContractError):
            r.manager.export(j2["job_id"], "schema", 2)
        self.assertEqual(list(r.store.root.glob(".stage-*")), [])

    def test_tilted_and_missing_z_masks_stay_review_candidates(self):
        r = self.rig()
        s = r.resolved[f"{1:024x}"]
        mask = {
            "kind": "keepout",
            "frame_key": s.descriptor.key,
            "polygon": [[0, 0], [1, 0], [0, 1]],
            "z_min": 0,
            "z_max": 2,
        }
        s = replace(s, semantic_masks=(mask, {**mask, "z_max": None}))
        t = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1]
        values = transform_masks([s], {s.descriptor.key: t})
        self.assertEqual(len(values[0]["transformed_prism"]), 6)
        self.assertTrue(
            all(v["review_required"] and not v["operational_installed"] for v in values)
        )
        self.assertIsNone(values[1]["transformed_prism"])


class SceneTests(unittest.TestCase):
    def test_1200_samples_are_bounded_latest_only_and_age_unknown(self):
        first = obstacle()
        scene = SceneSnapshotService(
            first.map_binding, max_history=8, host_clock_id="different-host"
        )
        for n in range(1200):
            self.assertTrue(scene.ingest("obstacle_frame", obstacle(n).to_dict()))
        self.assertEqual(
            scene.metrics(),
            {
                "history_size": 8,
                "history_limit": 8,
                "latest_size": 1,
                "dropped": 0,
                "persistent_ledger_writes": 0,
            },
        )
        packet = scene.snapshot()
        self.assertEqual(packet["obstacle_frame"]["sequence"], 1199)
        self.assertIsNone(packet["sources"]["obstacle_frame"]["received_age_ms"])
        self.assertIsNone(packet["global_path"])
        packet["obstacle_frame"]["health"]["state"] = "mutated"
        self.assertNotEqual(
            scene.snapshot()["obstacle_frame"]["health"]["state"], "mutated"
        )
        self.assertFalse(scene.ingest("obstacle_frame", obstacle(1198).to_dict()))

    def test_map_epoch_reset_and_missing_calibration(self):
        first = obstacle()
        scene = SceneSnapshotService(
            first.map_binding, host_clock_id="test-host", clock=lambda: 10000000
        )
        scene.ingest("obstacle_frame", first.to_dict())
        self.assertFalse(
            scene.ingest("obstacle_frame", obstacle(1, epoch="new").to_dict())
        )
        scene.reset_source("obstacle_frame", "new")
        self.assertFalse(scene.ingest("obstacle_frame", obstacle(2).to_dict()))
        self.assertTrue(
            scene.ingest(
                "obstacle_frame",
                obstacle(0, epoch="new", calibration_id=None).to_dict(),
            )
        )
        self.assertEqual(
            scene.snapshot()["sources"]["obstacle_frame"]["calibration_status"],
            "UNKNOWN",
        )
        scene.reset({**first.map_binding, "generation": 1}, "scene-1")
        self.assertFalse(scene.ingest("obstacle_frame", first.to_dict()))
        self.assertIsNone(scene.snapshot()["obstacle_frame"])
        with self.assertRaises(ContractError):
            scene.reset(first.map_binding, "old")

    def test_collision_reference_time_fences_and_scene_byte_bound(self):
        o = obstacle()
        scene = SceneSnapshotService(
            o.map_binding, host_clock_id="test-host", clock=lambda: 10
        )
        scene.ingest("obstacle_frame", o.to_dict())
        observation_keys = {
            "frame_key",
            "stamp_ns",
            "clock_domain",
            "host_clock_id",
            "received_monotonic_ns",
            "map_binding",
        }
        c = CollisionAssessment(
            **envelope(),
            **{k: o.to_dict()[k] for k in observation_keys},
            robot_pose_ref=None,
            joint_state_ref=None,
            robot_geometry_hash=None,
            obstacle_frame_ref={"source_epoch": o.source_epoch, "sequence": 0},
            path_ref=None,
            padded_envelope=None,
            unpadded_envelope=None,
            min_clearance=None,
            predicted_overlap=None,
            modeled_ttc=None,
            freshness={"status": "UNKNOWN"},
            validity_interval={},
            reason="UNKNOWN",
            severity="UNKNOWN",
            recommendation="observation only",
        )
        scene.ingest("collision_assessment", c.to_dict())
        self.assertIsNone(scene.snapshot()["collision_assessment"])
        c = replace(
            c,
            sequence=1,
            validity_interval={
                "host_clock_id": "test-host",
                "start_monotonic_ns": 0,
                "end_monotonic_ns": 20,
            },
        )
        scene.ingest("collision_assessment", c.to_dict())
        self.assertEqual(
            scene.snapshot()["collision_assessment"]["severity"], "UNKNOWN"
        )
        scene.ingest("obstacle_frame", obstacle(1).to_dict())
        self.assertIsNone(scene.snapshot()["collision_assessment"])
        with self.assertRaises(ContractError):
            scene.ingest(
                "obstacle_frame", {**o.to_dict(), "health": {"data": "x" * 20000}}
            )


class RouterAndImportTests(unittest.TestCase):
    def test_authenticated_router_offline_flow_size_origin_and_error_redaction(self):
        with tempfile.TemporaryDirectory() as root:
            bearer = "c1-public-synthetic-test-bearer"
            app = create_test_host(root, bearer)
            with TestClient(app, base_url="http://127.0.0.1") as client:
                url = "/api/v1/extensions"
                self.assertEqual(client.get(url + "/multimap/sources").status_code, 401)
                headers = {
                    "Authorization": "Bearer " + bearer,
                    "Origin": "http://127.0.0.1",
                }
                values = client.get(url + "/multimap/sources", headers=headers).json()[
                    "sources"
                ]
                from robot_dashboard.expansion_contracts import MapSourceDescriptor

                req = request(
                    [MapSourceDescriptor.from_dict(v) for v in values]
                ).to_dict()
                self.assertEqual(
                    client.post(
                        url + "/multimap/jobs",
                        headers={**headers, "Origin": "http://evil"},
                        json=req,
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.post(
                        url + "/multimap/jobs",
                        headers=headers,
                        json={**req, "path": "/etc/passwd"},
                    ).status_code,
                    422,
                )
                self.assertEqual(
                    client.post(
                        url + "/multimap/jobs",
                        headers={**headers, "content-type": "application/json"},
                        content=b"x" * 131073,
                    ).status_code,
                    413,
                )
                self.assertEqual(
                    client.post(
                        url + "/multimap/jobs",
                        headers={**headers, "content-type": "application/json"},
                        content=b'{"request_id":1,"request_id":2}',
                    ).status_code,
                    422,
                )
                response = client.post(
                    url + "/multimap/jobs", headers=headers, json=req
                )
                self.assertEqual(response.status_code, 202, response.text)
                job = response.json()["job_id"]
                for _ in range(100):
                    s = client.get(
                        url + "/multimap/jobs/" + job, headers=headers
                    ).json()
                    if s["state"] == "SOLVED_CANDIDATE":
                        break
                    time.sleep(0.005)
                reviewed = client.post(
                    url + f"/multimap/jobs/{job}/review",
                    headers=headers,
                    json={
                        "expected_proposal_revision": 1,
                        "accepted": True,
                        "manual_selection": None,
                    },
                )
                self.assertEqual(reviewed.status_code, 200, reviewed.text)
                exported = client.post(
                    url + f"/multimap/jobs/{job}/exports",
                    headers=headers,
                    json={"expected_proposal_revision": 2, "name": "fixture"},
                )
                self.assertEqual(exported.status_code, 201, exported.text)
                self.assertNotIn(root, exported.text)
                self.assertEqual(
                    client.get(
                        url + "/multimap/exports/" + exported.json()["id"],
                        headers=headers,
                    ).status_code,
                    200,
                )
                self.assertIsNone(
                    client.get(url + "/scene/snapshot", headers=headers).json()[
                        "controller_local_trajectory"
                    ]
                )
                self.assertFalse(
                    any(
                        "activate" in p or "goal" in p or "cmd_vel" in p
                        for p in app.openapi()["paths"]
                    )
                )

    def test_import_has_no_thread_process_ros_or_model_side_effect(self):
        code = """import threading, subprocess, socket, sys
threading.Thread.start=lambda *a,**k: (_ for _ in ()).throw(AssertionError("thread"))
subprocess.Popen=lambda *a,**k: (_ for _ in ()).throw(AssertionError("process"))
socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(AssertionError("network"))
import robot_dashboard.expansion_contracts
import robot_dashboard.expansion_services.catalogue
import robot_dashboard.expansion_services.export
import robot_dashboard.expansion_services.jobs
import robot_dashboard.expansion_services.scene
import robot_dashboard.expansion_services.router
import experiments.expansion_20261029.c1_service_host.host
assert not any(n in sys.modules for n in ("rclpy", "torch", "robot_dashboard.app"))
"""
        p = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
        )
        self.assertEqual(p.returncode, 0, p.stderr)
