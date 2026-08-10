import ast
import unittest
from pathlib import Path

from robot_dashboard.service_lifecycle import collect_service_lifecycle_blockers


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "robot_dashboard" / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def function_node(name: str):
    for node in APP_TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} was not found")


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
    def test_mutations_require_same_origin_admin_token_and_lifecycle_manager(self):
        for name in ("service_lifecycle_restart", "service_lifecycle_stop"):
            calls = called_names(function_node(name))
            self.assertIn("require_same_origin", calls)
            self.assertIn("require_service_admin", calls)
            self.assertIn("service_lifecycle", calls)

    def test_confirmation_field_is_strict_and_admin_header_is_hashed_elsewhere(self):
        request_model = function_node("require_service_admin")
        calls = called_names(request_model)
        self.assertIn("get", calls)
        self.assertIn("authenticate", calls)
        self.assertNotIn("ROBOT_SCOPE_SERVICE_ADMIN_TOKEN_SHA256", ast.unparse(request_model))

        model = next(
            node
            for node in APP_TREE.body
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
        guarded = {
            "control_arm",
            "navigation_start",
            "navigation_initial_pose",
            "navigation_goal",
            "mapping_start",
            "mapping_save",
            "convert_saved_pcd_to_2d",
            "save_edited_map_copy",
            "rename_saved_map",
            "delete_saved_map",
        }
        for name in guarded:
            self.assertIn(
                "require_service_lifecycle_idle",
                called_names(function_node(name)),
                name,
            )

        cleanup = {
            "control_disarm",
            "control_stop",
            "navigation_stop",
            "navigation_cancel",
            "navigation_clear_costmaps",
            "mapping_stop",
        }
        for name in cleanup:
            self.assertNotIn(
                "require_service_lifecycle_idle",
                called_names(function_node(name)),
                name,
            )

        control_arm = function_node("control_arm")
        critical_sections = [
            child for child in control_arm.body if isinstance(child, ast.AsyncWith)
        ]
        self.assertEqual(len(critical_sections), 1)
        critical_calls = called_names(critical_sections[0])
        self.assertIn("require_service_lifecycle_idle", critical_calls)
        self.assertIn("control_acquire", critical_calls)


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

    def test_manual_lease_and_top_level_software_stop_are_blockers(self):
        blockers = self.blockers(
            control={
                "lease": {"active": True, "input_source": "keyboard"},
                "action_guard": {"active": False},
                "estop_latched": True,
                "estop_reason": "dashboard_button",
            }
        )
        self.assertIn("manual_control_active", blockers)
        self.assertIn("software_stop_latched", blockers)

    def test_nested_software_stop_and_one_shot_action_are_blockers(self):
        blockers = self.blockers(
            control={
                "lease": {"active": False, "input_source": None},
                "action_guard": {"active": True},
                "estop": {"latched": True},
            }
        )
        self.assertIn("robot_action_active", blockers)
        self.assertIn("software_stop_latched", blockers)

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
