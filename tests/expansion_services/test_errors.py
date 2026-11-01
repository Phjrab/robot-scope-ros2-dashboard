"""Actual C1 router/worker/storage; fixture solver is plumbing, never alignment."""

from contextlib import asynccontextmanager
from dataclasses import replace
import tempfile
import unittest

from fastapi import FastAPI, HTTPException, Request

from robot_dashboard.expansion_services.catalogue import Conflict
from robot_dashboard.expansion_services.router import create_router
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from tests.expansion_c1.test_services import Rig
from tests.expansion_services.http_client import TestClient


class ErrorPropagationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rig = Rig(self.temp.name)
        self.auth = {
            "Authorization": "Bearer public-error-contract-test-only",
            "Origin": "http://127.0.0.1",
        }

        def authorize(request: Request):
            if request.headers.get("authorization") != self.auth["Authorization"]:
                raise HTTPException(401)

        def origin(request: Request):
            if request.headers.get("origin") != self.auth["Origin"]:
                raise HTTPException(403)

        @asynccontextmanager
        async def lifespan(app):
            try:
                yield
            finally:
                self.rig.manager.close()

        app = FastAPI(lifespan=lifespan)
        app.include_router(
            create_router(
                self.rig.manager,
                self.rig.catalogue,
                SceneSnapshotService(
                    {"map_id": "a" * 24, "revision": "b" * 64, "generation": 0}
                ),
                self.rig.store,
                authorize=authorize,
                require_origin=origin,
            )
        )
        self.client = TestClient(app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def post(self, path, value):
        return self.client.post(
            "/api/v1/extensions/multimap/" + path, json=value, headers=self.auth
        )

    def check(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        value = response.json()
        self.assertEqual(value["error"]["code"], code)
        self.assertIsInstance(value["detail"], str)
        self.assertEqual(value["detail"], value["error"]["message"])
        for secret in (
            self.temp.name,
            "secret-marker",
            "Traceback",
            self.auth["Authorization"],
        ):
            self.assertNotIn(secret, response.text)
        return value

    def test_reloaded_ancestry_overlap_reaches_http_without_acceptance(self):
        r = self.rig
        job = r.solve_review()
        saved = r.manager.export(job["job_id"], "first", job["proposal_revision"])
        merged = r.store.reload(saved["id"])
        r.resolved[merged.descriptor.map_id] = merged
        from robot_dashboard.expansion_contracts.fixtures import request

        req = request(
            [merged.descriptor, r.resolved[f"{1:024x}"].descriptor], "overlap"
        )
        with self.assertRaisesRegex(Conflict, "duplicate ancestor"):
            r.catalogue.pinned(req)
        before = len(r.manager._jobs)
        error = self.check(self.post("jobs", req.to_dict()), 409, "ANCESTRY_OVERLAP")
        self.assertIn("share original sources", error["detail"])
        self.assertEqual(len(r.manager._jobs), before)
        self.assertEqual(len(r.store.list()), 1)

    def test_source_revision_and_identity_are_distinct(self):
        r = self.rig
        old = r.request()
        source = r.resolved[f"{1:024x}"]
        r.resolved[source.descriptor.map_id] = replace(
            source,
            descriptor=replace(source.descriptor, revision="c" * 64),
            asset=replace(source.asset, revision="c" * 64),
        )
        self.check(self.post("jobs", old.to_dict()), 409, "STALE_SOURCE_REVISION")
        r.resolved[source.descriptor.map_id] = replace(
            source, asset=replace(source.asset, frame_id="wrong")
        )
        self.check(self.post("jobs", old.to_dict()), 409, "SOURCE_IDENTITY_MISMATCH")
        # Envelope endpoints must retain the HTTP error status, not wrap it in 200.
        self.check(
            self.client.get("/api/v1/extensions/multimap/sources", headers=self.auth),
            409,
            "SOURCE_IDENTITY_MISMATCH",
        )

    def test_source_content_drift_stays_rejected(self):
        r = self.rig
        req = r.request()
        source = r.resolved[f"{1:024x}"]
        with source.asset.path.open("ab") as f:
            f.write(b"changed")
        self.check(self.post("jobs", req.to_dict()), 409, "SOURCE_CONTENT_CHANGED")

    def test_stale_proposal_and_general_request_conflict_are_distinct(self):
        r = self.rig
        req = r.request()
        job = r.solve_review(req)
        self.check(
            self.post(
                f"jobs/{job['job_id']}/review",
                dict(
                    expected_proposal_revision=1, accepted=True, manual_selection=None
                ),
            ),
            409,
            "STALE_PROPOSAL_REVISION",
        )
        self.check(
            self.post(
                f"jobs/{job['job_id']}/exports",
                dict(expected_proposal_revision=1, name="stale"),
            ),
            409,
            "STALE_PROPOSAL_REVISION",
        )
        changed = replace(req, anchor_source_key=r.resolved[f"{2:024x}"].descriptor.key)
        self.check(self.post("jobs", changed.to_dict()), 409, "REQUEST_CONFLICT")

    def test_invalid_ancestry_is_not_reported_as_stale(self):
        r = self.rig
        source = r.resolved[f"{1:024x}"]
        r.resolved[source.descriptor.map_id] = replace(
            source, lineage={source.descriptor.key: [source.descriptor.key]}
        )
        self.check(self.post("jobs", r.request().to_dict()), 409, "INVALID_PROVENANCE")

    def test_private_io_and_unexpected_errors_have_safe_messages(self):
        r = self.rig
        for exception, status, code in (
            (
                PermissionError(self.temp.name + "/secret-marker"),
                503,
                "STORAGE_UNAVAILABLE",
            ),
            (RuntimeError("secret-marker Traceback"), 500, "INTERNAL_ERROR"),
            (KeyError("secret-marker"), 404, "NOT_FOUND"),
            (TypeError("secret-marker"), 422, "INVALID_CONTRACT"),
        ):

            def fail(*args):
                raise exception

            r.catalogue.resolver = (
                fail  # Explicit I/O/error injection at the trusted boundary.
            )
            self.check(
                self.client.get(
                    "/api/v1/extensions/multimap/sources", headers=self.auth
                ),
                status,
                code,
            )
            self.check(
                self.client.get(
                    f"/api/v1/extensions/multimap/sources/{1:024x}/preview",
                    headers=self.auth,
                ),
                status,
                code,
            )
        self.check(
            self.client.get(
                "/api/v1/extensions/scene/assets/missing/revision", headers=self.auth
            ),
            404,
            "NOT_FOUND",
        )

    def test_async_job_error_has_safe_code_without_changing_status_protocol(self):
        r = self.rig
        for i, exception in enumerate(
            (
                RuntimeError("secret-marker Traceback"),
                PermissionError(self.temp.name + "/secret-marker"),
                Conflict("secret-marker", code="SOURCE_IDENTITY_MISMATCH"),
            )
        ):

            def fail(*args, **kwargs):
                raise exception

            r.manager.solver = fail  # Fault injection, explicitly not an actual D1 run.
            response = self.post("jobs", r.request(request_id=f"fault-{i}").to_dict())
            self.assertEqual(response.status_code, 202)
            job = r.wait(response.json()["job_id"])
            self.assertEqual(job["state"], "FAILED")
            response = self.client.get(
                f"/api/v1/extensions/multimap/jobs/{job['job_id']}", headers=self.auth
            )
            self.assertEqual(response.status_code, 200)
            value = response.json()
            self.assertEqual(value["error"], type(exception).__name__)
            self.assertEqual(
                value["error_detail"]["code"],
                ("JOB_FAILED", "STORAGE_UNAVAILABLE", "SOURCE_IDENTITY_MISMATCH")[i],
            )
            self.assertIsNone(value["proposal"])
            self.assertNotIn("secret-marker", response.text)
            self.assertNotIn(self.temp.name, response.text)

    def test_auth_origin_and_request_body_policies_unchanged(self):
        req = self.rig.request().to_dict()
        self.assertEqual(
            self.client.post("/api/v1/extensions/multimap/jobs", json=req).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/extensions/multimap/jobs",
                json=req,
                headers={"Authorization": self.auth["Authorization"]},
            ).status_code,
            403,
        )
        self.assertEqual(self.post("jobs", {}).status_code, 422)
        response = self.client.post(
            "/api/v1/extensions/multimap/jobs",
            content=b"x" * (128 * 1024 + 1),
            headers={**self.auth, "Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self.rig.manager._jobs)

    def test_closed_worker_retains_busy_http_status(self):
        self.rig.manager.close()
        self.check(self.post("jobs", self.rig.request().to_dict()), 429, "SERVICE_BUSY")

    def test_explicit_host_policy_exception_retains_status_and_headers(self):
        def denied(*args):
            raise HTTPException(
                403, "host policy denied", headers={"X-Host-Policy": "denied"}
            )

        self.rig.catalogue.resolver = denied
        response = self.client.get(
            "/api/v1/extensions/multimap/sources", headers=self.auth
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["X-Host-Policy"], "denied")
        self.assertEqual(response.json(), {"detail": "host policy denied"})
