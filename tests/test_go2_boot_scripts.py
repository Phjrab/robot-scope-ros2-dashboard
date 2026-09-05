import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WAITER = ROOT / "scripts" / "wait_for_go2_interface.sh"
SUPERVISOR = ROOT / "scripts" / "run_go2_dashboard_supervisor.py"
CONTROL_SUPERVISOR = ROOT / "scripts" / "run_go2_control_bridge_supervisor.sh"
FOXY_SETUP = ROOT / "scripts" / "setup_go2_ros2_foxy.sh"


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


class Go2InterfaceWaiterTests(unittest.TestCase):
    def run_check(self, *, address: str, lower_up: bool = True):
        with tempfile.TemporaryDirectory() as temporary:
            fake_bin = Path(temporary)
            write_executable(
                fake_bin / "ip",
                """#!/usr/bin/env bash
if [[ "$*" == "-o link show dev eno1" ]]; then
  if [[ "${FAKE_LOWER_UP:-1}" == "1" ]]; then
    echo '4: eno1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP'
  else
    echo '4: eno1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 state DOWN'
  fi
  exit 0
fi
if [[ "$*" == "-o -4 addr show dev eno1 scope global" ]]; then
  echo "4: eno1 inet ${FAKE_ADDRESS} brd 192.168.123.255 scope global eno1"
  exit 0
fi
exit 1
""",
            )
            environ = os.environ.copy()
            environ.update(
                {
                    "PATH": f"{fake_bin}:{environ['PATH']}",
                    "FAKE_ADDRESS": address,
                    "FAKE_LOWER_UP": "1" if lower_up else "0",
                }
            )
            return subprocess.run(
                [str(WAITER), "--check"],
                check=False,
                capture_output=True,
                text=True,
                env=environ,
                timeout=2,
            )

    def test_exact_interface_address_and_carrier_are_required(self):
        self.assertEqual(self.run_check(address="192.168.123.99/24").returncode, 0)
        self.assertEqual(self.run_check(address="192.168.123.98/24").returncode, 1)
        self.assertEqual(
            self.run_check(address="192.168.123.99/24", lower_up=False).returncode,
            1,
        )

    def test_invalid_interface_configuration_fails_closed(self):
        environ = os.environ.copy()
        environ["ROBOT_SCOPE_GO2_INTERFACE"] = "eno1;unsafe"
        result = subprocess.run(
            [str(WAITER), "--check"],
            check=False,
            capture_output=True,
            text=True,
            env=environ,
            timeout=2,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid Go2 interface label", result.stderr)


class Go2FoxySetupTests(unittest.TestCase):
    def test_conda_environment_is_rejected_before_ros_setup(self):
        result = subprocess.run(
            ["bash", str(FOXY_SETUP)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "CONDA_PREFIX": "/tmp/untrusted-conda"},
            timeout=2,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("deactivate Conda", result.stderr)


class Go2DashboardSupervisorTests(unittest.TestCase):
    def test_wireless_profiles_skip_the_direct_go2_interface_waiter(self):
        spec = importlib.util.spec_from_file_location(
            "robot_scope_dashboard_supervisor_wireless_test", SUPERVISOR
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for profile in (
            "go2-xt16-wireless",
            "go2-xt16-wireless-competition-fastlio",
        ):
            self.assertTrue(
                module._uses_wireless_gateway(
                    {"ROBOT_SCOPE_MAPPING_PROFILE": profile}
                )
            )
        self.assertFalse(
            module._uses_wireless_gateway(
                {"ROBOT_SCOPE_MAPPING_PROFILE": "go2-xt16-wired"}
            )
        )

    @staticmethod
    def make_scripts(temporary: str, *, waiter_delay: float = 0.05):
        script_dir = Path(temporary)
        supervisor = script_dir / SUPERVISOR.name
        shutil.copy2(SUPERVISOR, supervisor)
        supervisor.chmod(0o755)
        write_executable(
            script_dir / "wait_for_go2_interface.sh",
            f"""#!/usr/bin/env bash
if [[ "$1" == "--check" ]]; then
  exit 1
fi
echo "$$" > "$ROBOT_SCOPE_TEST_WAITER_PID"
sleep_pid=''
stop_waiter() {{
  if [[ -n "$sleep_pid" ]]; then
    kill -TERM "$sleep_pid" 2>/dev/null || true
    wait "$sleep_pid" 2>/dev/null || true
  fi
  exit 143
}}
trap stop_waiter TERM INT HUP
while [[ ! -e "$ROBOT_SCOPE_TEST_OFFLINE_READY" ]]; do
  sleep 0.01 &
  sleep_pid=$!
  echo "$sleep_pid" > "$ROBOT_SCOPE_TEST_SLEEP_PID"
  wait "$sleep_pid" 2>/dev/null || true
done
sleep {waiter_delay} &
sleep_pid=$!
echo "$sleep_pid" > "$ROBOT_SCOPE_TEST_SLEEP_PID"
wait "$sleep_pid" 2>/dev/null || true
touch "$ROBOT_SCOPE_TEST_READY"
if [[ "$2" == "--notify" ]]; then kill -USR1 "$3"; fi
exit 0
""",
        )
        write_executable(
            script_dir / "run_go2_humble.sh",
            """#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import sys
import time

log = Path(os.environ["ROBOT_SCOPE_TEST_LOG"])
ready = Path(os.environ["ROBOT_SCOPE_TEST_READY"])
with log.open("a", encoding="utf-8") as stream:
    stream.write("start\\n")
if ready.exists():
    with log.open("a", encoding="utf-8") as stream:
        stream.write("online\\n")
    raise SystemExit(0)

def stop(_signum, _frame):
    with log.open("a", encoding="utf-8") as stream:
        stream.write("term\\n")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGHUP, stop)
Path(os.environ["ROBOT_SCOPE_TEST_OFFLINE_READY"]).touch()
while True:
    time.sleep(0.05)
""",
        )
        return supervisor

    @staticmethod
    def make_test_environment(temporary: str, log: Path):
        environ = os.environ.copy()
        environ.update(
            {
                "ROBOT_SCOPE_TEST_LOG": str(log),
                "ROBOT_SCOPE_TEST_READY": str(Path(temporary) / "ready"),
                "ROBOT_SCOPE_TEST_OFFLINE_READY": str(
                    Path(temporary) / "offline-ready"
                ),
                "ROBOT_SCOPE_TEST_WAITER_PID": str(Path(temporary) / "waiter.pid"),
                "ROBOT_SCOPE_TEST_SLEEP_PID": str(Path(temporary) / "sleep.pid"),
            }
        )
        return environ

    def assert_process_gone(self, pid_file: Path):
        pid = int(pid_file.read_text(encoding="utf-8"))
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_offline_child_is_gracefully_replaced_when_interface_appears(self):
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = self.make_scripts(temporary)
            log = Path(temporary) / "events.log"
            environ = self.make_test_environment(temporary, log)
            result = subprocess.run(
                [str(supervisor)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environ,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["start", "term", "start", "online"],
            )
            self.assert_process_gone(Path(environ["ROBOT_SCOPE_TEST_WAITER_PID"]))
            self.assert_process_gone(Path(environ["ROBOT_SCOPE_TEST_SLEEP_PID"]))

    def test_service_stop_is_forwarded_to_offline_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = self.make_scripts(temporary, waiter_delay=30)
            log = Path(temporary) / "events.log"
            environ = self.make_test_environment(temporary, log)
            process = subprocess.Popen(
                [sys.executable, str(supervisor)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environ,
            )
            waiter_pid_file = Path(environ["ROBOT_SCOPE_TEST_WAITER_PID"])
            sleep_pid_file = Path(environ["ROBOT_SCOPE_TEST_SLEEP_PID"])
            deadline = time.monotonic() + 2
            while (
                not log.exists()
                or not waiter_pid_file.exists()
                or not sleep_pid_file.exists()
            ) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(log.exists(), "offline dashboard child did not start")
            self.assertTrue(waiter_pid_file.exists(), "interface waiter did not start")
            self.assertTrue(sleep_pid_file.exists(), "polling sleep did not start")
            process.terminate()
            stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["start", "term"],
            )
            self.assertIn("starting offline viewer", stdout)
            self.assert_process_gone(waiter_pid_file)
            self.assert_process_gone(sleep_pid_file)

    def test_service_stop_wins_over_an_online_transition_in_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = self.make_scripts(temporary, waiter_delay=0.05)
            log = Path(temporary) / "events.log"
            release = Path(temporary) / "release-child"
            child_stopping = Path(temporary) / "child-stopping"
            environ = self.make_test_environment(temporary, log)
            environ.update(
                {
                    "ROBOT_SCOPE_TEST_CHILD_RELEASE": str(release),
                    "ROBOT_SCOPE_TEST_CHILD_STOPPING": str(child_stopping),
                }
            )
            write_executable(
                Path(temporary) / "run_go2_humble.sh",
                """#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import time

log = Path(os.environ["ROBOT_SCOPE_TEST_LOG"])
ready = Path(os.environ["ROBOT_SCOPE_TEST_READY"])
with log.open("a", encoding="utf-8") as stream:
    stream.write("start\\n")
if ready.exists():
    with log.open("a", encoding="utf-8") as stream:
        stream.write("online\\n")
    raise SystemExit(0)

def stop(_signum, _frame):
    with log.open("a", encoding="utf-8") as stream:
        stream.write("term\\n")
    Path(os.environ["ROBOT_SCOPE_TEST_CHILD_STOPPING"]).touch()
    release = Path(os.environ["ROBOT_SCOPE_TEST_CHILD_RELEASE"])
    while not release.exists():
        time.sleep(0.01)
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGHUP, stop)
Path(os.environ["ROBOT_SCOPE_TEST_OFFLINE_READY"]).touch()
while True:
    time.sleep(0.05)
""",
            )
            process = subprocess.Popen(
                [sys.executable, str(supervisor)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environ,
            )
            deadline = time.monotonic() + 3
            while not child_stopping.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(
                child_stopping.exists(),
                "offline dashboard did not begin its online-transition shutdown",
            )

            process.terminate()
            release.touch()
            _stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["start", "term"],
            )

    def test_partial_child_start_failure_reaps_the_dashboard(self):
        spec = importlib.util.spec_from_file_location(
            "robot_scope_dashboard_supervisor_test", SUPERVISOR
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        dashboard = object()
        stopped = []
        with (
            mock.patch.object(module, "_executable", side_effect=["runner", "waiter"]),
            mock.patch.object(
                module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1),
            ),
            mock.patch.object(
                module.subprocess,
                "Popen",
                side_effect=[dashboard, OSError("waiter start failed")],
            ),
            mock.patch.object(module, "_stop_child", side_effect=stopped.append),
        ):
            with self.assertRaisesRegex(OSError, "waiter start failed"):
                module.main()

        self.assertEqual(stopped, [dashboard])

    def test_online_exec_restores_default_stop_signals_after_final_flag_check(self):
        source = SUPERVISOR.read_text(encoding="utf-8")
        restore_index = source.index("signal.signal(signum, signal.SIG_DFL)")
        final_check_index = source.index(
            "if stopping.is_set():", restore_index
        )
        exec_index = source.index("os.execv(runner, [runner])", final_check_index)
        self.assertLess(restore_index, final_check_index)
        self.assertLess(final_check_index, exec_index)


class Go2SystemdExampleTests(unittest.TestCase):
    def test_dashboard_uses_the_reinitializing_supervisor(self):
        unit = (ROOT / "deploy" / "robot-scope.service.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("ExecStart=/home/jetson_orin_nano/project/robot-scope/scripts/run_go2_dashboard_supervisor.py", unit)
        self.assertNotIn("robot-scope-control-bridge.service", unit)
        self.assertIn(
            "EnvironmentFile=-/home/jetson_orin_nano/project/robot-scope/runtime/config/robot-scope.env",
            unit,
        )
        self.assertNotIn("Environment=ROBOT_SCOPE_GO2_INTERFACE=", unit)
        self.assertIn("KillMode=mixed", unit)

    def test_bridge_waits_in_its_main_process_without_blocking_boot_target(self):
        unit = (
            ROOT / "deploy" / "robot-scope-control-bridge.service.example"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ExecStart=/home/jetson_orin_nano/project/robot-scope/scripts/run_go2_control_bridge_supervisor.sh",
            unit,
        )
        self.assertNotIn("ExecStartPre=", unit)
        self.assertNotIn("TimeoutStartSec=infinity", unit)
        self.assertIn("KillMode=control-group", unit)
        self.assertIn("StartLimitBurst=5", unit)
        self.assertIn(
            "EnvironmentFile=/home/jetson_orin_nano/project/robot-scope/runtime/config/robot-scope.env",
            unit,
        )
        self.assertNotIn("Environment=ROBOT_SCOPE_GO2_INTERFACE=", unit)

    def test_robot_side_bridge_is_foxy_udp_only_and_never_enabled_by_example(self):
        unit = (
            ROOT
            / "deploy"
            / "robot-scope-control-bridge-robot-side.service.example"
        ).read_text(encoding="utf-8")
        runner = (
            ROOT / "scripts" / "run_go2_control_bridge_foxy.sh"
        ).read_text(encoding="utf-8")
        setup = (
            ROOT / "scripts" / "setup_go2_ros2_foxy.sh"
        ).read_text(encoding="utf-8")
        environment = (
            ROOT
            / "deploy"
            / "robot-scope-control-bridge-robot-side.env.example"
        ).read_text(encoding="utf-8")

        self.assertIn("User=unitree", unit)
        self.assertIn("run_go2_control_bridge_foxy.sh", unit)
        self.assertNotIn("WantedBy=network-online.target", unit)
        self.assertNotIn("enable --now", unit)
        self.assertIn('ROBOT_SCOPE_CONTROL_TRANSPORT:-}', runner)
        self.assertIn('!= "udp"', runner)
        self.assertIn("setup_go2_ros2_foxy.sh", runner)
        self.assertIn("/opt/ros/foxy/setup.bash", setup)
        self.assertIn("192.168.123.18/24", setup)
        self.assertIn("NetworkInterface name=", setup)
        self.assertIn("ROBOT_SCOPE_CONTROL_BRIDGE_KEY=", environment)
        self.assertNotRegex(
            environment,
            r"ROBOT_SCOPE_CONTROL_BRIDGE_KEY=.+",
        )

    def test_c4c_motion_observer_is_manual_foxy_udp_and_has_no_boot_install(self):
        unit = (
            ROOT / "deploy" / "robot-scope-c4c-motion-observer.service.example"
        ).read_text(encoding="utf-8")
        runner = (
            ROOT / "scripts" / "run_go2_motion_observer_foxy.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("User=unitree", unit)
        self.assertIn("run_go2_motion_observer_foxy.sh", unit)
        self.assertNotIn("[Install]", unit)
        self.assertNotIn("WantedBy=", unit)
        self.assertNotIn("robot-scope-control-bridge.service", unit)
        self.assertIn('ROBOT_SCOPE_C4C_OBSERVATION_ONLY:-0}', runner)
        self.assertIn('ROBOT_SCOPE_CONTROL_TRANSPORT:-}', runner)
        self.assertIn('!= "udp"', runner)
        self.assertIn("setup_go2_ros2_foxy.sh", runner)
        self.assertIn("--observation-only", runner)
        self.assertNotIn("systemctl", runner)


class Go2ControlBridgeSupervisorTests(unittest.TestCase):
    def test_bridge_runner_starts_only_after_interface_waiter_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary:
            script_dir = Path(temporary)
            supervisor = script_dir / CONTROL_SUPERVISOR.name
            shutil.copy2(CONTROL_SUPERVISOR, supervisor)
            supervisor.chmod(0o755)
            log = script_dir / "events.log"
            write_executable(
                script_dir / "wait_for_go2_interface.sh",
                "#!/usr/bin/env bash\necho wait >> \"$ROBOT_SCOPE_TEST_LOG\"\nexit 0\n",
            )
            write_executable(
                script_dir / "run_go2_control_bridge_humble.sh",
                "#!/usr/bin/env bash\necho bridge >> \"$ROBOT_SCOPE_TEST_LOG\"\nexit 0\n",
            )
            environ = os.environ.copy()
            environ["ROBOT_SCOPE_TEST_LOG"] = str(log)
            result = subprocess.run(
                [str(supervisor)],
                check=False,
                capture_output=True,
                text=True,
                env=environ,
                timeout=2,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["wait", "bridge"],
            )


if __name__ == "__main__":
    unittest.main()
