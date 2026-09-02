import base64
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "track_c4_navigation_ready",
        ROOT / "scripts" / "check_track_c4_navigation_ready.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


c4 = load_script()


def completed(argv, returncode=0, stdout=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def safe_control():
    return {
        "control": {
            "enabled": True,
            "configured": True,
            "available": True,
            "estop_latched": False,
            "bridge": {
                "ready": True,
                "authenticated": True,
                "connected": True,
                "available": True,
                "status_age_s": 0.1,
                "lowstate_age_ms": 1,
                "lowstate_publishers": 1,
                "sport_subscribers": 1,
                "own_sport_publishers": 1,
                "foreign_named_sport_publishers": 0,
                "bare_unitree_sport_publishers": 10,
                "expected_bare_sport_publishers": 10,
                "total_sport_publishers": 11,
            },
            "lease": {
                "active": True,
                "bound": True,
                "input_source": "navigation",
            },
            "command": {
                "deadman": False,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
            "limits": {
                "max_linear_x": 0.30,
                "default_speed_scale": 0.35,
            },
        }
    }


def safe_navigation():
    return {
        "available": True,
        "robot_online": True,
        "pipeline": {"state": "running"},
        "session_mode": "navigation",
        "map": {"id": c4.MAP_ID, "revision": c4.MAP_REVISION},
        "localization": {"state": "localized"},
        "localization_session": {"active": False},
        "goal": {"state": "idle"},
        "safety": {"can_send_goal": True},
        "localization_health": {"state": "READY"},
        "bindings": {
            "navigation_profile": c4.PROFILE,
            "controller_odometry": c4.CONTROLLER_ODOM,
            "command": c4.RAW_COMMAND_TOPIC,
        },
        "readiness": {
            "map_server": True,
            "localization": True,
            "planner": True,
            "controller": True,
            "behavior": True,
            "cmd_bridge": True,
            "map": True,
            "scan": True,
            "odometry": True,
            "tf": True,
            "action_server": True,
            "cmd_vel_publishers": 1,
            "scan_publishers": 1,
            "odometry_publishers": 1,
            "controller_odometry_publishers": 1,
            "runtime_health_publishers": 1,
            "localization_publishers": 1,
        },
    }


def safe_parameters():
    return {
        "revision": "a" * 64,
        "values": {
            **c4.C4_PARAMETER_VALUES,
            "closed_loop": False,
            "use_rotate_to_heading": False,
        },
    }


def safe_map_data():
    width = height = 100
    occupancy = bytearray(width * height)
    for index in range(width):
        occupancy[index] = 100
        occupancy[(height - 1) * width + index] = 100
        occupancy[index * width] = 100
        occupancy[index * width + width - 1] = 100
    return {
        "map_id": c4.MAP_ID,
        "revision": c4.MAP_REVISION,
        "width": width,
        "height": height,
        "resolution": 0.05,
        "origin": [-1.0, -1.0, 0.0],
        "data_encoding": "int8-base64",
        "data_b64": base64.b64encode(occupancy).decode("ascii"),
    }


class TrackC4NavigationReadyTests(unittest.TestCase):
    environment = {
        "ROBOT_SCOPE_MAPPING_PROFILE": c4.PROFILE,
        "ROS_DISTRO": "humble",
    }

    @staticmethod
    def runner(argv, **_kwargs):
        values = tuple(argv)
        if values[1:3] == ("node", "list"):
            return completed(values, stdout="\n".join(c4.LIFECYCLE_NODES) + "\n")
        if values[:2] == (c4.TIMEOUT, "3") and "lifecycle" in values:
            return completed(values, stdout="active [3]\n")
        if values[1:3] == ("topic", "info"):
            return completed(values, stdout="Publisher count: 1\n")
        if values[:2] == (c4.TIMEOUT, "3") and "topic" in values:
            return completed(values, stdout="fresh sample\n")
        if "tf2_echo" in values:
            return completed(values, returncode=124, stdout="Translation:\nRotation:\n")
        if values[:2] == (c4.TIMEOUT, "2"):
            return completed(values, returncode=124)
        raise AssertionError(values)

    def check(self, *, control=None, navigation=None, runner=None):
        return c4.check(
            environment=self.environment,
            runner=runner or self.runner,
            control_fetcher=lambda: control or safe_control(),
            navigation_fetcher=lambda: navigation or safe_navigation(),
            parameters_fetcher=safe_parameters,
            map_data_fetcher=safe_map_data,
            ros2="/opt/ros/humble/bin/ros2",
        )

    def test_normal_localized_navigation_with_exclusive_lease_is_ready(self):
        result = self.check()
        self.assertEqual(result["goal"], "IDLE")
        self.assertEqual(result["raw_command"], "quiet")
        self.assertEqual(result["map_revision"], c4.MAP_REVISION)

    def test_localization_only_or_existing_goal_is_rejected(self):
        for changes in (
            {
                "session_mode": "localization_only",
                "localization_session": {"active": True},
            },
            {"goal": {"state": "active"}},
        ):
            navigation = safe_navigation()
            navigation.update(changes)
            with self.subTest(changes=changes), self.assertRaises(c4.C4ReadyError):
                self.check(navigation=navigation)

    def test_wrong_map_localization_health_or_binding_is_rejected(self):
        mutations = (
            ("map", "revision", "0" * 64),
            ("localization_health", "state", "DEGRADED"),
            ("bindings", "controller_odometry", "/utlidar/robot_odom"),
        )
        for section, key, value in mutations:
            navigation = safe_navigation()
            navigation[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(
                c4.C4ReadyError
            ):
                self.check(navigation=navigation)

    def test_navigation_lease_must_be_bound_and_command_must_be_zero(self):
        controls = []
        missing_lease = safe_control()
        missing_lease["control"]["lease"]["active"] = False
        controls.append(missing_lease)
        manual_lease = safe_control()
        manual_lease["control"]["lease"]["input_source"] = "keyboard"
        controls.append(manual_lease)
        moving = safe_control()
        moving["control"]["command"]["linear_x"] = 0.01
        controls.append(moving)
        for control in controls:
            with self.subTest(control=control), self.assertRaises(c4.C4ReadyError):
                self.check(control=control)

    def test_bridge_cardinality_and_freshness_remain_exact(self):
        mutations = (
            ("bare_unitree_sport_publishers", 9),
            ("foreign_named_sport_publishers", 1),
            ("total_sport_publishers", 12),
            ("status_age_s", 0.751),
            ("lowstate_age_ms", 501),
        )
        for key, value in mutations:
            control = safe_control()
            control["control"]["bridge"][key] = value
            with self.subTest(key=key), self.assertRaises(c4.C4ReadyError):
                self.check(control=control)

    def test_c4_speed_scale_and_velocity_clamp_remain_exact(self):
        for key, value in (
            ("default_speed_scale", 0.36),
            ("max_linear_x", 0.31),
        ):
            control = safe_control()
            control["control"]["limits"][key] = value
            with self.subTest(key=key), self.assertRaises(c4.C4ReadyError):
                self.check(control=control)

    def test_short_goal_parameters_are_pinned(self):
        for key, value in (
            ("desired_linear_vel", 0.25),
            ("xy_goal_tolerance", 0.35),
            ("required_movement_radius", 0.20),
        ):
            parameters = safe_parameters()
            parameters["values"][key] = value
            with self.subTest(key=key), self.assertRaises(c4.C4ReadyError):
                c4.check(
                    environment=self.environment,
                    runner=self.runner,
                    control_fetcher=safe_control,
                    navigation_fetcher=safe_navigation,
                    parameters_fetcher=lambda: parameters,
                    map_data_fetcher=safe_map_data,
                    ros2="/opt/ros/humble/bin/ros2",
                )

    def test_route_includes_robot_radius_and_stopping_buffer(self):
        payload = safe_map_data()
        occupancy = bytearray(base64.b64decode(payload["data_b64"]))
        obstacle_x, obstacle_y = 0.40, 0.20
        column = int((obstacle_x - payload["origin"][0]) / payload["resolution"])
        row = int((obstacle_y - payload["origin"][1]) / payload["resolution"])
        occupancy[row * payload["width"] + column] = 100
        payload["data_b64"] = base64.b64encode(occupancy).decode("ascii")

        with self.assertRaisesRegex(c4.C4ReadyError, "corridor"):
            c4.check(
                environment=self.environment,
                runner=self.runner,
                control_fetcher=safe_control,
                navigation_fetcher=safe_navigation,
                parameters_fetcher=safe_parameters,
                map_data_fetcher=lambda: payload,
                ros2="/opt/ros/humble/bin/ros2",
            )

    def test_all_readiness_counts_and_lifecycle_nodes_are_required(self):
        navigation = safe_navigation()
        navigation["readiness"]["planner"] = False
        with self.assertRaisesRegex(c4.C4ReadyError, "planner"):
            self.check(navigation=navigation)

        def missing_node(argv, **kwargs):
            values = tuple(argv)
            if values[1:3] == ("node", "list"):
                return completed(values, stdout="/map_server\n")
            return self.runner(argv, **kwargs)

        with self.assertRaisesRegex(c4.C4ReadyError, "child node"):
            self.check(runner=missing_node)

    def test_nonzero_raw_command_is_rejected(self):
        def moving_runner(argv, **kwargs):
            values = tuple(argv)
            if values[:2] == (c4.TIMEOUT, "2"):
                return completed(
                    values,
                    stdout=(
                        "linear:\n  x: 0.02\n  y: 0.0\n  z: 0.0\n"
                        "angular:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n"
                    ),
                )
            return self.runner(argv, **kwargs)

        with self.assertRaisesRegex(c4.C4ReadyError, "raw command is non-zero"):
            self.check(runner=moving_runner)

    def test_checker_does_not_claim_external_sport_topic_visibility(self):
        source = (ROOT / "scripts" / "check_track_c4_navigation_ready.py").read_text()
        self.assertNotIn("/api/sport/request", source)
        self.assertNotIn("SPORT_TOPIC", source)


if __name__ == "__main__":
    unittest.main()
