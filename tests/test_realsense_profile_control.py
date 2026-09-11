import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_dashboard.realsense_profile import (
    RealSenseProfileBlocked,
    RealSenseProfileConfirmationRequired,
    RealSenseProfileManager,
    RealSenseProfileUnavailable,
    parse_profile_status,
)


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "robot_scope_wireless_mapping_ssh_command.py"
SPEC = importlib.util.spec_from_file_location("wireless_mapping_helper_profile", HELPER_PATH)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def status(profile="640x480", active="active"):
    width, height = {
        "320x240": (320, 240),
        "640x480": (640, 480),
        "1280x720": (1280, 720),
    }[profile]
    return {
        "schema": "robot-scope.realsense-profile.v1",
        "profile": profile,
        "width": width,
        "height": height,
        "fps": 15,
        "jpeg_quality": 72,
        "service": {"load": "loaded", "active": active, "sub": "running"},
    }


class FakeRunner:
    def __init__(self):
        self.profile = "640x480"
        self.actions = []

    def __call__(self, action, timeout):
        self.actions.append((action, timeout))
        if action.startswith("realsense-profile-") and action != "realsense-profile-status":
            self.profile = action.removeprefix("realsense-profile-")
        return subprocess.CompletedProcess(
            (action,), 0, json.dumps(status(self.profile)), ""
        )


class RealSenseProfileManagerTests(unittest.TestCase):
    def test_status_and_apply_use_only_fixed_profiles(self):
        runner = FakeRunner()
        manager = RealSenseProfileManager(
            enabled=True, runner=runner, dataset_active=lambda: False
        )
        snapshot = manager.snapshot()
        self.assertEqual(snapshot["selected"]["profile"], "640x480")
        self.assertEqual(
            [entry["id"] for entry in snapshot["profiles"]],
            ["320x240", "640x480", "1280x720"],
        )
        applied = manager.apply("1280x720", confirmed=True)
        self.assertEqual(applied["selected"]["profile"], "1280x720")
        self.assertEqual(
            [action for action, _timeout in runner.actions],
            [
                "realsense-profile-status",
                "realsense-profile-1280x720",
                "realsense-profile-status",
            ],
        )
        with self.assertRaises(RealSenseProfileUnavailable):
            manager.apply("1920x1080", confirmed=True)

    def test_confirmation_and_dataset_capture_fail_before_mutation(self):
        runner = FakeRunner()
        manager = RealSenseProfileManager(
            enabled=True, runner=runner, dataset_active=lambda: True
        )
        with self.assertRaises(RealSenseProfileConfirmationRequired):
            manager.apply("320x240", confirmed=False)
        with self.assertRaises(RealSenseProfileBlocked):
            manager.apply("320x240", confirmed=True)
        self.assertEqual(runner.actions, [])

    def test_malformed_or_incomplete_remote_status_fails_closed(self):
        malformed = dict(status())
        malformed["unexpected"] = True
        with self.assertRaises(ValueError):
            parse_profile_status(malformed)
        malformed = dict(status())
        malformed["width"] = 641
        with self.assertRaises(ValueError):
            parse_profile_status(malformed)
        malformed = dict(status())
        malformed["fps"] = True
        with self.assertRaises(ValueError):
            parse_profile_status(malformed)


class RobotSideRealSenseProfileTests(unittest.TestCase):
    def test_install_document_targets_the_forced_authorized_key_helper(self) -> None:
        install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn(
            "/usr/local/libexec/robot-scope/wireless-mapping-lifecycle-ssh",
            install,
        )

    def fixture(self, root: Path) -> Path:
        path = root / "realsense-camera.env"
        path.write_text(
            "# fixed relay\n"
            "ROBOT_SCOPE_REALSENSE_BIND_HOST=192.168.123.18\n"
            "ROBOT_SCOPE_REALSENSE_WIDTH=640\n"
            "ROBOT_SCOPE_REALSENSE_HEIGHT=480\n"
            "ROBOT_SCOPE_REALSENSE_FPS=15\n"
            "ROBOT_SCOPE_REALSENSE_JPEG_QUALITY=72\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def test_atomic_profile_change_preserves_other_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.fixture(Path(temporary))
            with mock.patch.object(helper, "REALSENSE_ENV_FILE", path), mock.patch.object(
                helper, "_cycle_realsense_service", return_value=True
            ), mock.patch.object(
                helper,
                "_realsense_systemd",
                return_value={"load": "loaded", "active": "active", "sub": "running"},
            ):
                result = helper._apply_realsense_profile("1280x720")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(result["profile"], "1280x720")
            self.assertIn("ROBOT_SCOPE_REALSENSE_WIDTH=1280", text)
            self.assertIn("ROBOT_SCOPE_REALSENSE_HEIGHT=720", text)
            self.assertIn("ROBOT_SCOPE_REALSENSE_BIND_HOST=192.168.123.18", text)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_failed_service_transition_restores_original_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.fixture(Path(temporary))
            original = path.read_bytes()
            with mock.patch.object(helper, "REALSENSE_ENV_FILE", path), mock.patch.object(
                helper, "_cycle_realsense_service", side_effect=[False, True]
            ):
                with self.assertRaises(RuntimeError):
                    helper._apply_realsense_profile("320x240")
            self.assertEqual(path.read_bytes(), original)

    def test_environment_must_be_private_regular_and_profile_is_allowlisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.fixture(Path(temporary))
            path.chmod(0o644)
            with mock.patch.object(helper, "REALSENSE_ENV_FILE", path):
                with self.assertRaises(ValueError):
                    helper._read_realsense_environment()
            path.chmod(0o600)
            with mock.patch.object(helper, "REALSENSE_ENV_FILE", path):
                with self.assertRaises(ValueError):
                    helper._apply_realsense_profile("1920x1080")

    def test_forced_command_exposes_no_arbitrary_profile_or_restart(self):
        source = HELPER_PATH.read_text(encoding="utf-8")
        self.assertIn('"320x240": (320, 240)', source)
        self.assertIn('"640x480": (640, 480)', source)
        self.assertIn('"1280x720": (1280, 720)', source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn('"restart"', source)


if __name__ == "__main__":
    unittest.main()
