import json
import multiprocessing
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from robot_dashboard.dataset_capture import (
    MAX_MANIFEST_BYTES,
    DatasetCaptureConflict,
    DatasetCaptureManager,
    DatasetCaptureNotFound,
    DatasetCaptureUnavailable,
    DatasetCaptureValidationError,
)


JPEG_GO2 = b"\xff\xd8go2-frame\xff\xd9"
JPEG_RS = b"\xff\xd8realsense-frame\xff\xd9"


class FakeCameras:
    def __init__(self):
        self.opens = []
        self.closes = []
        self.fail_source = ""
        self.seq = 0
        self.mode = "ok"

    def open(self, source_id):
        self.opens.append(source_id)
        if source_id == self.fail_source:
            return {"accepted": False, "reason": "camera unavailable"}
        return {"accepted": True, "token": f"token-{source_id}"}

    def close(self, source_id, token):
        self.closes.append((source_id, token))
        return {"released": True}

    def snapshots(self, source_ids):
        self.seq += 1
        base_stamp = 1_800_000_000_000_000 + self.seq * 1_000
        result = {}
        for source_id in source_ids:
            stamp = base_stamp
            if self.mode == "skew" and source_id == "realsense_color":
                stamp += 500_000
            result[source_id] = {
                "source_id": source_id,
                "stream_id": f"stream-{source_id}",
                "seq": self.seq,
                "stamp_us": stamp,
                "state": "stale" if self.mode == "stale" else "ok",
                "age_s": 3.0 if self.mode == "stale" else 0.01,
                "topic": f"camera://{source_id}",
                "transport": "jpeg",
                "width": 640,
                "height": 480,
                "data": JPEG_GO2 if source_id == "go2_front" else JPEG_RS,
            }
        return result


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def abandon_capture_process(root):
    cameras = FakeCameras()
    manager = DatasetCaptureManager(
        Path(root).resolve(),
        camera_open=cameras.open,
        camera_close=cameras.close,
        camera_snapshots=cameras.snapshots,
        metadata_snapshot=lambda: {"state": "ok", "pose": {"x": 1.0}},
        minimum_free_bytes=0,
        startup_timeout_s=0.5,
    )
    manager.start(("go2_front",), 5.0, "abrupt interruption")
    if not wait_until(lambda: manager.snapshot()["saved"] >= 1):
        os._exit(2)
    os._exit(0)


class DatasetCaptureTests(unittest.TestCase):
    def make_manager(self, root, cameras=None, **kwargs):
        cameras = cameras or FakeCameras()
        root_path = Path(root)
        if kwargs.pop("resolve_root", True):
            root_path = root_path.resolve()
        manager = DatasetCaptureManager(
            root_path,
            camera_open=cameras.open,
            camera_close=cameras.close,
            camera_snapshots=cameras.snapshots,
            metadata_snapshot=lambda: {"state": "ok", "pose": {"x": 1.0}},
            minimum_free_bytes=kwargs.pop("minimum_free_bytes", 0),
            startup_timeout_s=kwargs.pop("startup_timeout_s", 0.5),
            **kwargs,
        )
        return manager, cameras

    def test_single_and_dual_capture_publish_atomic_samples_and_gallery(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, cameras = self.make_manager(temporary)
            started = manager.start(
                ("go2_front", "realsense_color"), 5.0, "corridor run"
            )
            self.assertEqual(started["state"], "starting")
            self.assertTrue(wait_until(lambda: manager.snapshot()["saved"] >= 2))
            session_id = manager.snapshot()["session_id"]
            stopped = manager.stop(session_id)
            self.assertEqual(stopped["state"], "completed")
            self.assertFalse(stopped["active"])
            self.assertGreaterEqual(stopped["saved"], 2)
            self.assertGreater(stopped["elapsed_s"], 0)
            self.assertEqual(cameras.opens, ["go2_front", "realsense_color"])
            self.assertEqual(
                set(cameras.closes),
                {
                    ("go2_front", "token-go2_front"),
                    ("realsense_color", "token-realsense_color"),
                },
            )

            session = Path(temporary) / "sessions" / session_id
            manifest = json.loads((session / "manifest.json").read_text())
            self.assertEqual(manifest["state"], "completed")
            self.assertFalse(manifest["pairing"]["hardware_synchronised"])
            self.assertFalse(any((session / "samples").glob(".tmp-*")))
            sample = session / "samples" / "00000001"
            self.assertEqual((sample / "go2_front.jpg").read_bytes(), JPEG_GO2)
            self.assertEqual((sample / "realsense_color.jpg").read_bytes(), JPEG_RS)
            metadata = json.loads((sample / "metadata.json").read_text())
            self.assertEqual(set(metadata["sources"]), {"go2_front", "realsense_color"})
            self.assertEqual(metadata["robot_pose"]["pose"]["x"], 1.0)
            self.assertEqual(metadata["schema_version"], 2)
            self.assertFalse(metadata["cross_host_clock_verified"])
            self.assertIsNone(
                metadata["sources"]["go2_front"]["capture_source_sequence"]
            )
            self.assertEqual(
                metadata["sources"]["go2_front"]["external_receive_sequence"],
                metadata["sources"]["go2_front"]["seq"],
            )
            self.assertEqual(
                metadata["receive_timestamp_domain"],
                "external-orin-monotonic",
            )
            self.assertEqual(
                metadata["sources"]["go2_front"]["image_sha256"],
                metadata["sources"]["go2_front"]["sha256"],
            )

            catalog = manager.list_sessions()
            self.assertEqual(catalog["sessions"][0]["session_id"], session_id)
            detail = manager.session_detail(session_id)
            self.assertGreaterEqual(detail["sample_count"], 2)
            self.assertLessEqual(len(detail["samples"]), 24)
            self.assertIn("has_older", detail["page"])
            self.assertEqual(
                manager.read_image(session_id, 1, "go2_front"), JPEG_GO2
            )

    def test_wp05_manifest_context_is_bounded_and_not_ground_truth(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(
                temporary,
                session_context_snapshot=lambda: {
                    "capture_profile": "dual-camera-shadow",
                    "robot_side_source_id": "go2-internal-realsense",
                    "network_topology_revision": "be5100m-wifi-v1",
                    "git_commit": "a" * 40,
                    "active_preview_profile": "640x480-mjpeg",
                    "perception_shadow_enabled": True,
                    "model_ids": ["lane-1", "object-1", "../invalid", "lane-1"],
                },
            )
            started = manager.start(("go2_front",), 5.0, "not-ground-truth")
            self.assertTrue(wait_until(lambda: manager.snapshot()["saved"] >= 1))
            manager.stop(started["session_id"])
            manifest = json.loads(
                (
                    Path(temporary)
                    / "sessions"
                    / started["session_id"]
                    / "manifest.json"
                ).read_text()
            )
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["created_at"], manifest["started_at"])
            self.assertEqual(manifest["finalized_at"], manifest["completed_at"])
            self.assertEqual(manifest["capture_profile"], "dual-camera-shadow")
            self.assertEqual(manifest["model_ids"], ["lane-1", "object-1"])
            self.assertTrue(manifest["perception_shadow_enabled"])
            self.assertEqual(manifest["filesystem_reserve"]["minimum_free_bytes"], 0)
            self.assertEqual(manifest["drop_counters"], manifest["drop_counts"])
            self.assertFalse(manifest["annotations_present"])

    def test_finalized_export_is_atomic_bounded_and_checksum_manifested(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(temporary)
            started = manager.start(("go2_front",), 5.0, "export")
            self.assertTrue(wait_until(lambda: manager.snapshot()["saved"] >= 1))
            manager.stop(started["session_id"])
            exported = manager.export_session(started["session_id"])
            self.assertTrue(exported["finalized"])
            self.assertRegex(exported["sha256"], r"^[0-9a-f]{64}$")
            archive, metadata = manager.export_download(exported["export_id"])
            self.assertEqual(metadata, exported)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertIn("manifest.json", names)
                self.assertIn("SHA256SUMS.json", names)
                self.assertIn("samples/00000001/go2_front.jpg", names)
                checksums = json.loads(bundle.read("SHA256SUMS.json"))
                self.assertEqual(
                    checksums["schema_version"],
                    "robot-scope.dataset-export/v1",
                )
                exported_manifest = json.loads(bundle.read("manifest.json"))
                self.assertEqual(exported_manifest["output_path"], "managed-dataset-root")
            self.assertFalse(any(manager.exports_dir.glob(".*.tmp")))

    def test_export_rejects_unfinished_traversal_low_disk_and_cleans_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(temporary)
            session_id = "20260812T120000Z_" + "9" * 32
            session = Path(temporary) / "sessions" / session_id
            (session / "samples").mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "state": "interrupted",
                        "sources": ["go2_front"],
                        "sample_count": 0,
                    }
                )
            )
            with self.assertRaises(DatasetCaptureConflict):
                manager.export_session(session_id)
            with self.assertRaises(DatasetCaptureNotFound):
                manager.export_session("../../private")

            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "state": "completed",
                        "completed_at": "2026-08-30T00:00:00.000Z",
                        "sources": ["go2_front"],
                        "sample_count": 0,
                    }
                )
            )
            manager._minimum_free_bytes = 100
            with patch.object(manager, "_free_bytes", return_value=100):
                with self.assertRaisesRegex(DatasetCaptureUnavailable, "reserve"):
                    manager.export_session(session_id)
            self.assertFalse(any(manager.exports_dir.iterdir()))

            manager._minimum_free_bytes = 0
            sample = session / "samples" / "00000001"
            sample.mkdir()
            (sample / "metadata.json").write_text("{}")
            (sample / "go2_front.jpg").write_bytes(JPEG_GO2)
            manifest = json.loads((session / "manifest.json").read_text())
            manifest["sample_count"] = 1
            (session / "manifest.json").write_text(json.dumps(manifest))
            with patch.object(
                manager,
                "_write_export_source",
                side_effect=DatasetCaptureUnavailable("synthetic export failure"),
            ):
                with self.assertRaisesRegex(DatasetCaptureUnavailable, "synthetic"):
                    manager.export_session(session_id)
            self.assertFalse(any(manager.exports_dir.iterdir()))
            self.assertFalse(manager.is_active())

    def test_partial_camera_open_rolls_back_exact_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            cameras = FakeCameras()
            cameras.fail_source = "realsense_color"
            manager, _ = self.make_manager(temporary, cameras)
            with self.assertRaises(DatasetCaptureUnavailable):
                manager.start(("go2_front", "realsense_color"), 1.0, "")
            self.assertEqual(
                cameras.closes, [("go2_front", "token-go2_front")]
            )
            self.assertEqual(manager.snapshot()["state"], "failed")

    def test_storage_failure_does_not_expose_host_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(temporary)
            secret_path = str(Path(temporary) / "sessions")
            manager.sessions_dir.rmdir()

            with self.assertRaises(DatasetCaptureUnavailable) as raised:
                manager.start(("go2_front",), 1.0, "")

            self.assertEqual(str(raised.exception), "dataset session storage is unavailable")
            self.assertEqual(
                manager.snapshot()["last_error"],
                "dataset session storage is unavailable",
            )
            self.assertNotIn(secret_path, str(raised.exception))
            self.assertNotIn(secret_path, manager.snapshot()["last_error"])

    def test_stale_and_excessively_skewed_frames_fail_closed_and_release(self):
        for mode in ("stale", "skew"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                cameras = FakeCameras()
                cameras.mode = mode
                manager, _ = self.make_manager(
                    temporary, cameras, startup_timeout_s=0.05
                )
                manager.start(("go2_front", "realsense_color"), 5.0, mode)
                self.assertTrue(
                    wait_until(
                        lambda: manager.snapshot()["state"] == "failed"
                        and len(cameras.closes) == 2
                    )
                )
                self.assertEqual(len(cameras.closes), 2)
                self.assertGreater(manager.snapshot()["dropped"], 0)
                manager.close()

    def test_quota_failure_stops_writer_and_releases_camera(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, cameras = self.make_manager(
                temporary, session_quota_bytes=MAX_MANIFEST_BYTES
            )
            manager.start(("go2_front",), 5.0, "tiny quota")
            self.assertTrue(wait_until(lambda: manager.snapshot()["state"] == "failed"))
            self.assertEqual(
                cameras.closes, [("go2_front", "token-go2_front")]
            )
            manager.close()
            self.assertEqual(len(cameras.closes), 1)

    def test_free_space_reserve_blocks_start_before_camera_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            minimum_free_bytes = 5 * 1024 * 1024
            manager, cameras = self.make_manager(
                temporary,
                minimum_free_bytes=minimum_free_bytes,
            )
            with patch.object(
                manager,
                "_free_bytes",
                return_value=minimum_free_bytes + MAX_MANIFEST_BYTES - 1,
            ):
                with self.assertRaisesRegex(
                    DatasetCaptureUnavailable,
                    "free-space reserve is not available",
                ):
                    manager.start(("go2_front",), 1.0, "reserve preflight")
            self.assertEqual(cameras.opens, [])
            self.assertEqual(list((Path(temporary) / "sessions").iterdir()), [])

    def test_free_space_reserve_failure_stops_writer_without_partial_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            cameras = FakeCameras()
            cameras.mode = "stale"
            manager, _ = self.make_manager(
                temporary,
                cameras,
                minimum_free_bytes=1,
            )
            started = manager.start(("go2_front",), 5.0, "reserve write")
            with patch.object(manager, "_free_bytes", return_value=0):
                cameras.mode = "ok"
                self.assertTrue(
                    wait_until(lambda: manager.snapshot()["state"] == "failed")
                )
            snapshot = manager.snapshot()
            self.assertEqual(
                snapshot["last_error"],
                "dataset storage free-space reserve was reached",
            )
            self.assertEqual(snapshot["saved"], 0)
            session = Path(temporary) / "sessions" / started["session_id"]
            self.assertFalse((session / "samples" / "00000001").exists())
            self.assertEqual(cameras.closes, [("go2_front", "token-go2_front")])
            manager.close()

    def test_validation_and_stale_session_stop_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(temporary)
            for sources in (
                (),
                ("go2_front", "go2_front"),
                ("http://evil.invalid/camera",),
            ):
                with self.assertRaises(DatasetCaptureValidationError):
                    manager.start(sources, 1.0, "")
            for rate in (0.1, 5.1, True):
                with self.assertRaises(DatasetCaptureValidationError):
                    manager.start(("go2_front",), rate, "")
            with self.assertRaises(DatasetCaptureValidationError):
                manager.start(("go2_front",), 1.0, "x\ny")

            started = manager.start(("go2_front",), 1.0, "valid")
            with self.assertRaises(DatasetCaptureConflict):
                manager.stop("20260812T120000Z_" + "0" * 32)
            manager.stop(started["session_id"])

    def test_root_and_image_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "real"
            target.mkdir()
            link = base / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(DatasetCaptureValidationError):
                self.make_manager(link, resolve_root=False)
            with self.assertRaises(DatasetCaptureValidationError):
                self.make_manager(Path("relative-datasets"), resolve_root=False)
            with self.assertRaises(DatasetCaptureValidationError):
                self.make_manager(Path("//"))
            with self.assertRaises(DatasetCaptureValidationError):
                self.make_manager(Path("/tmp/.."), resolve_root=False)
            parent_link = base / "parent-link"
            parent_link.symlink_to(base / "real", target_is_directory=True)
            with self.assertRaises(DatasetCaptureValidationError):
                self.make_manager(parent_link / "nested", resolve_root=False)

            manager, _ = self.make_manager(base / "datasets")
            started = manager.start(("go2_front",), 5.0, "")
            self.assertTrue(wait_until(lambda: manager.snapshot()["saved"] >= 1))
            session_id = started["session_id"]
            manager.stop(session_id)
            image = (
                base
                / "datasets"
                / "sessions"
                / session_id
                / "samples"
                / "00000001"
                / "go2_front.jpg"
            )
            image.unlink()
            image.symlink_to(Path("/etc/passwd"))
            with self.assertRaises(DatasetCaptureNotFound):
                manager.read_image(session_id, 1, "go2_front")
            with self.assertRaises(DatasetCaptureNotFound):
                manager.read_image("../../etc", 1, "go2_front")
            with self.assertRaises(DatasetCaptureNotFound):
                manager.read_image(session_id, 1, "../../secret")

    def test_active_manifest_is_recovered_as_interrupted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session_id = "20260812T120000Z_" + "a" * 32
            session = root / "sessions" / session_id
            (session / "samples").mkdir(parents=True)
            abandoned = session / "samples" / (".tmp-" + "b" * 32)
            abandoned.mkdir()
            (abandoned / "partial.jpg").write_bytes(b"partial")
            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "state": "capturing",
                        "sources": ["go2_front"],
                        "sample_count": 0,
                    }
                )
            )
            manager, _ = self.make_manager(root)
            recovered = json.loads((session / "manifest.json").read_text())
            self.assertEqual(recovered["state"], "interrupted")
            self.assertIn("dashboard stopped", recovered["last_error"])
            self.assertFalse(abandoned.exists())
            self.assertEqual(
                manager.list_sessions()["sessions"][0]["state"], "interrupted"
            )

    def test_abrupt_process_exit_recovers_published_files_as_interrupted(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = multiprocessing.get_context("spawn")
            process = context.Process(
                target=abandon_capture_process,
                args=(temporary,),
            )
            process.start()
            process.join(5.0)
            if process.is_alive():
                process.terminate()
                process.join(2.0)
            self.assertEqual(process.exitcode, 0)

            sessions = list((Path(temporary) / "sessions").iterdir())
            self.assertEqual(len(sessions), 1)
            manager, _ = self.make_manager(temporary)
            recovered = json.loads((sessions[0] / "manifest.json").read_text())
            self.assertEqual(recovered["state"], "interrupted")
            self.assertGreaterEqual(recovered["sample_count"], 1)
            self.assertIn("dashboard stopped", recovered["last_error"])
            self.assertFalse(any((sessions[0] / "samples").glob(".tmp-*")))
            self.assertEqual(
                manager.list_sessions()["sessions"][0]["state"],
                "interrupted",
            )

    def test_recovery_reconciles_one_atomically_published_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session_id = "20260812T120000Z_" + "d" * 32
            session = root / "sessions" / session_id
            sample = session / "samples" / "00000001"
            sample.mkdir(parents=True)
            (sample / "go2_front.jpg").write_bytes(JPEG_GO2)
            metadata = {
                "session_id": session_id,
                "sample_index": 1,
                "sources": {"go2_front": {"seq": 1}},
            }
            metadata_bytes = json.dumps(metadata).encode()
            (sample / "metadata.json").write_bytes(metadata_bytes)
            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "state": "capturing",
                        "sources": ["go2_front"],
                        "sample_count": 0,
                        "bytes_written": 0,
                    }
                )
            )
            self.make_manager(root)
            recovered = json.loads((session / "manifest.json").read_text())
            self.assertEqual(recovered["state"], "interrupted")
            self.assertEqual(recovered["sample_count"], 1)
            self.assertEqual(
                recovered["bytes_written"], len(JPEG_GO2) + len(metadata_bytes)
            )

    def test_completed_session_samples_are_never_scanned_at_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session_id = "20260812T120000Z_" + "f" * 32
            session = root / "sessions" / session_id
            (session / "samples").mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "state": "completed",
                        "sources": ["go2_front"],
                        "sample_count": 99_999_999,
                    }
                )
            )
            original_scandir = os.scandir

            def guarded_scandir(path):
                if Path(path) == session / "samples":
                    raise AssertionError("completed sample tree was scanned")
                return original_scandir(path)

            with patch("robot_dashboard.dataset_capture.os.scandir", guarded_scandir):
                manager, _ = self.make_manager(root)
            self.assertEqual(
                manager.list_sessions()["sessions"][0]["sample_count"],
                99_999_999,
            )

    def test_thread_start_failure_releases_token_and_never_leaks_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, cameras = self.make_manager(temporary)
            real_thread = threading.Thread
            starts = 0

            class FailingSecondThread(real_thread):
                def start(self):
                    nonlocal starts
                    starts += 1
                    if starts == 2:
                        raise RuntimeError("synthetic sampler start failure")
                    return super().start()

            original = threading.Thread
            threading.Thread = FailingSecondThread
            try:
                with self.assertRaises(DatasetCaptureUnavailable):
                    manager.start(("go2_front",), 1.0, "")
            finally:
                threading.Thread = original
            self.assertFalse(manager.is_active())
            self.assertEqual(cameras.closes, [("go2_front", "token-go2_front")])
            manager.close()

    def test_writer_owns_token_when_start_cleanup_join_times_out(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, cameras = self.make_manager(temporary)
            release_writer = threading.Event()

            def delayed_writer():
                release_writer.wait(2.0)
                manager._release_tokens()
                manager._writer_done_event.set()

            manager._writer_loop = delayed_writer
            real_thread = threading.Thread
            starts = 0

            class FailingSamplerThread(real_thread):
                def start(self):
                    nonlocal starts
                    starts += 1
                    if starts == 2:
                        raise RuntimeError("synthetic sampler start failure")
                    return super().start()

                def join(self, timeout=None):
                    if self.name == "robot-scope-dataset-writer":
                        return None
                    return super().join(timeout)

            original = threading.Thread
            threading.Thread = FailingSamplerThread
            try:
                with self.assertRaises(DatasetCaptureUnavailable):
                    manager.start(("go2_front",), 1.0, "")
            finally:
                threading.Thread = original
            self.assertEqual(cameras.closes, [])
            self.assertTrue(manager.is_active())
            release_writer.set()
            self.assertTrue(wait_until(lambda: len(cameras.closes) == 1))
            self.assertEqual(cameras.closes, [("go2_front", "token-go2_front")])
            manager.close()
            self.assertEqual(len(cameras.closes), 1)

    def test_quota_counts_metadata_before_any_sample_is_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, cameras = self.make_manager(
                temporary,
                session_quota_bytes=MAX_MANIFEST_BYTES + len(JPEG_GO2),
            )
            started = manager.start(("go2_front",), 5.0, "")
            self.assertTrue(wait_until(lambda: manager.snapshot()["state"] == "failed"))
            session = Path(temporary) / "sessions" / started["session_id"]
            self.assertFalse((session / "samples" / "00000001").exists())
            self.assertEqual(manager.snapshot()["saved"], 0)
            self.assertEqual(cameras.closes, [("go2_front", "token-go2_front")])
            # The writer publishes the terminal state before its final atomic
            # manifest fsync.  Join it before TemporaryDirectory removes the
            # session root so the full parallel test suite cannot race that
            # final write.
            manager.close()

    def test_corrupt_manifest_fields_are_bounded_in_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(temporary)
            session_id = "20260812T120000Z_" + "c" * 32
            session = Path(temporary) / "sessions" / session_id
            (session / "samples").mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "label": "x" * 10_000,
                        "state": "not-a-state",
                        "sources": ["go2_front"] * 10_000,
                        "capture_hz": 999,
                        "sample_count": 10**20,
                        "bytes_written": 10**30,
                        "output_path": "/" + "y" * 10_000,
                        "started_at": "z" * 1_000,
                    }
                )
            )
            summary = manager.list_sessions()["sessions"][0]
            self.assertEqual(summary["sources"], ["go2_front"])
            self.assertEqual(summary["state"], "unknown")
            self.assertEqual(summary["capture_hz"], 5.0)
            self.assertEqual(summary["sample_count"], 99_999_999)
            self.assertLessEqual(len(summary["label"]), 64)
            self.assertLessEqual(len(summary["output_path"]), 4096)
            self.assertLessEqual(len(summary["started_at"]), 64)

    def test_gallery_pages_are_bounded_and_cover_older_samples(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager, _ = self.make_manager(temporary)
            session_id = "20260812T120000Z_" + "e" * 32
            session = Path(temporary) / "sessions" / session_id
            samples = session / "samples"
            samples.mkdir(parents=True)
            for index in range(1, 61):
                sample = samples / f"{index:08d}"
                sample.mkdir()
                (sample / "go2_front.jpg").write_bytes(JPEG_GO2)
                (sample / "metadata.json").write_text(
                    json.dumps({"captured_at": f"sample-{index}", "pair_skew_us": 0})
                )
            (session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "state": "completed",
                        "sources": ["go2_front"],
                        "sample_count": 60,
                    }
                )
            )
            newest = manager.session_detail(session_id, limit=24)
            self.assertEqual(
                [sample["index"] for sample in newest["samples"]],
                list(range(37, 61)),
            )
            self.assertEqual(newest["page"]["next_before"], 37)
            older = manager.session_detail(
                session_id,
                before=newest["page"]["next_before"],
                limit=24,
            )
            self.assertEqual(
                [sample["index"] for sample in older["samples"]],
                list(range(13, 37)),
            )
            self.assertTrue(older["page"]["has_newer"])
            with self.assertRaises(DatasetCaptureValidationError):
                manager.session_detail(session_id, before=True)
            with self.assertRaises(DatasetCaptureValidationError):
                manager.session_detail(session_id, limit=49)

            metadata_path = samples / "00000060" / "metadata.json"
            metadata_path.write_text(
                json.dumps({"captured_at": "x" * 100_000, "pair_skew_us": 10**30})
            )
            bounded = manager.session_detail(session_id, limit=1)["samples"][0]
            self.assertEqual(len(bounded["captured_at"]), 64)
            self.assertEqual(bounded["pair_skew_us"], manager._pair_skew_us)


if __name__ == "__main__":
    unittest.main()
