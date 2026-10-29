"""Actual D1 solver -> exact external C1 worker/store, without HTTP or mocks.

D1_C1_ROUND2_EXPORT points to a git archive of the pinned C1 packages. No C1
source is vendored. Inputs and exported PCDs exist only in temporary storage.
"""

import hashlib
import importlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from dataclasses import replace

import numpy as np
import robot_dashboard
from experiments.expansion_20261029.d1_multimap.generate import fixture
from robot_dashboard.multimap_core.contract_adapter import solve_contract
from robot_dashboard.pcd_editing.pcd import _read_header
from robot_dashboard.pcd_editing.store import SourceAsset

C1_SHA = "54629c793ad4ae0ea88127f00ed1b7f8805fc4e2"
C2_INSPECTED_SHA = "5eed1a9959ca25a4f30bd5b5712806a5ad660c51"


def read_pcd(path):
    with path.open("rb") as stream:
        _, _, dtype, count, _ = _read_header(stream, path.stat().st_size, 20000000)
        return np.frombuffer(stream.read(), dtype=dtype), count


@unittest.skipUnless(
    os.environ.get("D1_C1_ROUND2_EXPORT"), "exact round2 C1 export not supplied"
)
class Round2ConnectionTests(unittest.TestCase):
    def test_actual_solver_worker_review_full_source_store_reload(self):
        external = str(Path(os.environ["D1_C1_ROUND2_EXPORT"]) / "robot_dashboard")
        robot_dashboard.__path__.append(external)
        self.addCleanup(robot_dashboard.__path__.remove, external)
        contract = importlib.import_module("robot_dashboard.expansion_contracts")
        fixtures = importlib.import_module(
            "robot_dashboard.expansion_contracts.fixtures"
        )
        catalogue_module = importlib.import_module(
            "robot_dashboard.expansion_services.catalogue"
        )
        storage_module = importlib.import_module(
            "robot_dashboard.expansion_services.export"
        )
        jobs_module = importlib.import_module("robot_dashboard.expansion_services.jobs")
        with tempfile.TemporaryDirectory(prefix="d1-round2-") as temporary:
            root = Path(temporary)
            raw, resolver, truth = fixture(root, count=400)
            resolved = {}
            before = {}
            for i, descriptor in enumerate(raw[:2]):
                path = resolver(descriptor)
                records, count = read_pcd(path)
                wire = replace(
                    fixtures.source(i + 1, descriptor["sha256"]),
                    revision=descriptor["sha256"],
                    point_count=count,
                    mapping_session_id=f"{101+i:024x}",
                    point_schema=[
                        dict(name=n, size=4, type="F", count=1)
                        for n in records.dtype.names
                    ],
                    acquisition={"origin": "SYNTHETIC D1 generator"},
                )
                resolved[wire.map_id] = catalogue_module.ResolvedSource(
                    wire, SourceAsset(wire.map_id, wire.revision, path, wire.frame_id)
                )
                before[wire.map_id] = hashlib.sha256(path.read_bytes()).hexdigest()
            catalogue = catalogue_module.CatalogueAdapter(
                lambda: list(resolved), lambda i: resolved[i]
            )
            store = storage_module.BundleStore(
                root / "bundles", catalogue, chunk_points=17
            )

            def solver(request, sources, cancel, progress, *, job_id):
                paths = {s.descriptor.map_id: s.asset.path for s in sources}
                return solve_contract(
                    request,
                    lambda d: paths[d["map_id"]],
                    contract.FusionProposal,
                    job_id=job_id,
                    cancel_token=cancel,
                    progress=lambda event: progress(
                        min(0.95, event["completed_pairs"])
                    ),
                )

            manager = jobs_module.FusionJobManager(catalogue, solver, store)
            try:
                descriptors = [s.descriptor for s in resolved.values()]
                request = contract.FusionRequest(
                    **fixtures.envelope(),
                    request_id="d1-round2",
                    anchor_source_key=descriptors[0].key,
                    sources=[d.to_dict() for d in descriptors],
                    source_pins={d.key: d.sha256 for d in descriptors},
                    mode="seeded",
                    options={"voxel_size": 0.05},
                    correspondences=[],
                    initial_guesses=[
                        dict(
                            source_key=descriptors[1].key,
                            T_anchor_source=truth[1].reshape(16).tolist(),
                        )
                    ],
                )
                job = manager.enqueue(request)
                deadline = time.monotonic() + 10
                while True:
                    status = manager.status(job["job_id"])
                    if status["state"] not in ("QUEUED", "RUNNING"):
                        break
                    if time.monotonic() > deadline:
                        self.fail("bounded synthetic solver job did not finish")
                    time.sleep(0.01)
                self.assertEqual(status["state"], "SOLVED_CANDIDATE", status)
                reviewed = manager.review(
                    job["job_id"], status["proposal_revision"], True
                )
                with self.assertRaises(catalogue_module.Conflict):
                    manager.export(job["job_id"], "stale", status["proposal_revision"])
                manifest = manager.export(
                    job["job_id"], "round2", reviewed["proposal_revision"]
                )
                self.assertEqual(manifest["point_count"], 800)
                self.assertFalse(manifest["operational_installed"])
                self.assertIsNone(manifest["occupancy"]["free_evidence"])
                output = store.root / manifest["id"]
                merged, count = read_pcd(output / "map.pcd")
                self.assertEqual(count, 800)
                for i, source in enumerate(resolved.values()):
                    original, n = read_pcd(source.asset.path)
                    T = np.array(
                        manifest["T_fused_source"][source.descriptor.key]
                    ).reshape(4, 4)
                    xyz = (
                        np.column_stack([original[k] for k in ("x", "y", "z")])
                        @ T[:3, :3].T
                        + T[:3, 3]
                    )
                    normals = (
                        np.column_stack(
                            [original[k] for k in ("normal_x", "normal_y", "normal_z")]
                        )
                        @ T[:3, :3].T
                    )
                    block = merged[i * n : (i + 1) * n]
                    np.testing.assert_allclose(
                        np.column_stack([block[k] for k in ("x", "y", "z")]),
                        xyz,
                        atol=3e-7,
                    )
                    np.testing.assert_allclose(
                        np.column_stack(
                            [block[k] for k in ("normal_x", "normal_y", "normal_z")]
                        ),
                        normals,
                        atol=3e-7,
                    )
                    np.testing.assert_array_equal(
                        block["intensity"], original["intensity"]
                    )
                    self.assertEqual(
                        hashlib.sha256(source.asset.path.read_bytes()).hexdigest(),
                        before[source.descriptor.map_id],
                    )
                pixels = (output / "occupancy.pgm").read_bytes().split(b"\n", 3)[3]
                self.assertIn(205, pixels)
                self.assertNotIn(254, pixels)
                reloaded = store.reload(manifest["id"])
                self.assertEqual(
                    reloaded.descriptor.sha256,
                    hashlib.sha256((output / "map.pcd").read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    store.get(manifest["id"])["revision"], manifest["revision"]
                )
                report = dict(
                    classification="SYNTHETIC actual core/storage; HTTP/UI NOT_RUN in this check",
                    c1_sha=C1_SHA,
                    c2_inspected_sha=C2_INSPECTED_SHA,
                    input_hashes=before,
                    output_hashes=manifest["output_hashes"],
                    point_count=count,
                    proposal_state=status["state"],
                    review_revision=reviewed["proposal_revision"],
                    operational_installed=manifest["operational_installed"],
                    full_record_xyz_normal_scalar_checks="PASS",
                    stale_revision_rejected=True,
                    source_hashes_preserved=True,
                )
                if os.environ.get("D1_ROUND2_REPORT"):
                    Path(os.environ["D1_ROUND2_REPORT"]).write_text(
                        json.dumps(report, indent=2) + "\n"
                    )
                print(json.dumps(report, sort_keys=True))
            finally:
                manager.close()
