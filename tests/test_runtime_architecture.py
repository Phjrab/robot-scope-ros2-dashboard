import ast
import asyncio
import unittest
from pathlib import Path

from robot_dashboard.application.runtime import ApplicationRuntime


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "robot_dashboard" / "app.py"
ROUTER_ROOT = ROOT / "robot_dashboard" / "api" / "routers"
APPLICATION_ROOT = ROOT / "robot_dashboard" / "application"


def declared_routes(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "patch", "delete", "websocket"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                result.add((decorator.func.attr, decorator.args[0].value))
    return result


class ApplicationRuntimeOwnershipTests(unittest.TestCase):
    def test_each_runtime_owns_coordinators_one_lock_caches_and_discovery(self):
        first = ApplicationRuntime()
        second = ApplicationRuntime()
        self.assertIsNone(first.agent)
        self.assertIsNone(first.mapping)
        self.assertIsNone(first.navigation)
        self.assertIsNone(first.mission)
        self.assertIsNone(first.lifecycle)
        self.assertIsNone(first.competition)
        self.assertIsNot(first.pipeline_coordination_lock, second.pipeline_coordination_lock)
        self.assertIsNot(first.json_cache, second.json_cache)
        self.assertIsNot(first.control_bindings, second.control_bindings)
        self.assertIsNot(first.robot_discovery, second.robot_discovery)
        self.assertIsInstance(first.pipeline_coordination_lock, asyncio.Lock)
        for legacy in (
            "mapping_jobs",
            "navigation_jobs",
            "service_lifecycle",
            "control_bridge_lifecycle",
            "mapping_task",
            "navigation_start_task",
            "navigation_start_state_lock",
            "navigation_start",
        ):
            self.assertFalse(hasattr(first, legacy), legacy)

    def test_task_and_navigation_rlock_ownership_moved_to_coordinators(self):
        runtime_source = (APPLICATION_ROOT / "runtime.py").read_text(encoding="utf-8")
        mapping_source = (APPLICATION_ROOT / "mapping_coordinator.py").read_text(
            encoding="utf-8"
        )
        navigation_source = (
            APPLICATION_ROOT / "navigation_coordinator.py"
        ).read_text(encoding="utf-8")

        self.assertIn("mapping: MappingCoordinator | None", runtime_source)
        self.assertIn("navigation: NavigationCoordinator | None", runtime_source)
        self.assertIn("mission: MissionCoordinator | None", runtime_source)
        self.assertIn("lifecycle: LifecycleCoordinator | None", runtime_source)
        self.assertNotIn("mapping_task:", runtime_source)
        self.assertNotIn("navigation_start_task:", runtime_source)
        self.assertNotIn("navigation_start_state_lock:", runtime_source)
        self.assertIn("self._task: asyncio.Task[None] | None", mapping_source)
        self.assertIn(
            "self._start_task: asyncio.Task[None] | None",
            navigation_source,
        )
        self.assertIn("self._state_lock = threading.RLock()", navigation_source)

    def test_app_has_one_container_instead_of_manager_and_task_globals(self):
        source = APP_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned_names = {
            target.id
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            if isinstance(target, ast.Name)
        }
        self.assertIn("RUNTIME", assigned_names)
        self.assertTrue(
            {
                "AGENT",
                "SAVED_MAPS",
                "MAPPING_JOBS",
                "NAVIGATION_JOBS",
                "SERVICE_LIFECYCLE",
                "CONTROL_BRIDGE_LIFECYCLE",
                "DATASET_CAPTURE",
                "MAPPING_TASK",
                "NAVIGATION_START_TASK",
                "PIPELINE_COORDINATION_LOCK",
                "NAVIGATION_START_STATE",
            }.isdisjoint(assigned_names)
        )
        self.assertIn("app.state.runtime = RUNTIME", source)
        self.assertNotIn("RUNTIME.mapping_jobs", source)
        self.assertNotIn("RUNTIME.navigation_jobs", source)
        self.assertNotIn("RUNTIME.mapping_task", source)
        self.assertNotIn("RUNTIME.navigation_start_task", source)
        self.assertEqual(
            source.count("coordination_lock=RUNTIME.pipeline_coordination_lock"),
            2,
        )
        self.assertIn("mapping_task_active_provider=RUNTIME.mapping.task_active", source)
        self.assertIn(
            "navigation_start_snapshot_provider=(\n"
            "            RUNTIME.navigation.internal_start_state",
            source,
        )
        self.assertLess(len(source.splitlines()), 1_600)


class DomainRouterContractTests(unittest.TestCase):
    def test_extracted_transport_paths_are_preserved_exactly(self):
        expected = {
            ("get", "/api/v1/system/service"),
            ("post", "/api/v1/system/service/restart"),
            ("post", "/api/v1/system/service/stop"),
            ("get", "/api/v1/control/bridge-service"),
            ("post", "/api/v1/control/bridge-service/start"),
            ("post", "/api/v1/control/bridge-service/stop"),
            ("post", "/api/v1/system/diagnostics/export"),
            ("get", "/api/v1/health"),
            ("get", "/api/v1/state"),
            ("get", "/api/v1/topics"),
            ("get", "/api/v1/sources"),
            ("post", "/api/v1/sources"),
            ("get", "/api/v1/cameras"),
            ("get", "/api/v1/pointcloud"),
            ("get", "/api/v1/pointcloud.bin"),
            ("get", "/api/v1/pointcloud/settings"),
            ("post", "/api/v1/pointcloud/settings"),
            ("get", "/api/v1/map"),
            ("get", "/api/v1/joints"),
            ("get", "/api/v1/pose"),
            ("get", "/api/v1/robots/types"),
            ("post", "/api/v1/robots/discover"),
            ("post", "/api/v1/robot"),
            ("delete", "/api/v1/robot"),
            ("get", "/api/v1/datasets/capture"),
            ("post", "/api/v1/datasets/capture/start"),
            ("post", "/api/v1/datasets/capture/stop"),
            ("get", "/api/v1/datasets"),
            ("post", "/api/v1/datasets/{session_id}/export"),
            ("get", "/api/v1/datasets/exports/{export_id}"),
            ("get", "/api/v1/datasets/{session_id}"),
            (
                "get",
                "/api/v1/datasets/{session_id}/samples/{sample_index}/{source_id}.jpg",
            ),
            ("websocket", "/api/v1/ws/pointcloud"),
            ("websocket", "/api/v1/ws/camera"),
            ("websocket", "/api/v1/ws/cameras/{source_id}"),
            ("websocket", "/api/v1/ws/joints"),
            ("websocket", "/api/v1/ws/pose"),
        }
        actual = set()
        for filename in ("system.py", "telemetry.py", "cameras.py", "dataset.py", "discovery.py"):
            actual.update(declared_routes(ROUTER_ROOT / filename))
        self.assertEqual(actual, expected)

    def test_routers_use_runtime_dependency_and_app_does_not_own_nav_transaction(self):
        for filename in ("system.py", "telemetry.py", "cameras.py", "dataset.py", "discovery.py"):
            source = (ROUTER_ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("runtime_from_", source, filename)
            self.assertNotIn("subprocess", source, filename)
            self.assertNotIn("NavigationJobManager", source, filename)
            self.assertNotIn("run_navigation_start_operation", source, filename)
        app_source = APP_PATH.read_text(encoding="utf-8")
        navigation_source = (
            APPLICATION_ROOT / "navigation_coordinator.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("async def run_navigation_start_operation", app_source)
        self.assertNotIn("def request_navigation_terminal_cancel", app_source)
        self.assertIn("async def _run_start_operation", navigation_source)
        self.assertIn("def request_terminal_cancel", navigation_source)


if __name__ == "__main__":
    unittest.main()
