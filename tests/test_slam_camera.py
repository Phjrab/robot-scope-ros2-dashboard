"""SYNTHETIC ownership fixtures; no camera or robot is accessed."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from robot_dashboard.slam_camera import (
    CameraBusy, CameraOwnerCoordinator, acquire_producer_lock,
    devices_free, release_producer_lock,
)


class CameraOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = self.root / "producer.lock"
        self.handoff = self.root / "handoff.json"
        self.session = {"session_id": "synthetic-session", "generation": 4}
        self.write_handoff()

    def write_handoff(self, **values):
        record = dict(checked_at_epoch=1000, relay_released=True,
                      lock_protocol="robot-scope-camera-v1", devices=["/dev/video99"])
        record.update(values)
        self.handoff.write_text(json.dumps(record))
        self.handoff.chmod(0o600)

    def coordinator(self, probe=lambda _: True, handoff=True):
        return CameraOwnerCoordinator(self.lock, self.handoff if handoff else None,
                                      owner_probe=probe, wall_clock=lambda: 1100)

    def test_free_cooperative_lock_is_insufficient_without_handoff(self):
        fd = acquire_producer_lock(self.lock)
        release_producer_lock(fd)
        manager = self.coordinator(handoff=False)
        with self.assertRaisesRegex(CameraBusy, "CAMERA_HANDOFF_REQUIRED"):
            manager.acquire(self.session)
        self.assertFalse(manager.snapshot()["reserved"])

    def test_one_producer_multiple_consumers_and_exact_owner_release(self):
        manager = self.coordinator()
        manager.acquire(self.session)
        self.assertEqual(manager.snapshot(), dict(reserved=True,
            session_id="synthetic-session", generation=4, rgb_available=False))
        with self.assertRaisesRegex(CameraBusy, "CAMERA_BUSY"):
            acquire_producer_lock(self.lock)
        for foreign in ({**self.session, "generation": 3}, {**self.session, "session_id": "foreign"}):
            with self.subTest(foreign=foreign):
                with self.assertRaisesRegex(CameraBusy, "CAMERA_OWNER_MISMATCH"):
                    manager.release(foreign)
                self.assertTrue(manager.snapshot()["reserved"])
        manager.release(self.session)
        self.assertTrue(manager.snapshot()["rgb_available"])
        relay = acquire_producer_lock(self.lock)
        release_producer_lock(relay)

    def test_two_coordinators_cannot_reserve_same_device_lock(self):
        first, second = self.coordinator(), self.coordinator()
        first.acquire(self.session)
        try:
            with self.assertRaisesRegex(CameraBusy, "CAMERA_BUSY"):
                second.acquire({"session_id": "second", "generation": 1})
            self.assertFalse(second.snapshot()["reserved"])
        finally:
            first.release(self.session)

    def test_uncertain_acquire_reconciliation_releases_only_matching_owner(self):
        manager = self.coordinator()
        manager.release_if_owned(self.session)
        self.assertFalse(manager.snapshot()["reserved"])
        manager.acquire(self.session)
        manager.release_if_owned({**self.session, "generation": 3})
        manager.release_if_owned({**self.session, "session_id": "synthetic-foreign"})
        self.assertTrue(manager.snapshot()["reserved"])
        with self.assertRaises(CameraBusy):
            acquire_producer_lock(self.lock)
        manager.release_if_owned(self.session)
        self.assertFalse(manager.snapshot()["reserved"])
        fd = acquire_producer_lock(self.lock)
        release_producer_lock(fd)

    def test_rgb_relay_cooperative_lock_blocks_vslam_until_release(self):
        relay = acquire_producer_lock(self.lock)
        manager = self.coordinator()
        try:
            with self.assertRaisesRegex(CameraBusy, "CAMERA_BUSY"):
                manager.acquire(self.session)
        finally:
            release_producer_lock(relay)
        manager.acquire(self.session)
        manager.release(self.session)

    def test_expired_future_and_incomplete_handoff_are_rejected(self):
        for change in (dict(checked_at_epoch=799), dict(checked_at_epoch=1101),
                       dict(relay_released=False), dict(relay_released=1),
                       dict(lock_protocol="old"), dict(devices=[]),
                       dict(devices=["device"] * 17), dict(devices=[None])):
            with self.subTest(change=change):
                self.write_handoff(**change)
                with self.assertRaisesRegex(CameraBusy, "CAMERA_HANDOFF_REQUIRED"):
                    self.coordinator().acquire(self.session)

    def test_unsafe_handoff_permissions_symlink_and_size_fail_closed(self):
        self.handoff.chmod(0o644)
        with self.assertRaises(CameraBusy):
            self.coordinator().acquire(self.session)
        self.handoff.unlink()
        target = self.root / "target.json"
        target.write_text("{}")
        target.chmod(0o600)
        self.handoff.symlink_to(target)
        with self.assertRaises(CameraBusy):
            self.coordinator().acquire(self.session)
        self.handoff.unlink()
        self.handoff.write_bytes(b" " * 16385)
        self.handoff.chmod(0o600)
        with self.assertRaises(CameraBusy):
            self.coordinator().acquire(self.session)

    def test_probe_checks_after_reservation_and_releases_on_failure(self):
        calls = []
        def occupied(devices):
            calls.append(devices)
            with self.assertRaises(CameraBusy):
                acquire_producer_lock(self.lock)
            return False
        manager = self.coordinator(occupied)
        with self.assertRaisesRegex(CameraBusy, "CAMERA_BUSY"):
            manager.acquire(self.session)
        self.assertEqual(calls, [["/dev/video99"]])
        self.assertFalse(manager.snapshot()["reserved"])
        fd = acquire_producer_lock(self.lock)
        release_producer_lock(fd)

    def test_probe_exception_also_releases_cooperative_reservation(self):
        def failed(_):
            raise RuntimeError("synthetic probe failure")
        manager = self.coordinator(failed)
        with self.assertRaises(RuntimeError):
            manager.acquire(self.session)
        self.assertFalse(manager.snapshot()["reserved"])
        fd = acquire_producer_lock(self.lock)
        release_producer_lock(fd)

    def test_symlink_lock_never_opens_or_modifies_target(self):
        target = self.root / "untouched"
        target.write_bytes(b"user-data")
        self.lock.symlink_to(target)
        with self.assertRaises((CameraBusy, OSError)):
            acquire_producer_lock(self.lock)
        self.assertEqual(target.read_bytes(), b"user-data")

    def test_device_probe_fails_closed_on_unsupported_or_invalid_paths(self):
        self.assertFalse(devices_free([]))
        self.assertFalse(devices_free(["/tmp/untrusted"]))
        with patch("robot_dashboard.slam_camera.Path.is_dir", return_value=False):
            self.assertFalse(devices_free(["/dev/video99"]))

    def test_handoff_wrong_owner_fails_closed(self):
        actual = os.geteuid()
        with patch("robot_dashboard.slam_camera.os.geteuid", return_value=actual+1):
            with self.assertRaisesRegex(CameraBusy, "CAMERA_HANDOFF_REQUIRED"):
                self.coordinator().acquire(self.session)


if __name__ == "__main__":
    unittest.main()
