import ast
import unittest
from pathlib import Path

from robot_dashboard.service_lifecycle import collect_service_lifecycle_blockers


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "robot_dashboard" / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)
SYSTEM_TREE = ast.parse(
    (ROOT / "robot_dashboard" / "api" / "routers" / "system.py").read_text(
        encoding="utf-8"
    )
)
MAPPING_TREE = ast.parse(
    (ROOT / "robot_dashboard" / "application" / "mapping_coordinator.py").read_text(
        encoding="utf-8"
    )
)
NAVIGATION_TREE = ast.parse(
    (
        ROOT
        / "robot_dashboard"
        / "application"
        / "navigation_coordinator.py"
    ).read_text(encoding="utf-8")
)
MODELS_TREE = ast.parse(
    (ROOT / "robot_dashboard" / "api" / "models.py").read_text(encoding="utf-8")
)


def function_node(name: str):
    for tree in (APP_TREE, SYSTEM_TREE):
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    raise AssertionError(f"function {name} was not found")


def tree_function(tree, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} was not found")


def class_function(tree, class_name: str, name: str):
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {class_name}.{name} was not found")


def called_names(node) -> set[str]:
    result = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            result.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            result.add(child.func.attr)
    return result


class ServiceLifecycleAppContractTests(unittest.TestCase):
    def test_mutations_require_same_origin_confirmation_and_lifecycle_manager(self):
        for name in ("service_lifecycle_restart", "service_lifecycle_stop"):
            calls = called_names(function_node(name))
            self.assertIn("require_same_origin", calls)
            self.assertIn("_service", calls)
            self.assertNotIn("require_service_admin", calls)

    def test_confirmation_field_is_strict_and_no_admin_auth_helper_remains(self):
        with self.assertRaises(AssertionError):
            function_node("require_service_admin")
        self.assertNotIn("X-Robot-Scope-Admin-Token", APP_SOURCE)
        model = next(
            node
            for node in MODELS_TREE.body
            if isinstance(node, ast.ClassDef) and node.name == "ServiceLifecycleRequest"
        )
        confirmed = next(
            node
            for node in model.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "confirmed"
        )
        self.assertIsInstance(confirmed.value, ast.Call)
        keywords = {item.arg: item.value for item in confirmed.value.keywords}
        self.assertIsInstance(keywords.get("strict"), ast.Constant)
        self.assertIs(keywords["strict"].value, True)

    def test_new_work_routes_are_gated_while_cleanup_routes_remain_available(self):
        # Manual control remains an app-level operation and must reserve the
        # same lock before checking the lifecycle gate and acquiring motion.
        control_arm = function_node("control_arm")
        self.assertIn("require_service_lifecycle_idle", called_names(control_arm))
        critical_sections = [
            child for child in control_arm.body if isinstance(child, ast.AsyncWith)
        ]
        self.assertEqual(len(critical_sections), 1)
        critical_calls = called_names(critical_sections[0])
        self.assertIn("require_service_lifecycle_idle", critical_calls)
        self.assertIn("control_acquire", critical_calls)

        # Mapping and navigation now own their application interlocks. Every
        # new-work operation checks the injected lifecycle gate while holding
        # the shared application coordination lock.
        mapping_guarded = {
            "start",
            "save",
            "convert_pcd_to_2d",
            "save_edited_copy",
            "rename",
            "delete",
        }
        for name in mapping_guarded:
            node = tree_function(MAPPING_TREE, name)
            self.assertIn(
                "_require_lifecycle_idle",
                called_names(node),
                name,
            )
            self.assertTrue(
                any(
                    isinstance(child, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Attribute)
                        and item.context_expr.attr == "_coordination_lock"
                        for item in child.items
                    )
                    for child in ast.walk(node)
                ),
                name,
            )

        navigation_guarded = {"start", "set_initial_pose"}
        for name in navigation_guarded:
            node = class_function(NAVIGATION_TREE, "NavigationCoordinator", name)
            self.assertIn("_require_lifecycle_idle", called_names(node), name)
            self.assertTrue(
                any(
                    isinstance(child, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Attribute)
                        and item.context_expr.attr == "_coordination_lock"
                        for item in child.items
                    )
                    for child in ast.walk(node)
                ),
                name,
            )

        goal_safety = class_function(
            NAVIGATION_TREE,
            "NavigationCoordinator",
            "_send_goal_locked",
        )
        self.assertIn("_require_lifecycle_idle", called_names(goal_safety))
        for name in ("send_goal", "send_annotation_goal"):
            node = class_function(NAVIGATION_TREE, "NavigationCoordinator", name)
            self.assertIn("_send_goal_locked", called_names(node), name)
            self.assertTrue(
                any(
                    isinstance(child, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Attribute)
                        and item.context_expr.attr == "_coordination_lock"
                        for item in child.items
                    )
                    for child in ast.walk(node)
                ),
                name,
            )

        app_cleanup = {
            "control_disarm",
            "control_stop",
            "navigation_stop",
            "navigation_cancel",
            "navigation_clear_costmaps",
            "mapping_stop",
        }
        for name in app_cleanup:
            self.assertNotIn(
                "require_service_lifecycle_idle",
                called_names(function_node(name)),
                name,
            )

        self.assertNotIn(
            "_require_lifecycle_idle",
            called_names(tree_function(MAPPING_TREE, "stop")),
        )
        for name in ("stop", "cancel_goal", "clear_costmaps"):
            self.assertNotIn(
                "_require_lifecycle_idle",
                called_names(
                    class_function(NAVIGATION_TREE, "NavigationCoordinator", name)
                ),
                name,
            )


class ServiceLifecycleBlockerTests(unittest.TestCase):
    @staticmethod
    def blockers(
        *,
        control=None,
        navigation_runtime=None,
        navigation_jobs=None,
        mapping_jobs=None,
        mapping_task_active=False,
    ):
        return collect_service_lifecycle_blockers(
            control=control
            if control is not None
            else {
                "lease": {"active": False, "input_source": None},
                "action_guard": {"active": False},
                "estop_latched": False,
            },
            navigation_runtime=navigation_runtime
            if navigation_runtime is not None
            else {"active": False, "goal": {"state": "idle"}},
            navigation_jobs=navigation_jobs
            if navigation_jobs is not None
            else {"pipeline": {"state": "idle"}},
            mapping_jobs=mapping_jobs
            if mapping_jobs is not None
            else {
                "pipeline": {"state": "idle"},
                "operation": {"state": "idle"},
            },
            mapping_task_active=mapping_task_active,
        )

    def test_idle_system_has_no_blockers(self):
        self.assertEqual(self.blockers(), [])

    def test_manual_lease_blocks_but_latched_stop_is_safe_for_restart(self):
        blockers = self.blockers(
            control={
                "lease": {"active": True, "input_source": "keyboard"},
                "action_guard": {"active": False},
                "estop_latched": True,
                "estop_reason": "dashboard_button",
            }
        )
        self.assertIn("manual_control_active", blockers)
        self.assertNotIn("software_stop_latched", blockers)

    def test_one_shot_action_blocks_but_nested_software_stop_does_not(self):
        blockers = self.blockers(
            control={
                "lease": {"active": False, "input_source": None},
                "action_guard": {"active": True},
                "estop": {"latched": True},
            }
        )
        self.assertIn("robot_action_active", blockers)
        self.assertNotIn("software_stop_latched", blockers)

    def test_navigation_lease_goal_and_pipeline_are_deduplicated(self):
        blockers = self.blockers(
            control={
                "lease": {"active": True, "input_source": "navigation"},
                "action_guard": {"active": False},
                "estop_latched": False,
            },
            navigation_runtime={"active": True, "goal": {"state": "active"}},
            navigation_jobs={"pipeline": {"state": "running"}},
        )
        self.assertEqual(blockers.count("navigation_active"), 1)

    def test_mapping_pipeline_operation_and_task_are_blockers(self):
        blockers = self.blockers(
            mapping_jobs={
                "pipeline": {"state": "starting"},
                "operation": {"state": "saving"},
            },
            mapping_task_active=True,
        )
        self.assertIn("mapping_pipeline_active", blockers)
        self.assertEqual(blockers.count("mapping_operation_active"), 1)

    def test_missing_snapshots_fail_closed(self):
        blockers = collect_service_lifecycle_blockers(
            control=None,
            navigation_runtime=None,
            navigation_jobs=None,
            mapping_jobs=None,
            mapping_task_active=False,
        )
        self.assertIn("control_status_unavailable", blockers)
        self.assertIn("navigation_status_unavailable", blockers)
        self.assertIn("mapping_status_unavailable", blockers)


if __name__ == "__main__":
    unittest.main()
