import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
APP_PATH = ROOT / "robot_dashboard" / "app.py"
NAVIGATION_COORDINATOR_PATH = (
    ROOT / "robot_dashboard" / "application" / "navigation_coordinator.py"
)
MAPPING_COORDINATOR_PATH = (
    ROOT / "robot_dashboard" / "application" / "mapping_coordinator.py"
)


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def functions(tree):
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def class_functions(tree, class_name):
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name: node
        for node in owner.body
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
    def setUp(self):
        self.app_tree = parsed(APP_PATH)
        self.app_functions = functions(self.app_tree)
        self.navigation_tree = parsed(NAVIGATION_COORDINATOR_PATH)
        self.navigation_methods = class_functions(
            self.navigation_tree,
            "NavigationCoordinator",
        )
        self.mapping_methods = class_functions(
            parsed(MAPPING_COORDINATOR_PATH),
            "MappingCoordinator",
        )

    def test_exact_navigation_routes_are_declared(self):
        routes = set()
        for node in self.app_tree.body:
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
        node = self.app_functions["navigation_logs"]
        source = ast.unparse(node)
        self.assertIn("navigation_coordinator().progress_snapshot", source)
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
        delegate = ast.unparse(self.navigation_methods["progress_snapshot"])
        self.assertIn("self._jobs.progress_snapshot", delegate)

    def test_stopped_shared_mapping_pipeline_is_idle_not_failed(self):
        source = ast.unparse(self.mapping_methods["pipeline_state"])
        self.assertIn("if state == 'stopped'", source)
        self.assertIn("return 'idle'", source)

    def test_every_navigation_mutation_is_same_origin_guarded(self):
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
                node = self.app_functions[name]
                self.assertTrue(calls_name(node, "require_same_origin"))
                self.assertIn("request", [argument.arg for argument in node.args.args])

    def test_both_pipeline_directions_use_one_coordination_lock(self):
        main_source = ast.unparse(self.app_functions["main"])
        shared_argument = "coordination_lock=RUNTIME.pipeline_coordination_lock"
        self.assertEqual(main_source.count(shared_argument), 2)
        self.assertIn("RUNTIME.mapping = MappingCoordinator", main_source)
        self.assertIn("RUNTIME.navigation = NavigationCoordinator", main_source)

        for name in (
            "start",
            "stop",
            "set_initial_pose",
            "send_goal",
            "update_parameters",
        ):
            source = ast.unparse(self.navigation_methods[name])
            self.assertIn(
                "async with self._coordination_lock",
                source,
                f"NavigationCoordinator.{name} must use the shared lock",
            )
        for name in (
            "start",
            "stop",
            "save",
            "convert_pcd_to_2d",
            "save_edited_copy",
            "rename",
            "delete",
        ):
            source = ast.unparse(self.mapping_methods[name])
            self.assertIn(
                "async with self._coordination_lock",
                source,
                f"MappingCoordinator.{name} must use the shared lock",
            )
            self.assertIn(
                "self._require_navigation_idle",
                source,
                f"MappingCoordinator.{name} must reject active navigation",
            )

    def test_navigation_start_reuses_or_starts_shared_fastlio_pipeline(self):
        route = self.app_functions["navigation_start"]
        route_source = ast.unparse(route)
        self.assertIn("navigation_coordinator().start", route_source)
        self.assertIn("status_code=202", route_source)
        self.assertNotIn("wait_prelocalization_ready", route_source)

        start = ast.unparse(self.navigation_methods["start"])
        operation = ast.unparse(self.navigation_methods["_run_start_operation"])
        self.assertIn("self._mapping.snapshot", start)
        self.assertIn("self._run_start_operation", start)
        self.assertIn(
            "start_localization=shared_pipeline_state in {'idle', 'failed'}",
            start,
        )
        self.assertIn("mapping_owned=False", start)
        self.assertIn("'pending': True", start)
        self.assertIn("self._agent.navigation_start_preflight", start)
        self.assertLess(
            operation.index("self.run_manager_start"),
            operation.index("self.run_activation"),
        )
        self.assertIn("self.wait_localization_dependency", operation)
        self.assertIn("self.wait_prelocalization_ready", operation)
        self.assertIn("self.rollback_transaction", operation)
        self.assertIn("asyncio.CancelledError", operation)
        self.assertIn("self.run_manager_start", operation)
        self.assertIn("self.run_activation", operation)
        returns = [item for item in ast.walk(route) if isinstance(item, ast.Return)]
        self.assertTrue(returns)
        activation = ast.unparse(self.navigation_methods["run_activation"])
        self.assertIn("await asyncio.to_thread(self.view)", activation)
        self.assertIn("self.rollback_start", activation)

    def test_navigation_dependency_cleanup_is_exact_and_status_exposes_progress(self):
        cleanup = ast.unparse(
            self.navigation_methods["cleanup_localization_dependency_sync"]
        )
        self.assertIn("stop_mapping_if_job_id", cleanup)
        self.assertIn("mapping_owned", cleanup)
        view = ast.unparse(self.navigation_methods["view"])
        self.assertIn("startup_cleanup_required", view)
        self.assertIn("'phase': startup_phase", view)
        self.assertIn("'pending': startup_pending", view)
        self.assertIn("'owned_by_navigation'", view)
        self.assertIn("startup_cleanup_required", view)

    def test_stop_cancels_background_start_outside_the_coordination_lock(self):
        route = ast.unparse(self.app_functions["navigation_stop"])
        self.assertIn("navigation_coordinator().stop", route)
        source = ast.unparse(self.navigation_methods["stop"])
        self.assertIn("self.request_start_cancel", source)
        self.assertIn("task.cancel()", source)
        self.assertIn("await asyncio.shield(task)", source)
        self.assertIn("self._perform_stop_cleanup", source)
        cleanup = ast.unparse(self.navigation_methods["_perform_stop_cleanup"])
        self.assertIn("self.cleanup_localization_dependency", cleanup)

    def test_manual_arm_blocks_every_navigation_start_transition(self):
        node = self.app_functions["control_arm"]
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
        self.assertIn("navigation_coordinator().manual_control_blocked", source)
        self.assertIn("control_acquire", source)
        self.assertLess(
            source.index("navigation_coordinator().manual_control_blocked"),
            source.index("control_acquire"),
        )
        expected_phases = {
            "starting_localization",
            "waiting_localization",
            "starting_navigation",
            "warming_navigation",
            "activating",
            "stopping",
        }
        phase_assignment = next(
            item
            for item in self.navigation_tree.body
            if isinstance(item, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "MANUAL_CONTROL_BLOCKING_PHASES"
                for target in item.targets
            )
        )
        actual_phases = {
            item.value
            for item in ast.walk(phase_assignment.value)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
        self.assertEqual(actual_phases, expected_phases)
        manual_guard = ast.unparse(self.navigation_methods["manual_control_blocked"])
        self.assertIn("startup.get('pending')", manual_guard)
        self.assertIn("MANUAL_CONTROL_BLOCKING_PHASES", manual_guard)

    def test_terminal_deactivation_failure_cannot_skip_owned_mapping_cleanup(self):
        source = ast.unparse(self.navigation_methods["handle_terminal"])
        self.assertIn("except Exception", source)
        self.assertIn("self.cleanup_localization_dependency_sync", source)
        self.assertLess(
            source.index("except Exception"),
            source.index("self.cleanup_localization_dependency_sync"),
        )
        self.assertIn("self.request_terminal_cancel", source)

    def test_shutdown_settles_start_task_then_exact_dependency_cleanup(self):
        lifespan = ast.unparse(self.app_functions["lifespan"])
        self.assertIn("await runtime.navigation.settle_startup()", lifespan)
        self.assertIn("await runtime.navigation.close()", lifespan)
        self.assertLess(
            lifespan.index("await runtime.navigation.settle_startup()"),
            lifespan.index("runtime.lifecycle.close()"),
        )
        self.assertLess(
            lifespan.index("runtime.lifecycle.close()"),
            lifespan.index("await runtime.navigation.close()"),
        )
        source = ast.unparse(self.navigation_methods["close"])
        self.assertIn("await self.settle_startup()", source)
        self.assertIn("self.cleanup_localization_dependency", source)
        self.assertLess(source.index("self._jobs.close"), source.index("self.cleanup_localization_dependency"))
        settlement = ast.unparse(self.navigation_methods["settle_startup"])
        self.assertIn("self.request_start_cancel", settlement)
        self.assertIn("task.cancel()", settlement)
        self.assertIn("await asyncio.shield(task)", settlement)

    def test_navigation_cleanup_union_covers_manager_runtime_goal_and_lease(self):
        source = ast.unparse(self.navigation_methods["is_active"])
        self.assertIn("pipeline.get('job_id')", source)
        self.assertIn("runtime.get('cleanup_required')", source)
        self.assertIn("goal.get('state')", source)
        self.assertIn("lease.get('input_source') == 'navigation'", source)
        view = ast.unparse(self.navigation_methods["view"])
        self.assertIn("manager_cleanup_required", view)
        self.assertIn("runtime_cleanup_required", view)
        self.assertIn("'can_stop'", view)

    def test_goal_requires_explicit_confirmation_and_pinned_free_pose(self):
        route_source = ast.unparse(self.app_functions["navigation_goal"])
        self.assertIn("confirmed=body.confirmed", route_source)
        source = ast.unparse(self.navigation_methods["send_goal"])
        self.assertIn("confirmed is not True", source)
        self.assertIn("self._jobs.validate_active_pose", source)
        self.assertIn("self.require_runtime_capability", source)
        self.assertIn("self._mapping.pipeline_state() != 'running'", source)
        self.assertIn("self._agent.navigation_send_goal", source)
        self.assertLess(
            source.index("self._jobs.validate_active_pose"),
            source.index("self._agent.navigation_send_goal"),
        )

    def test_initialization_wires_private_map_snapshot_and_terminal_stop(self):
        source = ast.unparse(self.app_functions["main"])
        self.assertIn("RUNTIME.navigation = NavigationCoordinator", source)
        self.assertIn("NavigationJobManager.for_go2_humble", source)
        self.assertIn("map_snapshotter=catalog.snapshot_navigation_map", source)
        constructor = ast.unparse(self.navigation_methods["__init__"])
        self.assertIn("navigation_jobs.on_terminal = self.handle_terminal", constructor)
        terminal = ast.unparse(self.navigation_methods["handle_terminal"])
        self.assertIn("self._agent.navigation_deactivate(reason=reason)", terminal)

    def test_status_exposes_fixed_private_bindings(self):
        source = ast.unparse(self.navigation_methods["view"])
        self.assertIn("'scan': '/scan'", source)
        self.assertIn("'odometry': '/utlidar/robot_odom'", source)
        self.assertIn("'localization_odometry': '/Odometry'", source)
        self.assertIn("'command': '/robot_scope/nav/cmd_vel_raw'", source)
        self.assertIn("deactivation_reason", source)
        self.assertIn("_public_navigation_diagnostic", source)


if __name__ == "__main__":
    unittest.main()
