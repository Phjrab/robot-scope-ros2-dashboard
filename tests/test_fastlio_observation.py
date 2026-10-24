"""Synthetic lifecycle and admission checks. No systemd/ROS/hardware calls."""

import copy
import importlib.util
import json
from types import SimpleNamespace
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI

from robot_dashboard.application.fastlio_observation import (
    FastlioObservationSession,
    ObservationSessionConflict,
)
from robot_dashboard.api.routers.fastlio_observation import router
from robot_dashboard.observation_service import (
    SERVICE,
    COMMANDS,
    ObservationService,
    ObservationServiceError,
    inputs_ready,
    parse_status,
)
from test_ownership_readback import idle_runtime
from robot_dashboard.application.ownership_readback import ownership_readback


def text_status(state="inactive", invocation="a" * 32, *, job="0"):
    return (
        f"Id={SERVICE}\nLoadState=loaded\nActiveState={state}\nInvocationID={invocation}\n"
        f"RuntimeMaxUSec=30min\nKillMode=control-group\nJob={job}\n"
        f"ActiveEnterTimestampMonotonic={int((time.monotonic() - 5) * 1e6)}\n"
    )


def inputs(now=None):
    now = time.monotonic() if now is None else now
    obs = dict(
        received_monotonic_s=now - 0.1,
        subscription_evidence={
            "graph": {
                "state": "ok",
                "endpoint_count": 1,
                "reported_publisher_count": 1,
                "observed_monotonic_s": now - 0.2,
            }
        },
    )
    return (
        dict(
            state="ok",
            topic="/Odometry",
            frame_id="camera_init",
            child_frame_id="body",
            observation=copy.deepcopy(obs),
        ),
        dict(
            topic="/cloud_registered",
            frame_id="camera_init",
            units="m",
            sent_points=5,
            observation=copy.deepcopy(obs),
        ),
    )


class ServiceTests(unittest.TestCase):
    def test_status_is_bounded_and_never_means_registered(self):
        value = parse_status(text_status("active"))
        self.assertEqual(value["state"], "WAITING_INPUTS")
        self.assertTrue(value["busy"])
        self.assertTrue(1790 < value["remaining_s"] <= 1800)
        self.assertTrue(parse_status(text_status(job="42 /org/job/42"))["busy"])
        self.assertEqual(parse_status("LoadState=not-found\n")["state"], "UNAVAILABLE")

    def test_reject_foreign_unbounded_or_unidentified_unit(self):
        text = text_status("active")
        for bad in [
            text.replace(SERVICE, "robot-scope.service"),
            text.replace("30min", "infinity"),
            text.replace("control-group", "process"),
            text.replace("a" * 32, ""),
            text.replace("ActiveState=active", "ActiveState=unknown"),
        ]:
            with self.assertRaises(ObservationServiceError):
                parse_status(bad)

    def test_only_fixed_commands_can_dispatch(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, ""))
        service = ObservationService(runner)
        service.dispatch("start")
        service.dispatch("stop")
        self.assertEqual(
            [call.args[0] for call in runner.call_args_list],
            [COMMANDS["start"], COMMANDS["stop"]],
        )
        with self.assertRaises(ObservationServiceError):
            service.dispatch("restart")
        runner.return_value.returncode = 1
        with self.assertRaises(ObservationServiceError):
            service.dispatch("start")

    def test_readiness_requires_this_run_fresh_frames_graph_and_nonempty_cloud(self):
        pose, cloud = inputs(100.0)
        self.assertTrue(inputs_ready(pose, cloud, 90.0, now=100.0))
        self.assertFalse(inputs_ready(pose, cloud, 99.95, now=100.0))
        self.assertFalse(inputs_ready(pose, cloud, 90.0, now=102.0))
        for target, key, value in [
            (pose, "topic", "/utlidar/robot_odom"),
            (pose, "state", "stale"),
            (cloud, "frame_id", "body"),
            (cloud, "sent_points", 0),
        ]:
            before = target[key]
            target[key] = value
            self.assertFalse(inputs_ready(pose, cloud, 90.0, now=100.0))
            target[key] = before
        cloud["observation"]["subscription_evidence"]["graph"]["endpoint_count"] = 2
        self.assertFalse(inputs_ready(pose, cloud, 90.0, now=100.0))


class FakeService:
    def __init__(self):
        self.state = "inactive"
        self.invocation = "a" * 32
        self.calls = []
        self.failure = False

    def status(self):
        if self.failure:
            raise OSError("unavailable")
        return parse_status(text_status(self.state, self.invocation))

    def dispatch(self, action):
        self.calls.append(action)
        self.state = "active" if action == "start" else "inactive"


def session_runtime():
    runtime = idle_runtime()
    runtime.lifecycle.control_bridge_snapshot = lambda: {
        "systemd": {"active_state": "inactive"}
    }
    runtime.lifecycle.require_idle = lambda: None
    runtime.agent.set_sources = Mock()
    runtime.agent.pose_snapshot = lambda: inputs()[0]
    runtime.agent.pointcloud_binary_snapshot = lambda: inputs()[1]
    runtime.competition = Mock()
    service = FakeService()
    owner = FastlioObservationSession(runtime, enabled=True, service=service)
    runtime.fastlio_observation = owner
    return runtime, owner, service


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_start_readiness_stop_and_no_implicit_extension(self):
        runtime, owner, service = session_runtime()
        self.assertEqual((await owner.refresh())["state"], "STOPPED")
        self.assertEqual(service.calls, [])
        state = await owner.start()
        self.assertEqual(state["state"], "READY")
        self.assertFalse(state["map_registration_applied"])
        runtime.agent.set_sources.assert_called_once_with(
            {"odometry": "/Odometry", "pointcloud": "/cloud_registered"}
        )
        with self.assertRaises(ObservationSessionConflict):
            await owner.start()
        await owner.stop("a" * 32)
        self.assertEqual(service.calls, ["start", "stop"])
        await owner.refresh()
        await owner.close()
        self.assertEqual(service.calls, ["start", "stop"])

    async def test_mapping_and_bridge_block_start_but_not_owned_stop(self):
        runtime, owner, service = session_runtime()
        runtime.mapping._manager._pipeline["state"] = "running"
        with self.assertRaisesRegex(ObservationSessionConflict, "mapping"):
            await owner.start()
        self.assertEqual(service.calls, [])
        runtime.mapping._manager._pipeline["state"] = "idle"
        runtime.lifecycle.control_bridge_snapshot = lambda: {
            "systemd": {"active_state": "active"}
        }
        with self.assertRaisesRegex(ObservationSessionConflict, "control_bridge"):
            await owner.start()
        runtime.lifecycle.control_bridge_snapshot = lambda: {
            "systemd": {"active_state": "inactive"}
        }
        await owner.start()
        runtime.mapping._manager._pipeline["state"] = "running"
        await owner.stop("a" * 32)
        self.assertEqual(service.calls, ["start", "stop"])

    async def test_old_tab_cannot_stop_new_invocation_or_unknown_state(self):
        _, owner, service = session_runtime()
        await owner.start()
        service.invocation = "b" * 32
        with self.assertRaises(ObservationSessionConflict):
            await owner.stop("a" * 32)
        service.failure = True
        with self.assertRaises(ObservationSessionConflict):
            await owner.stop("b" * 32)
        self.assertEqual(service.calls, ["start"])
        self.assertTrue(owner.busy())

    async def test_missing_input_never_ready_and_monitor_shutdown_never_starts(self):
        runtime, owner, service = session_runtime()
        runtime.agent.pointcloud_binary_snapshot = lambda: {}
        self.assertEqual((await owner.start())["state"], "WAITING_INPUTS")
        await owner.start_monitor()
        await owner.close()
        self.assertEqual(service.calls, ["start"])
        self.assertFalse(owner.snapshot()["can_start"])

    async def test_queued_start_blocks_a_second_start(self):
        _, owner, service = session_runtime()
        service.dispatch = lambda action: service.calls.append(action)
        service.status = lambda: parse_status(text_status(job="44 /org/job/44"))
        with self.assertRaises(ObservationSessionConflict):
            await owner.start()
        self.assertEqual(service.calls, [])

    async def test_stale_monitor_blocks_conflicting_owners(self):
        runtime, owner, _ = session_runtime()
        await owner.refresh()
        owner._updated_at = time.monotonic() - 10
        self.assertTrue(owner.busy())
        self.assertFalse(owner.snapshot()["can_start"])
        self.assertIn("fastlio_observation", ownership_readback(runtime)["busy_components"])


class ApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runtime, self.owner, self.service = session_runtime()
        app = FastAPI()
        app.state.runtime = self.runtime
        app.include_router(router)
        self.app = app
        self.origin = {"Origin": "http://testserver"}

    async def request(self, method, path, body=None, origin="http://testserver"):
        encoded = json.dumps(body).encode() if body is not None else b""
        messages = []

        async def receive():
            return {"type": "http.request", "body": encoded, "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(
            dict(
                type="http",
                asgi={"version": "3.0"},
                http_version="1.1",
                method=method,
                scheme="http",
                path=path,
                raw_path=path.encode(),
                query_string=b"",
                root_path="",
                headers=[
                    (b"host", b"testserver"),
                    (b"origin", origin.encode()),
                    (b"content-type", b"application/json"),
                ],
                client=("127.0.0.1", 123),
                server=("testserver", 80),
            ),
            receive,
            send,
        )
        return SimpleNamespace(
            status_code=next(
                m["status"] for m in messages if m["type"] == "http.response.start"
            ),
            text=b"".join(m.get("body", b"") for m in messages).decode(),
        )

    async def test_origin_confirmation_and_extra_args_are_rejected(self):
        path = "/api/v1/observations/fastlio/start"
        self.assertEqual(
            (
                await self.request(
                    "POST", path, {"confirmed": True}, origin="http://evil"
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (await self.request("POST", path, {"confirmed": False})).status_code, 400
        )
        for body in [{"confirmed": "true"}, {"confirmed": True, "command": "anything"}]:
            self.assertEqual((await self.request("POST", path, body)).status_code, 422)
        self.assertEqual(self.service.calls, [])

    async def test_start_and_stop_fixed_session_and_read_only_get(self):
        self.assertEqual(
            (await self.request("GET", "/api/v1/observations/fastlio")).status_code, 200
        )
        self.assertEqual(self.service.calls, [])
        response = await self.request(
            "POST", "/api/v1/observations/fastlio/start", {"confirmed": True}
        )
        self.assertEqual(response.status_code, 202, response.text)
        response = await self.request(
            "POST",
            "/api/v1/observations/fastlio/stop",
            {"confirmed": True, "session_id": "a" * 32},
        )
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.service.calls, ["start", "stop"])


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "observation_entry",
            Path(__file__).resolve().parents[1]
            / "scripts/start_observation_fastlio.py",
        )
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_reject_existing_fastlio_and_preserve_unmounted_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            proc = root / "proc"
            proc.mkdir()
            (proc / "123").mkdir()
            (proc / "123/cmdline").write_bytes(
                b"/opt/ros/bin/fastlio_mapping\0--ros-args\0"
            )
            self.assertTrue(self.module.existing_fastlio(proc))
            state, fastlio = root / "state", root / "fastlio"
            for target in [
                state / "log",
                state / "pcd",
                fastlio / "Log",
                fastlio / "PCD",
            ]:
                target.mkdir(parents=True)
            original = fastlio / "Log/original"
            original.write_text("keep")
            with self.assertRaisesRegex(RuntimeError, "mounts"):
                self.module.prepare_outputs(state, fastlio, "a" * 32)
            self.assertEqual(original.read_text(), "keep")
            self.assertFalse((state / "sessions").exists())

    def test_archives_previous_private_output_and_never_reuses_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ["log", "pcd", "fastlio/Log", "fastlio/PCD"]:
                (root / name).mkdir(parents=True)
            (root / "log/old.log").write_text("preserved")
            with patch.object(self.module.os.path, "samefile", return_value=True):
                result = self.module.prepare_outputs(root, root / "fastlio", "a" * 32)
                self.assertTrue(result.is_dir())
                self.assertEqual(
                    (result.parent / "previous-log/old.log").read_text(), "preserved"
                )
                with self.assertRaises(FileExistsError):
                    self.module.prepare_outputs(root, root / "fastlio", "a" * 32)


if __name__ == "__main__":
    unittest.main()
