"""Hardware-free checks for the real ROS adapter's validation boundaries."""

import base64
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from robot_dashboard.slam_features import FeatureStream, StreamContext
from robot_dashboard.slam_ros_runtime import (
    CORRECTED_POSE_TOPIC, EXPECTED_PARAMETERS, IsaacRuntimeError, IsaacStereoAdapter,
    MAP_FRAME, _private_json, compose_optical_pose, decode_cloud, encode_png,
)


def header(stamp=100_000_000_000, frame=MAP_FRAME):
    return NS(frame_id=frame, stamp=NS(sec=stamp // 1_000_000_000, nanosec=stamp % 1_000_000_000))


def cloud(points, *, endian=False, padding=0):
    data = b"".join(struct.pack((">" if endian else "<") + "fffI", *point, 0) for point in points)
    return NS(header=header(), width=len(points), height=1, point_step=16,
              row_step=len(data) + padding, data=data + bytes(padding), is_bigendian=endian,
              fields=[NS(name=key, datatype=7, count=1, offset=i*4) for i, key in enumerate("xyz")])


class RuntimeValidationTests(unittest.TestCase):
    def test_decodes_padding_endianness_and_omits_nonfinite(self):
        for endian in (False, True):
            with self.subTest(endian=endian):
                self.assertEqual(decode_cloud(cloud([(1, 2, 3), (float("nan"), 0, 0)], endian=endian, padding=4), 3), [[1, 2, 3]])

    def test_cloud_cap_and_bad_field_rejected(self):
        with self.assertRaisesRegex(IsaacRuntimeError, "source limit"):
            decode_cloud(cloud([(0, 0, 1)] * 3), 2)
        value = cloud([(0, 0, 1)])
        value.fields[0].datatype = 8
        with self.assertRaisesRegex(IsaacRuntimeError, "FLOAT32"):
            decode_cloud(value, 2)

    def test_cloud_short_payload_rejected(self):
        value = cloud([(1, 2, 3)])
        value.data = value.data[:-1]
        with self.assertRaisesRegex(IsaacRuntimeError, "byte count"):
            decode_cloud(value, 2)

    def test_optical_composition_rotates_observed_offset(self):
        root = 2**-0.5
        pose = {"position": [10, 20, 30], "quaternion_xyzw": [0, 0, root, root]}
        transform = NS(transform=NS(translation=NS(x=1, y=0, z=0), rotation=NS(x=0, y=0, z=0, w=1)))
        position, quaternion = compose_optical_pose(pose, transform)
        self.assertAlmostEqual(position[0], 10)
        self.assertAlmostEqual(position[1], 21)
        self.assertEqual(quaternion, pose["quaternion_xyzw"])

    def test_private_config_refuses_world_readable_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{}")
            path.chmod(0o644)
            with self.assertRaisesRegex(IsaacRuntimeError, "private"):
                _private_json(path)
            path.chmod(0o600)
            self.assertEqual(_private_json(path), {})
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(IsaacRuntimeError):
                _private_json(link)

    def test_disabled_capability_never_starts_ros(self):
        adapter = IsaacStereoAdapter(Path.cwd(), Path("/tmp/unused"))
        with patch("importlib.util.find_spec", return_value=None), patch("subprocess.Popen") as process:
            self.assertFalse(adapter.capability()["available_now"])
            with self.assertRaises(IsaacRuntimeError):
                adapter.preflight("mapping")
            process.assert_not_called()

    def test_environment_config_and_default_are_explicit(self):
        with patch.dict("os.environ", {"ROBOT_SCOPE_SLAM_ENABLE": "1", "ROBOT_SCOPE_SLAM_RUNTIME_CONFIG": "/private/config.json"}):
            adapter = IsaacStereoAdapter.from_environment(Path.cwd(), Path("/tmp/unused"))
        self.assertTrue(adapter.enabled)
        self.assertEqual(adapter.config_path, Path("/private/config.json"))

    def test_png_fallback_uses_actual_pixels_with_row_padding(self):
        import zlib

        image = {"encoding": "mono8", "width": 2, "height": 2, "step": 3, "data": bytes([1,2,99,3,4,99])}
        encoded = encode_png(image)
        self.assertEqual(encoded[:8], b"\x89PNG\r\n\x1a\n")
        position = encoded.index(b"IDAT")
        size = struct.unpack(">I", encoded[position-4:position])[0]
        self.assertEqual(zlib.decompress(encoded[position+4:position+4+size]), bytes([0,1,2,0,3,4]))

    def test_static_compatibility_reads_installed_package_and_contract_hashes_without_ros_start(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("input", "camera"):
                path = root / (name + ".json")
                path.write_text(json.dumps({"evidence": name}))
                path.chmod(0o600)
            (root / "package.xml").write_text("<package><version>3.2.6</version></package>")
            config = root / "config.json"
            config.write_text(json.dumps({"input_contract": str(root/"input.json"), "camera_contract": str(root/"camera.json")}))
            config.chmod(0o600)
            adapter = IsaacStereoAdapter(Path.cwd(), root, enabled=True, config_path=config)
            with patch.dict("sys.modules", {"ament_index_python.packages": NS(get_package_share_directory=lambda name: str(root))}), patch("subprocess.Popen") as process:
                result = adapter.compatibility()
                process.assert_not_called()
            self.assertEqual(result["engine_version"], "3.2.6")
            self.assertEqual(len(result["calibration_hash"]), 64)
            self.assertNotEqual(result["calibration_hash"], result["sensor_config_hash"])

    def test_environment_selects_broker_without_connecting_or_importing_ros(self):
        from robot_dashboard.slam_broker import BrokerIsaacAdapter

        with patch.dict("os.environ", {"ROBOT_SCOPE_SLAM_BROKER_SOCKET": "/private/runtime/slam.sock"}), patch("socket.socket") as connect:
            adapter = IsaacStereoAdapter.from_environment(Path.cwd(), Path("/tmp/unused"))
            connect.assert_not_called()
        self.assertIsInstance(adapter, BrokerIsaacAdapter)


class RuntimeCallbackTests(unittest.TestCase):
    def setUp(self):
        self.confirmation_now = 0.0
        self.confirmation_step = None
        def wait(delay):
            self.confirmation_now += delay
            if self.confirmation_step is not None:
                self.confirmation_step()
        self.adapter = IsaacStereoAdapter(Path.cwd(), Path("/tmp/unused"),
            confirmation_clock=lambda: self.confirmation_now, confirmation_wait=wait)
        self.session = {"session_id": "session-test", "generation": 1, "map_epoch": "map-test"}
        context = StreamContext("session-test", 1, "map-test")
        self.job = {"identity": ("session-test", 1), "lock": threading.RLock(), "frames": {}, "errors": [],
                    "features": FeatureStream(context, engine_id="visual_stereo", map_frame=MAP_FRAME),
                    "feature_context": context, "calibration_revision": "measured-calibration-sha",
                    "effective_parameters": dict(EXPECTED_PARAMETERS),
                    "process": NS(poll=lambda: None), "config": {"input": {"base_frame": "camera_link", "left": {"image_frame": "left_optical"}}}}
        self.adapter._job = self.job

    def _feed_post_localize_output(self, stamp=100_000_000_001, *, pose_frame=MAP_FRAME):
        self.job["node"] = None
        image = NS(header=header(stamp=stamp, frame="left_optical"), width=4, height=4,
                   step=4, encoding="mono8", data=bytes([64]*16))
        self.adapter._receive(self.job, "image", image)
        self.adapter._receive(self.job, "right_image", image)
        self.job["tf_buffer"] = NS(lookup_transform=lambda *args: NS(transform=NS(
            translation=NS(x=0,y=0,z=0), rotation=NS(x=0,y=0,z=0,w=1))))
        pose = NS(header=header(stamp=stamp, frame=pose_frame), child_frame_id="camera_link",
                  pose=NS(pose=NS(position=NS(x=1,y=2,z=3), orientation=NS(x=0,y=0,z=0,w=1))))
        with patch.dict("sys.modules", {"rclpy.time": NS(Time=lambda **kwargs: kwargs)}):
            self.adapter._receive(self.job, "pose", pose)
        self.adapter._receive(self.job, "tracking", NS(vo_state=1, header=header(stamp=stamp)))
        self.confirmation_step = None

    def test_stale_generation_cannot_observe_or_stop(self):
        stale = dict(self.session, generation=2)
        for operation in (self.adapter.status, self.adapter.frame, self.adapter.stop):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(IsaacRuntimeError, "ownership changed"):
                operation(stale)

    def test_real_cloud_callback_feeds_global_map_not_overlay(self):
        self.adapter._receive(self.job, "landmarks", cloud([(0, 0, 1), (20, 0, -5)]))
        frame = self.adapter.frame(self.session)
        self.assertEqual(frame["global_map"]["points"], [[0, 0, 1], [20, 0, -5]])
        self.assertEqual(frame["global_map"]["coverage"], "unknown")
        self.assertEqual(frame["global_map"]["backend_limit"], 32768)
        self.assertEqual(frame["overlay"]["points"], [])

    def test_actual_callbacks_join_image_calibration_observations_and_corrected_optical_pose(self):
        stamp = header(frame="left_optical")
        image = NS(header=stamp, width=4, height=4, step=4, encoding="mono8", data=bytes([64]*16))
        info = NS(header=stamp, width=4, height=4, k=[2, 0, 2, 0, 2, 2, 0, 0, 1],
                  p=[2, 0, 2, 0, 0, 2, 2, 0, 0, 0, 1, 0], r=[1,0,0,0,1,0,0,0,1], d=[],
                  distortion_model="plumb_bob", roi=NS(x_offset=0,y_offset=0,width=0,height=0), binning_x=0, binning_y=0)
        self.adapter._receive(self.job, "image", image)
        self.adapter._receive(self.job, "right_image", image)
        self.adapter._receive(self.job, "camera_info", info)
        transform = NS(transform=NS(translation=NS(x=1,y=0,z=0), rotation=NS(x=0,y=0,z=0,w=1)))
        lookup = unittest.mock.Mock(return_value=transform)
        self.job["tf_buffer"] = NS(lookup_transform=lookup)
        pose = NS(header=header(), child_frame_id="camera_link",
                  pose=NS(pose=NS(position=NS(x=0,y=0,z=0), orientation=NS(x=0,y=0,z=0,w=1))))
        with patch.dict("sys.modules", {"rclpy.time": NS(Time=lambda **kwargs: kwargs)}):
            self.adapter._receive(self.job, "pose", pose)
        lookup.assert_called_once_with("camera_link", "left_optical", {"nanoseconds": 100_000_000_000})
        self.adapter._receive(self.job, "tracking", NS(vo_state=1, header=header()))
        without_observations = self.adapter.frame(self.session)
        self.assertEqual(without_observations["overlay"]["reason"], "OBSERVATIONS_UNAVAILABLE")
        self.assertTrue(without_observations["camera_view"]["available"])
        self.assertEqual(without_observations["camera_view"]["position"], [1,0,0])
        self.assertEqual(without_observations["camera_view"]["camera_frame_id"], "left_optical")
        self.assertEqual(without_observations["camera_view"]["intrinsics"], [2,2,2,2])
        self.assertEqual(without_observations["camera_view"]["pose_source_timestamp_ns"], "100000000000")
        self.assertEqual(without_observations["camera_pose"]["position"], [0,0,0])
        self.adapter._receive(self.job, "observations", cloud([(1,0,1),(100,0,1)]))
        frame = self.adapter.frame(self.session)
        self.assertEqual(frame["overlay"]["overlay_kind"], "current_observations_reprojected")
        self.assertEqual(frame["overlay"]["points"], [[2,2]])
        self.assertEqual(frame["image"]["stamp_ns"], "100000000000")
        self.assertEqual(frame["camera_pose"]["source_topic"], CORRECTED_POSE_TOPIC)
        self.assertTrue(frame["readiness"]["ready"])
        self.assertNotIn("data", frame["image"])
        if "jpeg_base64" in frame["image"]:
            self.assertEqual(base64.b64decode(frame["image"]["jpeg_base64"])[:2], b"\xff\xd8")

    def test_wrong_pose_child_frame_is_rejected(self):
        pose = NS(header=header(), child_frame_id="robot_body",
                  pose=NS(pose=NS(position=NS(x=0,y=0,z=0), orientation=NS(x=0,y=0,z=0,w=1))))
        self.adapter._receive(self.job, "pose", pose)
        self.assertNotIn("pose", self.job["frames"])
        self.assertTrue(self.job["errors"])

    def test_missing_timestamped_optical_transform_never_exports_body_pose_as_camera_view(self):
        pose = NS(header=header(), child_frame_id="camera_link",
                  pose=NS(pose=NS(position=NS(x=8,y=9,z=10), orientation=NS(x=0,y=0,z=0,w=1))))
        self.job["tf_buffer"] = NS(lookup_transform=unittest.mock.Mock(side_effect=LookupError("missing optical chain")))
        with patch.dict("sys.modules", {"rclpy.time": NS(Time=lambda **kwargs: kwargs)}):
            self.adapter._receive(self.job, "pose", pose)
        result = self.adapter.frame(self.session)
        self.assertEqual(result["camera_pose"]["position"], [8,9,10])
        self.assertFalse(result["camera_view"]["available"])
        self.assertNotIn("position", result["camera_view"])

    def test_lost_tracking_disables_ready(self):
        self.adapter._receive(self.job, "tracking", NS(vo_state=2, header=header()))
        self.assertFalse(self.adapter.status(self.session)["ready"])

    def test_effective_parameter_readback_rejects_operational_tf(self):
        kind = NS(Request=lambda: NS(names=[]))
        values = [NS(type=1, bool_value=value) for value in EXPECTED_PARAMETERS.values()]
        values[list(EXPECTED_PARAMETERS).index("publish_map_to_odom_tf")].bool_value = True
        with patch.dict("sys.modules", {"rcl_interfaces.srv": NS(GetParameters=kind)}), patch.object(self.adapter, "_call", return_value=NS(values=values)):
            with self.assertRaisesRegex(IsaacRuntimeError, "parameter mismatch"):
                self.adapter._read_parameters(self.job, timeout=0.1)

    def test_tracking_mode_reads_mapping_disabled_truthfully(self):
        expected = dict(EXPECTED_PARAMETERS, enable_localization_n_mapping=False)
        self.job["expected_parameters"] = expected
        kind = NS(Request=lambda: NS(names=[]))
        values = [NS(type=1, bool_value=value) for value in expected.values()]
        with patch.dict("sys.modules", {"rcl_interfaces.srv": NS(GetParameters=kind)}), patch.object(self.adapter, "_call", return_value=NS(values=values)):
            self.adapter._read_parameters(self.job, timeout=0.1)
        self.assertFalse(self.job["effective_parameters"]["enable_localization_n_mapping"])

    def test_official_save_checks_service_result_and_real_native_artifact(self):
        kind = NS(Request=lambda: NS(file_path=""))
        self.job["config"].update(input_hash="a"*64, camera_hash="b"*64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            def call(job, service_type, service, request, timeout):
                self.assertTrue(service.endswith("/save_map"))
                self.assertEqual(request.file_path, str(path))
                (path / "data.mdb").write_bytes(b"real-native-save-test")
                return NS(success=True)
            with patch.dict("sys.modules", {"isaac_ros_visual_slam_interfaces.srv": NS(FilePath=kind)}), patch.object(self.adapter, "status", return_value={"ready": True}), patch.object(self.adapter, "_call", side_effect=call):
                result = self.adapter.save(self.session, path)
            self.assertTrue(result["official_save_completed"])
            self.assertEqual(result["required_native_files"], ["data.mdb"])
            self.assertEqual(result["metadata"]["calibration_hash"], "a"*64)

    def test_official_save_success_without_native_file_is_failure(self):
        kind = NS(Request=lambda: NS(file_path=""))
        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules", {"isaac_ros_visual_slam_interfaces.srv": NS(FilePath=kind)}), patch.object(self.adapter, "status", return_value={"ready": True}), patch.object(self.adapter, "_call", return_value=NS(success=True)):
            with self.assertRaisesRegex(IsaacRuntimeError, "data.mdb"):
                self.adapter.save(self.session, Path(directory))

    def test_cleanup_failure_retains_owned_session(self):
        process = NS(pid=51234, wait=lambda timeout: None)
        self.job["process"] = process
        with patch("os.killpg", side_effect=PermissionError("not owned")):
            with self.assertRaises(PermissionError):
                self.adapter.stop(self.session)
        self.assertIs(self.adapter._job, self.job)

    def test_stop_without_owned_job_is_idempotent(self):
        self.adapter._job = None
        self.adapter.stop(self.session)

    def test_official_localize_uses_hint_and_changes_feature_epoch_without_load_path_shortcut(self):
        kind = NS(Request=lambda: NS(map_folder_path="", pose_hint=NS(position=NS(), orientation=NS())))
        hint = {"frame_id": MAP_FRAME, "operator_verified": True,
                "position": [1,2,3], "quaternion_xyzw": [0,0,0,1]}
        session = dict(self.session, map_epoch="new-native-map-epoch")
        self.adapter._receive(self.job, "landmarks", cloud([(0,0,1)]))
        self.confirmation_step = self._feed_post_localize_output
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "data.mdb").write_bytes(b"native-copy")
            self.job["node"] = NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=100_000_000_000)))
            def call(job, service_type, service, request, timeout):
                self.assertTrue(service.endswith("/localize_in_map"))
                self.assertEqual(request.map_folder_path, str(path))
                self.assertEqual(request.pose_hint.position.x, 1.0)
                self.assertEqual(request.pose_hint.orientation.w, 1.0)
                self.assertEqual(job["feature_context"].map_epoch, "new-native-map-epoch")
                self.adapter._receive(job, "landmarks", cloud([(5,0,1)]))
                self.assertEqual(job["frames"], {})
                return NS(success=True)
            with patch.dict("sys.modules", {"isaac_ros_visual_slam_interfaces.srv": NS(LocalizeInMap=kind)}), patch.object(self.adapter, "_call", side_effect=call):
                result = self.adapter.localize(session, path, hint)
        self.assertTrue(result["localize_success"])
        self.assertTrue(result["official_localization_completed"])
        self.assertTrue(result["fresh_pose_tracking_confirmed"])
        self.assertIsNone(result["confirmation_reason"])
        self.assertIsNone(result["reason"])
        self.assertFalse(self.job["localizing"])
        self.assertEqual(self.job["source_stamp_floor_ns"], 100_000_000_000)
        self.job["node"] = None
        self.assertIsNone(self.adapter.frame(session)["global_map"])
        # A DDS callback queued before the native map epoch changed cannot be
        # relabeled as fresh output in the localized map.
        self.adapter._receive(self.job, "landmarks", cloud([(6,0,1)]))
        self.assertNotIn("landmarks", self.job["frames"])
        fresh = cloud([(7,0,1)])
        fresh.header = header(stamp=100_000_000_001)
        self.adapter._receive(self.job, "landmarks", fresh)
        self.assertEqual(self.adapter.frame(session)["global_map"]["points"], [[7,0,1]])
        self.assertFalse(result["operational_pose_approved"])
        self.assertEqual(self.job["feature_context"].map_epoch, session["map_epoch"])

    def test_official_localize_completion_without_fresh_pose_does_not_claim_success(self):
        kind = NS(Request=lambda: NS(map_folder_path="", pose_hint=NS(position=NS(), orientation=NS())))
        hint = {"frame_id": MAP_FRAME, "operator_verified": True,
                "position": [1,2,3], "quaternion_xyzw": [0,0,0,1]}
        session = dict(self.session, map_epoch="confirmed-service-unconfirmed-output")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "data.mdb").write_bytes(b"native-copy")
            self.job["node"] = NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=100_000_000_000)))
            with patch.dict("sys.modules", {"isaac_ros_visual_slam_interfaces.srv": NS(LocalizeInMap=kind)}), patch.object(self.adapter, "_call", return_value=NS(success=True)):
                result = self.adapter.localize(session, path, hint)
        self.assertTrue(result["official_localization_completed"])
        self.assertFalse(result["localize_success"])
        self.assertFalse(result["fresh_pose_tracking_confirmed"])
        self.assertEqual(result["native_load"], "verified")
        self.assertEqual(result["confirmation_reason"], "FRESH_CORRECTED_POSE_TRACKING_UNAVAILABLE")
        self.assertEqual(result["reason"], "FRESH_CORRECTED_POSE_TRACKING_UNAVAILABLE")
        self.assertEqual(self.confirmation_now, 5.0)

    def test_old_wrong_frame_or_wrong_epoch_output_cannot_confirm_localization(self):
        for failure in ("old_stamp", "wrong_frame", "wrong_epoch"):
            with self.subTest(failure=failure):
                self.setUp()
                kind = NS(Request=lambda: NS(map_folder_path="", pose_hint=NS(position=NS(), orientation=NS())))
                hint = {"frame_id": MAP_FRAME, "operator_verified": True,
                        "position": [1,2,3], "quaternion_xyzw": [0,0,0,1]}
                session = dict(self.session, map_epoch="new-native-epoch")
                def feed():
                    self._feed_post_localize_output(stamp=100_000_000_000 if failure == "old_stamp" else 100_000_000_001,
                                                   pose_frame="old_map" if failure == "wrong_frame" else MAP_FRAME)
                    if failure == "wrong_epoch":
                        self.job["feature_context"] = StreamContext(session["session_id"], session["generation"], "other-native-epoch")
                self.confirmation_step = feed
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory)
                    (path / "data.mdb").write_bytes(b"native-copy")
                    self.job["node"] = NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=100_000_000_000)))
                    with patch.dict("sys.modules", {"isaac_ros_visual_slam_interfaces.srv": NS(LocalizeInMap=kind)}), patch.object(self.adapter, "_call", return_value=NS(success=True)):
                        result = self.adapter.localize(session, path, hint)
                self.assertTrue(result["official_localization_completed"])
                self.assertFalse(result["localize_success"])
                self.assertEqual(result["reason"], "LOCALIZATION_CONTEXT_CHANGED" if failure == "wrong_epoch" else "FRESH_CORRECTED_POSE_TRACKING_UNAVAILABLE")

    def test_native_localize_timeout_quarantines_inflight_frames_until_owned_cleanup(self):
        kind = NS(Request=lambda: NS(map_folder_path="", pose_hint=NS(position=NS(), orientation=NS())))
        hint = {"frame_id": MAP_FRAME, "operator_verified": True,
                "position": [1,2,3], "quaternion_xyzw": [0,0,0,1]}
        session = dict(self.session, map_epoch="uncertain-native-map-epoch")
        self.job["node"] = NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=100_000_000_000)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "data.mdb").write_bytes(b"native-copy")
            with patch.dict("sys.modules", {"isaac_ros_visual_slam_interfaces.srv": NS(LocalizeInMap=kind)}), patch.object(self.adapter, "_call", side_effect=IsaacRuntimeError("request timed out")):
                with self.assertRaisesRegex(IsaacRuntimeError, "request timed out"):
                    self.adapter.localize(session, path, hint)
        self.assertTrue(self.job["localizing"])
        self.assertEqual(self.job["source_stamp_floor_ns"], 100_000_000_000)
        self.assertEqual(self.job["frames"], {})
        self.assertEqual(self.job["feature_context"].map_epoch, session["map_epoch"])
        fresh = cloud([(7,0,1)])
        fresh.header = header(stamp=100_000_000_001)
        self.adapter._receive(self.job, "landmarks", fresh)
        self.assertEqual(self.job["frames"], {})


if __name__ == "__main__":
    unittest.main()
