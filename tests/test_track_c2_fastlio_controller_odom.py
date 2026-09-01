import copy
from dataclasses import replace
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

from robot_dashboard.navigation_jobs import (
    COMPETITION_FASTLIO_NAVIGATION_PROFILE,
    FASTLIO_CONTROLLER_ODOM_TOPIC,
    NavigationJobManager,
    PARAMETER_FIELDS,
    SAFE_TUNED_PARAMETERS,
    STRICT_CONTROLLER_ODOM_TOPIC,
)
from robot_dashboard.navigation_runtime import (
    ControllerOdometrySample,
    FastLioControllerOdomGate,
    NavigationRuntimeError,
)
from robot_dashboard.ros.navigation_gateway import (
    NAVIGATION_FASTLIO_CONTROLLER_ODOM_TOPIC,
    NavigationRosGateway,
)


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


no_goal = load_script("track_c2_no_goal", "check_competition_no_goal_ready.py")


def completed(argv, returncode=0, stdout=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def safe_control():
    return {
        "control": {
            "lease": {"active": False},
            "command": {
                "deadman": False,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
        }
    }


def sample(**changes):
    base = ControllerOdometrySample(
        stamp_ns=10_000_000_000,
        parent_frame="camera_init",
        child_frame="body",
        position=(1.0, 2.0, 0.1),
        orientation=(0.0, 0.0, 0.0, 1.0),
        linear_velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        pose_covariance=(0.0,) * 36,
        twist_covariance=(0.0,) * 36,
    )
    return replace(base, **changes)


def observe(gate, value=None, **changes):
    return gate.observe(
        value or sample(),
        now_ns=changes.pop("now_ns", 10_100_000_000),
        observed_monotonic=changes.pop("observed_monotonic", 1.0),
        input_publishers=changes.pop("input_publishers", 1),
        output_publishers=changes.pop("output_publishers", 1),
        process_generation=changes.pop("process_generation", 7),
        **changes,
    )


class FastLioControllerOdomGateTests(unittest.TestCase):
    def test_valid_sample_preserves_stamp_and_uses_canonical_frames(self):
        output = observe(FastLioControllerOdomGate())
        self.assertEqual(output.stamp_ns, 10_000_000_000)
        self.assertEqual((output.parent_frame, output.child_frame), ("odom", "base_link"))
        self.assertEqual(output.sample, sample())

    def test_frame_mismatch_zero_stamp_and_nonadvancing_stamp_fail_closed(self):
        with self.assertRaisesRegex(NavigationRuntimeError, "frames"):
            observe(FastLioControllerOdomGate(), sample(parent_frame="odom"))
        with self.assertRaisesRegex(NavigationRuntimeError, "zero"):
            observe(FastLioControllerOdomGate(), sample(stamp_ns=0))
        gate = FastLioControllerOdomGate()
        observe(gate)
        with self.assertRaisesRegex(NavigationRuntimeError, "did not increase"):
            observe(gate, observed_monotonic=1.1)

    def test_stale_and_future_stamp_fail_closed(self):
        with self.assertRaisesRegex(NavigationRuntimeError, "stale"):
            observe(FastLioControllerOdomGate(), now_ns=10_600_000_001)
        with self.assertRaisesRegex(NavigationRuntimeError, "future"):
            observe(FastLioControllerOdomGate(), now_ns=9_749_999_999)

    def test_nonfinite_quaternion_and_implausible_velocity_fail_closed(self):
        with self.assertRaisesRegex(NavigationRuntimeError, "finite"):
            observe(
                FastLioControllerOdomGate(),
                sample(position=(float("nan"), 0.0, 0.0)),
            )
        with self.assertRaisesRegex(NavigationRuntimeError, "quaternion"):
            observe(
                FastLioControllerOdomGate(),
                sample(orientation=(0.0, 0.0, 0.0, 0.0)),
            )
        with self.assertRaisesRegex(NavigationRuntimeError, "implausible"):
            observe(
                FastLioControllerOdomGate(),
                sample(linear_velocity=(5.1, 0.0, 0.0)),
            )

    def test_translation_and_heading_jump_fail_closed(self):
        gate = FastLioControllerOdomGate()
        observe(gate)
        with self.assertRaisesRegex(NavigationRuntimeError, "translation"):
            observe(
                gate,
                sample(stamp_ns=10_020_000_000, position=(4.0, 2.0, 0.1)),
                now_ns=10_120_000_000,
                observed_monotonic=1.02,
            )
        gate = FastLioControllerOdomGate()
        observe(gate)
        yaw = 2.0
        with self.assertRaisesRegex(NavigationRuntimeError, "heading"):
            observe(
                gate,
                sample(
                    stamp_ns=10_020_000_000,
                    orientation=(0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)),
                ),
                now_ns=10_120_000_000,
                observed_monotonic=1.02,
            )

    def test_publisher_conflicts_silence_and_generation_change_fail_closed(self):
        with self.assertRaisesRegex(NavigationRuntimeError, "input publisher"):
            observe(FastLioControllerOdomGate(), input_publishers=2)
        with self.assertRaisesRegex(NavigationRuntimeError, "output publisher"):
            observe(FastLioControllerOdomGate(), output_publishers=2)
        gate = FastLioControllerOdomGate()
        observe(gate)
        self.assertTrue(gate.snapshot(1.70)["ready"])
        self.assertFalse(gate.snapshot(1.76)["ready"])
        with self.assertRaisesRegex(NavigationRuntimeError, "generation changed"):
            observe(
                gate,
                sample(stamp_ns=10_020_000_000),
                now_ns=10_120_000_000,
                observed_monotonic=1.02,
                process_generation=8,
            )
        self.assertFalse(gate.snapshot(1.03)["ready"])
        with self.assertRaisesRegex(NavigationRuntimeError, "generation changed"):
            observe(
                gate,
                sample(stamp_ns=10_040_000_000),
                now_ns=10_140_000_000,
                observed_monotonic=1.04,
                process_generation=8,
            )


class TrackC2ProfileTests(unittest.TestCase):
    def test_strict_and_competition_profiles_select_only_fixed_topics(self):
        strict = NavigationRosGateway(
            object(),
            node_getter=lambda: None,
            tick=lambda *_: None,
            graph_getter=lambda: {},
        )
        competition = NavigationRosGateway(
            object(),
            node_getter=lambda: None,
            tick=lambda *_: None,
            graph_getter=lambda: {},
            navigation_profile=COMPETITION_FASTLIO_NAVIGATION_PROFILE,
        )
        self.assertEqual(strict._controller_odom_topic, STRICT_CONTROLLER_ODOM_TOPIC)
        self.assertEqual(
            competition._controller_odom_topic,
            NAVIGATION_FASTLIO_CONTROLLER_ODOM_TOPIC,
        )
        with self.assertRaisesRegex(ValueError, "unsupported"):
            NavigationRosGateway(
                object(),
                node_getter=lambda: None,
                tick=lambda *_: None,
                graph_getter=lambda: {},
                navigation_profile="http-selected-topic",
            )

    def test_profile_parameter_patch_is_deterministic_and_default_unchanged(self):
        document = yaml.safe_load(
            (ROOT / "config" / "nav2_params_go2_humble.yaml").read_text()
        )
        base = copy.deepcopy(document)
        strict = NavigationJobManager._patch_yaml(
            copy.deepcopy(document),
            SAFE_TUNED_PARAMETERS,
        )
        competition = NavigationJobManager._patch_yaml(
            copy.deepcopy(document),
            SAFE_TUNED_PARAMETERS,
            controller_odom_topic=FASTLIO_CONTROLLER_ODOM_TOPIC,
            controller_odom_mode="competition_fastlio",
        )
        self.assertEqual(
            strict["controller_server"]["ros__parameters"]["odom_topic"],
            STRICT_CONTROLLER_ODOM_TOPIC,
        )
        for node in ("bt_navigator", "controller_server"):
            self.assertEqual(
                competition[node]["ros__parameters"]["odom_topic"],
                FASTLIO_CONTROLLER_ODOM_TOPIC,
            )
        runtime = competition["robot_scope_navigation_runtime"]["ros__parameters"]
        self.assertEqual(runtime["controller_odom_mode"], "competition_fastlio")
        self.assertEqual(runtime["controller_odom_topic"], FASTLIO_CONTROLLER_ODOM_TOPIC)
        self.assertEqual(
            base["controller_server"]["ros__parameters"]["odom_topic"],
            STRICT_CONTROLLER_ODOM_TOPIC,
        )
        self.assertNotIn("controller_odom_topic", PARAMETER_FIELDS)
        self.assertNotIn("controller_odom_mode", PARAMETER_FIELDS)

    def test_c2_launcher_never_starts_wireless_onboard_odometry_or_motion_bridge(self):
        source = (ROOT / "scripts" / "run_go2_navigation_humble.sh").read_text()
        start = source.index("  go2-xt16-wireless-competition-fastlio)")
        end = source.index("  *)", start)
        branch = source[start:end]
        self.assertIn("setup_wireless_mapping_ros2_humble.sh", branch)
        self.assertNotIn("wireless_odom", branch)
        self.assertNotIn("cmd_vel_to_sport", source)
        self.assertNotIn("/api/sport/request", source)
        self.assertIn("stop_children", source)
        self.assertIn("trap 'stop_children 130' INT TERM", source)
        self.assertIn("wait -n", source)

    def test_strict_wireless_guards_and_direct_profile_remain_intact(self):
        protocol = (ROOT / "scripts" / "wireless_odom_protocol.py").read_text()
        self.assertIn("MAX_SOURCE_AGE_NS = 500_000_000", protocol)
        self.assertIn("MAX_FUTURE_SKEW_NS = 100_000_000", protocol)
        launcher = (ROOT / "scripts" / "run_go2_navigation_humble.sh").read_text()
        self.assertIn("  competition-pdf-direct)", launcher)
        self.assertIn('if [[ "$MAPPING_PROFILE" == "go2-xt16-wireless" ]]', launcher)


class TrackC2NoGoalTests(unittest.TestCase):
    environment = {
        "ROBOT_SCOPE_MAPPING_PROFILE": no_goal.TRACK_C2_PROFILE,
        "ROS_DISTRO": "humble",
    }

    @staticmethod
    def runner(argv, **_kwargs):
        values = tuple(argv)
        if values[1:3] == ("node", "list"):
            return completed(values, stdout="\n".join(no_goal.LIFECYCLE_NODES) + "\n")
        if values[1:3] == ("topic", "list"):
            return completed(values, stdout=f"{no_goal.RAW_COMMAND_TOPIC}\n")
        if values[:2] == (no_goal.TIMEOUT, "3") and "lifecycle" in values:
            return completed(values, stdout="active [3]\n")
        if values[1:3] == ("topic", "info"):
            return completed(values, stdout="Publisher count: 1\n")
        if values[:2] == (no_goal.TIMEOUT, "3") and "topic" in values:
            return completed(values, stdout="fresh sample\n")
        if "tf2_echo" in values:
            if values[-2:] == ("odom", "base_link"):
                return completed(values, returncode=124, stdout="Translation:\nRotation:\n")
            return completed(values, returncode=124)
        if values[:2] == (no_goal.TIMEOUT, "2"):
            return completed(values, returncode=124)
        raise AssertionError(values)

    def test_ng0_does_not_require_map_to_base_link(self):
        result = no_goal.check(
            stage="prelocalization",
            environment=self.environment,
            runner=self.runner,
            control_fetcher=safe_control,
            ros2="/opt/ros/humble/bin/ros2",
        )
        self.assertEqual(result["localization"], "WAITING_FOR_INITIAL_POSE")

    def test_ng1_requires_map_to_base_link(self):
        with self.assertRaisesRegex(no_goal.NoGoalError, "map to base_link"):
            no_goal.check(
                stage="localized",
                environment=self.environment,
                runner=self.runner,
                control_fetcher=safe_control,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_ng0_allows_prelocolization_lifecycle_but_ng1_requires_all_active(self):
        def staged_runner(argv, **kwargs):
            values = tuple(argv)
            if (
                values[:2] == (no_goal.TIMEOUT, "3")
                and "lifecycle" in values
                and values[-1] == "/planner_server"
            ):
                return completed(values, stdout="inactive [2]\n")
            if "tf2_echo" in values:
                return completed(values, returncode=124, stdout="Translation:\nRotation:\n")
            return self.runner(argv, **kwargs)

        result = no_goal.check(
            stage="prelocalization",
            environment=self.environment,
            runner=staged_runner,
            control_fetcher=safe_control,
            ros2="/opt/ros/humble/bin/ros2",
        )
        self.assertEqual(result["stage"], "prelocalization")
        with self.assertRaisesRegex(no_goal.NoGoalError, "planner_server"):
            no_goal.check(
                stage="localized",
                environment=self.environment,
                runner=staged_runner,
                control_fetcher=safe_control,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_ng0_detects_nonzero_motion_output(self):
        def moving_runner(argv, **kwargs):
            values = tuple(argv)
            result = self.runner(argv, **kwargs)
            if values[:2] == (no_goal.TIMEOUT, "2") and no_goal.RAW_COMMAND_TOPIC in values:
                return completed(
                    values,
                    stdout=(
                        "linear:\n  x: 0.1\n  y: 0.0\n  z: 0.0\n"
                        "angular:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n"
                    ),
                )
            return result

        with self.assertRaisesRegex(no_goal.NoGoalError, "non-zero raw command"):
            no_goal.check(
                stage="prelocalization",
                environment=self.environment,
                runner=moving_runner,
                control_fetcher=safe_control,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_ng0_detects_sport_output_but_accepts_an_absent_bridge_topic(self):
        absent = no_goal.check(
            stage="prelocalization",
            environment=self.environment,
            runner=self.runner,
            control_fetcher=safe_control,
            ros2="/opt/ros/humble/bin/ros2",
        )
        self.assertEqual(absent["stage"], "prelocalization")

        def sport_runner(argv, **kwargs):
            values = tuple(argv)
            if values[1:3] == ("topic", "list"):
                return completed(
                    values,
                    stdout=f"{no_goal.RAW_COMMAND_TOPIC}\n{no_goal.SPORT_TOPIC}\n",
                )
            if values[1:3] == ("topic", "info") and values[-1] == no_goal.SPORT_TOPIC:
                return completed(values, stdout="Publisher count: 1\n")
            if values[:2] == (no_goal.TIMEOUT, "2") and values[-2] == no_goal.SPORT_TOPIC:
                return completed(values, stdout="api_id: 1008\n")
            return self.runner(argv, **kwargs)

        with self.assertRaisesRegex(no_goal.NoGoalError, "unexpected sport request"):
            no_goal.check(
                stage="prelocalization",
                environment=self.environment,
                runner=sport_runner,
                control_fetcher=safe_control,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_ng0_rejects_lease_deadman_or_nonzero_dashboard_velocity(self):
        for command in (
            {"lease": {"active": True}, "command": safe_control()["control"]["command"]},
            {
                "lease": {"active": False},
                "command": {**safe_control()["control"]["command"], "deadman": True},
            },
            {
                "lease": {"active": False},
                "command": {**safe_control()["control"]["command"], "linear_x": 0.01},
            },
        ):
            with self.assertRaises(no_goal.NoGoalError):
                no_goal.check(
                    stage="prelocalization",
                    environment=self.environment,
                    runner=self.runner,
                    control_fetcher=lambda command=command: {"control": command},
                    ros2="/opt/ros/humble/bin/ros2",
                )


if __name__ == "__main__":
    unittest.main()
