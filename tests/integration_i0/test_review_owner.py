"""Exercise the configured product bootstrap over an ephemeral local TLS server."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import os
import ssl
import threading
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException

from robot_dashboard.expansion_contracts import FusionRequest
from robot_dashboard.expansion_integration.bootstrap import configure_expansion
from robot_dashboard.expansion_integration.catalogue import compose_maps
from robot_dashboard.expansion_integration.review_access import AccessUnavailable, ReviewAccess
from robot_dashboard.expansion_integration.review_owner import API, COOKIE, ReviewInputs, qualified_context
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
        self.now = 10000
        self.db = self.root / "access.sqlite3"
        self.store = ReviewAccess(self.db, clock=lambda: self.now)
        self.store.initialize()
        self.origin = "https://review.example"
        self.env = {"ROBOT_SCOPE_EXPANSION_MULTIMAP": "1", "ROBOT_SCOPE_EXPANSION_SCENE": "1",
                    "ROBOT_SCOPE_EXPANSION_REVIEW_DB": str(self.db),
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
        with patch("robot_dashboard.expansion_integration.review_owner.ReviewAccess", return_value=self.store):
            configure_expansion(app, self.env, review_inputs=ports)
        self.client = TestClient(app, self.origin, tls=self.tls)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def login(self, role="read", ttl=90):
        grant, code = self.store.issue(role, ttl)
        response = self.client.post(API + "/session", json=code, headers={"Origin": self.origin})
        self.assertEqual(response.status_code, 200, response.text)
        cookie = response.headers["Set-Cookie"]
        for part in (COOKIE, "Secure", "HttpOnly", "SameSite=strict", "Path=" + API):
            self.assertIn(part, cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertNotIn(code, response.text + cookie)
        return grant, code, {"Origin": self.origin, "Cookie": cookie.split(";")[0]}

    def test_session_role_revocation_expiry_and_logout(self):
        routes = ["/multimap/sources", "/scene/context", "/scene/snapshot", "/scene/assets/x/y"]
        for path in routes:
            response = self.client.get(API + path, headers={"x-i0-synthetic-fixture":"local-test-only"})
            self.assertEqual(response.status_code, 401)
            self.assertIn("no-store", response.headers["Cache-Control"])
        grant, code, headers = self.login()
        self.assertEqual(self.client.get(API + "/session", headers=headers).json()["role"], "read")
        self.assertEqual(self.client.post(API + "/session", json=code, headers=headers).status_code, 401)
        self.assertEqual(self.client.get(API + "/multimap/sources", headers=headers).status_code, 200)
        for path in ("/jobs", "/jobs/x/cancel", "/jobs/x/review", "/jobs/x/exports"):
            self.assertEqual(self.client.post(API + "/multimap" + path, json={}, headers=headers).status_code, 403)
        self.assertFalse((self.root / "bundles").exists())
        self.store.revoke(grant)
        self.assertEqual(self.client.get(API + "/scene/context", headers=headers).status_code, 401)
        _, _, short = self.login(ttl=5)
        self.now += 5
        self.assertEqual(self.client.get(API + "/scene/context", headers=short).status_code, 401)
        _, _, active = self.login()
        response = self.client.post(API + "/session/logout", headers=active)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
        self.assertEqual(self.client.get(API + "/multimap/sources", headers=active).status_code, 401)

    def test_origin_storage_failure_and_single_redemption(self):
        _, code = self.store.issue("review", 5)
        for origin in ("http://review.example", "https://elsewhere.example", ""):
            self.assertEqual(self.client.post(API + "/session", json=code, headers={"Origin": origin}).status_code, 403)
        self.assertEqual(self.client.get(API + "/session?code=" + code).status_code, 401)
        self.assertEqual(self.client.post(API + "/session", json="x"*257,
                                         headers={"Origin": self.origin}).status_code, 413)
        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = list(workers.map(lambda _: self.client.post(API + "/session", json=code,
                                    headers={"Origin": self.origin}).status_code, range(2)))
        self.assertCountEqual(statuses, [200, 401])
        _, _, h = self.login("review")
        self.assertEqual(self.client.post(API + "/multimap/jobs", json={},
                                         headers={**h, "Origin": "https://wrong.example"}).status_code, 403)
        os.chmod(self.db, 0o644)
        result = self.client.get(API + "/session", headers=h)
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(str(self.root), result.text)
        self.assertIn("no-store", result.headers["Cache-Control"])
        os.chmod(self.db, 0o600)
        alias = self.root / "alias"
        alias.symlink_to(self.db)
        with self.assertRaises(AccessUnavailable):
            ReviewAccess(alias).issue("review", 10)

    def test_revoked_session_cannot_dispatch_after_slow_request_body(self):
        _, _, headers = self.login("review")
        # Pause the real TLS body after the initial authorization checks.
        checked = threading.Event()
        lookup = self.store.lookup
        calls = []

        def observe(session):
            grant = lookup(session)
            calls.append(bool(grant))
            if len(calls) >= 2:
                checked.set()
            return grant

        address = urlsplit(self.client.url)
        conn = http.client.HTTPSConnection(address.hostname, address.port,
            context=ssl.create_default_context(cafile=self.tls[0]), timeout=5)
        self.addCleanup(conn.close)
        with patch.object(self.store, "lookup", side_effect=observe):
            conn.putrequest("POST", API + "/multimap/jobs/x/cancel", skip_host=True)
            for key, value in {**headers, "Host":"review.example", "Content-Length":"2",
                               "Content-Type":"application/json"}.items():
                conn.putheader(key, value)
            conn.endheaders(b"{")
            self.assertTrue(checked.wait(2))
            self.assertEqual(self.client.post(API + "/session/logout", headers=headers).status_code, 200)
            conn.send(b"}")
            response = conn.getresponse()
            self.assertEqual(response.status, 401, response.read())

    def test_http_cannot_redeem_with_spoofed_forwarded_scheme(self):
        app = FastAPI()
        configure_expansion(app, self.env)
        _, code = self.store.issue("read", 30)
        with TestClient(app, self.origin) as client:
            response = client.post(API + "/session", json=code, headers={
                "Origin": self.origin, "X-Forwarded-Proto":"https"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("set-cookie", response.headers)

    def test_missing_map_factory_leaves_scene_readable(self):
        def unavailable():
            raise FileNotFoundError("private source directory")
        app = FastAPI()
        # Use a grant on the actual system clock of this separate app instance.
        access = ReviewAccess(self.db)
        _, code = access.issue("read", 90)
        inputs = ReviewInputs(maps_factory=unavailable, scene=self.scene, scene_context=lambda: self.ctx)
        with self.assertLogs("robot_dashboard.expansion_integration.review_owner", level="WARNING"):
            configure_expansion(app, self.env, review_inputs=inputs)
        with TestClient(app, self.origin, tls=self.tls) as client:
            response = client.post(API + "/session", json=code, headers={"Origin": self.origin})
            headers = {"Cookie": response.headers["Set-Cookie"].split(";")[0]}
            self.assertEqual(client.get(API + "/multimap/sources", headers=headers).status_code, 503)
            self.assertEqual(client.get(API + "/scene/snapshot", headers=headers).status_code, 200)

    def test_private_asset_context_fence_and_error_redaction(self):
        _, _, h = self.login()
        self.ctx["private_owner_note"] = "not-public"
        current = self.client.get(API + "/scene/context", headers=h)
        self.assertNotIn("private_owner_note", current.json())
        ref = self.scene.publish_asset("live_cloud", "recording", b"opaque")
        path = API + f"/scene/assets/{ref['id']}/{ref['revision']}"
        self.assertEqual(self.client.get(path).status_code, 401)
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

    def test_review_grant_full_source_save_and_stale_revision(self):
        _, _, h = self.login("review")
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
