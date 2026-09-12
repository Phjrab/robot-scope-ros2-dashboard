import asyncio
import json
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI

from robot_dashboard.api.routers.navigation_presets import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.navigation_jobs import NavigationJobManager, NavigationParameterError, SAFE_TUNED_PARAMETERS
from robot_dashboard.navigation_presets import NavigationPresetStore, PresetConflict, PresetInvalid, PresetUnavailable


class LocalASGIClient:
    """Exercise real routing/validation without a server, ROS or optional HTTP clients."""

    def __init__(self, app):
        self.app = app

    def request(self, method, path, body=None, headers=None):
        async def run():
            messages = []
            async def receive():
                return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b"", "more_body": False}
            async def send(message):
                messages.append(message)
            request_headers = {"host": "testserver", "origin": "http://testserver", "content-type": "application/json", **{k.lower(): v for k, v in (headers or {}).items()}}
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": [(k.encode(), v.encode()) for k, v in request_headers.items()], "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
            await self.app(scope, receive, send)
            status = next(m["status"] for m in messages if m["type"] == "http.response.start")
            text = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body").decode()
            return SimpleNamespace(status_code=status, text=text, json=lambda: json.loads(text))
        return asyncio.run(run())

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, json, headers=None):
        return self.request("POST", path, json, headers)


class NavigationPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.new_store()
        self.values = dict(SAFE_TUNED_PARAMETERS)

    def new_store(self):
        return NavigationPresetStore(self.root, NavigationJobManager._validate_parameter_set)

    def test_persists_full_values_across_instances_with_private_permissions(self):
        self.assertEqual(self.store.snapshot(), {"presets": []})
        saved = self.store.create(" 복도 · 팀 A ", self.values)
        self.assertEqual(saved["preset"]["label"], "복도 · 팀 A")
        self.assertEqual(saved["preset"]["values"], self.values)
        self.assertEqual(self.new_store().snapshot()["presets"], saved["presets"])
        self.assertEqual(stat.S_IMODE((self.root / "presets.json").stat().st_mode), 0o600)

    def test_duplicate_normalized_name_does_not_overwrite(self):
        self.store.create("팀 A", self.values)
        before = (self.root / "presets.json").read_bytes()
        with self.assertRaises(PresetConflict):
            self.store.create(" 팀 a ", {**self.values, "desired_linear_vel": 0.5})
        self.assertEqual((self.root / "presets.json").read_bytes(), before)

    def test_invalid_names_and_parameter_sets_never_write(self):
        for name in (" ", "a" * 65, "a\nb", "a\x00b"):
            with self.subTest(name=repr(name)), self.assertRaises(PresetInvalid):
                self.store.create(name, self.values)
        for values in ({}, {**self.values, "desired_linear_vel": 1.1}, {**self.values, "desired_linear_vel": float("nan")}, {**self.values, "enable_stamped_cmd_vel": True}, {**self.values, "inflation_radius": 0.1}):
            with self.subTest(values=values), self.assertRaises(NavigationParameterError):
                self.store.create("test", values)
        self.assertFalse((self.root / "presets.json").exists())

    def test_concurrent_creates_do_not_lose_presets(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.new_store().create(f"team {i}", self.values), range(12)))
        self.assertEqual(len(self.store.snapshot()["presets"]), 12)

    def test_concurrent_duplicate_only_creates_once(self):
        def create(_):
            try:
                self.new_store().create("same", self.values)
                return True
            except PresetConflict:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(create, range(8))), 1)

    def test_store_limits_and_corruption_fail_closed(self):
        self.store.create("one", self.values)
        with patch.object(self.store, "MAX_PRESETS", 1), self.assertRaises(PresetConflict):
            self.store.create("two", self.values)
        for content in (b"bad", b"{}", b"x" * (self.store.MAX_BYTES + 1)):
            (self.root / "presets.json").write_bytes(content)
            with self.assertRaises(PresetUnavailable):
                self.store.snapshot()
            with self.assertRaises(PresetUnavailable):
                self.store.create("two", self.values)
            self.assertEqual((self.root / "presets.json").read_bytes(), content)

    def test_symlink_not_read_or_overwritten(self):
        target = self.root / "other"
        target.write_text("private")
        (self.root / "presets.json").symlink_to(target)
        with self.assertRaises(PresetUnavailable):
            self.store.create("one", self.values)
        self.assertEqual(target.read_text(), "private")

    def test_atomic_replace_failure_keeps_previous_catalog(self):
        self.store.create("one", self.values)
        before = (self.root / "presets.json").read_bytes()
        with patch("robot_dashboard.navigation_presets.os.replace", side_effect=OSError("disk")), self.assertRaises(PresetUnavailable):
            self.store.create("two", self.values)
        self.assertEqual((self.root / "presets.json").read_bytes(), before)
        self.assertEqual(list(self.root.glob(".presets-*")), [])

    def test_manager_catalog_does_not_apply_parameters_or_touch_pipeline(self):
        # Bind only catalog methods: a call to any other manager method fails.
        manager = object.__new__(NavigationJobManager)
        manager.runtime_dir = self.root
        with patch.object(manager, "_materialize_parameters", side_effect=AssertionError("must not apply")):
            manager.create_preset("running-safe-save", self.values)
            self.assertEqual(len(manager.saved_presets()["presets"]), 1)
        self.assertFalse((self.root / "nav2_params.generated.yaml").exists())

    def client(self):
        manager = object.__new__(NavigationJobManager)
        manager.runtime_dir = self.root
        app = FastAPI()
        app.include_router(router)
        app.state.runtime = ApplicationRuntime(navigation=manager)
        return LocalASGIClient(app)

    def test_api_create_list_duplicate_and_origin_guard(self):
        client = self.client()
        path = "/api/v1/navigation/presets"
        body = {"name": "팀 공용", "values": self.values}
        self.assertEqual(client.post(path, json=body, headers={"Origin": "http://evil.test"}).status_code, 403)
        response = client.post(path, json=body, headers={"Origin": "http://testserver"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(client.get(path).json()["presets"], response.json()["presets"])
        self.assertEqual(client.post(path, json=body).status_code, 409)

    def test_api_rejects_bad_values_extra_fields_and_sanitizes_storage_error(self):
        client = self.client()
        path = "/api/v1/navigation/presets"
        for body in ({"name": " ", "values": self.values}, {"name": "one", "values": {}}, {"name": "one", "values": self.values, "path": "/tmp/test"}, {"name": "one", "values": {**self.values, "desired_linear_vel": 5}}):
            self.assertEqual(client.post(path, json=body).status_code, 422)
        (self.root / "presets.json").write_text(json.dumps({"version": 1, "presets": ["bad"]}))
        response = client.get(path)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.root), response.text)
