"""Mocked runtime safety regression tests. Never execute Docker, SSH or ROS."""
from argparse import Namespace
from collections import namedtuple
import contextlib
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from experiments.isaac_vslam import labctl, preflight, run_bag


class ContainerOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.state = {"run_id": "test-run", "container_id": "a" * 64, "owner": "this-run-only", "created": "2026-10-13T01:02:03.000000000Z"}
        self.obj = {"Id": self.state["container_id"], "Created": self.state["created"],
                    "Config": {"Labels": {labctl.LABEL: self.state["owner"]}}, "State": {"Running": True}}

    def test_all_three_ownership_components_match(self):
        with patch.object(labctl, "inspect", return_value=self.obj) as inspect:
            self.assertEqual(labctl.owned(self.state), self.obj)
        inspect.assert_called_once_with(self.state["container_id"])

    def test_same_label_does_not_allow_different_container_id(self):
        self.obj["Id"] = "b" * 64
        with patch.object(labctl, "inspect", return_value=self.obj):
            with self.assertRaisesRegex(RuntimeError, "ownership mismatch"):
                labctl.owned(self.state)

    def test_same_id_does_not_allow_different_created_or_owner(self):
        for field in ("created", "owner"):
            state = {**self.state, field: "different"}
            with self.subTest(field=field), patch.object(labctl, "inspect", return_value=self.obj):
                with self.assertRaises(RuntimeError):
                    labctl.owned(state)

    def test_missing_labels_refuses(self):
        self.obj["Config"]["Labels"] = {}
        with patch.object(labctl, "inspect", return_value=self.obj):
            with self.assertRaises(RuntimeError):
                labctl.owned(self.state)

    def test_cleanup_stops_exact_owned_id_and_retains_container(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ownership.json"
            state_path.write_text(json.dumps(self.state))
            with patch("sys.argv", ["labctl", "cleanup", "--state", str(state_path)]), \
                    patch.object(labctl, "inspect", return_value=self.obj), \
                    patch.object(labctl.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
                labctl.main()
            run.assert_called_once_with(["docker", "stop", "--time", "20", self.state["container_id"]], check=True)
            self.assertTrue(state_path.exists())

    def test_cleanup_of_stopped_owned_container_sends_no_command(self):
        self.obj["State"]["Running"] = False
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ownership.json"
            state_path.write_text(json.dumps(self.state))
            with patch("sys.argv", ["labctl", "cleanup", "--state", str(state_path)]), \
                    patch.object(labctl, "inspect", return_value=self.obj), \
                    patch.object(labctl.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
                labctl.main()
            run.assert_not_called()

    def test_cleanup_ownership_mismatch_sends_no_stop(self):
        self.obj["Created"] = "different"
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ownership.json"
            state_path.write_text(json.dumps(self.state))
            with patch("sys.argv", ["labctl", "cleanup", "--state", str(state_path)]), \
                    patch.object(labctl, "inspect", return_value=self.obj), \
                    patch.object(labctl.subprocess, "run") as run:
                with self.assertRaises(RuntimeError):
                    labctl.main()
            run.assert_not_called()

    def test_exec_clears_operational_dds_settings_and_sets_lab_domain(self):
        state = {**self.state, "domain": 71}
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ownership.json"
            state_path.write_text(json.dumps(state))
            with patch("sys.argv", ["labctl", "exec", "--state", str(state_path), "--", "python3", "experiment.py"]), \
                    patch.object(labctl, "inspect", return_value=self.obj), \
                    patch.object(labctl.subprocess, "call", return_value=0) as call:
                with self.assertRaises(SystemExit) as stopped:
                    labctl.main()
            self.assertEqual(stopped.exception.code, 0)
            args = call.call_args.args[0]
            self.assertEqual(args[:4], ["docker", "exec", state["container_id"], "env"])
            self.assertEqual(args[-2:], ["python3", "experiment.py"])
            self.assertIn("ROS_DOMAIN_ID=71", args)
            self.assertIn("ROS_LOCALHOST_ONLY=1", args)
            for setting in ("CYCLONEDDS_URI", "FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE", "ROS_DISCOVERY_SERVER"):
                self.assertEqual(args[args.index(setting) - 1], "-u")


class ContainerCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "isaac-vslam-lab"
        self.root.mkdir()
        for name in ("runs", "code", "sources", "data"):
            (self.root / name).mkdir()
        self.args = Namespace(root=str(self.root), run="T0-test-001", image="sha256:" + "a" * 64,
                              domain=71, cpus=2, setup_network=False, resource_window_confirmed=True)
        self.obj = {"Id": "c" * 64, "Created": "created", "Image": self.args.image,
                    "HostConfig": {"NetworkMode": "none", "Memory": 6 * 1024 ** 3}}
        for target, kwargs in (("ROOT", {"new": self.root}),
                               ("call", {"return_value": "c" * 64}),
                               ("inspect", {"return_value": self.obj}),
                               ("disk_gate", {"return_value": None})):
            patcher = patch.object(labctl, target, **kwargs)
            setattr(self, "mock_" + target, patcher.start())
            self.addCleanup(patcher.stop)
        self.proc_patch = patch.object(labctl.Path, "glob", return_value=[])
        self.proc_patch.start()
        self.addCleanup(self.proc_patch.stop)
        self.run_patch = patch.object(labctl.subprocess, "run")
        self.mock_run = self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

    def start(self):
        with contextlib.redirect_stdout(io.StringIO()):
            labctl.start(self.args)

    def test_create_has_isolated_mounts_network_and_resources(self):
        self.start()
        cmd = self.mock_call.call_args.args[0]
        self.assertEqual(cmd[:2], ["docker", "create"])
        self.assertEqual(cmd[cmd.index("--network") + 1], "none")
        self.assertEqual(cmd[cmd.index("--runtime") + 1], "nvidia")
        self.assertEqual(cmd[cmd.index("--cpus") + 1], "2")
        self.assertNotIn("--privileged", cmd)
        self.assertNotIn("--device", cmd)
        self.assertFalse(any("docker.sock" in v for v in cmd))
        mounts = [cmd[i + 1] for i, value in enumerate(cmd) if value == "--mount"]
        self.assertEqual(len(mounts), 5)
        self.assertEqual(sum(m.endswith(",readonly") for m in mounts), 3)
        self.assertEqual(sum("dst=/lab/run" in m for m in mounts), 1)
        self.assertIn("ROS_DOMAIN_ID=71", cmd)
        self.assertIn("ROS_LOCALHOST_ONLY=1", cmd)
        self.assertIn("RMW_IMPLEMENTATION=rmw_fastrtps_cpp", cmd)
        saved = json.loads((self.root / "runs" / self.args.run / "ownership.json").read_text())
        self.assertEqual(saved["container_id"], self.obj["Id"])
        self.assertEqual(saved["created"], self.obj["Created"])
        self.assertIn(labctl.LABEL + "=" + saved["owner"], cmd)

    def test_mutable_images_and_unapproved_registry_rejected(self):
        for image in ("latest", "nvcr.io/nvidia/isaac/ros:latest", "sha256:abcd", "docker.io/x/y@sha256:" + "a" * 64):
            with self.subTest(image=image):
                self.args.image = image
                with self.assertRaisesRegex(ValueError, "immutable"):
                    self.start()
        self.mock_call.assert_not_called()

    def test_nvidia_digest_accepted(self):
        self.args.image = "nvcr.io/nvidia/isaac/ros@sha256:" + "b" * 64
        self.start()
        self.assertIn(self.args.image, self.mock_call.call_args.args[0])

    def test_unconfirmed_resource_window_does_not_create_container(self):
        self.args.resource_window_confirmed = False
        with self.assertRaisesRegex(ValueError, "resource window"):
            self.start()
        self.mock_call.assert_not_called()

    def test_default_or_out_of_range_domain_rejected(self):
        for domain in (0, -1, 102):
            with self.subTest(domain=domain):
                self.args.domain = domain
                with self.assertRaisesRegex(ValueError, "domain"):
                    self.start()
        self.mock_call.assert_not_called()

    def test_existing_run_never_overwritten_or_reused(self):
        run = self.root / "runs" / self.args.run
        run.mkdir()
        marker = run / "existing.txt"
        marker.write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.start()
        self.assertEqual(marker.read_text(), "preserve")
        self.mock_call.assert_not_called()

    def test_run_path_traversal_rejected(self):
        self.args.run = "../../other-project"
        with self.assertRaises(ValueError):
            self.start()
        self.mock_call.assert_not_called()

    def test_root_symlink_refused(self):
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.args.root = str(alias)
        with self.assertRaisesRegex(RuntimeError, "dedicated runtime root"):
            self.start()
        self.mock_call.assert_not_called()

    def test_subdirectory_symlink_refused(self):
        (self.root / "data").rmdir()
        outside = self.root.parent / "other-data"
        outside.mkdir()
        (self.root / "data").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "real dedicated directories"):
            self.start()
        self.mock_call.assert_not_called()

    def test_host_observed_domain_conflict_refuses(self):
        self.proc_patch.stop()
        process_env = Mock()
        process_env.read_bytes.return_value = b"PATH=/bin\0ROS_DOMAIN_ID=71\0"
        with patch.object(labctl.Path, "glob", return_value=[process_env]):
            with self.assertRaisesRegex(RuntimeError, "observed on host"):
                self.start()
        self.mock_call.assert_not_called()

    def test_cli_rejects_nonfinite_or_excess_cpu_limit(self):
        for cpus in ("nan", "inf", "0", "3"):
            with self.subTest(cpus=cpus), patch("sys.argv", ["labctl", "start", "--run", "test", "--image", self.args.image,
                                                             "--domain", "71", "--cpus", cpus]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    labctl.main()
        self.mock_call.assert_not_called()


class ReplaySelectionTests(unittest.TestCase):
    def spec(self):
        return {"topics": [
            {"source": "/stereo/left", "destination": "/vslam_lab/camera/left", "type": "sensor_msgs/msg/Image"},
            {"source": "/stereo/right", "destination": "/vslam_lab/camera/right", "type": "sensor_msgs/msg/Image"},
            {"source": "/stereo/left_info", "destination": "/vslam_lab/camera/left_info", "type": "sensor_msgs/msg/CameraInfo"},
            {"source": "/stereo/right_info", "destination": "/vslam_lab/camera/right_info", "type": "sensor_msgs/msg/CameraInfo"}]}

    def input_contract(self):
        return {side: {"image_topic": "/vslam_lab/camera/" + side,
                       "camera_info_topic": "/vslam_lab/camera/" + side + "_info"} for side in ('left', 'right')}

    def test_only_selected_inputs_normal_rate_and_clock(self):
        args = run_bag.replay_args(self.spec(), Path("/lab/data/sample"))
        self.assertEqual(args[:4], ["ros2", "bag", "play", "/lab/data/sample"])
        self.assertEqual(args[args.index("--rate") + 1], "1.0")
        self.assertIn("--clock", args)
        self.assertNotIn("-a", args)
        self.assertNotIn("--loop", args)
        self.assertNotIn("/tf", args)
        selected = args[args.index("--topics") + 1:args.index("--remap")]
        self.assertEqual(selected, [r["source"] for r in self.spec()["topics"]])

    def test_dynamic_tf_and_estimator_outputs_rejected(self):
        for source, typ in (("/tf", "tf2_msgs/msg/TFMessage"),
                            ("/odom", "nav_msgs/msg/Odometry"),
                            ("/visual_slam/path", "nav_msgs/msg/Path"),
                            ("/visual_slam/status", "isaac_ros_visual_slam_interfaces/msg/VisualSlamStatus"),
                            ("/cmd_vel", "geometry_msgs/msg/Twist")):
            spec = {"topics": [{"source": source, "destination": "/vslam_lab/input", "type": typ}],
                    "static_tf_sensor_only_verified": True}
            with self.subTest(source=source), self.assertRaises(ValueError):
                run_bag.replay_args(spec, "bag")

    def test_static_tf_requires_content_review_and_exact_lab_destination(self):
        spec = {"topics": [{"source": "/tf_static", "destination": "/vslam_lab/tf_static", "type": "tf2_msgs/msg/TFMessage"}]}
        with self.assertRaisesRegex(ValueError, "Review TF"):
            run_bag.replay_args(spec, "bag")
        spec["static_tf_sensor_only_verified"] = True
        self.assertIn("/tf_static:=/vslam_lab/tf_static", run_bag.replay_args(spec, "bag"))
        spec["topics"][0]["destination"] = "/tf_static"
        with self.assertRaises(ValueError):
            run_bag.replay_args(spec, "bag")

    def test_empty_oversized_relative_or_duplicate_topic_map_refused(self):
        cases = [{"topics": []}, {"topics": self.spec()["topics"] * 3}]
        relative = self.spec()
        relative["topics"][0]["source"] = "left"
        cases.append(relative)
        same_destination = self.spec()
        same_destination["topics"][1]["destination"] = same_destination["topics"][0]["destination"]
        cases.append(same_destination)
        same_source = self.spec()
        same_source["topics"][1]["source"] = same_source["topics"][0]["source"]
        cases.append(same_source)
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                run_bag.replay_args(spec, "bag")

    def test_actual_bag_type_mismatch_prevents_all_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.json"
            contract.write_text(json.dumps(self.input_contract()))
            spec = root / "replay.json"
            spec.write_text(json.dumps(self.spec()))
            reader = Mock()
            reader.get_all_topics_and_types.return_value = [SimpleNamespace(name="/stereo/left", type="nav_msgs/msg/Odometry")]
            rosbag = SimpleNamespace(SequentialReader=Mock(return_value=reader), StorageOptions=Mock(), ConverterOptions=Mock())
            guard = {"isolated_environment": Mock(), "validate_input": Mock()}
            argv = ["run_bag", "--bag", str(root / "bag"), "--contract", str(contract), "--replay-spec", str(spec),
                    "--run-dir", str(root / "run"), "--timeout", "5"]
            with patch("sys.argv", argv), patch.dict("sys.modules", {"rosbag2_py": rosbag}), \
                    patch.object(run_bag.runpy, "run_path", return_value=guard), \
                    patch.object(run_bag.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(ValueError, "type/source differs"):
                    run_bag.main()
            popen.assert_not_called()
            self.assertFalse((root / "run").exists())

    def test_destination_or_type_mismatch_prevents_reader_and_publication(self):
        for field, wrong_value in (("destination", "/vslam_lab/camera/other"), ("type", "sensor_msgs/msg/Imu")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                contract = root / "contract.json"
                contract.write_text(json.dumps(self.input_contract()))
                changed = self.spec()
                changed['topics'][0][field] = wrong_value
                spec = root / "replay.json"
                spec.write_text(json.dumps(changed))
                rosbag = SimpleNamespace(SequentialReader=Mock())
                guard = {"isolated_environment": Mock(), "validate_input": Mock()}
                argv = ["run_bag", "--bag", str(root / "bag"), "--contract", str(contract), "--replay-spec", str(spec),
                        "--run-dir", str(root / "run"), "--timeout", "5"]
                with patch("sys.argv", argv), patch.dict("sys.modules", {"rosbag2_py": rosbag}), \
                        patch.object(run_bag.runpy, "run_path", return_value=guard), \
                        patch.object(run_bag.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(ValueError, "destination/type"):
                        run_bag.main()
                popen.assert_not_called()
                rosbag.SequentialReader.assert_not_called()
                self.assertFalse((root / "run").exists())


class OwnedChildCleanupTests(unittest.TestCase):
    def test_exited_child_sends_no_signal(self):
        child = Mock(pid=987654)
        child.poll.return_value = 0
        with patch.object(run_bag.os, "killpg") as kill:
            run_bag.stop_owned(child)
        kill.assert_not_called()

    def test_liveness_rechecked_before_first_signal(self):
        child = Mock(pid=987654)
        child.poll.side_effect = [None, 0]
        with patch.object(run_bag.os, "killpg") as kill:
            run_bag.stop_owned(child)
        kill.assert_not_called()

    def test_clean_exit_stops_escalation(self):
        child = Mock(pid=987654)
        child.poll.return_value = None
        child.wait.return_value = 0
        with patch.object(run_bag.os, "killpg") as kill:
            run_bag.stop_owned(child)
        kill.assert_called_once_with(987654, signal.SIGINT)
        child.wait.assert_called_once_with(timeout=15)

    def test_escalation_only_on_same_owned_group(self):
        child = Mock(pid=987654)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("owned-child", 15), subprocess.TimeoutExpired("owned-child", 5), 0]
        with patch.object(run_bag.os, "killpg") as kill:
            run_bag.stop_owned(child)
        self.assertEqual([c.args for c in kill.call_args_list], [(987654, signal.SIGINT), (987654, signal.SIGTERM), (987654, signal.SIGKILL)])

    def test_vanished_process_does_not_escalate(self):
        child = Mock(pid=987654)
        child.poll.return_value = None
        with patch.object(run_bag.os, "killpg", side_effect=ProcessLookupError) as kill:
            run_bag.stop_owned(child)
        kill.assert_called_once_with(987654, signal.SIGINT)
        child.wait.assert_not_called()


class PreflightTests(unittest.TestCase):
    def test_passive_command_error_is_not_observed(self):
        with patch.object(preflight.subprocess, "run", side_effect=FileNotFoundError("unavailable")):
            result = preflight.command(["missing-read-only-query"])
        self.assertEqual(result["status"], "NOT_OBSERVED")

    def test_passive_command_timeout_preserved(self):
        with patch.object(preflight.subprocess, "run", side_effect=subprocess.TimeoutExpired("read-only-query", 15)):
            result = preflight.command(["read-only-query"])
        self.assertEqual(result["status"], "NOT_OBSERVED")

    def test_safe_environment_does_not_include_credentials(self):
        for key in ("PASSWORD", "TOKEN", "SSH_AUTH_SOCK", "AWS_SECRET_ACCESS_KEY", "DOCKER_PASSWORD"):
            self.assertNotIn(key, preflight.SAFE_ENV)

    def test_disk_floor_ten_gib_or_ten_percent(self):
        disk = namedtuple("usage", "total used free")
        for total, free, should_pass in ((50 * 1024**3, 9 * 1024**3, False),
                                         (50 * 1024**3, 10 * 1024**3, True),
                                         (200 * 1024**3, 19 * 1024**3, False),
                                         (200 * 1024**3, 20 * 1024**3, True)):
            with self.subTest(total=total, free=free), patch.object(labctl.shutil, "disk_usage", return_value=disk(total, total-free, free)):
                if should_pass:
                    labctl.disk_gate(Path("unused"))
                else:
                    with self.assertRaises(RuntimeError):
                        labctl.disk_gate(Path("unused"))


if __name__ == "__main__":
    unittest.main()
