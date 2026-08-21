import ast
import importlib.machinery
import importlib.util
import inspect
import sys
import threading
import types
import unittest
from pathlib import Path


def _install_ros_stubs():
    class Dummy:
        pass

    rclpy = types.ModuleType("rclpy")
    rclpy.__spec__ = importlib.machinery.ModuleSpec("rclpy", loader=None)
    rclpy.ok = lambda: False
    rclpy.init = lambda **_kwargs: None
    rclpy.shutdown = lambda: None
    stubs = {
        "rclpy": rclpy,
        "rclpy.callback_groups": types.ModuleType("rclpy.callback_groups"),
        "rclpy.executors": types.ModuleType("rclpy.executors"),
        "rclpy.node": types.ModuleType("rclpy.node"),
        "rclpy.qos": types.ModuleType("rclpy.qos"),
        "rosidl_runtime_py": types.ModuleType("rosidl_runtime_py"),
        "rosidl_runtime_py.utilities": types.ModuleType(
            "rosidl_runtime_py.utilities"
        ),
        "std_msgs": types.ModuleType("std_msgs"),
        "std_msgs.msg": types.ModuleType("std_msgs.msg"),
    }
    stubs["rclpy.callback_groups"].MutuallyExclusiveCallbackGroup = Dummy
    stubs["rclpy.executors"].MultiThreadedExecutor = Dummy
    stubs["rclpy.node"].Node = Dummy
    for name in ("DurabilityPolicy", "HistoryPolicy", "QoSProfile", "ReliabilityPolicy"):
        setattr(stubs["rclpy.qos"], name, Dummy)
    stubs["rosidl_runtime_py.utilities"].get_message = lambda _value: Dummy
    stubs["std_msgs.msg"].String = Dummy
    sys.modules.update(stubs)


try:
    _RCLPY_AVAILABLE = importlib.util.find_spec("rclpy") is not None
except (ImportError, ValueError):
    existing = sys.modules.get("rclpy")
    _RCLPY_AVAILABLE = bool(getattr(existing, "__file__", None))

if not _RCLPY_AVAILABLE:
    _install_ros_stubs()

from robot_dashboard.ros.control_transport import (  # noqa: E402
    CONTROL_COMMAND_TOPIC,
    CONTROL_STATUS_TOPIC,
    ControlTransport,
)
from robot_dashboard.ros.navigation_gateway import (  # noqa: E402
    NAVIGATION_CMD_VEL_TOPIC,
    NavigationRosGateway,
    public_navigation_reason,
)
from robot_dashboard import ros_agent as ros_agent_module  # noqa: E402
from robot_dashboard.ros_agent import RosAgent  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "robot_dashboard" / "ros_agent.py"
CONTROL_PATH = ROOT / "robot_dashboard" / "ros" / "control_transport.py"
NAVIGATION_PATH = ROOT / "robot_dashboard" / "ros" / "navigation_gateway.py"
CONTROL_MANAGER_PATH = ROOT / "robot_dashboard" / "control.py"


class RosControlNavigationArchitectureTests(unittest.TestCase):
    def test_agent_constructs_one_transport_and_gateway_with_one_manager_lock(self):
        agent = RosAgent()

        self.assertIsInstance(agent._control_transport, ControlTransport)
        self.assertIsInstance(agent._navigation_gateway, NavigationRosGateway)
        self.assertIs(
            agent._navigation_gateway._control_port,
            agent._control_transport,
        )
        self.assertIs(
            agent._navigation_gateway._control_port.manager,
            agent._control_manager,
        )
        self.assertIs(
            agent._navigation_gateway._control_port.operation_lock,
            agent._control_operation_lock,
        )
        self.assertIsNot(agent._navigation_lock, agent._control_transport_lock)

        tree = ast.parse(AGENT_PATH.read_text(encoding="utf-8"))
        init = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        calls = [
            node.func.id
            for node in ast.walk(init)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertEqual(calls.count("ControlTransport"), 1)
        self.assertEqual(calls.count("NavigationRosGateway"), 1)

    def test_components_keep_the_phase5_dependency_boundary(self):
        control_source = CONTROL_PATH.read_text(encoding="utf-8")
        navigation_source = NAVIGATION_PATH.read_text(encoding="utf-8")
        manager_source = CONTROL_MANAGER_PATH.read_text(encoding="utf-8")

        def imported_modules(source):
            modules = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    modules.add("." * node.level + (node.module or ""))
            return modules

        control_imports = imported_modules(control_source)
        navigation_imports = imported_modules(navigation_source)
        for forbidden in ("fastapi", "..app", ".navigation_gateway", "..navigation_jobs"):
            self.assertNotIn(forbidden, control_imports)
        for forbidden in ("fastapi", "..app", "..navigation_jobs", "..mapping_jobs"):
            self.assertNotIn(forbidden, navigation_imports)
        self.assertNotIn("rclpy", manager_source)

    def test_facade_reexports_fixed_topics_and_reason_helper(self):
        self.assertEqual(ros_agent_module.CONTROL_COMMAND_TOPIC, CONTROL_COMMAND_TOPIC)
        self.assertEqual(ros_agent_module.CONTROL_STATUS_TOPIC, CONTROL_STATUS_TOPIC)
        self.assertEqual(
            ros_agent_module.NAVIGATION_CMD_VEL_TOPIC,
            NAVIGATION_CMD_VEL_TOPIC,
        )
        self.assertIs(
            ros_agent_module._public_navigation_reason,
            public_navigation_reason,
        )

    def test_public_control_and_navigation_signatures_remain_stable(self):
        expected_parameters = {
            "control_snapshot": ("self",),
            "control_acquire": ("self", "input_source"),
            "control_bind": ("self", "token", "binding"),
            "control_heartbeat": ("self", "token", "binding", "seq"),
            "control_drive": ("self", "token", "binding", "seq", "kwargs"),
            "control_action": (
                "self",
                "token",
                "binding",
                "seq",
                "action",
                "confirm",
            ),
            "control_release": ("self", "token", "binding"),
            "control_estop": ("self", "reason"),
            "control_clear_estop": ("self", "confirm"),
            "shutdown_control": ("self",),
            "navigation_activate": (
                "self",
                "map_id",
                "map_revision",
                "map_name",
                "ready_after",
            ),
            "navigation_start_preflight": ("self",),
            "navigation_prelocalization_snapshot": ("self", "ready_after"),
            "navigation_deactivate": ("self", "reason"),
            "navigation_set_initial_pose": (
                "self",
                "map_id",
                "map_revision",
                "x",
                "y",
                "yaw",
            ),
            "navigation_send_goal": (
                "self",
                "map_id",
                "map_revision",
                "x",
                "y",
                "yaw",
            ),
            "navigation_cancel_goal": ("self", "goal_id"),
            "navigation_clear_costmaps": ("self", "scope"),
            "navigation_runtime_snapshot": ("self",),
        }
        for name, expected in expected_parameters.items():
            with self.subTest(name=name):
                self.assertEqual(
                    tuple(inspect.signature(getattr(RosAgent, name)).parameters),
                    expected,
                )

    def test_control_tick_keeps_navigation_fences_around_publication(self):
        events = []

        class FakeTransport:
            def __init__(self):
                self.operation_lock = threading.RLock()

            def update_staleness_locked(self, _now):
                events.append("bridge-staleness")

            def manager_tick_locked(self):
                events.append("manager-tick")
                return [{"type": "stop", "reason": "test"}]

            def publish_outputs(self, _outputs, **_kwargs):
                events.append("publish")

        class FakeNavigation:
            def __init__(self):
                self.reconciles = 0

            def reconcile_control_locked(self, _now):
                self.reconciles += 1
                events.append(f"navigation-reconcile-{self.reconciles}")
                return None

            def keepalive_locked(self, _now):
                events.append("navigation-keepalive")
                return None

        agent = object.__new__(RosAgent)
        agent._control_transport = FakeTransport()
        agent._navigation_gateway = FakeNavigation()

        agent._control_tick()

        self.assertEqual(
            events,
            [
                "navigation-reconcile-1",
                "navigation-keepalive",
                "bridge-staleness",
                "manager-tick",
                "publish",
                "navigation-reconcile-2",
            ],
        )

    def test_stop_deactivates_navigation_and_control_before_executor(self):
        events = []

        class FakeNavigation:
            def deactivate(self, reason):
                events.append(f"navigation:{reason}")
                return {}

        class FakeTransport:
            def shutdown(self):
                events.append("control-shutdown")

        class FakeRuntime:
            def request_stop(self):
                events.append("runtime-stop")

            def shutdown_executor(self):
                events.append("executor-shutdown")

            def join(self):
                events.append("runtime-join")

        agent = object.__new__(RosAgent)
        agent._navigation_gateway = FakeNavigation()
        agent._control_transport = FakeTransport()
        agent._ros_runtime = FakeRuntime()
        agent._camera_hub = types.SimpleNamespace(
            shutdown=lambda: events.append("camera-shutdown")
        )

        agent.stop()

        self.assertEqual(
            events,
            [
                "navigation:agent_stop",
                "control-shutdown",
                "runtime-stop",
                "camera-shutdown",
                "executor-shutdown",
                "runtime-join",
            ],
        )


if __name__ == "__main__":
    unittest.main()
