"""SYNTHETIC ASGI contract checks, without httpx, ROS, cameras or drivers."""

import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

from fastapi import FastAPI

from robot_dashboard.api.routers.slam import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.competition import CompetitionConflict
from robot_dashboard.slam_packages import MapPackageStore
from robot_dashboard.slam_sessions import SlamError


class SyntheticCompetition:
    locked = False
    manual = True

    def require_unlocked(self, action):
        if self.locked:
            raise CompetitionConflict("synthetic competition lock")

    def require_manual_mode(self):
        if not self.manual:
            raise CompetitionConflict("synthetic manual mode required")


class SyntheticApiManager:
    def __init__(self, store):
        self.packages = store
        self.calls = []
        self.error = None
        self.adapters = {}
        self.frame_value = dict(schema_version=1, session_id="fixture-session", generation=1,
            map_epoch="fixture-epoch", provenance="synthetic_fixture",
            source_timestamp_ns="1792026000123456789", overlay={"points": []})

    def engines(self):
        return {"engines": [dict(engine_id="visual_stereo", available_now=False,
                                 blocked_reason="SYNTHETIC_FIXTURE") ]}

    def snapshot(self):
        return {"active_session": None, "generation": 0}

    def navigation_context(self):
        return {"operational_pose": {"source": "unchanged-lidar"}}

    async def _call(self, operation, *args, **kwargs):
        self.calls.append((operation, args, deepcopy(kwargs)))
        if self.error:
            raise self.error
        return dict(operation=operation, session_id="fixture-session", generation=kwargs.get("generation", 1))

    async def start(self, **kwargs):
        return await self._call("start", **kwargs)

    async def stop(self, *args, **kwargs):
        return await self._call("stop", *args, **kwargs)

    async def save(self, *args, **kwargs):
        return await self._call("save", *args, **kwargs)

    async def localize(self, *args, **kwargs):
        return await self._call("localize", *args, **kwargs)

    def job(self, identifier):
        raise SlamError("JOB_NOT_FOUND", 404)

    async def mutate_package(self, operation, package_id=None, **kwargs):
        self.calls.append((operation, (package_id,), deepcopy(kwargs)))
        method = getattr(self.packages, operation)
        return await asyncio.to_thread(method, **({"package_id": package_id, **kwargs} if package_id else kwargs))

    def frame(self):
        return deepcopy(self.frame_value)


class SlamApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = MapPackageStore(Path(self.temporary.name) / "managed", quiescence_seconds=0.001)
        self.manager = SyntheticApiManager(self.store)
        self.competition = SyntheticCompetition()
        self.runtime = ApplicationRuntime(competition=self.competition)
        self.runtime.slam = self.manager
        self.app = FastAPI()
        self.app.state.runtime = self.runtime
        self.app.include_router(router)

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def request(self, method, path, *, body=None, raw=None, headers=None):
        base, _, query = path.partition("?")
        values = {"host": "testserver", "origin": "http://testserver", "content-type": "application/json"}
        values.update(headers or {})
        payload = raw if raw is not None else json.dumps(body or {}).encode()
        queue = [dict(type="http.request", body=payload, more_body=False)]
        messages = []
        async def receive():
            return queue.pop(0) if queue else {"type": "http.disconnect"}
        async def send(message):
            messages.append(message)
        scope = dict(type="http", asgi={"version": "3.0", "spec_version": "2.4"},
            http_version="1.1", method=method, scheme="http", path=base,
            raw_path=base.encode(), query_string=query.encode(), root_path="",
            server=("testserver", 80), client=("127.0.0.1", 1000),
            headers=[(k.lower().encode(), v.encode()) for k, v in values.items() if v is not None])
        await self.app(scope, receive, send)
        start = next(m for m in messages if m["type"] == "http.response.start")
        content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return SimpleNamespace(status=start["status"], content=content, json=lambda: json.loads(content),
                               headers=dict(start["headers"]))

    async def publish(self, preview=None):
        staging = self.store.create_staging()
        (staging.native_path / "data.mdb").write_bytes(b"SYNTHETIC native fixture")
        return self.store.publish_staging(staging.token, official_save_completed=True,
            required_native_files=["data.mdb"], metadata={"name": "Fixture room",
                "engine_id": "visual_stereo", "data_provenance": "synthetic_fixture", "map_frame": "map"},
            preview=preview if preview is not None else {"points": [[1, 2, 3]], "coverage": "unknown"})

    def start_body(self, **changes):
        return dict(engine_id="visual_stereo", task="mapping", request_id="request-0001",
                    operator_confirmed=True) | changes

    async def test_reads_never_start_any_session_and_need_no_mutation_origin(self):
        for path in ("engines", "session", "navigation-context", "packages"):
            response = await self.request("GET", "/api/v1/slam/"+path, headers={"origin": None})
            self.assertEqual(response.status, 200, response.content)
        self.assertEqual(self.manager.calls, [])

    async def test_start_requires_same_origin_before_manager_mutation(self):
        for origin in (None, "http://attacker.example", "null", "http://testserver/path", "http://testserver:81"):
            with self.subTest(origin=origin):
                response = await self.request("POST", "/api/v1/slam/sessions",
                    body=self.start_body(), headers={"origin": origin})
                self.assertEqual(response.status, 403)
        self.assertEqual(self.manager.calls, [])
        response = await self.request("POST", "/api/v1/slam/sessions", body=self.start_body())
        self.assertEqual(response.status, 202)
        self.assertEqual(self.manager.calls[0][0], "start")

    async def test_engine_task_and_extra_runtime_injections_rejected_by_schema(self):
        changes = [dict(engine_id="shell"), dict(task="localize_saved"), dict(task="nav2_goal"),
            dict(topic="/arbitrary"), dict(argv=["rm", "-rf"]), dict(native_path="/tmp/native"),
            dict(container_image="unapproved"), dict(ros_domain_id=0), dict(operator_confirmed=1),
            dict(operator_confirmed="true")]
        for change in changes:
            with self.subTest(change=change):
                response = await self.request("POST", "/api/v1/slam/sessions", body=self.start_body(**change))
                self.assertEqual(response.status, 422, response.content)
        self.assertEqual(self.manager.calls, [])

    async def test_strict_generation_and_booleans_prevent_implicit_cleanup(self):
        for body in (dict(generation=True, request_id="stop-0001"),
                     dict(generation="1", request_id="stop-0001"),
                     dict(generation=1, request_id="stop-0001", discard_unsaved="true"),
                     dict(generation=1, request_id="stop-0001", arbitrary_path="/tmp")):
            response = await self.request("POST", "/api/v1/slam/sessions/fixture/stop", body=body)
            self.assertEqual(response.status, 422, response.content)
        self.assertEqual(self.manager.calls, [])

    async def test_competition_and_manual_gates_block_start_but_allow_exact_owner_cleanup(self):
        self.competition.locked = True
        response = await self.request("POST", "/api/v1/slam/sessions", body=self.start_body())
        self.assertEqual(response.status, 423)
        response = await self.request("POST", "/api/v1/slam/sessions/fixture/stop",
            body=dict(generation=1, request_id="stop-0001", discard_unsaved=True))
        self.assertEqual(response.status, 202)
        self.assertEqual(self.manager.calls[-1][0], "stop")
        self.competition.locked = False
        self.competition.manual = False
        response = await self.request("POST", "/api/v1/slam/sessions", body=self.start_body())
        self.assertEqual(response.status, 409)
        self.assertEqual(len(self.manager.calls), 1)

    async def test_mutation_domain_errors_are_path_free_and_keep_status_code(self):
        self.manager.error = SlamError("SESSION_GENERATION_CONFLICT", 409)
        response = await self.request("POST", "/api/v1/slam/sessions/fixture/stop",
            body=dict(generation=2, request_id="stop-0001"))
        self.assertEqual(response.status, 409)
        self.assertEqual(response.json(), {"detail": {"code": "SESSION_GENERATION_CONFLICT"}})
        self.assertNotIn(self.temporary.name, response.content.decode())
        response = await self.request("GET", "/api/v1/slam/jobs/missing")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.json()["detail"]["code"], "JOB_NOT_FOUND")

    async def test_native_package_preview_does_not_launch_and_unknown_compatibility_is_blocked(self):
        package = await self.publish()
        listing = await self.request("GET", "/api/v1/slam/packages")
        self.assertEqual(listing.status, 200)
        self.assertEqual(listing.json()["packages"][0]["compatibility"]["status"], "blocked")
        response = await self.request("GET", f'/api/v1/slam/packages/{package["id"]}/preview')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["points"], [[1, 2, 3]])
        self.assertEqual(self.manager.calls, [])

    async def test_resource_conflict_explains_resource_without_forwarding_private_details(self):
        self.manager.error = SlamError("RESOURCE_CONFLICT", resources=[
            {"resource": "camera", "reason": "device_busy"},
            {"resource": "camera", "reason": "/private/device/path"},
            {"resource": ["camera"], "reason": "device_busy"},
            {"resource": "camera", "reason": "device_busy", "owner": "/private/process"},
        ])
        response = await self.request("POST", "/api/v1/slam/sessions", body=self.start_body())
        self.assertEqual(response.status, 409)
        self.assertEqual(response.json(), {"detail": {"code": "RESOURCE_CONFLICT",
            "resources": [{"resource": "camera", "reason": "device_busy"}]}})

    async def test_map_ids_revisions_and_names_cannot_supply_native_paths(self):
        package = await self.publish()
        response = await self.request("GET", "/api/v1/slam/packages/not-an-opaque-id")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.json()["detail"]["code"], "PACKAGE_NOT_FOUND")
        response = await self.request("POST", f'/api/v1/slam/packages/{package["id"]}/rename',
            body=dict(name="Renamed", expected_revision="bad"))
        self.assertEqual(response.status, 422)
        response = await self.request("POST", f'/api/v1/slam/packages/{package["id"]}/rename',
            body=dict(name="Renamed", expected_revision=package["revision"], native_path="/tmp/private"))
        self.assertEqual(response.status, 422)
        response = await self.request("POST", "/api/v1/slam/sessions/fixture/localize", body=dict(
            generation=1, request_id="localize-0001", package_id="/tmp/database",
            revision=package["revision"], hint={}))
        self.assertEqual(response.status, 422)
        self.assertEqual(self.manager.calls, [])

    async def test_rename_revision_conflict_is_409_and_identity_is_preserved(self):
        package = await self.publish()
        path = f'/api/v1/slam/packages/{package["id"]}/rename'
        body = dict(name="Renamed fixture", expected_revision=package["revision"])
        response = await self.request("POST", path, body=body)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["id"], package["id"])
        self.assertEqual(response.json()["native_content_revision"], package["native_content_revision"])
        response = await self.request("POST", path, body=body)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.json()["detail"]["code"], "REVISION_CONFLICT")

    async def test_import_is_bounded_and_invalid_archive_does_not_start_an_engine(self):
        self.store.max_archive_bytes = 16
        response = await self.request("POST", "/api/v1/slam/packages/import", raw=b"x"*17)
        self.assertEqual(response.status, 413)
        self.assertEqual(self.manager.calls, [])
        self.store.max_archive_bytes = 1024
        response = await self.request("POST", "/api/v1/slam/packages/import", raw=b"invalid archive")
        self.assertEqual(response.status, 422)
        self.assertEqual(self.store.list_packages(), [])
        self.assertFalse(any(call[0] == "start" for call in self.manager.calls))

    async def test_export_requires_revision_and_streams_native_bundle_without_runtime(self):
        package = await self.publish()
        path = f'/api/v1/slam/packages/{package["id"]}/export'
        response = await self.request("GET", path)
        self.assertEqual(response.status, 422)
        response = await self.request("GET", path+"?expected_revision="+package["revision"])
        self.assertEqual(response.status, 200)
        self.assertTrue(response.content.startswith(b"PK"))
        self.assertEqual(self.manager.calls, [])

    async def test_saved_preview_export_requires_revision_and_does_not_launch_runtime(self):
        package = await self.publish(preview=dict(frame_id="map", map_epoch="fixture-epoch",
            global_map=dict(points=[[1, 2, 3]], coordinate_frame="map", map_epoch="fixture-epoch",
                            coverage="unknown", source_timestamp_ns="1792144977080785000")))
        path = f'/api/v1/slam/packages/{package["id"]}/preview-export'
        self.assertEqual((await self.request("GET", path)).status, 422)
        self.assertEqual((await self.request("GET", path+"?expected_revision="+"0"*64)).status, 409)
        self.competition.locked = True
        response = await self.request("GET", path+"?expected_revision="+package["revision"], headers={"origin": None})
        self.assertEqual(response.status, 200, response.content)
        self.assertEqual(response.headers[b"content-type"], b"application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(archive.read("global-map.xyz"), b"1 2 3\n")
            self.assertFalse(json.loads(archive.read("provenance.json"))["native_full_map_export"])
        self.assertEqual(self.manager.calls, [])

    async def websocket_messages(self, origin="http://testserver"):
        headers = [(b"host", b"testserver")]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        queue = [dict(type="websocket.connect"), dict(type="websocket.disconnect", code=1000)]
        sent = []
        async def receive():
            return queue.pop(0)
        async def send(value):
            sent.append(value)
        await self.app(dict(type="websocket", asgi={"version": "3.0"}, scheme="ws",
            path="/api/v1/ws/slam", raw_path=b"/api/v1/ws/slam", query_string=b"", root_path="",
            server=("testserver", 80), client=("127.0.0.1", 1000), headers=headers,
            subprotocols=[]), receive, send)
        return sent

    async def test_websocket_denies_cross_origin_before_accepting(self):
        for origin in (None, "http://foreign"):
            with self.subTest(origin=origin):
                messages = await self.websocket_messages(origin)
                self.assertEqual(messages, [dict(type="websocket.close", code=4403, reason="")])
        self.assertEqual(self.manager.calls, [])

    async def test_websocket_preserves_64bit_stamp_string_and_uses_shared_read_only_frame(self):
        messages = await self.websocket_messages()
        frames = [json.loads(m["text"]) for m in messages if m["type"] == "websocket.send"]
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["source_timestamp_ns"], "1792026000123456789")
        self.assertEqual(frames[0]["provenance"], "synthetic_fixture")
        self.assertEqual(self.manager.calls, [])

    async def test_websocket_rejects_oversized_or_nonfinite_source_before_sending_frame(self):
        for value in ({"payload": "x" * (8 * 1024**2)}, {"invalid": float("nan")}):
            with self.subTest(oversized="payload" in value):
                self.manager.frame_value = value
                messages = await self.websocket_messages()
                self.assertFalse(any(m["type"] == "websocket.send" for m in messages))


if __name__ == "__main__":
    unittest.main()
