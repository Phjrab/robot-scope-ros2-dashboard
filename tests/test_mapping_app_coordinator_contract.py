import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "robot_dashboard" / "app.py"
COORDINATOR_PATH = (
    ROOT / "robot_dashboard" / "application" / "mapping_coordinator.py"
)


def parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def functions(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def called_names(node: ast.AST) -> set[str]:
    result = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            result.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            result.add(child.func.attr)
    return result


def mapping_coordinator_methods(node: ast.AST) -> set[str]:
    result = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        owner = child.func.value
        if (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "mapping_coordinator"
        ):
            result.add(child.func.attr)
    return result


def declared_app_routes(tree: ast.Module) -> set[tuple[str, str]]:
    result = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.func.attr in {"get", "post", "patch", "delete"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                result.add((decorator.func.attr, decorator.args[0].value))
    return result


class MappingAppCoordinatorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app_tree = parsed(APP_PATH)
        cls.app_functions = functions(cls.app_tree)
        cls.coordinator_tree = parsed(COORDINATOR_PATH)
        coordinator_class = next(
            node
            for node in cls.coordinator_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MappingCoordinator"
        )
        cls.coordinator_functions = {
            node.name: node
            for node in coordinator_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_mapping_and_saved_map_paths_are_preserved_exactly(self):
        expected = {
            ("get", "/api/v1/mapping/control"),
            ("post", "/api/v1/mapping/start"),
            ("post", "/api/v1/mapping/stop"),
            ("post", "/api/v1/mapping/save"),
            ("get", "/api/v1/saved-maps"),
            ("post", "/api/v1/saved-maps/{map_id}/convert-2d"),
            ("post", "/api/v1/saved-maps/{map_id}/edited-copy"),
            ("get", "/api/v1/saved-maps/{map_id}"),
            ("get", "/api/v1/saved-maps/{map_id}/annotations"),
            ("patch", "/api/v1/saved-maps/{map_id}/annotations"),
            ("patch", "/api/v1/saved-maps/{map_id}"),
            ("delete", "/api/v1/saved-maps/{map_id}"),
            ("get", "/api/v1/saved-maps/{map_id}/data"),
        }
        actual = {
            route
            for route in declared_app_routes(self.app_tree)
            if route[1].startswith("/api/v1/mapping")
            or route[1].startswith("/api/v1/saved-maps")
        }
        self.assertEqual(actual, expected)

        for name in ("mapping_save", "convert_saved_pcd_to_2d"):
            decorator = next(
                item
                for item in self.app_functions[name].decorator_list
                if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute)
                and item.func.attr == "post"
            )
            keywords = {item.arg: item.value for item in decorator.keywords}
            self.assertEqual(keywords["status_code"].value, 202)

    def test_every_mapping_mutation_keeps_same_origin_and_thin_delegation(self):
        expected_method = {
            "mapping_start": "start",
            "mapping_stop": "stop",
            "mapping_save": "save",
            "convert_saved_pcd_to_2d": "convert_pcd_to_2d",
            "save_edited_map_copy": "save_edited_copy",
            "rename_saved_map": "rename",
            "delete_saved_map": "delete",
            "update_saved_map_annotations": "update_annotations",
        }
        forbidden_calls = {
            "create_task",
            "require_navigation_idle",
            "require_service_lifecycle_idle",
            "reserve_local_operation",
            "run_reserved_local_operation",
            "save_map",
            "start_mapping",
            "stop_mapping",
            "validate_map_name",
        }
        for name, method in expected_method.items():
            with self.subTest(route=name):
                node = self.app_functions[name]
                calls = called_names(node)
                self.assertIn("require_same_origin", calls)
                self.assertIn("request", [argument.arg for argument in node.args.args])
                self.assertEqual(mapping_coordinator_methods(node), {method})
                self.assertFalse(
                    any(isinstance(child, ast.AsyncWith) for child in ast.walk(node)),
                    f"{name} must not own the shared application lock",
                )
                self.assertTrue(forbidden_calls.isdisjoint(calls), name)

    def test_routes_translate_errors_but_coordinator_owns_interlocks(self):
        new_work = {
            "mapping_start",
            "mapping_save",
            "convert_saved_pcd_to_2d",
            "save_edited_map_copy",
            "rename_saved_map",
            "delete_saved_map",
            "update_saved_map_annotations",
        }
        for name in new_work:
            source = ast.unparse(self.app_functions[name])
            self.assertIn("LifecycleTransitionBusy", source, name)
            self.assertIn("mapping_coordination_error", source, name)

        stop_source = ast.unparse(self.app_functions["mapping_stop"])
        self.assertNotIn("LifecycleTransitionBusy", stop_source)
        self.assertIn("mapping_coordination_error", stop_source)
        self.assertIn("mapping_error", stop_source)

        translator = ast.unparse(
            self.app_functions["mapping_coordination_error"]
        )
        self.assertIn("MappingCoordinatorConflict", translator)
        self.assertIn("status_code=409", translator)
        self.assertIn("MappingCoordinatorUnavailable", translator)
        self.assertIn("status_code=503", translator)

    def test_coordinator_owns_one_shared_lock_and_navigation_interlocks(self):
        mutations = (
            "start",
            "stop",
            "save",
            "convert_pcd_to_2d",
            "save_edited_copy",
            "rename",
            "delete",
            "update_annotations",
        )
        for name in mutations:
            with self.subTest(method=name):
                node = self.coordinator_functions[name]
                calls = called_names(node)
                lock_contexts = [
                    child
                    for child in ast.walk(node)
                    if isinstance(child, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Attribute)
                        and isinstance(item.context_expr.value, ast.Name)
                        and item.context_expr.value.id == "self"
                        and item.context_expr.attr == "_coordination_lock"
                        for item in child.items
                    )
                ]
                self.assertEqual(len(lock_contexts), 1)
                self.assertIn("_require_navigation_idle", calls)

        for name in set(mutations) - {"stop"}:
            self.assertIn(
                "_require_lifecycle_idle",
                called_names(self.coordinator_functions[name]),
                name,
            )
        self.assertNotIn(
            "_require_lifecycle_idle",
            called_names(self.coordinator_functions["stop"]),
        )

    def test_exact_manager_and_catalog_fences_remain_below_transport(self):
        source = COORDINATOR_PATH.read_text(encoding="utf-8")
        self.assertNotIn("fastapi", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell=", source)
        self.assertNotIn("Path(", source)

        stop = ast.unparse(self.coordinator_functions["stop_mapping_if_job_id"])
        self.assertIn("self._manager.stop_mapping_if_job_id(job_id)", stop)
        conversion = ast.unparse(
            self.coordinator_functions["convert_pcd_to_2d"]
        )
        worker = ast.unparse(
            self.coordinator_functions["_run_saved_pcd_conversion"]
        )
        self.assertIn("reserve_local_operation", conversion)
        self.assertIn("fail_reserved_local_operation", conversion)
        self.assertIn("run_reserved_local_operation", worker)
        self.assertIn("local_operation_cancelled(job_id)", worker)
        self.assertIn("local_publication_guard(job_id)", worker)
        self.assertIn("expected_revision=expected_revision", worker)


if __name__ == "__main__":
    unittest.main()
