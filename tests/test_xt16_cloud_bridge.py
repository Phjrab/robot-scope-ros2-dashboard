import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    ROOT / "ros2" / "robot_scope_xt16_bridge" / "src" / "xt16_fastlio_bridge.cpp"
)
CMAKE_PATH = ROOT / "ros2" / "robot_scope_xt16_bridge" / "CMakeLists.txt"
CPP_TEST_PATH = (
    ROOT
    / "ros2"
    / "robot_scope_xt16_bridge"
    / "test"
    / "xt16_cloud_contract_test.cpp"
)
RUNNER_PATH = ROOT / "scripts" / "run_xt16_cloud_bridge_humble.sh"
BUILD_RUNNER_PATH = ROOT / "scripts" / "build_xt16_cloud_bridge_humble.sh"
DOCUMENT_PATH = ROOT / "docs" / "WIRELESS_XT16_CLOUD_BRIDGE.md"


def compiled_projection(source: str, *, cloud_only: bool) -> str:
    """Project only the one repository-owned feature macro used by this source."""

    output = []
    stack = []
    active = True
    for line in source.splitlines():
        directive = line.strip()
        if directive == "#if defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)":
            stack.append((active, cloud_only))
            active = active and cloud_only
        elif directive == "#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)":
            stack.append((active, not cloud_only))
            active = active and not cloud_only
        elif directive == "#else" and stack:
            parent, condition = stack[-1]
            stack[-1] = (parent, not condition)
            active = parent and not condition
        elif directive == "#endif" and stack:
            parent, _condition = stack.pop()
            active = parent
        elif active:
            output.append(line)
    if stack:
        raise AssertionError("unbalanced cloud-only preprocessor contract")
    return "\n".join(output)


class Xt16CloudOnlyBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.cloud = compiled_projection(cls.source, cloud_only=True)
        cls.legacy = compiled_projection(cls.source, cloud_only=False)
        cls.cmake = CMAKE_PATH.read_text(encoding="utf-8")
        cls.cpp_test = CPP_TEST_PATH.read_text(encoding="utf-8")
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")
        cls.build_runner = BUILD_RUNNER_PATH.read_text(encoding="utf-8")
        cls.document = DOCUMENT_PATH.read_text(encoding="utf-8")

    def test_cloud_target_is_explicit_and_has_no_unitree_target_dependency(self):
        self.assertIn("robot_scope_xt16_cloud_bridge_node", self.cmake)
        self.assertIn("ROBOT_SCOPE_XT16_CLOUD_ONLY=1", self.cmake)
        match = re.search(
            r"ament_target_dependencies\(\s*robot_scope_xt16_cloud_bridge_node(.*?)\)",
            self.cmake,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertIn("rclcpp", match.group(1))
        self.assertIn("sensor_msgs", match.group(1))
        self.assertNotIn("unitree_go", match.group(1))

    def test_runner_accepts_only_an_absolute_persistent_dependency_workspace(self):
        self.assertIn("ROBOT_SCOPE_DEPENDENCY_WORKSPACE_ROOT", self.runner)
        self.assertIn('DEPENDENCY_WORKSPACE_ROOT" == /*', self.runner)
        self.assertIn('DEPENDENCY_WORKSPACE_ROOT" != "/"', self.runner)
        self.assertIn(
            '$DEPENDENCY_WORKSPACE_ROOT/ws/xt16_bridge_ws/install/lib/',
            self.runner,
        )

    def test_cloud_projection_has_no_lowstate_or_imu_dependency(self):
        for forbidden in (
            "unitree_go",
            "/lowstate",
            "/imu/body",
            "sensor_msgs::msg::Imu",
            "on_lowstate",
            "imu_subscription_",
            "imu_publisher_",
        ):
            self.assertNotIn(forbidden, self.cloud)
        self.assertIn('Node("robot_scope_xt16_cloud_bridge")', self.cloud)
        self.assertIn('constexpr char kRawTopic[] = "/lidar_points"', self.cloud)
        self.assertIn(
            'constexpr char kOutputCloudTopic[] = "/velodyne_points"', self.cloud
        )

    def test_cloud_projection_preserves_layout_decimation_qos_and_cpp_path(self):
        for contract in (
            "constexpr std::size_t kCloudDecimation = 4",
            "constexpr std::size_t kOutputPointStep = 22",
            "message.height != 1",
            'require_field(message, "timestamp", 18, PointField::FLOAT64)',
            'set__name("time").set__offset(16)',
            'set__name("ring").set__offset(20)',
            "rclcpp::KeepLast(1)).reliable().durability_volatile()",
            "rclcpp::KeepLast(5)).reliable().durability_volatile()",
        ):
            self.assertIn(contract, self.cloud)
        self.assertNotIn("python", self.cloud.lower())

    def test_cloud_projection_preserves_timestamp_and_freshness_rejection(self):
        for contract in (
            "kClockResidualLimitS = 0.25",
            "kConvertedCloudMaxAgeS = 0.50",
            "kConvertedCloudMaxFutureS = 0.05",
            "raw cloud device timestamp did not increase",
            "sample rejected without clock rebase",
            "converted cloud age",
            "converted cloud future skew",
            "converted cloud timestamp did not increase",
        ):
            self.assertIn(contract, self.cloud)

    def test_legacy_projection_and_runner_remain_backward_compatible(self):
        for contract in (
            'Node("xt16_fastlio_bridge")',
            'constexpr char kLowStateTopic[] = "/lowstate"',
            'constexpr char kOutputImuTopic[] = "/imu/body"',
            "create_subscription<unitree_go::msg::LowState>",
            "create_publisher<sensor_msgs::msg::Imu>",
            "rclcpp::KeepLast(5)).best_effort().durability_volatile()",
        ):
            self.assertIn(contract, self.legacy)
        legacy_runner = (ROOT / "scripts" / "run_xt16_bridge_humble.sh").read_text()
        legacy_builder = (ROOT / "scripts" / "build_xt16_bridge_humble.sh").read_text()
        self.assertIn("robot_scope_xt16_bridge_node", legacy_runner)
        self.assertNotIn("robot_scope_xt16_cloud_bridge_node", legacy_runner)
        self.assertIn("-DROBOT_SCOPE_XT16_BUILD_LEGACY=ON", legacy_builder)

    def test_cloud_runner_is_fixed_cpp_only_and_does_not_bypass_network_contracts(self):
        subprocess.run(["bash", "-n", str(RUNNER_PATH)], check=True)
        self.assertIn("robot_scope_xt16_cloud_bridge_node", self.runner)
        self.assertIn("setup_wireless_mapping_ros2_humble.sh", self.runner)
        self.assertIn('[[ "$#" -ne 0 ]]', self.runner)
        for forbidden in (
            "run_xt16_bridge_humble.sh",
            "xt16_fastlio_bridge.py",
            "setup_go2_ros2_humble.sh",
            "ROBOT_SCOPE_GO2_INTERFACE_CIDR",
            "sysctl",
            "robot_scope_doctor",
        ):
            self.assertNotIn(forbidden, self.runner)

    def test_cloud_only_build_does_not_require_the_unitree_workspace(self):
        subprocess.run(["bash", "-n", str(BUILD_RUNNER_PATH)], check=True)
        self.assertIn("ROBOT_SCOPE_XT16_BUILD_LEGACY", self.cmake)
        self.assertIn("if(ROBOT_SCOPE_XT16_BUILD_LEGACY)", self.cmake)
        self.assertIn("find_package(unitree_go REQUIRED)", self.cmake)
        self.assertIn("-DROBOT_SCOPE_XT16_BUILD_LEGACY=OFF", self.build_runner)
        self.assertNotIn("ROBOT_SCOPE_UNITREE_SETUP", self.build_runner)
        self.assertNotIn("unitree_ros2", self.build_runner)
        self.assertNotIn("sudo", self.build_runner)

    def test_gate_document_separates_repository_pass_from_live_evidence(self):
        for contract in (
            "robot_scope_xt16_bridge_node",
            "robot_scope_xt16_cloud_bridge_node",
            "same reviewed",
            "C++ conversion source",
            "At Gate 7",
            "HW-4 remained `NOT_RUN`",
            "`CLOUD_PASS`",
            "`NOT_RUN`",
        ):
            self.assertIn(contract, self.document)

    def test_ctest_registers_a_ros_free_cloud_contract_executable(self):
        for contract in (
            "include(CTest)",
            "if(BUILD_TESTING)",
            "robot_scope_xt16_cloud_contract_test",
            "test/xt16_cloud_contract_test.cpp",
            "NAME robot_scope_xt16_cloud_contract",
        ):
            self.assertIn(contract, self.cmake)
        dependency = re.search(
            r"ament_target_dependencies\(\s*"
            r"robot_scope_xt16_cloud_contract_test(.*?)\)",
            self.cmake,
            re.DOTALL,
        )
        self.assertIsNotNone(dependency)
        self.assertIn("rclcpp", dependency.group(1))
        self.assertIn("sensor_msgs", dependency.group(1))
        self.assertNotIn("unitree_go", dependency.group(1))

    def test_cpp_contract_covers_layout_freshness_and_fail_closed_inputs(self):
        for contract in (
            "ROBOT_SCOPE_XT16_CLOUD_ONLY",
            "ROBOT_SCOPE_XT16_BRIDGE_NO_MAIN",
            "four-to-one decimation changed",
            "output stride changed",
            "device timestamp did not increase",
            "residual discontinuity",
            "frame must be hesai_lidar",
            "header does not match",
            "field x is duplicated",
            "payload length does not match",
            "too few finite decimated",
        ):
            self.assertIn(contract, self.cpp_test)
        self.assertNotIn("rclcpp::init", self.cpp_test)
        self.assertNotIn("spin", self.cpp_test)


if __name__ == "__main__":
    unittest.main()
