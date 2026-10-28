import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from robot_dashboard.application.mission_coordinator import MissionConflict, MissionError
from robot_dashboard.application.navigation_stop import stop_navigation_with_mission
from robot_dashboard.navigation_jobs import NavigationJobError


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "robot_dashboard" / "api" / "routers" / "missions.py"
APP = ROOT / "robot_dashboard" / "app.py"
MODELS = ROOT / "robot_dashboard" / "api" / "models.py"


class MissionSchemaTests(unittest.TestCase):
    def test_strict_schema_accepts_only_bounded_annotation_metadata(self):
        tree = ast.parse(MODELS.read_text(encoding="utf-8"))
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        waypoint = classes["MissionWaypointRequest"]
        fields = {node.target.id for node in waypoint.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
        self.assertEqual(fields, {"annotation_id", "arrival_action", "arrival_tolerance", "hold_seconds", "requires_operator_confirmation", "label"})
        create = classes["MissionCreateRequest"]
        create_fields = {node.target.id for node in create.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
        self.assertEqual(create_fields, {"label", "map_id", "map_revision", "annotation_revision", "waypoints"})
        action = classes["MissionActionRequest"]
        self.assertEqual([node for node in action.body if isinstance(node, ast.AnnAssign)], [])
        source = ast.get_source_segment(MODELS.read_text(encoding="utf-8"), waypoint)
        self.assertIn("le=300.0", source)
        self.assertIn("max_length=32", MODELS.read_text(encoding="utf-8"))


class MissionRouterContractTests(unittest.TestCase):
    def test_exact_routes_are_bounded_and_every_mutation_is_same_origin(self):
        tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
        routes = {}
        for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
            for decorator in function.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    routes[(decorator.func.attr, decorator.args[0].value)] = function
        self.assertEqual(
            set(routes),
            {
                ("get", "/api/v1/missions"),
                ("post", "/api/v1/missions"),
                ("get", "/api/v1/missions/{mission_id}"),
                *{("post", f"/api/v1/missions/{{mission_id}}/{action}") for action in ("start", "pause", "resume", "skip", "retry", "abort")},
                ('post', '/api/v1/missions/{mission_id}/operator-test-enable'),
                ('post', '/api/v1/missions/{mission_id}/operator-test-green'),
            },
        )
        source = ROUTER.read_text(encoding="utf-8")
        self.assertIn("require_same_origin(request)", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("localStorage", source)

    def test_navigation_routes_fence_mission_goal_ownership_and_stop_aborts_first(self):
        source = APP.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("require_mission_navigation_idle("), 5)
        stop = source.index("async def navigation_stop")
        stop_end = source.index("async def navigation_initial_pose")
        stop_source = source[stop:stop_end]
        self.assertIn("stop_navigation_with_mission(RUNTIME.mission, navigation_coordinator())", stop_source)
        self.assertIn("await runtime.mission.close()", source)


class MissionGlobalStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncertain_mission_cannot_prevent_global_navigation_stop(self):
        # Execute the production endpoint without importing ROS/application boot.
        function = next(node for node in ast.parse(APP.read_text()).body
                        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'navigation_stop')
        function.decorator_list = []
        function.returns = None
        for argument in function.args.args:
            argument.annotation = None
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        mission = SimpleNamespace(blocks_navigation_goal=lambda: True,
            abort_active=AsyncMock(side_effect=MissionConflict('mission goal ownership is uncertain')))
        navigation = SimpleNamespace(stop=AsyncMock(return_value={'navigation': {'pipeline': {'state': 'idle'}}}))
        scope = {'RUNTIME': SimpleNamespace(mission=mission), 'require_same_origin': lambda request: None,
                 'navigation_coordinator': lambda: navigation, 'MissionError': MissionError,
                 'NavigationJobError': NavigationJobError, 'HTTPException': HTTPException,
                 'stop_navigation_with_mission': stop_navigation_with_mission}
        exec(compile(module, str(APP), 'exec'), scope)
        with self.assertRaises(HTTPException) as raised:
            await scope['navigation_stop'](object(), object())
        navigation.stop.assert_awaited_once()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn('Nav2 stop requested; mission cleanup unresolved', raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
