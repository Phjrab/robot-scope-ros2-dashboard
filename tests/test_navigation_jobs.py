import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import yaml

from robot_dashboard.navigation_jobs import (
    COSTMAP_MAX_OBSTACLE_HEIGHT,
    COSTMAP_MIN_OBSTACLE_HEIGHT,
    HUMBLE_BT_PLUGIN_LIBRARIES,
    MAP_YAML_TOKEN,
    PARAMETER_FIELDS,
    PARAMS_FILE_TOKEN,
    PRIVATE_CMD_VEL_TOPIC,
    NavigationBusy,
    NavigationCommandSpec,
    NavigationConflict,
    NavigationJobManager,
    NavigationParameterError,
    NavigationPoseError,
    NavigationUnavailable,
)
from robot_dashboard.saved_maps import NavigationMapSnapshot


MAP_ID = "a" * 24
MAP_REVISION = "b" * 64


class NavigationJobManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.project = Path(__file__).parents[1].resolve()
        self.launcher = self.root / "fake_launcher.py"
        self.launcher.write_text(
            "import pathlib,sys,time\n"
            "assert pathlib.Path(sys.argv[1]).is_file()\n"
            "assert pathlib.Path(sys.argv[2]).is_file()\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        self.manager = self.make_manager()

    def tearDown(self):
        self.manager.close()
        self.temporary.cleanup()

    def make_manager(self, **overrides):
        options = {
            "project_dir": self.project,
            "runtime_dir": self.runtime,
            "base_parameters_file": self.project / "config" / "nav2_params_go2_humble.yaml",
            "start_command": NavigationCommandSpec(
                (
                    str(Path(sys.executable).resolve()),
                    str(self.launcher),
                    MAP_YAML_TOKEN,
                    PARAMS_FILE_TOKEN,
                ),
                cwd=self.project,
            ),
            "map_snapshotter": self.snapshot_map,
            "startup_grace_seconds": 0.02,
            "stop_grace_seconds": 0.25,
        }
        options.update(overrides)
        return NavigationJobManager(**options)

    @staticmethod
    def snapshot_map(map_id, revision, destination):
        yaml_path = destination / "map.yaml"
        image_path = destination / "map.pgm"
        image_path.write_bytes(b"P5\n30 30\n255\n" + bytes([255]) * 900)
        yaml_path.write_text(
            "image: map.pgm\nresolution: 0.1\norigin: [0, 0, 0]\n"
            "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n",
            encoding="utf-8",
        )
        return NavigationMapSnapshot(
            map_id=map_id,
            revision=revision,
            name="classroom",
            frame_id="map",
            yaml_path=yaml_path,
            image_path=image_path,
            width=30,
            height=30,
            resolution=0.1,
            origin=(0.0, 0.0, 0.0),
            occupancy=bytes([0]) * 900,
        )

    def test_parameter_contract_has_exact_27_fields_and_safe_caps(self):
        snapshot = self.manager.parameters_snapshot()
        self.assertEqual(len(PARAMETER_FIELDS), 27)
        self.assertEqual(set(snapshot["values"]), set(PARAMETER_FIELDS))
        self.assertEqual(set(snapshot["presets"][0]["values"]), set(PARAMETER_FIELDS))
        self.assertLessEqual(snapshot["values"]["desired_linear_vel"], 0.30)
        self.assertLessEqual(snapshot["values"]["rotate_to_heading_angular_vel"], 0.50)
        self.assertLessEqual(snapshot["values"]["max_angular_accel"], 1.20)
        self.assertFalse(snapshot["values"]["use_rotate_to_heading"])
        self.assertFalse(snapshot["values"]["closed_loop"])
        self.assertFalse(snapshot["values"]["enable_stamped_cmd_vel"])
        self.assertRegex(snapshot["revision"], r"^[0-9a-f]{64}$")
        self.assertNotIn(str(self.runtime), json.dumps(snapshot))

    def test_parameter_patch_is_cas_allowlisted_and_transactional(self):
        before = self.manager.parameters_snapshot()
        updated = self.manager.update_parameters(
            before["revision"],
            {"desired_linear_vel": 0.20, "min_obstacle_height": -0.25},
        )
        self.assertEqual(updated["values"]["desired_linear_vel"], 0.20)
        self.assertTrue(self.manager.generated_parameters_file.is_file())
        document = yaml.safe_load(self.manager.generated_parameters_file.read_text())
        runtime = document["robot_scope_navigation_runtime"]["ros__parameters"]
        self.assertEqual(
            runtime,
            {
                "scan_topic": "/scan",
                "odom_topic": "/Odometry",
                "cmd_vel_topic": PRIVATE_CMD_VEL_TOPIC,
                "min_obstacle_height": -0.25,
                "max_obstacle_height": 2.0,
                "obstacle_max_range": 8.0,
                "raytrace_max_range": 10.0,
            },
        )
        global_scan = document["global_costmap"]["global_costmap"]["ros__parameters"][
            "obstacle_layer"
        ]["scan"]
        self.assertEqual(global_scan["min_obstacle_height"], COSTMAP_MIN_OBSTACLE_HEIGHT)
        self.assertEqual(global_scan["max_obstacle_height"], COSTMAP_MAX_OBSTACLE_HEIGHT)
        self.assertNotIn("enable_stamped_cmd_vel", document["controller_server"]["ros__parameters"])
        self.assertEqual(
            document["bt_navigator"]["ros__parameters"]["plugin_lib_names"],
            list(HUMBLE_BT_PLUGIN_LIBRARIES),
        )
        self.assertEqual(
            document["planner_server"]["ros__parameters"]["GridBased"]["plugin"],
            "nav2_navfn_planner/NavfnPlanner",
        )
        with self.assertRaises(NavigationConflict):
            self.manager.update_parameters(before["revision"], {"desired_linear_vel": 0.15})

    def test_parameter_patch_rejects_unknown_locked_nonfinite_and_cross_field_values(self):
        revision = self.manager.parameters_snapshot()["revision"]
        invalid = (
            {"shell": "rm"},
            {"use_rotate_to_heading": True},
            {"rotation_shim_enabled": False},
            {"desired_linear_vel": float("nan")},
            {"desired_linear_vel": 0.31},
            {"controller_frequency": 9.99},
            {"inflation_radius": 0.16, "robot_radius": 0.30},
            {"min_obstacle_height": 0.8, "max_obstacle_height": 0.5},
            {"obstacle_max_range": 10.0, "raytrace_max_range": 9.0},
        )
        for patch in invalid:
            with self.subTest(patch=patch), self.assertRaises(NavigationParameterError):
                self.manager.update_parameters(revision, patch)

    def test_start_uses_private_snapshots_single_process_group_and_no_public_paths(self):
        revision = self.manager.parameters_snapshot()["revision"]
        started = self.manager.start(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            parameters_revision=revision,
        )
        self.assertEqual(started["pipeline"]["state"], "running")
        self.assertEqual(started["map"]["id"], MAP_ID)
        self.assertNotIn(str(self.runtime), json.dumps(started))
        with self.assertRaises(NavigationBusy):
            self.manager.start(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                parameters_revision=revision,
            )
        job_dir = self.manager._job_dir
        self.assertIsNotNone(job_dir)
        self.assertTrue((job_dir / "map.yaml").is_file())
        self.assertTrue((job_dir / "nav2_params.yaml").is_file())
        self.assertNotEqual(
            os.stat(job_dir / "nav2_params.yaml").st_ino,
            os.stat(self.manager.generated_parameters_file).st_ino,
        )
        stopped = self.manager.stop()
        self.assertEqual(stopped["pipeline"]["state"], "idle")
        self.assertFalse(job_dir.exists())

    def test_start_rejects_stale_parameter_revision_and_missing_prerequisites(self):
        with self.assertRaises(NavigationConflict):
            self.manager.start(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                parameters_revision="0" * 64,
            )
        unavailable_runtime = self.root / "unavailable"
        unavailable = self.make_manager(
            runtime_dir=unavailable_runtime,
            prerequisites={"missing": self.root / "does-not-exist"},
        )
        try:
            self.assertFalse(unavailable.snapshot()["available"])
            with self.assertRaises(NavigationUnavailable):
                unavailable.start(
                    map_id=MAP_ID,
                    map_revision=MAP_REVISION,
                    parameters_revision=unavailable.parameters_snapshot()["revision"],
                )
        finally:
            unavailable.close()

    def test_active_pose_requires_pinned_known_free_clearance(self):
        revision = self.manager.parameters_snapshot()["revision"]
        self.manager.start(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            parameters_revision=revision,
        )
        pose = self.manager.validate_active_pose(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            x=1.5,
            y=1.5,
            yaw=0.2,
        )
        self.assertEqual(pose, {"x": 1.5, "y": 1.5, "yaw": 0.2})
        with self.assertRaises(NavigationConflict):
            self.manager.validate_active_pose(
                map_id=MAP_ID,
                map_revision="c" * 64,
                x=1.5,
                y=1.5,
                yaw=0.0,
            )
        with self.assertRaises(NavigationPoseError):
            self.manager.validate_active_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=0.01,
                y=0.01,
                yaw=0.0,
            )

    def test_unexpected_exit_invokes_terminal_callback_once_outside_lock(self):
        self.manager.close()
        exiting = self.root / "exit_launcher.py"
        exiting.write_text("import time; time.sleep(0.05); raise SystemExit(7)\n")
        event = threading.Event()
        reasons = []
        holder = {}

        def terminal(reason):
            # Calling back into snapshot would deadlock if invoked under lock.
            holder["manager"].snapshot()
            reasons.append(reason)
            event.set()

        self.launcher = exiting
        self.runtime = self.root / "runtime-exit"
        self.manager = self.make_manager(
            on_terminal=terminal,
            startup_grace_seconds=0.0,
        )
        holder["manager"] = self.manager
        self.manager.start(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            parameters_revision=self.manager.parameters_snapshot()["revision"],
        )
        self.assertTrue(event.wait(2.0))
        self.assertEqual(reasons, ["pipeline_exit"])
        self.assertEqual(self.manager.snapshot()["pipeline"]["state"], "failed")
        time.sleep(0.1)
        self.assertEqual(reasons, ["pipeline_exit"])

    def test_launcher_exit_closes_gate_before_terminating_surviving_group(self):
        events = []
        token = "surviving-group-test"
        job_dir = self.manager.jobs_dir / token
        job_dir.mkdir(parents=True)

        class ExitedProcess:
            def wait(self):
                events.append("wait")
                return 9

        process = ExitedProcess()

        def terminal(reason):
            # Re-entering the manager proves the callback is outside its lock.
            self.manager.snapshot()
            events.append(f"callback:{reason}")

        self.manager.on_terminal = terminal
        with self.manager._lock:
            self.manager._pipeline_token = token
            self.manager._process = process
            self.manager._pgid = 4242
            self.manager._job_dir = job_dir
            self.manager._stop_requested = False
            self.manager._pipeline = {
                "state": "running",
                "job_id": token,
                "error": None,
                "started_at": "now",
                "stopped_at": None,
            }
        self.manager._group_alive = lambda pgid: pgid == 4242
        self.manager._terminate_group = (
            lambda observed_process, pgid: events.append(
                f"terminate:{observed_process is process}:{pgid}"
            )
        )
        self.manager._cleanup_job_dir = (
            lambda observed: events.append(f"cleanup:{observed == job_dir}")
        )

        self.manager._monitor(token, process, 4242)

        self.assertEqual(
            events,
            [
                "wait",
                "callback:pipeline_exit",
                "terminate:True:4242",
                "cleanup:True",
            ],
        )
        self.assertEqual(self.manager.snapshot()["pipeline"]["state"], "failed")
        self.assertIsNone(self.manager._process)
        self.assertIsNone(self.manager._pgid)

    def test_monitor_leaves_expected_stop_teardown_to_stop_owner(self):
        events = []
        token = "expected-stop-test"

        class ExitedProcess:
            def wait(self):
                events.append("wait")
                return 130

        process = ExitedProcess()
        with self.manager._lock:
            self.manager._pipeline_token = token
            self.manager._process = process
            self.manager._pgid = 4343
            self.manager._stop_requested = True
            self.manager._pipeline = {
                "state": "stopping",
                "job_id": token,
                "error": None,
                "started_at": "now",
                "stopped_at": None,
            }
        self.manager.on_terminal = lambda reason: events.append(f"callback:{reason}")
        self.manager._group_alive = lambda pgid: events.append(f"alive:{pgid}") or True
        self.manager._terminate_group = lambda process, pgid: events.append("terminate")

        self.manager._monitor(token, process, 4343)

        self.assertEqual(events, ["wait"])
        self.assertEqual(self.manager.snapshot()["pipeline"]["state"], "stopping")

    def test_command_spec_rejects_shell_like_or_missing_tokens(self):
        executable = str(Path(sys.executable).resolve())
        for argv in (
            (executable, PARAMS_FILE_TOKEN),
            (executable, MAP_YAML_TOKEN),
            (executable, MAP_YAML_TOKEN, PARAMS_FILE_TOKEN, "{command}"),
        ):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                NavigationCommandSpec(argv)


if __name__ == "__main__":
    unittest.main()
