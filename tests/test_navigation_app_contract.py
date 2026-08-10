import ast
import unittest
from pathlib import Path


APP_PATH = Path(__file__).parents[1] / "robot_dashboard" / "app.py"


def parsed_app():
    return ast.parse(APP_PATH.read_text(encoding="utf-8"))


def functions(tree):
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def calls_name(node, name):
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == name
        for item in ast.walk(node)
    )


class NavigationAppContractTests(unittest.TestCase):
    def test_exact_navigation_routes_are_declared(self):
        tree = parsed_app()
        routes = set()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "app"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    routes.add((decorator.func.attr, decorator.args[0].value))
        self.assertTrue(
            {
                ("get", "/api/v1/navigation"),
                ("get", "/api/v1/navigation/parameters"),
                ("patch", "/api/v1/navigation/parameters"),
                ("post", "/api/v1/navigation/start"),
                ("post", "/api/v1/navigation/stop"),
                ("post", "/api/v1/navigation/initial-pose"),
                ("post", "/api/v1/navigation/goal"),
                ("post", "/api/v1/navigation/cancel"),
                ("post", "/api/v1/navigation/clear-costmaps"),
            }.issubset(routes)
        )
        self.assertNotIn(("post", "/api/v1/navigation/goal/cancel"), routes)
        self.assertNotIn(("post", "/api/v1/navigation/costmaps/clear"), routes)

    def test_every_navigation_mutation_is_same_origin_guarded(self):
        tree_functions = functions(parsed_app())
        mutations = (
            "update_navigation_parameters",
            "navigation_start",
            "navigation_stop",
            "navigation_initial_pose",
            "navigation_goal",
            "navigation_cancel",
            "navigation_clear_costmaps",
        )
        for name in mutations:
            with self.subTest(route=name):
                node = tree_functions[name]
                self.assertTrue(calls_name(node, "require_same_origin"))
                self.assertIn("request", [argument.arg for argument in node.args.args])

    def test_both_pipeline_directions_use_one_coordination_lock(self):
        tree_functions = functions(parsed_app())
        lock_routes = (
            "navigation_start",
            "mapping_start",
            "mapping_stop",
            "mapping_save",
            "convert_saved_pcd_to_2d",
            "save_edited_map_copy",
            "rename_saved_map",
            "delete_saved_map",
        )
        for name in lock_routes:
            node = tree_functions[name]
            lock_contexts = [
                item
                for item in ast.walk(node)
                if isinstance(item, ast.AsyncWith)
                and any(
                    isinstance(entry.context_expr, ast.Name)
                    and entry.context_expr.id == "PIPELINE_COORDINATION_LOCK"
                    for entry in item.items
                )
            ]
            self.assertTrue(lock_contexts, f"{name} must use the pipeline coordination lock")
        for name in (
            "mapping_start",
            "mapping_stop",
            "mapping_save",
            "convert_saved_pcd_to_2d",
            "save_edited_map_copy",
            "rename_saved_map",
            "delete_saved_map",
        ):
            self.assertTrue(
                calls_name(tree_functions[name], "require_navigation_idle"),
                f"{name} must reject an active pinned navigation map",
            )

    def test_navigation_start_reuses_or_starts_shared_fastlio_pipeline(self):
        node = functions(parsed_app())["navigation_start"]
        source = ast.unparse(node)
        self.assertIn("mapping_pipeline_state()", source)
        self.assertIn("mapping_jobs().start_mapping", source)
        self.assertIn("shared_pipeline_state != 'running'", source)
        self.assertIn("still verifying sensor readiness", source)
        self.assertNotIn("stop_mapping", source)
        self.assertLess(source.index("navigation_activate"), source.index("manager.start"))
        self.assertIn("navigation_start_failed", source)

    def test_goal_requires_explicit_confirmation_and_pinned_free_pose(self):
        node = functions(parsed_app())["navigation_goal"]
        source = ast.unparse(node)
        self.assertIn("body.confirmed is not True", source)
        self.assertIn("validate_active_pose", source)
        self.assertIn("require_navigation_runtime_capability", source)
        self.assertIn("mapping_pipeline_state() != 'running'", source)
        self.assertIn("navigation_send_goal", source)
        self.assertLess(source.index("validate_active_pose"), source.index("navigation_send_goal"))

    def test_initialization_wires_private_map_snapshot_and_terminal_stop(self):
        source = ast.unparse(functions(parsed_app())["main"])
        self.assertIn("NAVIGATION_JOBS", source)
        self.assertIn("NavigationJobManager.for_go2_humble", source)
        self.assertIn("map_snapshotter=catalog.snapshot_navigation_map", source)
        self.assertIn("on_terminal=navigation_terminal", source)
        self.assertIn("navigation_deactivate(reason=reason)", source)

    def test_status_exposes_fixed_private_bindings(self):
        source = ast.unparse(functions(parsed_app())["navigation_view"])
        self.assertIn("'scan': '/scan'", source)
        self.assertIn("'odometry': '/utlidar/robot_odom'", source)
        self.assertIn("'localization_odometry': '/Odometry'", source)
        self.assertIn("'command': '/robot_scope/nav/cmd_vel_raw'", source)


if __name__ == "__main__":
    unittest.main()
