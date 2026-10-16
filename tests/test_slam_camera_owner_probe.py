import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import struct
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("camera_owner_probe", Path(__file__).resolve().parents[1] / "scripts/slam/camera_owner_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class CameraOwnerProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name)
        self.fd = self.proc / "123" / "fd"
        self.fd.mkdir(parents=True)

    def test_observes_open_char_device_without_opening_it(self):
        (self.fd / "4").symlink_to("/dev/null")
        self.assertEqual(probe.observe(["/dev/null"], self.proc), "occupied")

    def test_free_requires_complete_fd_scan(self):
        (self.fd / "4").symlink_to("/dev/zero")
        self.assertEqual(probe.observe(["/dev/null"], self.proc), "free")
        with patch.object(probe.os, "scandir", side_effect=PermissionError("hidden process")):
            self.assertEqual(probe.observe(["/dev/null"], self.proc), "unavailable")

    def test_known_owner_does_not_hide_partial_process_visibility(self):
        (self.fd / "4").symlink_to("/dev/null")
        other = self.proc / "456"
        other.mkdir()
        self.assertEqual(probe.observe(["/dev/null"], self.proc), "unavailable")

    def test_disappearing_fds_do_not_block_other_live_owners(self):
        (self.fd / "4").symlink_to(self.proc / "exited")
        (self.fd / "5").symlink_to("/dev/null")
        self.assertEqual(probe.observe(["/dev/null"], self.proc), "occupied")

    def test_missing_devices_and_empty_process_view_are_unavailable(self):
        self.assertEqual(probe.observe([str(self.proc / "missing")], self.proc), "unavailable")
        self.assertEqual(probe.observe([], self.proc), "unavailable")
        self.fd.rmdir()
        self.fd.parent.rmdir()
        self.assertEqual(probe.observe(["/dev/null"], self.proc), "unavailable")

    def test_exhausted_observation_budget_is_unavailable(self):
        self.assertEqual(probe.observe(["/dev/null"], self.proc, budget=0), "unavailable")

    def test_invalid_and_unbounded_budgets_are_unavailable(self):
        for budget in (True, "3", float("nan"), float("inf"), -1, 3.01):
            with self.subTest(budget=budget):
                self.assertEqual(probe.observe(["/dev/null"], self.proc, budget=budget), "unavailable")

    def test_alarm_interrupts_blocked_scan_and_restores_signal_state(self):
        previous = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        with patch.object(probe, "_observe", side_effect=lambda *_: time.sleep(0.3)):
            self.assertEqual(probe.observe(["/dev/null"], self.proc, budget=0.03), "unavailable")
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)

    def test_existing_alarm_is_preserved_and_observation_unavailable(self):
        with patch.object(probe.signal, "getitimer", return_value=(5, 0)), \
                patch.object(probe.signal, "setitimer") as timer, \
                patch.object(probe, "_observe") as scan:
            self.assertEqual(probe.observe(["/dev/null"], self.proc), "unavailable")
        timer.assert_not_called()
        scan.assert_not_called()


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = {"schema_version": 1, "uid": 1000, "devices": ["/dev/video2", "/dev/bus/usb/001/004"],
                       "socket": "/run/robot-scope-camera-owner/owner.sock"}

    def load(self, config):
        content = json.dumps(config).encode()
        with patch.object(probe, "_protected_bytes", return_value=content):
            return probe.load_configuration(Path("/etc/robot-scope/camera-owner.json"))

    def test_exact_configuration_is_accepted(self):
        self.assertEqual(self.load(self.config), self.config)

    def test_configuration_schema_and_fixed_resources(self):
        invalid = [[], dict(self.config, schema_version=True), dict(self.config, uid=True),
                   dict(self.config, uid=0), dict(self.config, uid=2**31),
                   dict(self.config, devices=[]), dict(self.config, devices=["/dev/video2"] * 2),
                   dict(self.config, devices=["/dev/video2"] * 17),
                   dict(self.config, devices=["/etc/shadow"]),
                   dict(self.config, devices=["/dev/../dev/video2"]),
                   dict(self.config, devices=[False]), dict(self.config, socket=False),
                   dict(self.config, socket="/tmp/owner.sock"), dict(self.config, command="kill")]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.load(config)

    def test_duplicate_fields_and_nonfinite_values_are_rejected(self):
        for content in (b'{"uid":1000,"uid":1001}', b'{"uid":NaN}'):
            with self.subTest(content=content), patch.object(probe, "_protected_bytes", return_value=content), \
                    self.assertRaises(ValueError):
                probe.load_configuration(Path("/etc/robot-scope/probe.json"))

    def test_relative_and_parent_traversal_configuration_paths_are_rejected(self):
        for path in (Path("probe.json"), Path("/etc/../tmp/probe.json")):
            with self.subTest(path=path), patch.object(probe, "_protected_bytes") as reader, \
                    self.assertRaises(ValueError):
                probe.load_configuration(path)
            reader.assert_not_called()

    def test_root_directory_walk_uses_nofollow_and_rejects_writable_ancestor(self):
        safe = SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)
        unsafe = SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o755)
        with patch.object(probe.os, "open", side_effect=[10, 11]) as opener, \
                patch.object(probe.os, "fstat", side_effect=[safe, unsafe]), \
                patch.object(probe.os, "close") as closer, self.assertRaises(ValueError):
            probe._root_directory(Path("/owned"))
        self.assertTrue(all(call.args[1] & os.O_NOFOLLOW for call in opener.call_args_list))
        self.assertEqual({call.args[0] for call in closer.call_args_list}, {10, 11})
        for mode, uid in ((stat.S_IFDIR | 0o775, 0), (stat.S_IFDIR | 0o755, 1000), (stat.S_IFLNK | 0o777, 0)):
            with self.subTest(mode=mode, uid=uid), self.assertRaises(ValueError):
                probe._root_owned(SimpleNamespace(st_mode=mode, st_uid=uid), directory=True)

    def test_protected_file_is_opened_nofollow_and_read_is_bounded(self):
        source = io.BytesIO(b"abcdef")
        source.fileno = lambda: 11
        info = SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o600, st_size=1)
        with patch.object(probe, "_root_directory", return_value=10), \
                patch.object(probe.os, "open", return_value=11) as opener, \
                patch.object(probe.os, "fdopen", return_value=source), \
                patch.object(probe.os, "fstat", return_value=info), \
                patch.object(probe.os, "close") as closer, self.assertRaises(ValueError):
            probe._protected_bytes(Path("/etc/probe.json"), 3)
        self.assertTrue(opener.call_args.args[1] & os.O_NOFOLLOW)
        self.assertTrue(opener.call_args.args[1] & os.O_NONBLOCK)
        self.assertEqual(opener.call_args.kwargs["dir_fd"], 10)
        closer.assert_called_once_with(10)


class RequestTests(unittest.TestCase):
    def invoke(self, raw, uid=1000, state="free"):
        handler = probe.Handler.__new__(probe.Handler)
        handler.connection = Mock()
        handler.connection.getsockopt.return_value = struct.pack("3i", 123, uid, 1000)
        handler.rfile = raw if hasattr(raw, "readline") else io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.server = SimpleNamespace(config={"uid": 1000, "devices": ["/dev/video2"]})
        with patch.object(probe.socket, "SO_PEERCRED", 17, create=True), \
                patch.object(probe, "_observe", return_value=state) as observe, \
                patch.object(probe.os, "readlink", return_value="pid:[42]"):
            handler.handle()
        return handler.wfile.getvalue(), observe

    def test_exact_request_uses_only_configured_devices(self):
        for state in ("free", "occupied", "unavailable"):
            with self.subTest(state=state):
                result, observe = self.invoke(b'{"operation":"camera_owner_state"}\n', state=state)
                response = json.loads(result)
                self.assertEqual(response["state"], state)
                self.assertEqual(response["devices"], ["/dev/video2"])
                self.assertEqual(response["host_pid_namespace"], "pid:[42]")
                self.assertEqual(response["schema_version"], 1)
                self.assertEqual(observe.call_args.args[:2], (["/dev/video2"], Path("/proc")))
                self.assertGreater(observe.call_args.args[2], time.monotonic())
                observe.assert_called_once()

    def test_foreign_uid_is_rejected_before_observing(self):
        result, observe = self.invoke(b'{"operation":"camera_owner_state"}\n', uid=0)
        self.assertEqual(result, b"")
        observe.assert_not_called()

    def test_request_deadline_includes_a_slow_client_read(self):
        class SlowReader:
            def readline(self, _limit):
                time.sleep(0.3)
                return b'{"operation":"camera_owner_state"}\n'
        original = probe._alarm
        started = time.monotonic()
        with patch.object(probe, "_alarm", side_effect=lambda _: original(0.03)):
            result, observe = self.invoke(SlowReader())
        self.assertEqual(result, b"")
        observe.assert_not_called()
        self.assertLess(time.monotonic() - started, 0.25)

    def test_arbitrary_schema_oversize_duplicates_and_incomplete_requests_are_rejected(self):
        for raw in (b'{"operation":"kill"}\n', b'{"operation":"camera_owner_state","devices":["/dev/video0"]}\n',
                    b'{"operation":"kill","operation":"camera_owner_state"}\n',
                    b'{"operation":"camera_owner_state"}', b'[]\n', b'null\n',
                    b'x' * 257 + b'\n', b'{"operation":NaN}\n'):
            with self.subTest(raw=raw):
                result, observe = self.invoke(raw)
                self.assertEqual(result, b"")
                observe.assert_not_called()


class VisibilityTests(unittest.TestCase):
    def visible(self, mountinfo):
        with patch.object(probe.os, "geteuid", return_value=0), \
                patch.object(probe.os, "readlink", return_value="pid:[42]"), \
                patch.object(probe.Path, "open", return_value=io.BytesIO(mountinfo)):
            return probe._proc_visible(Path("/proc"))

    def test_full_proc_mount_is_required(self):
        self.assertTrue(self.visible(b"1 0 0:1 / /proc rw,nosuid - proc proc rw\n"))
        for mount in (b"1 0 0:1 / /proc rw - proc proc rw,hidepid=2\n",
                      b"1 0 0:1 /123 /proc rw - proc proc rw\n",
                      b"1 0 0:1 / /proc rw - tmpfs tmpfs rw\n", b""):
            with self.subTest(mount=mount):
                self.assertFalse(self.visible(mount))
        masked = b"1 0 0:1 / /proc rw - proc proc rw\n2 1 0:2 / /proc/123/fd rw - tmpfs tmpfs rw\n"
        self.assertFalse(self.visible(masked))


class SocketCleanupTests(unittest.TestCase):
    def close(self, info, identity=(1, 2)):
        server = probe.Server.__new__(probe.Server)
        server.config = {"socket": "/run/robot-scope-camera-owner/owner.sock"}
        server._identity = identity
        with patch.object(probe.socketserver.UnixStreamServer, "server_close"), \
                patch.object(probe.Path, "lstat", return_value=info), \
                patch.object(probe.Path, "unlink") as unlink:
            server.server_close()
        return unlink

    def test_only_own_socket_inode_is_unlinked(self):
        own = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFSOCK | 0o600)
        self.close(own).assert_called_once_with()
        self.close(own, identity=None).assert_not_called()
        self.close(SimpleNamespace(st_dev=1, st_ino=3, st_mode=stat.S_IFSOCK | 0o600)).assert_not_called()
        self.close(SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFLNK | 0o777)).assert_not_called()

    def test_socket_setup_failure_closes_and_removes_only_created_socket(self):
        own = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFSOCK | 0o600)
        with patch.object(probe, "_root_directory", return_value=10), \
                patch.object(probe.os, "close"), \
                patch.object(probe.os, "stat", side_effect=FileNotFoundError), \
                patch.object(probe.socketserver.UnixStreamServer, "__init__", return_value=None), \
                patch.object(probe.socketserver.UnixStreamServer, "server_close") as close, \
                patch.object(probe.Server, "server_bind"), \
                patch.object(probe.Path, "lstat", return_value=own), \
                patch.object(probe.Path, "unlink") as unlink, \
                patch.object(probe.os, "chmod", side_effect=PermissionError), self.assertRaises(PermissionError):
            probe.Server({"socket": "/run/robot-scope-camera-owner/owner.sock", "uid": 1000})
        close.assert_called_once()
        unlink.assert_called_once()

    def test_existing_endpoint_is_preserved_without_binding(self):
        with patch.object(probe, "_root_directory", return_value=10), \
                patch.object(probe.os, "close"), patch.object(probe.os, "stat", return_value=object()), \
                patch.object(probe.socketserver.UnixStreamServer, "__init__") as initialize, \
                patch.object(probe.Path, "unlink") as unlink, self.assertRaises(ValueError):
            probe.Server({"socket": "/run/robot-scope-camera-owner/owner.sock", "uid": 1000})
        initialize.assert_not_called()
        unlink.assert_not_called()


if __name__ == "__main__":
    unittest.main()
