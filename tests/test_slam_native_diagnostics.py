"""Hardware-free, bounded native-localization diagnostic contracts."""
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from robot_dashboard.slam_native_diagnostics import (
    MAX_LOG_EVENTS, NativeLogDiagnostics, digest, opaque_native_identity, persist_attempt,
)


def line(message, stamp="100.000000001", logger="vslam_lab.visual_slam_node"):
    return ("[component-2] [ERROR] [" + stamp + "] [" + logger + "]: " + message + "\n").encode()


class NativeDiagnosticsTests(unittest.TestCase):
    def test_fragmented_private_log_is_allowlisted_and_never_attributed(self):
        log = NativeLogDiagnostics()
        raw = line("Trying to localize in map '/private/secret/native' around [1, 2, 3]")
        for chunk in (raw[:19], raw[19:], line("Failed to localize in map. Error 3")):
            log.feed(chunk)
        value = log.window(0, 100_000_000_000, 100_000_000_002)
        self.assertEqual(value["correlation"], "unknown")
        self.assertIsNone(value["attributed_sdk_status"])
        self.assertEqual(value["candidate_events"][-1]["sdk_name_candidate"], "CUVSLAM_CAN_NOT_LOCALIZE")
        self.assertNotIn("secret", json.dumps(value))
        self.assertNotIn("around", json.dumps(value))

    def test_stale_buffered_event_and_wrong_logger_do_not_match_request_window(self):
        log = NativeLogDiagnostics()
        log.feed(line("Failed to localize in map. Error 3", stamp="99.999999999"))
        log.feed(line("Failed to localize in map. Error 3", logger="foreign.node"))
        self.assertEqual(log.window(0, 100_000_000_000, 100_000_000_002)["candidate_events"], [])
        self.assertEqual(log.window(0, None, 100_000_000_002)["reason"], "SOURCE_CLOCK_FENCE_UNAVAILABLE")

    def test_log_fence_excludes_previous_event_even_at_equal_timestamp(self):
        log = NativeLogDiagnostics()
        log.feed(line("Failed to localize in map. Error 3"))
        fence = log.sequence
        self.assertEqual(log.window(fence, 100_000_000_000, 100_000_000_002)["candidate_events"], [])

    def test_unknown_sdk_code_has_no_invented_name(self):
        log = NativeLogDiagnostics()
        log.feed(line("Failed to localize in map. Error 999"))
        event = log.window(0, 0, 101_000_000_000)["candidate_events"][0]
        self.assertIsNone(event["sdk_status_candidate"])
        self.assertIsNone(event["sdk_name_candidate"])

    def test_event_and_line_memory_bounds_preserve_next_valid_line(self):
        log = NativeLogDiagnostics()
        log.feed(b"x" * 5000)
        log.feed(b"private-fragment\n")
        for _ in range(MAX_LOG_EVENTS + 4):
            log.feed(line("Failed to localize in map. Error 3"))
        value = log.window(0, 0, 101_000_000_000)
        self.assertEqual(len(log._events), MAX_LOG_EVENTS)
        self.assertEqual(len(value["candidate_events"]), 16)
        self.assertTrue(value["candidate_events_truncated"])
        self.assertEqual(value["oversized_lines_dropped"], 1)
        value["candidate_events"][0]["event"] = "mutated"
        self.assertEqual(log.window(0, 0, 101_000_000_000)["candidate_events"][0]["event"], "CALLBACK_FAILED")

    def test_hash_is_opaque_bounded_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.mdb"
            path.write_bytes(b"opaque")
            value = opaque_native_identity(path)
            self.assertEqual(value["status"], "OPAQUE_BYTES_HASHED")
            self.assertEqual(value["size_bytes"], 6)
            self.assertEqual(len(value["sha256"]), 64)
            with patch("robot_dashboard.slam_native_diagnostics.MAX_NATIVE_HASH_BYTES", 4):
                self.assertEqual(opaque_native_identity(path)["status"], "HASH_BOUND_EXCEEDED")
            link = Path(directory) / "link"
            link.symlink_to(path)
            self.assertEqual(opaque_native_identity(link)["status"], "HASH_UNAVAILABLE")

    def test_private_attempt_is_bounded_exclusive_and_mode_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(persist_attempt(root, 1, "request", {"code": "REQUESTED"}))
            path = root / "native-localization-1-request.json"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(persist_attempt(root, 1, "request", {"code": "REPLACED"}))
            self.assertEqual(json.loads(path.read_text())["code"], "REQUESTED")
            for attempt, phase in ((65, "request"), (1, "../../escape")):
                self.assertFalse(persist_attempt(root, attempt, phase, {}))
            self.assertFalse(persist_attempt(root, 2, "result", {"large": "x" * 40000}))

    def test_fifo_without_writer_is_refused_without_blocking_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.mdb"
            os.mkfifo(path, 0o600)
            observed = []
            worker = threading.Thread(target=lambda: observed.append(opaque_native_identity(path)), daemon=True)
            worker.start()
            worker.join(timeout=0.5)
            self.assertFalse(worker.is_alive(), "native diagnostic blocked opening a FIFO without a writer")
            self.assertEqual(observed[0]["status"], "NOT_REGULAR")

    def test_request_digest_changes_with_hint_and_epoch(self):
        first = {"epoch": "one", "hint": [0, 0, 0, 1]}
        self.assertNotEqual(digest(first), digest(dict(first, epoch="two")))
        self.assertNotEqual(digest(first), digest(dict(first, hint=[1, 0, 0, 0])))


if __name__ == "__main__":
    unittest.main()
