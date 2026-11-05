"""Exercise the configured product bootstrap over an ephemeral local TLS server."""
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from fastapi import FastAPI, HTTPException

from robot_dashboard.expansion_contracts import FusionRequest
from robot_dashboard.expansion_integration.bootstrap import configure_expansion
from robot_dashboard.expansion_integration.catalogue import compose_maps
from robot_dashboard.expansion_integration.review_owner import API, ReviewInputs, qualified_context
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from tests.expansion_services.http_client import TestClient
from .fixture import saved_sources


class ConfiguredReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.keys.cleanup)
        cert, key = (str(Path(cls.keys.name) / name) for name in ("cert.pem", "key.pem"))
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
                        "-keyout", key, "-out", cert], check=True, capture_output=True)
        cls.tls = cert, key

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.origin = "https://review.example"
        self.env = {"ROBOT_SCOPE_EXPANSION_MULTIMAP": "1", "ROBOT_SCOPE_EXPANSION_SCENE": "1",
                    "ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN": self.origin}
        self.ctx = dict(map_id="a"*24, revision="b"*64, generation=1, source_epoch="recording",
                        stream_epoch="test-stream", frame_id="sensor", clock_domain="recorder",
                        source_identity="offline-copy", calibration_id="test-calibration", units="m")
        self.scene = SceneSnapshotService({k:self.ctx[k] for k in ("map_id","revision","generation")},
                                         schema_version="0.2", stream_epoch=self.ctx["stream_epoch"])
        self.saved, self.qualified = saved_sources(self.root)
        ports = ReviewInputs(maps_factory=lambda: compose_maps(self.saved, self.qualified.get, self.root / "bundles"),
                             scene=self.scene, scene_context=lambda: self.ctx)
        app = FastAPI()
        configure_expansion(app, self.env, review_inputs=ports)
        self.client = TestClient(app, self.origin, tls=self.tls)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_direct_reads_without_login_database_or_cookies(self):
        for path in ("/multimap/sources", "/scene/context", "/scene/snapshot"):
            response = self.client.get(API + path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertNotIn("set-cookie", response.headers)
        self.assertFalse((self.root / "bundles").exists())
        self.assertEqual(self.client.get(API + "/session").status_code, 404)
        for path in ("/session", "/session/logout"):
            self.assertEqual(self.client.post(API + path, json={},
                headers={"Origin": self.origin}).status_code, 404)
        page = self.client.get("/extensions")
        self.assertNotIn('id="expansion-login"', page.text)
        self.assertNotIn('id="expansion-code"', page.text)
        self.assertNotIn("REVIEW_SESSION", page.text)

    def test_wrong_origin_host_and_missing_mutation_origin_are_rejected(self):
        for origin in ("http://review.example", "https://elsewhere.example", "null", ""):
            headers = {"Origin": origin}
            self.assertEqual(self.client.get(API + "/multimap/sources", headers=headers).status_code, 403)
            self.assertEqual(self.client.post(API + "/multimap/jobs", json={}, headers=headers).status_code, 403)
        self.assertEqual(self.client.post(API + "/multimap/jobs", json={}).status_code, 403)
        self.assertEqual(self.client.get(API + "/multimap/sources",
            headers={"Host": "elsewhere.example"}).status_code, 403)
        self.assertFalse((self.root / "bundles").exists())

    def test_http_cannot_read_with_spoofed_forwarded_scheme(self):
        app = FastAPI()
        configure_expansion(app, self.env)
        with TestClient(app, self.origin) as client:
            response = client.get(API + "/multimap/sources", headers={
                "Origin": self.origin, "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("set-cookie", response.headers)

    def test_legacy_database_configuration_is_unused(self):
        app = FastAPI()
        environment = {**self.env, "ROBOT_SCOPE_EXPANSION_REVIEW_DB": "/missing/old-access.sqlite3"}
        inputs = ReviewInputs(scene=self.scene, scene_context=lambda: self.ctx)
        configure_expansion(app, environment, review_inputs=inputs)
        with TestClient(app, self.origin, tls=self.tls) as client:
            self.assertEqual(client.get(API + "/scene/snapshot").status_code, 200)
            self.assertEqual(client.get(API + "/multimap/sources").status_code, 503)

    def test_missing_map_factory_leaves_scene_readable(self):
        def unavailable():
            raise FileNotFoundError("private source directory")
        app = FastAPI()
        inputs = ReviewInputs(maps_factory=unavailable, scene=self.scene, scene_context=lambda: self.ctx)
        with self.assertLogs("robot_dashboard.expansion_integration.review_owner", level="WARNING"):
            configure_expansion(app, self.env, review_inputs=inputs)
        with TestClient(app, self.origin, tls=self.tls) as client:
            self.assertEqual(client.get(API + "/multimap/sources").status_code, 503)
            self.assertEqual(client.get(API + "/scene/snapshot").status_code, 200)

    def test_private_asset_context_fence_and_error_redaction(self):
        h = {"Origin": self.origin}
        self.ctx["private_owner_note"] = "not-public"
        current = self.client.get(API + "/scene/context", headers=h)
        self.assertNotIn("private_owner_note", current.json())
        ref = self.scene.publish_asset("live_cloud", "recording", b"opaque")
        path = API + f"/scene/assets/{ref['id']}/{ref['revision']}"
        response = self.client.get(path, headers=h)
        self.assertEqual(response.content, b"opaque")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(self.client.get(path[:-1] + "x", headers=h).status_code, 404)
        attack = self.client.get(API + "/multimap/exports/%2e%2e", headers=h)
        self.assertIn(attack.status_code, (404, 422))
        self.assertNotIn(str(self.root), attack.text)
        self.ctx["generation"] += 1
        self.assertEqual(self.client.get(path, headers=h).status_code, 409)
        self.assertEqual(self.client.get(API + "/scene/snapshot", headers=h).status_code, 409)
        self.ctx.pop("source_identity")
        for route in (path, API + "/scene/context", API + "/scene/snapshot"):
            self.assertEqual(self.client.get(route, headers=h).status_code, 503)
        for key in qualified_context({**self.ctx, "source_identity":"explicit"}):
            missing = {**self.ctx, "source_identity":"explicit"}
            del missing[key]
            with self.subTest(key=key), self.assertRaises(HTTPException):
                qualified_context(missing)

    def test_direct_full_source_save_and_stale_revision(self):
        h = {"Origin": self.origin}
        base = API + "/multimap"
        def get(path):
            return self.client.get(base + path, headers=h)
        def post(path, value):
            return self.client.post(base + path, headers=h, json=value)
        sources = get("/sources").json()["sources"][:2]
        from robot_dashboard.expansion_contracts import MapSourceDescriptor
        descriptors = [MapSourceDescriptor.from_dict(s) for s in sources]
        key = descriptors[0].key
        request = FusionRequest(schema_version="0.1", evidence_kind="SYNTHETIC", producer="review-test",
            sequence=1, source_epoch="generated", request_id="review-test", anchor_source_key=key, sources=sources,
            source_pins={d.key:d.sha256 for d in descriptors}, initial_guesses=[], correspondences=[],
            mode="auto", options={})
        preview = get("/sources/" + sources[0]["map_id"] + "/preview").json()["preview"]
        self.assertIsNone(preview["input_pin"]["session_id"])
        mislabeled = post("/jobs", {**request.to_dict(), "evidence_kind":"REPLAY"})
        self.assertEqual(mislabeled.status_code, 409)
        self.assertEqual(mislabeled.json()["error"]["code"], "REVIEW_EVIDENCE_MISMATCH")
        created = post("/jobs", request.to_dict())
        self.assertEqual(created.status_code, 202, created.text)
        job = "/jobs/" + created.json()["job_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = get(job).json()
            if state["state"] not in ("RUNNING","QUEUED"):
                break
            time.sleep(.02)
        self.assertEqual(state["state"], "SOLVED_CANDIDATE")
        review = {"expected_proposal_revision":state["proposal_revision"], "accepted":True, "manual_selection":None}
        reviewed = post(job + "/review", review)
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(post(job + "/review", review).status_code, 409)
        saved = post(job + "/exports", {"name":"offline_checked",
                                        "expected_proposal_revision":reviewed.json()["proposal_revision"]})
        self.assertEqual(saved.status_code, 201, saved.text)
        manifest = get("/exports/" + saved.json()["id"]).json()
        self.assertEqual(manifest["point_count"], 800)
        self.assertFalse(manifest["operational_installed"])
        self.assertEqual(get("/exports").json()["exports"][0]["revision"], manifest["revision"])
        after = {row["map_id"]:row for row in get("/sources").json()["sources"]}
        self.assertTrue(all(after[s["map_id"]] == s for s in sources))
