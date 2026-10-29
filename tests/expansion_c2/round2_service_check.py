"""Actual pinned C1 HTTP/BundleStore + D1 core, synthetic inputs, no device.

Run with PYTHONPATH=<C1>:<D1>:<C2 experiment directory>, from outside repo root.
HTTP here uses ASGI TestClient; browser.e2e.mjs separately checks actual TCP.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

import numpy as np
from fastapi.testclient import TestClient
from exact_service_host import compose
from robot_dashboard.expansion_contracts import FusionRequest, canonical
from robot_dashboard.expansion_contracts.fixtures import request
from robot_dashboard.expansion_services.catalogue import Conflict
from robot_dashboard.multimap_core.solver import metrics


def main(output):
    report = {"classification": "ACTUAL_CORE + ASGI_HTTP + OFFLINE_BUNDLESTORE / SYNTHETIC",
              "robot_ros_native": "NOT_RUN", "checks": []}
    with tempfile.TemporaryDirectory(prefix="c2-round2-") as directory:
        c = compose(Path(directory), source_count=3, include_bundles=True)
        originals = list(c.resolved.values())
        before = {s.descriptor.map_id: hashlib.sha256(s.asset.path.read_bytes()).hexdigest() for s in originals}
        ids = [s.descriptor.map_id for s in originals]
        sequence = 0

        def wire(map_ids, poses):
            nonlocal sequence
            sequence += 1
            sources = [c.catalogue.resolve(i).descriptor for i in map_ids]
            return replace(request(), request_id=f"c2-round2-{sequence}",
                           sources=[s.to_dict() for s in sources],
                           anchor_source_key=sources[0].key,
                           source_pins={s.key: s.sha256 for s in sources},
                           initial_guesses=[dict(source_key=s.key, T_anchor_source=t.reshape(16).tolist()) for s, t in zip(sources, poses)],
                           correspondences=[], mode="seeded", options={}).to_dict()

        base = "/api/v1/extensions/multimap"
        with TestClient(c.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000),
                        headers={"Authorization": "Bearer public-c2-exact-synthetic-only-bearer", "Origin": "http://127.0.0.1"}) as http:
            def post(path, body, expected=200):
                r = http.post(base + path, json=body)
                assert r.status_code == expected, (path, r.status_code, r.text)
                return r.json()

            def solve(value):
                initial = post("/jobs", value, 202)
                for _ in range(400):
                    status = http.get(base + "/jobs/" + initial["job_id"]).json()
                    if status["state"] not in ("QUEUED", "RUNNING"):
                        break
                    time.sleep(.025)
                assert status["state"] == "SOLVED_CANDIDATE", status
                assert len(status["proposal"]["connected_components"]) == 1
                return status

            def save(status, name):
                job = status["job_id"]
                review_body = dict(expected_proposal_revision=status["proposal_revision"], accepted=True, manual_selection=None)
                reviewed = post(f"/jobs/{job}/review", review_body)
                duplicate = post(f"/jobs/{job}/review", review_body, 409)
                result = post(f"/jobs/{job}/exports", dict(name=name, expected_proposal_revision=reviewed["proposal_revision"]), 201)
                assert result["operational_installed"] is False
                assert result["id"] not in ids and result["id"] in c.catalogue.list_ids()
                assert c.store.get(result["id"]) == result
                assert hashlib.sha256(c.store.reload(result["id"]).asset.path.read_bytes()).hexdigest() == result["output_hashes"]["map.pcd"]
                return result, duplicate

            two_request = wire(ids[:2], c.poses[:2])
            two = solve(two_request)
            ab, duplicate = save(two, "AB")
            assert ab["point_count"] == 800
            report["checks"].append({"name": "2-map / explicit review-export / double apply CAS", "result": "PASS", "duplicate_http": duplicate})
            three = solve(wire(ids, c.poses))
            abc, _ = save(three, "ABC")
            assert abc["point_count"] == 1200
            report["checks"].append({"name": "3-map actual solve/export", "result": "PASS", "edges": len(three["proposal"]["pairwise_edges"])})
            incremental = solve(wire([ab["id"], ids[2]], [np.eye(4), c.poses[2]]))
            ab_c, _ = save(incremental, "AB_C")
            lineage = c.store.reload(ab_c["id"]).lineage
            assert ab_c["point_count"] == 1200 and ab_c["id"] not in (ab["id"], abc["id"])
            assert all(s.descriptor.key in lineage for s in originals)
            assert c.store.reload(ab["id"]).descriptor.key in lineage
            report["checks"].append({"name": "(A+B)+C full-source / new identity / all ancestry", "result": "PASS", "ancestry_nodes": len(lineage), "point_count": ab_c["point_count"]})
            bc, _ = save(solve(wire(ids[1:], [np.eye(4), np.linalg.inv(c.poses[1]) @ c.poses[2]])), "BC")
            overlap = wire([ab["id"], bc["id"]], [np.eye(4), c.poses[1]])
            try:
                c.catalogue.pinned(FusionRequest.from_dict(overlap))
                raise AssertionError("overlapping roots accepted")
            except Conflict as error:
                internal_reason = str(error)
            assert internal_reason == "duplicate ancestor across fusion inputs"
            conflict = post("/jobs", overlap, 409)
            report["checks"].append({"name": "(A+B)+(B+C) refusal without dedup", "result": "PASS", "private_reason": internal_reason, "http_detail": conflict["detail"], "precise_reason_over_http": "BLOCKED_C1_GENERIC_CONFLICT"})
            stale = solve(wire(ids[:2], c.poses[:2]))
            original = c.resolved[ids[0]]
            c.resolved[ids[0]] = replace(original, descriptor=replace(original.descriptor, revision="a"*64), asset=replace(original.asset, revision="a"*64))
            post(f"/jobs/{stale['job_id']}/review", dict(expected_proposal_revision=stale["proposal_revision"], accepted=True, manual_selection=None), 409)
            c.resolved[ids[0]] = original
            cancelled = post(f"/jobs/{stale['job_id']}/cancel", {})
            assert cancelled["state"] == "CANCELED"
            post(f"/jobs/{stale['job_id']}/review", dict(expected_proposal_revision=stale["proposal_revision"], accepted=True, manual_selection=None), 409)
            report["checks"].append({"name": "completed source-revision drift + cancelled candidate cannot apply", "result": "PASS"})
            assert before == {s.descriptor.map_id: hashlib.sha256(s.asset.path.read_bytes()).hexdigest() for s in originals}
            report["source_bytes_unchanged"] = True
            report["contract_example_sha256"] = hashlib.sha256(canonical(two_request)).hexdigest()
            report["contract_version"] = "0.1"
            # Real metrics with exact identity input, not a fabricated solver success.
            points = np.asarray(c.points[ids[0]]).reshape(-1, 3)
            zero = metrics(points, points, np.eye(4), .05)
            assert zero["rmse_m"] == 0.0
            zero.pop("residual_samples", None)
            report["zero_residual"] = {"classification": "ACTUAL_CORE_METRIC; not end-to-end zero-candidate ranking", "metrics": zero, "d1_ranking_fix": "NOT_AVAILABLE_AT_PINNED_HEAD"}
            report["ui_fixture"] = {"request": two_request, "proposal": two["proposal"], "zero_metrics": zero, "manifest": ab_c}
    Path(output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"checks": report["checks"], "source_bytes_unchanged": True, "zero_rmse": 0.0}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
