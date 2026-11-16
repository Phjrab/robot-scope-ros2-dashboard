"""Local composed endpoints use the real existing engines and immutable stores."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np

from robot_dashboard.expansion_contracts import MapSourceDescriptor
from robot_dashboard.expansion_contracts.fixtures import request
from robot_dashboard.offline_slam.workbench import create_app
from robot_dashboard.pcd_editing.store import _digest
from tests.expansion_services.http_client import TestClient


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app = create_app(self.root, synthetic_demo=True)
        self.client = TestClient(self.app).__enter__()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_both_modes_and_source_preview(self):
        page = self.client.get("/extensions")
        self.assertEqual(page.status_code, 200)
        self.assertIn("analysis_local", page.text)
        self.assertEqual(self.client.get("/analysis/").status_code, 200)
        self.assertEqual(
            self.client.get("/analysis/api/sessions").json()["sessions"], []
        )
        sources = self.client.get("/api/v1/extensions/multimap/sources").json()[
            "sources"
        ]
        self.assertEqual(len(sources), 2)
        for source in sources:
            preview = self.client.get(
                f"/api/v1/extensions/multimap/sources/{source['map_id']}/preview"
            ).json()["preview"]
            self.assertLessEqual(len(preview["points"]), 900)
            self.assertEqual(preview["input_pin"]["sha256"], source["sha256"])

    def test_host_and_origin_protect_both_modes(self):
        for path in ["/analysis/api/sessions", "/api/v1/extensions/multimap/jobs"]:
            denied = self.client.post(
                path, content=b"", headers={"Origin": "https://untrusted.invalid"}
            )
            self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            self.client.get(
                "/extensions", headers={"Host": "untrusted.invalid"}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/status").status_code, 404)

    def test_real_merge_review_export_preserves_sources(self):
        prefix = "/api/v1/extensions/multimap"

        def post(path, **kwargs):
            return self.client.post(
                path, headers={"Origin": "http://127.0.0.1"}, **kwargs
            )

        sources = [
            MapSourceDescriptor.from_dict(d)
            for d in self.client.get(prefix + "/sources").json()["sources"]
        ]
        before = {p.name: _digest(p) for p in self.root.glob("*.pcd")}
        req = replace(
            request(sources),
            options={"voxel_size": 0.05},
            mode="seeded",
            initial_guesses=[
                {
                    "source_key": sources[1].key,
                    "T_anchor_source": np.eye(4).ravel().tolist(),
                }
            ],
        )
        response = post(prefix + "/jobs", json=req.to_dict())
        self.assertEqual(response.status_code, 202, response.text)
        url = prefix + "/jobs/" + response.json()["job_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = self.client.get(url).json()
            if job["state"] not in {"QUEUED", "RUNNING"}:
                break
            time.sleep(0.05)
        self.assertEqual(job["state"], "SOLVED_CANDIDATE", job)
        response = post(
            url + "/review",
            json={
                "expected_proposal_revision": job["proposal_revision"],
                "accepted": True,
                "manual_selection": None,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        reviewed = response.json()
        response = post(
            url + "/exports",
            json={
                "name": "synthetic_merged",
                "expected_proposal_revision": reviewed["proposal_revision"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.get(url).json()["state"], "EXPORTED")
        self.assertEqual(len(self.client.get(prefix + "/exports").json()["exports"]), 1)
        reloaded = self.client.get(prefix + "/sources").json()["sources"]
        self.assertEqual(len(reloaded), 3)
        merged = next(d for d in reloaded if d["point_count"] == 2400)
        self.assertEqual(
            self.client.get(
                prefix + "/sources/" + merged["map_id"] + "/preview"
            ).status_code,
            200,
        )
        self.assertEqual(before, {p.name: _digest(p) for p in self.root.glob("*.pcd")})
        self.assertEqual(
            post(
                url + "/exports",
                json={
                    "name": "overwrite",
                    "expected_proposal_revision": reviewed["proposal_revision"],
                },
            ).status_code,
            409,
        )

    def test_manifest_cannot_escape_local_root(self):
        sources = self.client.get("/api/v1/extensions/multimap/sources").json()[
            "sources"
        ]
        (self.root / "sources.json").write_text(
            json.dumps([{"descriptor": sources[0], "file": "../outside.pcd"}]),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "INVALID_LOCAL_SOURCE"):
            create_app(self.root)


if __name__ == "__main__":
    unittest.main()
