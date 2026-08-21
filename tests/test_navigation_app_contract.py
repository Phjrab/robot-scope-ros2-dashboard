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

    def test_navigation_progress_log_is_fixed_read_only_and_server_bounded(self):
        tree_functions = functions(parsed_app())
        node = tree_functions["navigation_logs"]
        source = ast.unparse(node)
        self.assertIn("navigation_jobs().progress_snapshot", source)
        self.assertIn("after=after", source)
        self.assertIn("limit=limit", source)
        self.assertNotIn("require_same_origin", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell", source)

        defaults = node.args.defaults
        self.assertEqual(len(defaults), 2)
        after_keywords = {item.arg: item.value for item in defaults[0].keywords}
        limit_keywords = {item.arg: item.value for item in defaults[1].keywords}
        self.assertEqual(after_keywords["default"].value, 0)
        self.assertEqual(after_keywords["ge"].value, 0)
        self.assertEqual(after_keywords["le"].value, 9_007_199_254_740_991)
        self.assertEqual(limit_keywords["default"].value, 80)
        self.assertEqual(limit_keywords["ge"].value, 1)
        self.assertEqual(limit_keywords["le"].value, 100)

        routes = [
            decorator.args[0].value
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "get"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ]
        self.assertEqual(routes, ["/api/v1/navigation/logs"])
        self.assertIn("Cache-Control", source)
        self.assertIn("no-store", source)

    def test_stopped_shared_mapping_pipeline_is_idle_not_failed(self):
        source = ast.unparse(functions(parsed_app())["mapping_pipeline_state"])
        self.assertIn("if state == 'stopped'", source)
        self.assertIn("return 'idle'", source)

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
                    isinstance(entry.context_expr, ast.Attribute)
                    and entry.context_expr.attr == "pipeline_coordination_lock"
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
        self.assertIn("mapping_jobs().snapshot", source)
        self.assertIn("run_navigation_start_operation", source)
        self.assertIn("start_localization=shared_pipeline_state in {'idle', 'failed'}", source)
        self.assertIn("mapping_owned=False", source)
        self.assertIn("status_code=202", source)
        self.assertIn("'pending': True", source)
        self.assertNotIn("wait_navigation_prelocalization_ready", source)
        operation = ast.unparse(functions(parsed_app())["run_navigation_start_operation"])
        self.assertLess(
            operation.index("run_navigation_manager_start"),
            operation.index("run_navigation_activation"),
        )
        self.assertIn("navigation_start_preflight", source)
        self.assertIn("wait_navigation_localization_dependency", operation)
        self.assertIn("wait_navigation_prelocalization_ready", operation)
        self.assertIn("rollback_navigation_transaction", operation)
        self.assertIn("asyncio.CancelledError", operation)
        self.assertIn("run_navigation_manager_start", operation)
        self.assertIn("run_navigation_activation", operation)
        returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
        self.assertTrue(returns)
        activation = ast.unparse(functions(parsed_app())["run_navigation_activation"])
        self.assertIn("await asyncio.to_thread(navigation_view)", activation)
        self.assertIn("rollback_navigation_start", activation)

    def test_navigation_dependency_cleanup_is_exact_and_status_exposes_progress(self):
        tree_functions = functions(parsed_app())
        cleanup = ast.unparse(
            tree_functions["cleanup_navigation_localization_dependency_sync"]
        )
        self.assertIn("stop_mapping_if_job_id", cleanup)
        self.assertIn("mapping_owned", cleanup)
        view = ast.unparse(tree_functions["navigation_view"])
        self.assertIn("startup_cleanup_required", view)
        self.assertIn("'phase': startup_phase", view)
        self.assertIn("'pending': startup_pending", view)
        self.assertIn("'owned_by_navigation'", view)
        self.assertIn("startup_cleanup_required", view)

    def test_stop_cancels_background_start_outside_the_coordination_lock(self):
        source = ast.unparse(functions(parsed_app())["navigation_stop"])
        self.assertIn("request_navigation_start_cancel", source)
        self.assertIn("task.cancel()", source)
        self.assertIn("await asyncio.shield(task)", source)
        self.assertIn("perform_navigation_stop_cleanup", source)
        cleanup = ast.unparse(
            functions(parsed_app())["perform_navigation_stop_cleanup"]
        )
        self.assertIn("cleanup_navigation_localization_dependency", cleanup)

    def test_manual_arm_blocks_every_navigation_start_transition(self):
        node = functions(parsed_app())["control_arm"]
        lock_context = next(
            item
            for item in ast.walk(node)
            if isinstance(item, ast.AsyncWith)
            and any(
                isinstance(entry.context_expr, ast.Attribute)
                and entry.context_expr.attr == "pipeline_coordination_lock"
                for entry in item.items
            )
        )
        source = ast.unparse(lock_context)
        self.assertIn("_navigation_start_internal", source)
        self.assertIn("startup.get('pending')", source)
        self.assertIn("control_acquire", source)
        self.assertLess(
            source.index("_navigation_start_internal"),
            source.index("control_acquire"),
        )
        for phase in (
            "starting_localization",
            "waiting_localization",
            "starting_navigation",
            "warming_navigation",
            "activating",
            "stopping",
        ):
            self.assertIn(repr(phase), source)

    def test_terminal_deactivation_failure_cannot_skip_owned_mapping_cleanup(self):
        main = functions(parsed_app())["main"]
        terminal = next(
            item
            for item in main.body
            if isinstance(item, ast.FunctionDef) and item.name == "navigation_terminal"
        )
        source = ast.unparse(terminal)
        self.assertIn("except Exception", source)
        self.assertIn("cleanup_navigation_localization_dependency_sync", source)
        self.assertLess(
            source.index("except Exception"),
            source.index("cleanup_navigation_localization_dependency_sync"),
        )

    def test_shutdown_settles_start_task_then_exact_dependency_cleanup(self):
        source = ast.unparse(functions(parsed_app())["lifespan"])
        self.assertIn("startup_task.cancel()", source)
        self.assertIn("await asyncio.shield(startup_task)", source)
        self.assertIn("cleanup_navigation_localization_dependency", source)

    def test_navigation_cleanup_union_covers_manager_runtime_goal_and_lease(self):
        source = ast.unparse(functions(parsed_app())["navigation_active"])
        self.assertIn("pipeline.get('job_id')", source)
        self.assertIn("runtime.get('cleanup_required')", source)
        self.assertIn("goal.get('state')", source)
        self.assertIn("lease.get('input_source') == 'navigation'", source)
        view = ast.unparse(functions(parsed_app())["navigation_view"])
        self.assertIn("manager_cleanup_required", view)
        self.assertIn("runtime_cleanup_required", view)
        self.assertIn("'can_stop'", view)

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
        self.assertIn("RUNTIME.navigation_jobs", source)
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
        self.assertIn("deactivation_reason", source)
        self.assertIn("deactivation_reason[:160]", source)


if __name__ == "__main__":
    unittest.main()
