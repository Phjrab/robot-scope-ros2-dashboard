import ast
import unittest
from pathlib import Path


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
        self.assertEqual(fields, {"annotation_id", "arrival_tolerance", "hold_seconds", "requires_operator_confirmation", "label"})
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
        self.assertLess(stop_source.index("abort_active"), stop_source.index("navigation_coordinator().stop"))
        self.assertIn("await runtime.mission.close()", source)


if __name__ == "__main__":
    unittest.main()
