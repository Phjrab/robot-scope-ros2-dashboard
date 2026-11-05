"""SYNTHETIC motion boundaries with the real dashboard ASGI app and coordinator."""

import asyncio
import importlib.util
import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.control import LeaseBindingError
from robot_dashboard.navigation_jobs import MANUAL_SEEDED_2D
from robot_dashboard.saved_maps import SavedMapConflict
from test_navigation_coordinator import (
    FakeAgent,
    FakeMappingCoordinator,
    FakeNavigationJobs,
    FakeSavedMaps,
    ROOT,
)


URL = "/api/v1/navigation"
MAP = {"map_id": "a" * 24, "map_revision": "b" * 64}
POSE = {"x": 1.5, "y": 2.0, "yaw": 0.3}
GOAL_ID = "synthetic_goal_01"


class SyntheticAgent(FakeAgent):
    def __init__(self):
        super().__init__()
        self.actions = []

    @property
    def navigation_manual(self):
        return SimpleNamespace(
            manual_start_preflight=self.navigation_manual_start_preflight,
            prelocalization_snapshot=self.navigation_prelocalization_snapshot,
            activate=self.navigation_activate,
            set_initial_pose=self.navigation_set_initial_pose,
            send_goal=self.navigation_send_goal,
        )

    def navigation_manual_start_preflight(self, *, cold_odometry=False):
        self.events.append("manual_preflight")

    def navigation_prelocalization_snapshot(self, *, ready_after, **identity):
        self.events.append(("readiness_identity", identity))
        return super().navigation_prelocalization_snapshot(ready_after=ready_after)

    def navigation_activate(self, *, mode="standard", job_id=None, **kwargs):
        result = super().navigation_activate(**kwargs)
        if mode == MANUAL_SEEDED_2D:
            self.runtime["manual_seed"] = {
                "mode": mode, "job_id": job_id,
                "map_id": kwargs["map_id"], "map_revision": kwargs["map_revision"],
                "state": "waiting_initial_pose", "source_epoch": 1,
                "seed_generation": 0, "inputs_ready": True, "tf_readback": False,
            }
            self.runtime["localization"] = {"state": "uninitialized", "pose": None}
            self.runtime["safety"]["can_send_goal"] = False
        return result

    def navigation_set_initial_pose(self, *, seed_generation, source_epoch, **kwargs):
        seed = self.runtime["manual_seed"]
        if (seed_generation, source_epoch) != (seed["seed_generation"], seed["source_epoch"]):
            raise LeaseBindingError("manual seed generation or source epoch changed")
        result = super().navigation_set_initial_pose(**kwargs)
        seed.update(state="ready_manual", seed_generation=seed["seed_generation"] + 1,
                    tf_readback=True)
        self.runtime["localization"] = {
            "state": "manual_seeded", "pose": {key: kwargs[key] for key in POSE},
        }
        self.runtime["safety"]["can_send_goal"] = True
        return result

    def navigation_send_goal(self, *, seed_generation, **kwargs):
        if seed_generation != self.runtime["manual_seed"]["seed_generation"]:
            raise LeaseBindingError("manual seed generation changed")
        self.actions.append(kwargs)
        super().navigation_send_goal(**kwargs)
        self.runtime["goal"]["goal_id"] = GOAL_ID
        return {}

    def navigation_cancel_goal(self, *, goal_id):
        result = super().navigation_cancel_goal(goal_id=goal_id)
        self.runtime["goal"] = {"state": "idle"}
        return result

    def navigation_deactivate(self, *, reason):
        self.runtime.pop("manual_seed", None)
        return super().navigation_deactivate(reason=reason)


class SyntheticMapping(FakeMappingCoordinator):
    def start_mapping(self, *, relative_odometry_only=False):
        if not relative_odometry_only:
            raise AssertionError("manual mode must launch only relative odometry")
        return super().start_mapping()


class SyntheticJobs(FakeNavigationJobs):
    mode = None

    def snapshot(self):
        result = super().snapshot()
        result["pipeline"]["mode"] = self.mode
        return result

    def start(self, *, mode="standard", **kwargs):
        self.mode = mode
        return super().start(**kwargs)

    def stop(self):
        self.mode = None
        return super().stop()

    def operational_preflight(self, map_id, map_revision):
        self.events.append("operational_preflight")
        raise ValueError("INITIAL_HEIGHT_TILT_REQUIRED")

    def operational_initial_pose_check(self, *args):
        raise AssertionError("manual mode must not check the operational handoff")


def load_synthetic_dashboard():
    # Load the actual routes with the hardware adapter import substituted.
    # Callers must disable the production app lifespan.
    ros_module = ModuleType("robot_dashboard.ros_agent")
    ros_module.RosAgent = SyntheticAgent
    spec = importlib.util.spec_from_file_location(
        "robot_dashboard._synthetic_manual_api", ROOT / "robot_dashboard" / "app.py",
    )
    dashboard = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"robot_dashboard.ros_agent": ros_module}):
        spec.loader.exec_module(dashboard)
    return dashboard


class ManualNavigationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dashboard = load_synthetic_dashboard()
        self.app = dashboard.app
        self.agent = SyntheticAgent()
        self.jobs = SyntheticJobs()
        self.maps = FakeSavedMaps()
        self.mapping = SyntheticMapping()
        self.mapping.job_id = None
        self.competition = SimpleNamespace(require_manual_mode=lambda: None)
        dashboard.RUNTIME.competition = self.competition
        self.nav = NavigationCoordinator(
            self.agent, self.jobs, self.mapping, self.maps,
            coordination_lock=asyncio.Lock(), require_lifecycle_idle=lambda: None,
            ready_timeout_s=0.15, localization_timeout_s=0.5, poll_interval_s=0.005,
        )
        dashboard.RUNTIME.navigation = self.nav
        self.addAsyncCleanup(self.nav.close)

    async def request(self, method, endpoint="", body=None, *, origin="http://testserver"):
        path = URL + endpoint
        data = json.dumps(body).encode() if body is not None else b""
        response = bytearray()
        status = None
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": data, "more_body": False}
            await asyncio.Future()

        async def send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response.extend(message.get("body", b""))

        await self.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "scheme": "http", "http_version": "1.1", "method": method,
            "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "server": ("testserver", 80), "client": ("tests", 1),
            "headers": [(b"host", b"testserver"), (b"origin", origin.encode()),
                        (b"content-type", b"application/json")],
        }, receive, send)
        return status, json.loads(response)

    async def post(self, endpoint, body, *, status=200, **options):
        code, response = await self.request("POST", endpoint, body, **options)
        self.assertEqual(code, status, response)
        return response

    def start_body(self):
        return {**MAP, "parameters_revision": self.jobs.parameters_revision}

    async def start_manual(self):
        result = await self.post(
            "/start", {**self.start_body(), "mode": MANUAL_SEEDED_2D}, status=202,
        )
        self.assertTrue(result["pending"])
        task = self.nav.start_task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=2)
        status, view = await self.request("GET")
        self.assertEqual(status, 200)
        return view

    async def test_manual_flow_uses_pinned_job_map_and_generation(self):
        view = await self.start_manual()
        self.assertEqual(view["mode"], MANUAL_SEEDED_2D)
        self.assertEqual(view["pipeline"]["state"], "running", view)
        job_id = view["pipeline"]["job_id"]
        seed = view["manual_seed"]
        self.assertEqual(seed["state"], "waiting_initial_pose")
        self.assertEqual(seed["job_id"], job_id)
        self.assertFalse(view["safety"]["can_send_goal"])
        self.assertIn(("readiness_identity", {**MAP, "job_id": job_id,
                                              "mode": MANUAL_SEEDED_2D}), self.agent.events)
        self.assertEqual(self.jobs.events, ["start"])
        self.assertEqual(self.mapping.events, ["start_mapping"])

        await self.post("/start", self.start_body(), status=409)
        await self.post("/localization/start", self.start_body(), status=409)
        pins = {**MAP, "job_id": job_id}
        await self.post("/goal", {**pins, "pose": POSE, "confirmed": True}, status=409)
        initial_pose = {**pins, "pose": POSE, "seed_generation": 0, "source_epoch": 1}
        await self.post("/initial-pose", {**MAP, "pose": POSE}, status=409)
        await self.post("/initial-pose", {**pins, "pose": POSE}, status=409)
        for mismatch in ({"job_id": "e" * 32}, {"map_id": "e" * 24},
                         {"map_revision": "e" * 64}, {"source_epoch": 2}, {"seed_generation": 1}):
            with self.subTest(mismatch=mismatch):
                await self.post("/initial-pose", {**initial_pose, **mismatch}, status=409)
        self.assertFalse(any(event[0] == "initial_pose" for event in self.agent.events
                             if isinstance(event, tuple)))

        seeded = await self.post("/initial-pose", initial_pose)
        self.assertTrue(seeded["accepted"])
        await self.post("/initial-pose", initial_pose, status=409)
        self.assertEqual(sum(isinstance(event, tuple) and event[0] == "initial_pose"
                             for event in self.agent.events), 1)
        seed = seeded["navigation"]["manual_seed"]
        self.assertTrue(seed["tf_readback"])
        generation = seed["seed_generation"]
        goal = {**pins, "pose": POSE, "confirmed": True, "seed_generation": generation}
        for mismatch in ({"job_id": "e" * 32}, {"map_revision": "e" * 64},
                         {"seed_generation": generation + 1}):
            with self.subTest(mismatch=mismatch):
                await self.post("/goal", {**goal, **mismatch}, status=409)
        await self.post("/goal", {**goal, "confirmed": False}, status=422)
        await self.post("/goal", {**goal, "seed_generation": str(generation)}, status=422)
        self.assertEqual(self.agent.actions, [])
        await self.post("/goal", goal)
        await self.post("/cancel", {"goal_id": GOAL_ID})

        annotation = {**pins, "annotation_id": "e" * 24, "annotation_revision": "f" * 64,
                      "confirmed": True, "seed_generation": generation}
        await self.post("/goal/annotation", {**annotation, "seed_generation": generation + 1},
                        status=409)
        await self.post("/goal/annotation", annotation)
        self.assertEqual(self.agent.actions, [
            {**MAP, **POSE},
            {**MAP, "x": 3.0, "y": 4.0, "yaw": 0.5},
        ])
        self.assertIn(("cancel", GOAL_ID), self.agent.events)
        await self.post("/stop", {})
        self.assertEqual(self.mapping.events, ["start_mapping", ("stop_mapping", "a" * 32)])
        self.assertEqual(self.jobs.events[-1], "stop")
        await self.post("/goal", goal, status=409)
        _, stopped = await self.request("GET")
        self.assertEqual(stopped["pipeline"]["state"], "idle")
        self.assertIsNone(stopped.get("manual_seed"))

    async def test_reads_and_default_3d_admission_have_no_start_side_effects(self):
        for endpoint in ("", "/parameters", "/logs"):
            status, _ = await self.request("GET", endpoint)
            self.assertEqual(status, 200)
        self.assertTrue(all(isinstance(event, str) and event.endswith("_snapshot")
                            for event in self.agent.events), self.agent.events)
        self.assertEqual(self.jobs.events, [])
        self.assertEqual(self.mapping.events, [])
        self.assertEqual(self.maps.calls, [])

        start = self.start_body()
        await self.post("/start", {**start, "mode": MANUAL_SEEDED_2D}, status=403,
                        origin="http://untrusted.invalid")
        await self.post("/start", {**start, "mode": "unrecognized"}, status=422)
        response = await self.post("/start", start, status=409)
        self.assertEqual(response["detail"], "INITIAL_HEIGHT_TILT_REQUIRED")
        self.assertEqual(self.jobs.events, ["operational_preflight"])
        self.assertEqual(self.mapping.events, [])

    async def test_missing_runtime_inputs_never_activate_and_roll_back(self):
        self.agent.preflight_ready = False
        view = await self.start_manual()
        self.assertEqual(view["pipeline"]["state"], "failed")
        self.assertFalse(any(event[0] == "activate" for event in self.agent.events
                             if isinstance(event, tuple)))
        self.assertEqual(self.jobs.events, ["start", "stop"])
        self.assertEqual(self.mapping.events, ["start_mapping", ("stop_mapping", "a" * 32)])

    async def test_changed_catalog_revision_closes_the_old_manual_job(self):
        view = await self.start_manual()
        pins = {**MAP, "job_id": view["pipeline"]["job_id"]}
        await self.post("/initial-pose", {**pins, "pose": POSE, "seed_generation": 0, "source_epoch": 1})
        with patch.object(self.maps, "resolve_navigation_map",
                          side_effect=SavedMapConflict("saved map revision changed")):
            await self.post("/goal", {**pins, "pose": POSE, "confirmed": True,
                                     "seed_generation": 1}, status=409)
        self.assertEqual(self.agent.actions, [])
        self.assertEqual(self.jobs.events[-1], "stop")
        _, stopped = await self.request("GET")
        self.assertIsNone(stopped.get("manual_seed"))
