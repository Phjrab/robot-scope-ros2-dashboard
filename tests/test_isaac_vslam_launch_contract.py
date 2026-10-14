"""Offline safety/regression checks for the standalone Isaac ROS experiment."""

import datetime as dt
import ast
import json
from pathlib import Path
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments" / "isaac_vslam" / "config"
API = runpy.run_path(str(CONFIG / "launch_contract.py"))


def input_contract():
    return {
        "schema_version": 1, "observation_state": "OBSERVED", "evidence_path": "/lab/run/observations.json",
        "source": {"kind": "bag", "id": "fixture-only", "sha256": "a" * 64},
        "base_frame": "fixture_camera_link", "rectified_images": True,
        "calibration_verified": True, "static_transforms_verified": True,
        "baseline_m": 0.05, "clock_domain": "bag_ros",
        "left": {"image_topic": "/vslam_lab/camera/left/image", "camera_info_topic": "/vslam_lab/camera/left/info",
                 "image_frame": "fixture_left_optical", "camera_info_frame": "fixture_left_optical", "encoding": "mono8"},
        "right": {"image_topic": "/vslam_lab/camera/right/image", "camera_info_topic": "/vslam_lab/camera/right/info",
                  "image_frame": "fixture_right_optical", "camera_info_frame": "fixture_right_optical", "encoding": "mono8"},
        "imu": {"verified": True, "topic": "/vslam_lab/camera/imu", "frame": "fixture_imu_optical",
                "units_axes_timestamps_and_transform_verified": True, "measured_rate_hz": 199.8,
                "noise_source": "Test fixture only, not physical calibration",
                "gyro_noise_density": 0.001, "gyro_random_walk": 0.001,
                "accel_noise_density": 0.001, "accel_random_walk": 0.001},
    }


NOW = dt.datetime(2026, 10, 13, 12, 0, 0, tzinfo=dt.timezone.utc)


def camera_contract():
    return {
        "schema_version": 1, "observation_state": "OBSERVED", "evidence_path": "/lab/run/ownership.txt",
        "checked_at_utc": NOW.isoformat(), "owner_status": "FREE", "camera_time_slot_confirmed": True,
        "serial": "fixture-only", "model": "Intel RealSense D435i", "firmware": "fixture",
        "usb_speed": "fixture", "sdk_version": "fixture", "wrapper_version": "fixture",
        "supported_stereo_profiles": ["640x480x30"],
        "supported_gyro_rates": [200, 400], "supported_accel_rates": [63, 250],
        "emitter_before": 1, "emitter_restore_command": "recorded command fixture only",
    }


class VslamInputContractTests(unittest.TestCase):
    def test_unobserved_examples_cannot_start(self):
        contract = json.loads((CONFIG / "input_contract.example.json").read_text())
        with self.assertRaisesRegex(ValueError, "OBSERVED"):
            API["validate_input"](contract, "vo", False)
        camera = json.loads((CONFIG / "camera_contract.example.json").read_text())
        with self.assertRaisesRegex(ValueError, "OBSERVED"):
            API["validate_camera"](camera, "640x480x30", now=NOW)

    def test_modes_are_distinct_and_keep_tf_and_ground_constraints_off(self):
        for mode, imu, mapping in (("vo", False, False), ("vio", True, False),
                                   ("slam_vo", False, True), ("slam_vio", True, True)):
            with self.subTest(mode=mode):
                params, remaps = API["validate_input"](input_contract(), mode, True)
                self.assertEqual(params["enable_imu_fusion"], imu)
                self.assertEqual(params["enable_localization_n_mapping"], mapping)
                for key in ("publish_map_to_odom_tf", "publish_odom_to_base_tf",
                            "enable_ground_constraint_in_odometry", "enable_ground_constraint_in_slam"):
                    self.assertIs(params[key], False)
                self.assertEqual(params["map_frame"], "vslam_lab_map")
                self.assertEqual(params["odom_frame"], "vslam_lab_odom")
                self.assertIn(("/tf_static", "/vslam_lab/tf_static"), remaps)

    def test_distinct_stereo_and_matching_info_frames_are_required(self):
        for mutate in (
            lambda c: c["right"].update(image_frame=c["left"]["image_frame"], camera_info_frame=c["left"]["image_frame"]),
            lambda c: c["right"].update(image_topic=c["left"]["image_topic"]),
            lambda c: c["left"].update(camera_info_frame="wrong"),
            lambda c: c.update(baseline_m=0),
            lambda c: c.update(static_transforms_verified=False),
            lambda c: c["left"].update(image_topic="/camera/operational"),
        ):
            contract = input_contract()
            mutate(contract)
            with self.assertRaises(ValueError):
                API["validate_input"](contract, "vo", True)

    def test_unknown_clocks_and_bag_without_hash_are_rejected(self):
        contract = input_contract()
        with self.assertRaisesRegex(ValueError, "use_sim_time"):
            API["validate_input"](contract, "vo", False)
        contract["clock_domain"] = "camera_device"
        with self.assertRaisesRegex(ValueError, "timestamps"):
            API["validate_input"](contract, "vo", True)
        contract = input_contract()
        contract["source"]["sha256"] = None
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            API["validate_input"](contract, "vo", True)

    def test_vio_requires_imu_evidence_but_vo_does_not(self):
        contract = input_contract()
        contract["imu"]["verified"] = False
        API["validate_input"](contract, "vo", True)
        with self.assertRaisesRegex(ValueError, "VIO"):
            API["validate_input"](contract, "vio", True)
        contract = input_contract()
        params, _ = API["validate_input"](contract, "vio", True)
        self.assertEqual(params["calibration_frequency"], 199.8)
        contract["imu"]["noise_source"] = "NOT_OBSERVED"
        with self.assertRaisesRegex(ValueError, "noise_source"):
            API["validate_input"](contract, "vio", True)

    def test_official_rgb8_bag_is_supported_but_live_uses_ir(self):
        contract = input_contract()
        contract["left"]["encoding"] = contract["right"]["encoding"] = "rgb8"
        contract["rectified_images"] = False
        params, _ = API["validate_input"](contract, "vo", True)
        self.assertIs(params["rectified_images"], False)
        contract["source"]["kind"] = "live"
        contract["clock_domain"] = "host_ros"
        with self.assertRaisesRegex(ValueError, "encoding"):
            API["validate_input"](contract, "vo", False)


class CameraContractTests(unittest.TestCase):
    def test_free_fresh_camera_and_observed_profile_required(self):
        for key, value in (("owner_status", "BUSY"), ("camera_time_slot_confirmed", False),
                           ("checked_at_utc", (NOW - dt.timedelta(minutes=6)).isoformat()),
                           ("supported_stereo_profiles", [])):
            contract = camera_contract()
            contract[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                API["validate_camera"](contract, "640x480x30", now=NOW)

    def test_rates_are_not_forced_and_independent_supported_rates_work(self):
        params = API["validate_camera"](camera_contract(), "640x480x30", enable_imu=True, now=NOW)
        self.assertNotIn("gyro_fps", params)
        self.assertNotIn("accel_fps", params)
        params = API["validate_camera"](camera_contract(), "640x480x30", enable_imu=True,
                                         gyro_fps=200, accel_fps=63, now=NOW)
        self.assertEqual(params["accel_fps"], 63)
        with self.assertRaisesRegex(ValueError, "accel_fps"):
            API["validate_camera"](camera_contract(), "640x480x30", enable_imu=True,
                                    gyro_fps=200, accel_fps=200, now=NOW)

    def test_emitter_change_requires_recorded_previous_value_and_restore_plan(self):
        params = API["validate_camera"](camera_contract(), "640x480x30", now=NOW)
        self.assertNotIn("depth_module.emitter_enabled", params)
        contract = camera_contract()
        contract["emitter_before"] = None
        with self.assertRaisesRegex(ValueError, "previous emitter"):
            API["validate_camera"](contract, "640x480x30", emitter="0", now=NOW)
        contract = camera_contract()
        params = API["validate_camera"](contract, "640x480x30", emitter="0", now=NOW)
        self.assertEqual(params["depth_module.emitter_enabled"], 0)


class LaunchIsolationTests(unittest.TestCase):
    def test_container_global_tf_remaps_cover_internal_transform_listener_node(self):
        # VSLAM 3.2's TransformListener creates a second node internally.
        # Component-only remaps leave it listening to the original /tf_static.
        tree = ast.parse((CONFIG.parent / 'launch/vslam.launch.py').read_text())
        containers = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name) and node.func.id == 'ComposableNodeContainer']
        self.assertEqual(len(containers), 1)
        remaps = next(keyword.value for keyword in containers[0].keywords if keyword.arg == 'remappings')
        self.assertEqual(dict(ast.literal_eval(remaps)),
                         {'/tf': '/vslam_lab/tf', '/tf_static': '/vslam_lab/tf_static'})

    def test_environment_must_not_inherit_operational_domain_or_dds(self):
        env = {"ROS_DOMAIN_ID": "71", "ROS_LOCALHOST_ONLY": "1", "VSLAM_LAB_OPERATIONAL_DOMAIN_ID": "0"}
        API["isolated_environment"](env)
        for delta in ({"ROS_DOMAIN_ID": "0"}, {"VSLAM_LAB_OPERATIONAL_DOMAIN_ID": "71"},
                      {"ROS_LOCALHOST_ONLY": "0"}, {"CYCLONEDDS_URI": "/operational.xml"}):
            with self.assertRaises(ValueError):
                API["isolated_environment"]({**env, **delta})

    def test_launch_manifest_retains_evidence_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(input_contract()))
            API["record_launch"](directory, "vslam_launch.json", path, {"use_sim_time": True})
            manifest = json.loads((Path(directory) / "vslam_launch.json").read_text())
            self.assertEqual(len(manifest["contract_sha256"]), 64)
            self.assertEqual(manifest["status"], "LAUNCH_REQUESTED_NOT_RUNTIME_VERIFIED")
            with self.assertRaises(FileExistsError):
                API["record_launch"](directory, "vslam_launch.json", path, {})


if __name__ == "__main__":
    unittest.main()
