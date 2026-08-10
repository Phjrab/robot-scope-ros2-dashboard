import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from robot_dashboard.mapping_jobs import (
    CommandSpec,
    InvalidMapName,
    JobBusyError,
    MappingJobError,
    MappingJobManager,
    PipelineNotRunning,
    SaveCommandSpec,
    SaveResultError,
)
from robot_dashboard.saved_maps import SavedMapCatalog


PIPELINE_PROGRAM = r"""
import signal
import subprocess
import sys
import time

child = subprocess.Popen([
    sys.executable,
    "-c",
    "import signal,sys,time; signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); print('child-ready', flush=True); time.sleep(120)",
])
print(f"pipeline-ready child={child.pid}", flush=True)
"""


PCD_SAVE_PROGRAM = r"""
from pathlib import Path
import struct
import sys

prefix = Path(sys.argv[1])
header = (
    "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z intensity\n"
    "SIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\n"
    "WIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA binary\n"
).encode("ascii")
prefix.with_name(prefix.name + ".pcd").write_bytes(header + struct.pack("<ffff", 1, 2, 3, 4))
print("pcd-written", flush=True)
"""


OCCUPANCY_SAVE_PROGRAM = r"""
from pathlib import Path
import sys

prefix = Path(sys.argv[1])
prefix.with_name(prefix.name + ".pgm").write_bytes(b"P5\n1 1\n255\n\x00")
prefix.with_name(prefix.name + ".yaml").write_text(
    f"image: {prefix.name}.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n",
    encoding="utf-8",
)
print("occupancy-written", flush=True)
"""


def wait_until(predicate, timeout=4.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    return None


def process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class MappingJobManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.maps = self.root / "maps"
        self.maps.mkdir()
        self.pipeline_script = self._script("pipeline.py", PIPELINE_PROGRAM)
        self.pcd_script = self._script("save_pcd.py", PCD_SAVE_PROGRAM)
        self.occupancy_script = self._script("save_grid.py", OCCUPANCY_SAVE_PROGRAM)
        self.managers = []

    def tearDown(self):
        for manager in reversed(self.managers):
            manager.close()
        self.temporary.cleanup()

    def _script(self, name, contents):
        path = self.root / name
        path.write_text(contents, encoding="utf-8")
        return path

    def manager(self, *, log_capacity=50, save_commands=None, require_pipeline=True):
        commands = save_commands or {
            "pointcloud3d": SaveCommandSpec(
                (sys.executable, str(self.pcd_script), "{output_prefix}"),
                (".pcd",),
                cwd=self.root,
                timeout_seconds=2,
            ),
            "occupancy2d": SaveCommandSpec(
                (sys.executable, str(self.occupancy_script), "{output_prefix}"),
                (".yaml", ".pgm"),
                cwd=self.root,
                timeout_seconds=2,
            ),
        }
        manager = MappingJobManager(
            project_dir=self.root,
            output_dir=self.maps,
            start_command=CommandSpec(
                (sys.executable, str(self.pipeline_script)),
                cwd=self.root,
                timeout_seconds=2,
            ),
            save_commands=commands,
            log_capacity=log_capacity,
            stop_grace_seconds=0.3,
            require_pipeline_for_save=require_pipeline,
        )
        self.managers.append(manager)
        return manager

    def start_ready(self, manager):
        snapshot = manager.start_mapping()
        self.assertEqual(snapshot["pipeline"]["state"], "starting")
        ready = wait_until(
            lambda: next(
                (
                    item
                    for item in manager.snapshot()["logs"]
                    if "pipeline-ready child=" in item["message"]
                ),
                None,
            )
        )
        self.assertIsNotNone(ready)
        self.assertIsNotNone(
            wait_until(lambda: manager.snapshot()["pipeline"]["state"] == "running")
        )
        return int(ready["message"].split("child=", 1)[1])

    def test_start_is_singleton_and_stop_terminates_the_process_group(self):
        manager = self.manager()
        child_pid = self.start_ready(manager)
        with self.assertRaises(JobBusyError):
            manager.start_mapping()

        snapshot = manager.stop_mapping()
        self.assertEqual(snapshot["pipeline"]["state"], "stopped")
        self.assertIsNotNone(snapshot["pipeline"]["stopped_at"])
        self.assertIsNotNone(wait_until(lambda: not process_exists(child_pid)))
        self.assertIn("mapping pipeline stopped", [item["message"] for item in snapshot["logs"]])

    def test_background_child_remains_owned_after_launcher_exits(self):
        pid_file = self.root / "background.pid"
        launcher = self._script(
            "background_launcher.py",
            "from pathlib import Path\n"
            "import subprocess,sys\n"
            f"pid_file=Path({str(pid_file)!r})\n"
            "child=subprocess.Popen([sys.executable, '-c', "
            "'import signal,sys,time; signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); time.sleep(120)'], "
            "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "pid_file.write_text(str(child.pid))\n"
            "print('launcher-complete', flush=True)\n",
        )
        manager = MappingJobManager(
            project_dir=self.root,
            output_dir=self.maps,
            start_command=CommandSpec((sys.executable, str(launcher)), cwd=self.root),
            save_commands={},
            log_capacity=20,
            stop_grace_seconds=0.2,
        )
        self.managers.append(manager)
        manager.start_mapping()
        self.assertIsNotNone(wait_until(pid_file.exists))
        child_pid = int(pid_file.read_text())
        self.assertIsNotNone(wait_until(lambda: process_exists(child_pid)))
        self.assertIsNotNone(
            wait_until(lambda: manager.snapshot()["pipeline"]["state"] == "running")
        )

        manager.stop_mapping()
        self.assertIsNotNone(wait_until(lambda: not process_exists(child_pid)))

    def test_nonzero_readiness_launcher_cleans_its_complete_process_group(self):
        pid_file = self.root / "failed-child.pid"
        launcher = self._script(
            "failed_launcher.py",
            "from pathlib import Path\n"
            "import subprocess,sys\n"
            f"pid_file=Path({str(pid_file)!r})\n"
            "child=subprocess.Popen([sys.executable, '-c', "
            "'import signal,sys,time; signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); time.sleep(120)'])\n"
            "pid_file.write_text(str(child.pid))\n"
            "print('raw readiness failed', flush=True)\n"
            "sys.exit(7)\n",
        )
        manager = MappingJobManager(
            project_dir=self.root,
            output_dir=self.maps,
            start_command=CommandSpec((sys.executable, str(launcher)), cwd=self.root),
            save_commands={},
            stop_grace_seconds=0.2,
        )
        self.managers.append(manager)

        started = manager.start_mapping()
        self.assertEqual(started["pipeline"]["state"], "starting")
        self.assertIsNotNone(wait_until(pid_file.exists))
        child_pid = int(pid_file.read_text())
        self.assertIsNotNone(
            wait_until(lambda: manager.snapshot()["pipeline"]["state"] == "failed")
        )
        self.assertIsNotNone(wait_until(lambda: not process_exists(child_pid)))
        failed = manager.snapshot()["pipeline"]
        self.assertEqual(failed["exit_code"], 7)
        self.assertIn("readiness launcher", failed["error"])

    def test_stop_during_readiness_start_cannot_transition_back_to_running(self):
        pid_file = self.root / "starting-child.pid"
        launcher = self._script(
            "slow_launcher.py",
            "from pathlib import Path\n"
            "import signal,subprocess,sys,time\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(130))\n"
            f"pid_file=Path({str(pid_file)!r})\n"
            "child=subprocess.Popen([sys.executable, '-c', "
            "'import signal,sys,time; signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); time.sleep(120)'])\n"
            "pid_file.write_text(str(child.pid))\n"
            "time.sleep(120)\n",
        )
        manager = MappingJobManager(
            project_dir=self.root,
            output_dir=self.maps,
            start_command=CommandSpec((sys.executable, str(launcher)), cwd=self.root),
            save_commands={},
            stop_grace_seconds=0.2,
        )
        self.managers.append(manager)

        self.assertEqual(manager.start_mapping()["pipeline"]["state"], "starting")
        self.assertIsNotNone(wait_until(pid_file.exists))
        child_pid = int(pid_file.read_text())
        stopped = manager.stop_mapping()
        self.assertEqual(stopped["pipeline"]["state"], "stopped")
        self.assertIsNotNone(wait_until(lambda: not process_exists(child_pid)))
        time.sleep(0.1)
        self.assertEqual(manager.snapshot()["pipeline"]["state"], "stopped")

    def test_successful_launcher_without_surviving_pipeline_fails_closed(self):
        launcher = self._script("empty_launcher.py", "print('done', flush=True)\n")
        manager = MappingJobManager(
            project_dir=self.root,
            output_dir=self.maps,
            start_command=CommandSpec((sys.executable, str(launcher)), cwd=self.root),
            save_commands={},
            stop_grace_seconds=0.2,
        )
        self.managers.append(manager)
        manager.start_mapping()
        self.assertIsNotNone(
            wait_until(lambda: manager.snapshot()["pipeline"]["state"] == "failed")
        )
        self.assertIn("no pipeline processes", manager.snapshot()["pipeline"]["error"])

    def test_all_processes_are_spawned_without_a_shell(self):
        manager = self.manager()
        real_popen = __import__("subprocess").Popen
        with mock.patch("robot_dashboard.mapping_jobs.subprocess.Popen", wraps=real_popen) as popen:
            self.start_ready(manager)
            manager.save_map("room_01", "pointcloud3d")
            manager.stop_mapping()

        self.assertGreaterEqual(len(popen.call_args_list), 2)
        for call in popen.call_args_list:
            self.assertIsInstance(call.args[0], list)
            self.assertIs(call.kwargs["shell"], False)
            self.assertIs(call.kwargs["start_new_session"], True)

    def test_map_names_and_map_kinds_are_not_command_input(self):
        manager = self.manager(require_pipeline=False)
        for name in ("", "../room", "/tmp/room", "room;touch", "room map", "맵", "-room", "a" * 65):
            with self.subTest(name=name), self.assertRaises(InvalidMapName):
                manager.save_map(name, "pointcloud3d")
        with self.assertRaises(MappingJobError):
            manager.save_map("room", "../../arbitrary-command")

    def test_save_requires_a_running_pipeline_by_default(self):
        manager = self.manager()
        with self.assertRaises(PipelineNotRunning):
            manager.save_map("room", "pointcloud3d")

    def test_pcd_save_is_validated_then_published_from_staging(self):
        manager = self.manager()
        self.start_ready(manager)
        snapshot = manager.save_map("lecture_room", "pointcloud3d")

        self.assertEqual(snapshot["operation"]["state"], "succeeded")
        self.assertEqual(snapshot["operation"]["files"], ["lecture_room.pcd"])
        self.assertTrue((self.maps / "lecture_room.pcd").is_file())
        self.assertFalse((self.maps / ".robot_scope_jobs").exists())
        serialized = str(snapshot)
        self.assertNotIn(str(self.root), serialized)
        with self.assertRaises(SaveResultError):
            manager.save_map("lecture_room", "pointcloud3d")

    def test_occupancy_save_requires_yaml_and_its_local_pgm(self):
        manager = self.manager()
        self.start_ready(manager)
        snapshot = manager.save_map("floor_a", "occupancy2d")

        self.assertEqual(snapshot["operation"]["files"], ["floor_a.yaml", "floor_a.pgm"])
        self.assertTrue((self.maps / "floor_a.yaml").is_file())
        self.assertTrue((self.maps / "floor_a.pgm").read_bytes().startswith(b"P5"))

    def test_missing_or_malformed_outputs_fail_without_partial_publication(self):
        no_output = self._script("no_output.py", "print('done')\n")
        bad_pcd = self._script(
            "bad_pcd.py",
            "from pathlib import Path; import sys; p=Path(sys.argv[1]); "
            "p.with_name(p.name+'.pcd').write_text('not a pcd')\n",
        )
        commands = {
            "missing": SaveCommandSpec(
                (sys.executable, str(no_output), "{output_prefix}"),
                (".pcd",),
                cwd=self.root,
                timeout_seconds=2,
            ),
            "malformed": SaveCommandSpec(
                (sys.executable, str(bad_pcd), "{output_prefix}"),
                (".pcd",),
                cwd=self.root,
                timeout_seconds=2,
            ),
        }
        manager = self.manager(save_commands=commands, require_pipeline=False)
        for name, kind in (("missing", "missing"), ("broken", "malformed")):
            with self.subTest(kind=kind), self.assertRaises(SaveResultError):
                manager.save_map(name, kind)
            self.assertEqual(manager.snapshot()["operation"]["state"], "failed")
            self.assertEqual(list(self.maps.glob(f"{name}.*")), [])

    def test_saver_and_catalog_share_the_exact_file_limit_boundary(self):
        catalog = SavedMapCatalog(
            [self.maps],
            managed_roots=[self.maps],
            max_file_bytes=1_024,
        )
        writer = self._script(
            "bounded_pcd.py",
            "from pathlib import Path\n"
            "import struct,sys\n"
            "prefix=Path(sys.argv[1]); target=int(sys.argv[2])\n"
            "header=(\"# .PCD v0.7\\nVERSION 0.7\\nFIELDS x y z intensity\\n\"\n"
            "        \"SIZE 4 4 4 4\\nTYPE F F F F\\nCOUNT 1 1 1 1\\n\"\n"
            "        \"WIDTH 1\\nHEIGHT 1\\nPOINTS 1\\nDATA binary\\n\").encode('ascii')\n"
            "content=header+struct.pack('<ffff',1,2,3,4)\n"
            "prefix.with_name(prefix.name+'.pcd').write_bytes(content+b'\\0'*(target-len(content)))\n",
        )
        commands = {
            "exact": SaveCommandSpec(
                (sys.executable, str(writer), "{output_prefix}", "1024"),
                (".pcd",),
                cwd=self.root,
                max_result_bytes=catalog.max_file_bytes,
            ),
            "over": SaveCommandSpec(
                (sys.executable, str(writer), "{output_prefix}", "1025"),
                (".pcd",),
                cwd=self.root,
                max_result_bytes=catalog.max_file_bytes,
            ),
        }
        manager = self.manager(save_commands=commands, require_pipeline=False)

        saved = manager.save_map("at_limit", "exact")
        self.assertEqual(commands["exact"].max_result_bytes, catalog.max_file_bytes)
        self.assertEqual((self.maps / "at_limit.pcd").stat().st_size, 1_024)
        self.assertEqual(saved["operation"]["state"], "succeeded")
        self.assertIn(
            "at_limit.pcd",
            [item["file_name"] for item in catalog.list_snapshot()["maps"]],
        )

        with self.assertRaisesRegex(SaveResultError, "exceeds the configured limit"):
            manager.save_map("over_limit", "over")
        self.assertFalse((self.maps / "over_limit.pcd").exists())

    def test_only_one_save_can_run_at_a_time(self):
        slow_script = self._script(
            "slow_save.py",
            "import sys,time; time.sleep(0.5); exec(open(sys.argv[2]).read())\n",
        )
        commands = {
            "pointcloud3d": SaveCommandSpec(
                (
                    sys.executable,
                    str(slow_script),
                    "{output_prefix}",
                    str(self.pcd_script),
                ),
                (".pcd",),
                cwd=self.root,
                timeout_seconds=2,
            )
        }
        manager = self.manager(save_commands=commands, require_pipeline=False)
        result = []
        thread = threading.Thread(
            target=lambda: result.append(manager.save_map("first", "pointcloud3d")),
            daemon=True,
        )
        thread.start()
        self.assertIsNotNone(wait_until(lambda: manager.snapshot()["operation"]["state"] == "saving"))
        with self.assertRaises(JobBusyError):
            manager.save_map("second", "pointcloud3d")
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]["operation"]["state"], "succeeded")

    def test_close_cancels_an_inflight_save_and_blocks_new_work(self):
        hanging_script = self._script(
            "hanging_save.py",
            "import signal,sys,time\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
            "time.sleep(120)\n",
        )
        manager = self.manager(
            save_commands={
                "pointcloud3d": SaveCommandSpec(
                    (sys.executable, str(hanging_script), "{output_prefix}"),
                    (".pcd",),
                    cwd=self.root,
                    timeout_seconds=30,
                )
            },
            require_pipeline=False,
        )
        errors = []

        def run_save():
            try:
                manager.save_map("cancelled", "pointcloud3d")
            except MappingJobError as exc:
                errors.append(exc)

        thread = threading.Thread(target=run_save, daemon=True)
        thread.start()
        self.assertIsNotNone(wait_until(lambda: manager.snapshot()["operation"]["state"] == "saving"))
        manager.close()
        thread.join(timeout=3)

        self.assertFalse(thread.is_alive())
        self.assertTrue(errors)
        self.assertEqual(manager.snapshot()["operation"]["state"], "failed")
        self.assertFalse((self.maps / "cancelled.pcd").exists())
        with self.assertRaises(MappingJobError):
            manager.start_mapping()

    def test_log_ring_buffer_is_bounded_and_reports_truncation(self):
        noisy_script = self._script(
            "noisy_pipeline.py",
            "import signal,sys,time\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
            "[print(f'line-{i}', flush=True) for i in range(40)]\n"
            "time.sleep(120)\n",
        )
        manager = MappingJobManager(
            project_dir=self.root,
            output_dir=self.maps,
            start_command=CommandSpec((sys.executable, str(noisy_script)), cwd=self.root),
            save_commands={},
            log_capacity=10,
            stop_grace_seconds=0.2,
        )
        self.managers.append(manager)
        manager.start_mapping()
        self.assertIsNotNone(wait_until(lambda: manager.snapshot()["log_cursor"] >= 40))
        snapshot = manager.snapshot(since_log_seq=1)
        self.assertLessEqual(len(snapshot["logs"]), 10)
        self.assertTrue(snapshot["logs_truncated"])
        self.assertEqual(snapshot["logs"][-1]["seq"], snapshot["log_cursor"])

    def test_local_operation_reuses_single_job_state_and_exposes_safe_details(self):
        manager = self.manager(require_pipeline=False)
        with mock.patch.object(manager, "_spawn") as spawn:
            snapshot = manager.run_local_operation(
                "pcd_to_2d",
                "converted_room",
                lambda: {
                    "files": ["converted_room.yaml", "converted_room.pgm"],
                    "details": {
                        "result_map_id": "a" * 24,
                        "selected_points": 123,
                        "occupied_cells": 45,
                        "width": 20,
                        "height": 10,
                    },
                },
            )

        spawn.assert_not_called()
        operation = snapshot["operation"]
        self.assertEqual(operation["state"], "succeeded")
        self.assertEqual(operation["kind"], "pcd_to_2d")
        self.assertEqual(
            operation["files"],
            ["converted_room.yaml", "converted_room.pgm"],
        )
        self.assertEqual(operation["details"]["result_map_id"], "a" * 24)
        self.assertEqual(operation["details"]["selected_points"], 123)

    def test_local_operation_failure_remains_in_operation_snapshot(self):
        manager = self.manager(require_pipeline=False)

        def fail():
            raise RuntimeError("projected filter left no points")

        with self.assertRaisesRegex(RuntimeError, "left no points"):
            manager.run_local_operation("pcd_to_2d", "failed_room", fail)

        operation = manager.snapshot()["operation"]
        self.assertEqual(operation["state"], "failed")
        self.assertEqual(operation["kind"], "pcd_to_2d")
        self.assertEqual(operation["files"], [])
        self.assertEqual(operation["details"], {})
        self.assertIn("left no points", operation["error"])

    def test_local_operation_holds_the_same_single_job_lease(self):
        manager = self.manager(require_pipeline=False)
        entered = threading.Event()
        release = threading.Event()
        results = []

        def worker():
            entered.set()
            release.wait(timeout=2)
            return {"files": ["first.yaml", "first.pgm"], "details": {}}

        thread = threading.Thread(
            target=lambda: results.append(
                manager.run_local_operation("pcd_to_2d", "first", worker)
            ),
            daemon=True,
        )
        thread.start()
        self.assertTrue(entered.wait(timeout=1))
        with self.assertRaises(JobBusyError):
            manager.run_local_operation(
                "pcd_to_2d",
                "second",
                lambda: {"files": [], "details": {}},
            )
        with self.assertRaises(JobBusyError):
            manager.start_mapping()
        release.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]["operation"]["state"], "succeeded")

    def test_local_reservation_exists_before_worker_and_has_stable_job_id(self):
        manager = self.manager(require_pipeline=False)
        reservation = manager.reserve_local_operation("pcd_to_2d", "reserved")
        operation = reservation["operation"]
        job_id = operation["job_id"]

        self.assertRegex(job_id, r"^[0-9a-f]{32}$")
        self.assertEqual(operation["state"], "saving")
        self.assertEqual(operation["map_name"], "reserved")
        self.assertEqual(manager.snapshot()["operation"]["job_id"], job_id)

        completed = manager.run_reserved_local_operation(
            job_id,
            lambda: {
                "files": ["reserved.yaml", "reserved.pgm"],
                "details": {"result_map_id": "b" * 24},
            },
        )
        self.assertEqual(completed["operation"]["job_id"], job_id)
        self.assertEqual(completed["operation"]["state"], "succeeded")

    def test_reservation_preflight_rejects_busy_stopping_and_closing(self):
        manager = self.manager(require_pipeline=False)
        first = manager.reserve_local_operation("pcd_to_2d", "first")
        first_id = first["operation"]["job_id"]
        with self.assertRaises(JobBusyError):
            manager.reserve_local_operation("pcd_to_2d", "second")
        self.assertEqual(manager.snapshot()["operation"]["job_id"], first_id)
        manager.run_reserved_local_operation(
            first_id,
            lambda: {"files": ["first.yaml", "first.pgm"], "details": {}},
        )

        with manager._lock:
            manager._pipeline["state"] = "stopping"
        with self.assertRaises(JobBusyError):
            manager.reserve_local_operation("pcd_to_2d", "stopping")
        with manager._lock:
            manager._pipeline["state"] = "idle"
        manager.close()
        with self.assertRaises(MappingJobError):
            manager.reserve_local_operation("pcd_to_2d", "closing")

    def test_reserved_worker_failure_is_recorded_under_reserved_job_id(self):
        manager = self.manager(require_pipeline=False)
        reservation = manager.reserve_local_operation("pcd_to_2d", "failed_reserved")
        job_id = reservation["operation"]["job_id"]

        def fail():
            raise RuntimeError("source revision changed")

        with self.assertRaisesRegex(RuntimeError, "revision changed"):
            manager.run_reserved_local_operation(job_id, fail)
        operation = manager.snapshot()["operation"]
        self.assertEqual(operation["job_id"], job_id)
        self.assertEqual(operation["state"], "failed")
        self.assertIn("revision changed", operation["error"])

    def test_unscheduled_reservation_is_failed_and_releases_the_job_lease(self):
        manager = self.manager(require_pipeline=False)
        reservation = manager.reserve_local_operation("pcd_to_2d", "unscheduled")
        job_id = reservation["operation"]["job_id"]
        failed = manager.fail_reserved_local_operation(job_id, "worker scheduling failed")
        self.assertEqual(failed["operation"]["job_id"], job_id)
        self.assertEqual(failed["operation"]["state"], "failed")
        self.assertIn("scheduling failed", failed["operation"]["error"])
        replacement = manager.reserve_local_operation("pcd_to_2d", "replacement")
        replacement_id = replacement["operation"]["job_id"]
        self.assertNotEqual(replacement_id, job_id)
        manager.run_reserved_local_operation(
            replacement_id,
            lambda: {"files": ["replacement.yaml", "replacement.pgm"], "details": {}},
        )

    def test_wrong_concurrent_and_replayed_reservation_ids_cannot_execute(self):
        manager = self.manager(require_pipeline=False)
        reservation = manager.reserve_local_operation("pcd_to_2d", "once")
        job_id = reservation["operation"]["job_id"]
        calls = []
        with self.assertRaises(MappingJobError):
            manager.run_reserved_local_operation("0" * 32, lambda: calls.append("wrong"))
        self.assertEqual(calls, [])
        self.assertEqual(manager.snapshot()["operation"]["job_id"], job_id)

        entered = threading.Event()
        release = threading.Event()

        def worker():
            entered.set()
            release.wait(timeout=2)
            calls.append("right")
            return {"files": ["once.yaml", "once.pgm"], "details": {}}

        thread = threading.Thread(
            target=lambda: manager.run_reserved_local_operation(job_id, worker),
            daemon=True,
        )
        thread.start()
        self.assertTrue(entered.wait(timeout=1))
        with self.assertRaises(JobBusyError):
            manager.run_reserved_local_operation(job_id, lambda: calls.append("concurrent"))
        release.set()
        thread.join(timeout=2)
        self.assertEqual(calls, ["right"])
        succeeded = manager.snapshot()["operation"].copy()
        with self.assertRaises(MappingJobError):
            manager.run_reserved_local_operation(job_id, lambda: calls.append("replay"))
        self.assertEqual(manager.snapshot()["operation"], succeeded)
        self.assertEqual(calls, ["right"])

    def test_shutdown_signal_reaches_running_local_worker_before_publication(self):
        manager = self.manager(require_pipeline=False)
        reservation = manager.reserve_local_operation("pcd_to_2d", "shutdown_guard")
        job_id = reservation["operation"]["job_id"]
        entered = threading.Event()
        errors = []

        def worker():
            entered.set()
            self.assertIsNotNone(
                wait_until(lambda: manager.local_operation_cancelled(job_id), timeout=2)
            )
            raise RuntimeError("cancelled before publication")

        def run_worker():
            try:
                manager.run_reserved_local_operation(job_id, worker)
            except RuntimeError as exc:
                errors.append(exc)

        worker_thread = threading.Thread(target=run_worker, daemon=True)
        worker_thread.start()
        self.assertTrue(entered.wait(timeout=1))
        close_thread = threading.Thread(target=manager.close, daemon=True)
        close_thread.start()
        worker_thread.join(timeout=3)
        close_thread.join(timeout=3)

        self.assertFalse(worker_thread.is_alive())
        self.assertFalse(close_thread.is_alive())
        self.assertTrue(errors)
        operation = manager.snapshot()["operation"]
        self.assertEqual(operation["job_id"], job_id)
        self.assertEqual(operation["state"], "failed")
        self.assertIn("before publication", operation["error"])

    def test_command_specs_reject_relative_executables_and_unknown_templates(self):
        with self.assertRaises(ValueError):
            CommandSpec(("python3", "worker.py"))
        with self.assertRaises(ValueError):
            CommandSpec((sys.executable, "{output_prefix}"))
        with self.assertRaises(ValueError):
            SaveCommandSpec((sys.executable, "{user_command}"), (".pcd",))
        with self.assertRaises(ValueError):
            SaveCommandSpec((sys.executable, "noop"), (".pcd",))
        with self.assertRaises(ValueError):
            SaveCommandSpec((sys.executable, "{output_prefix}"), ("../pcd",))


if __name__ == "__main__":
    unittest.main()
