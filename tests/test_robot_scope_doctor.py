import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTOR_PATH = ROOT / "scripts" / "robot_scope_doctor.py"
SPEC = importlib.util.spec_from_file_location("robot_scope_doctor", DOCTOR_PATH)
assert SPEC and SPEC.loader
doctor_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = doctor_module
SPEC.loader.exec_module(doctor_module)


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class FakeRunner:
    def __init__(self, *, interface="eno9", cidr="192.168.123.99/24"):
        self.interface = interface
        self.cidr = cidr
        self.commands = []

    def __call__(self, command, **_kwargs):
        self.commands.append(tuple(command))
        if "-c" in command:
            return completed(command)
        if "link" in command:
            return completed(
                command,
                stdout=(
                    f"2: {self.interface}: <BROADCAST,MULTICAST,UP,LOWER_UP> "
                    "mtu 1500 state UP\n"
                ),
            )
        if "addr" in command:
            return completed(
                command,
                stdout=(
                    f"2: {self.interface} inet {self.cidr} "
                    f"scope global {self.interface}\n"
                ),
            )
        if command and str(command[0]).endswith("gst-inspect-1.0"):
            return completed(command)
        return completed(command, returncode=1, stderr="unexpected probe")


class DoctorFixture:
    def __init__(self, base: Path):
        self.base = base
        self.project = base / "project"
        self.home = base / "home"
        self.ros_prefix = base / "opt" / "ros" / "humble"
        self.os_release = base / "os-release"
        (self.project / "config").mkdir(parents=True)
        self.home.mkdir()
        self.ros_prefix.mkdir(parents=True)
        (self.project / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (self.project / "config" / "go2.json").write_text(
            '{"direct_camera":{"allowed_interfaces":["eno9"]}}',
            encoding="utf-8",
        )
        (self.ros_prefix / "setup.bash").write_text("", encoding="utf-8")
        self.os_release.write_text(
            'ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04 LTS"\n',
            encoding="utf-8",
        )

    def use_jazzy(self):
        self.ros_prefix = self.base / "opt" / "ros" / "jazzy"
        self.ros_prefix.mkdir(parents=True)
        (self.ros_prefix / "setup.bash").write_text("", encoding="utf-8")
        self.os_release.write_text(
            'ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04 LTS"\n',
            encoding="utf-8",
        )

    def make_doctor(
        self,
        mode,
        *,
        env_file=None,
        runner=None,
        which=None,
        environment_updates=None,
        allow_hardware_offline=False,
        realsense_relay_env_file=None,
    ):
        environment = {
            "HOME": str(self.home),
            "ROBOT_SCOPE_GO2_INTERFACE": "eno9",
            "ROBOT_SCOPE_GO2_INTERFACE_CIDR": "192.168.123.99/24",
            "ROBOT_SCOPE_CAMERA_INTERFACE": "eno9",
        }
        environment.update(environment_updates or {})
        return doctor_module.Doctor(
            mode=mode,
            project_dir=self.project,
            env_file=env_file,
            realsense_relay_env_file=realsense_relay_env_file,
            os_release_file=self.os_release,
            architecture="x86_64",
            environment=environment,
            allow_hardware_offline=allow_hardware_offline,
            command_runner=runner or FakeRunner(),
            which=which or (lambda name: f"/usr/bin/{name}" if name == "ip" else None),
            ros_prefix=self.ros_prefix,
        )


class RobotScopeDoctorTests(unittest.TestCase):
    def test_realsense_local_access_requires_exact_same_private_address(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            relay_env = Path(temporary) / "realsense-camera.env"
            self._write_realsense_env(relay_env, ROBOT_SCOPE_REALSENSE_ACCESS_MODE="local",
                                      ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST="192.168.50.30")
            runner = FakeRunner(interface="wlan0", cidr="192.168.50.30/24")
            doctor = fixture.make_doctor("observer", runner=runner, realsense_relay_env_file=relay_env)
            checks = {check.id: check for check in doctor.run()}
            self.assertEqual(checks["realsense.config"].status, "pass")
            self._write_realsense_env(relay_env, ROBOT_SCOPE_REALSENSE_ACCESS_MODE="local")
            rejected = fixture.make_doctor("observer", realsense_relay_env_file=relay_env)
            self.assertEqual({check.id: check for check in rejected.run()}["realsense.config"].status, "fail")
            self._write_realsense_env(relay_env, ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST="192.168.50.30")
            remote = fixture.make_doctor("observer", realsense_relay_env_file=relay_env)
            self.assertEqual({check.id: check for check in remote.run()}["realsense.config"].status, "fail")

    def test_onboard_doctor_selects_direct_configs_and_no_relay_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            (fixture.project / "config/go2-onboard.json").write_text('{"robot_type":"go2"}', encoding="utf-8")
            (fixture.project / "config/hesai_xt16_onboard.yaml").write_text("{}", encoding="utf-8")
            runner = FakeRunner()
            doctor = fixture.make_doctor("go2-nav", runner=runner,
                                         which=lambda name: f"/usr/bin/{name}",
                                         environment_updates={"ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard"})
            checks = {check.id: check for check in doctor.run()}
            self.assertEqual(checks["onboard.robot_profile"].status, "pass")
            self.assertEqual(checks["onboard.hesai_config"].status, "pass")
            self.assertEqual(checks["onboard.transport"].status, "pass")
            self.assertFalse(any(command[0].endswith("ping") for command in runner.commands))
            rejected = fixture.make_doctor("go2", environment_updates={
                "ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard", "ROBOT_SCOPE_CONTROL_TRANSPORT": "udp"})
            self.assertEqual({check.id: check for check in rejected.run()}["onboard.transport"].status, "fail")

    def test_onboard_native_probe_sources_selected_overlay_and_checks_real_abi_operation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            profile = fixture.project / "config/go2-onboard.json"
            profile.write_text('{"robot_type":"go2"}', encoding="utf-8")
            overlay = Path(temporary) / "selected-overlay/setup.bash"
            overlay.parent.mkdir()
            overlay.write_text("", encoding="utf-8")
            commands = []

            def runner(command, **kwargs):
                commands.append((command, kwargs))
                if "robot-scope-onboard-doctor" in command:
                    payload = {"numpy_abi_family": "1.x", "modules": {name: {"path": "/verified/" + name, "version": "observed"}
                               for name in ("numpy", "cv2", "rclpy", "unitree_go.msg", "unitree_api.msg")}}
                    return completed(command, stdout=json.dumps(payload))
                return FakeRunner()(command, **kwargs)

            doctor = fixture.make_doctor("go2", runner=runner, environment_updates={
                "ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard", "ROBOT_SCOPE_UNITREE_SETUP": str(overlay), "PYTHONNOUSERSITE": "1"})
            checks = {check.id: check for check in doctor.run()}
            self.assertEqual(checks["onboard.native_modules"].status, "pass")
            self.assertEqual(checks["go2.unitree_workspace"].detail, str(overlay))
            command, options = next(item for item in commands if "robot-scope-onboard-doctor" in item[0])
            self.assertIn(str(fixture.ros_prefix / "setup.bash"), command)
            self.assertIn(str(overlay), command)
            self.assertIn("cv2.cvtColor", command[-1])
            self.assertEqual(options["env"]["PYTHONNOUSERSITE"], "1")
            failed = fixture.make_doctor("go2", runner=lambda command, **kwargs: completed(command, returncode=1, stdout='{"error_type":"ImportError"}'),
                                        environment_updates={"ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard", "ROBOT_SCOPE_UNITREE_SETUP": str(overlay)})
            self.assertEqual({check.id: check for check in failed.run()}["onboard.native_modules"].status, "fail")

    def test_onboard_doctor_matches_launcher_contract_and_rejects_profile_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            profile = fixture.project / "config/go2-onboard.json"
            profile.write_text('{"robot_type":"go2"}', encoding="utf-8")
            for key, bad_value in (("ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE", "ssh"),
                                   ("ROBOT_SCOPE_FASTLIO_DDS_MODE", "local"), ("ROS_LOCALHOST_ONLY", "1"),
                                   ("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")):
                doctor = fixture.make_doctor("go2", environment_updates={"ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard", key: bad_value})
                self.assertEqual({check.id: check for check in doctor.run()}["onboard.startup_contract"].status, "fail")
            linked = fixture.project / "config/linked.json"
            linked.symlink_to(profile)
            doctor = fixture.make_doctor("go2", environment_updates={"ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard", "ROBOT_SCOPE_ROBOT_PROFILE_PATH": str(linked)})
            self.assertEqual({check.id: check for check in doctor.run()}["onboard.robot_profile"].status, "fail")
            profile.write_text('{"robot_type":"other"}', encoding="utf-8")
            doctor = fixture.make_doctor("go2", environment_updates={"ROBOT_SCOPE_MAPPING_PROFILE": "go2-onboard"})
            self.assertEqual({check.id: check for check in doctor.run()}["onboard.robot_profile"].status, "fail")

    @staticmethod
    def _write_realsense_env(path, **overrides):
        values = {
            "ROBOT_SCOPE_REALSENSE_BIND_HOST": "192.168.50.30",
            "ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST": "192.168.50.10",
            "ROBOT_SCOPE_REALSENSE_PORT": "8090",
            "ROBOT_SCOPE_REALSENSE_WIDTH": "640",
            "ROBOT_SCOPE_REALSENSE_HEIGHT": "480",
            "ROBOT_SCOPE_REALSENSE_FPS": "15",
            "ROBOT_SCOPE_REALSENSE_JPEG_QUALITY": "72",
        }
        values.update(overrides)
        path.write_text(
            "".join(f"{key}={value}\n" for key, value in values.items()),
            encoding="utf-8",
        )
        path.chmod(0o600)

    def test_mode_features_are_explicit_and_cumulative(self):
        self.assertEqual(doctor_module.MODE_FEATURES["observer"], {"core"})
        self.assertEqual(
            doctor_module.MODE_FEATURES["go2-nav"],
            {"core", "go2", "control", "xt16", "nav"},
        )

    def test_env_parser_never_evaluates_shell_syntax(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            marker = base / "should-not-exist"
            env_file = base / "robot-scope.env"
            env_file.write_text(
                f"SAFE_LITERAL=$(touch {marker})\nexport SIMPLE='plain value'\n",
                encoding="utf-8",
            )
            values = doctor_module.parse_env_file(env_file)
            self.assertEqual(values["SAFE_LITERAL"], f"$(touch {marker})")
            self.assertEqual(values["SIMPLE"], "plain value")
            self.assertFalse(marker.exists())

    def test_observer_is_ready_without_gstreamer(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            runner = FakeRunner()
            doctor = fixture.make_doctor("observer", runner=runner)
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["platform.os"].status, "pass")
            self.assertEqual(by_id["platform.arch"].status, "pass")
            self.assertEqual(by_id["camera.gstreamer"].status, "warn")
            self.assertFalse(by_id["camera.gstreamer"].required)
            self.assertEqual(doctor.exit_code, 0)
            python_probe = next(
                command
                for command in runner.commands
                if any("import fastapi" in argument for argument in command)
            )
            self.assertEqual(python_probe[:3], ("/bin/bash", "--noprofile", "--norc"))
            self.assertTrue(
                any('source "$1"' in argument for argument in python_probe)
            )
            self.assertIn(str(fixture.ros_prefix / "setup.bash"), python_probe)

    def test_realsense_relay_doctor_validates_config_and_exact_local_bind(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            relay_env = Path(temporary) / "realsense-camera.env"
            self._write_realsense_env(relay_env)
            runner = FakeRunner(interface="wlan0", cidr="192.168.50.30/24")
            doctor = fixture.make_doctor(
                "observer",
                runner=runner,
                realsense_relay_env_file=relay_env,
            )
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["realsense.config"].status, "pass")
            self.assertEqual(by_id["realsense.env_permissions"].status, "pass")
            self.assertEqual(by_id["realsense.bind_address"].status, "pass")
            self.assertEqual(doctor.exit_code, 0)
            address_probe = next(
                command
                for command in runner.commands
                if "addr" in command and "scope" in command
            )
            self.assertEqual(
                address_probe,
                ("/usr/bin/ip", "-o", "-4", "addr", "show", "scope", "global"),
            )

    def test_realsense_relay_doctor_rejects_bad_profile_and_missing_bind(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            relay_env = Path(temporary) / "realsense-camera.env"
            self._write_realsense_env(
                relay_env,
                ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST="192.168.50.255",
            )
            rejected = fixture.make_doctor(
                "observer", realsense_relay_env_file=relay_env
            )
            rejected_checks = {check.id: check for check in rejected.run()}
            self.assertEqual(rejected_checks["realsense.config"].status, "fail")

            self._write_realsense_env(relay_env)
            missing = fixture.make_doctor(
                "observer",
                runner=FakeRunner(cidr="192.168.50.31/24"),
                realsense_relay_env_file=relay_env,
            )
            missing_checks = {check.id: check for check in missing.run()}
            self.assertEqual(missing_checks["realsense.config"].status, "pass")
            self.assertEqual(missing_checks["realsense.bind_address"].status, "fail")
            self.assertEqual(missing.exit_code, 1)

    def test_realsense_relay_doctor_requires_every_setting_and_private_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            relay_env = Path(temporary) / "realsense-camera.env"
            relay_env.write_text(
                "ROBOT_SCOPE_REALSENSE_BIND_HOST=192.168.50.30\n",
                encoding="utf-8",
            )
            incomplete = fixture.make_doctor(
                "observer", realsense_relay_env_file=relay_env
            )
            checks = {check.id: check for check in incomplete.run()}
            self.assertEqual(checks["realsense.config"].status, "fail")

            self._write_realsense_env(relay_env)
            relay_env.chmod(0o644)
            public = fixture.make_doctor(
                "observer",
                runner=FakeRunner(cidr="192.168.50.30/24"),
                realsense_relay_env_file=relay_env,
            )
            public_checks = {check.id: check for check in public.run()}
            self.assertEqual(public_checks["realsense.env_permissions"].status, "fail")
            self.assertEqual(public.exit_code, 1)

    def test_jazzy_observer_is_supported_on_ubuntu_2404(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            fixture.use_jazzy()
            doctor = fixture.make_doctor("observer")
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(doctor.ros_distro, "jazzy")
            self.assertEqual(by_id["platform.os"].status, "pass")
            self.assertEqual(by_id["platform.ros_pair"].status, "pass")
            self.assertEqual(by_id["core.ros_setup"].status, "pass")
            self.assertEqual(doctor.exit_code, 0)

    def test_jazzy_go2_mode_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            fixture.use_jazzy()
            doctor = fixture.make_doctor("go2", allow_hardware_offline=True)
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["platform.mode"].status, "fail")
            self.assertIn("not supported", by_id["platform.mode"].summary)
            self.assertEqual(doctor.exit_code, 1)

    def test_mismatched_ros_distro_fails_platform_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            doctor = fixture.make_doctor(
                "observer", environment_updates={"ROS_DISTRO": "jazzy"}
            )
            checks = doctor.run()
            pair = next(check for check in checks if check.id == "platform.ros_pair")
            self.assertEqual(pair.status, "fail")
            self.assertIn("expected=humble", pair.detail)

    def test_go2_checks_configured_interface_and_cyclonedds(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            (fixture.home / "setup_go2_ros2_humble.sh").write_text(
                "# installed helper\n", encoding="utf-8"
            )
            helper = fixture.project / "scripts" / "setup_go2_ros2_humble.sh"
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("# repository helper\n", encoding="utf-8")
            cyclone = (
                fixture.home
                / "unitree_ros2"
                / "cyclonedds_ws"
                / "install"
                / "setup.bash"
            )
            cyclone.parent.mkdir(parents=True, exist_ok=True)
            cyclone.write_text("", encoding="utf-8")
            doctor = fixture.make_doctor("go2")
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["go2.interface"].status, "pass")
            self.assertEqual(by_id["go2.unitree_workspace"].status, "pass")
            self.assertEqual(by_id["go2.camera_interface"].status, "pass")
            self.assertEqual(doctor.exit_code, 0)

    def test_matching_dynamic_go2_camera_interface_is_trusted(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            (fixture.project / "config" / "go2.json").write_text(
                '{"direct_camera":{"allowed_interfaces":["eno1"]}}',
                encoding="utf-8",
            )
            helper = fixture.project / "scripts" / "setup_go2_ros2_humble.sh"
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("# repository helper\n", encoding="utf-8")
            setup = (
                fixture.home
                / "unitree_ros2"
                / "cyclonedds_ws"
                / "install"
                / "setup.bash"
            )
            setup.parent.mkdir(parents=True)
            setup.write_text("", encoding="utf-8")
            doctor = fixture.make_doctor("go2")
            checks = doctor.run()
            camera = next(check for check in checks if check.id == "go2.camera_interface")
            self.assertEqual(camera.status, "pass")
            self.assertIn("trusted Go2 host interface", camera.summary)

    def test_install_mode_warns_for_missing_nic_but_strict_doctor_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            helper = fixture.project / "scripts" / "setup_go2_ros2_humble.sh"
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("# repository helper\n", encoding="utf-8")
            setup = (
                fixture.home
                / "unitree_ros2"
                / "cyclonedds_ws"
                / "install"
                / "setup.bash"
            )
            setup.parent.mkdir(parents=True)
            setup.write_text("", encoding="utf-8")

            def missing_interface(command, **_kwargs):
                if "-c" in command:
                    return completed(command)
                if "link" in command or "addr" in command:
                    return completed(command, returncode=1, stderr="not found")
                return completed(command)

            strict = fixture.make_doctor("go2", runner=missing_interface)
            strict_check = next(
                item for item in strict.run() if item.id == "go2.interface"
            )
            self.assertEqual(strict_check.status, "fail")
            self.assertTrue(strict_check.required)

            install = fixture.make_doctor(
                "go2",
                runner=missing_interface,
                allow_hardware_offline=True,
            )
            install_check = next(
                item for item in install.run() if item.id == "go2.interface"
            )
            self.assertEqual(install_check.status, "warn")
            self.assertFalse(install_check.required)

    def test_control_fails_closed_for_blank_key_and_public_env_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            env_file = Path(temporary) / "robot-scope.env"
            env_file.write_text(
                "ROBOT_SCOPE_CONTROL_ENABLED=1\nROBOT_SCOPE_CONTROL_BRIDGE_KEY=\n",
                encoding="utf-8",
            )
            env_file.chmod(0o644)
            doctor = fixture.make_doctor("go2-control", env_file=env_file)
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["control.configuration"].status, "fail")
            self.assertEqual(by_id["control.env_permissions"].status, "fail")
            self.assertEqual(doctor.exit_code, 1)

    def test_separate_private_control_env_overrides_general_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            env_file = Path(temporary) / "robot-scope.env"
            env_file.write_text(
                "ROBOT_SCOPE_CONTROL_ENABLED=0\n", encoding="utf-8"
            )
            env_file.chmod(0o600)
            control_file = Path(temporary) / "control.env"
            control_file.write_text(
                "ROBOT_SCOPE_CONTROL_ENABLED=1\n"
                f"ROBOT_SCOPE_CONTROL_BRIDGE_KEY={'a' * 64}\n",
                encoding="utf-8",
            )
            control_file.chmod(0o600)
            doctor = fixture.make_doctor("go2-control", env_file=env_file)
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["control.configuration"].status, "pass")
            self.assertEqual(by_id["control.env_permissions"].status, "pass")

    def test_nav_mode_reports_every_external_layer(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            doctor = fixture.make_doctor("go2-nav")
            checks = doctor.run()
            ids = {check.id for check in checks}
            self.assertIn("go2.setup_helper", ids)
            self.assertIn("control.configuration", ids)
            self.assertIn("xt16.hesai_workspace", ids)
            self.assertIn("xt16.livox_sdk_library", ids)
            self.assertIn("xt16.livox_sdk_header", ids)
            self.assertIn("xt16.bridge", ids)
            self.assertIn("xt16.bridge_source", ids)
            self.assertIn("xt16.bridge_reference", ids)
            self.assertIn("xt16.dds_receive_buffer", ids)
            self.assertIn("xt16.map_saver", ids)
            self.assertIn("xt16.map_converter", ids)
            self.assertNotIn("xt16.pcd2pgm_workspace", ids)
            self.assertIn("xt16.relay_host", ids)
            self.assertIn("nav.nav2_map_server.map_server", ids)
            self.assertEqual(doctor.exit_code, 1)

    def test_livox_sdk_private_prefix_override_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            prefix = Path(temporary) / "private-sdk"
            library = prefix / "lib" / "liblivox_lidar_sdk_shared.so"
            header = prefix / "include" / "livox_lidar_api.h"
            library.parent.mkdir(parents=True)
            header.parent.mkdir(parents=True)
            library.write_bytes(b"sdk")
            header.write_text("/* sdk */\n", encoding="utf-8")
            doctor = fixture.make_doctor(
                "go2-xt16",
                environment_updates={"ROBOT_SCOPE_LIVOX_SDK_PREFIX": str(prefix)},
            )
            checks = doctor.run()
            by_id = {check.id: check for check in checks}
            self.assertEqual(by_id["xt16.livox_sdk_library"].status, "pass")
            self.assertEqual(by_id["xt16.livox_sdk_header"].status, "pass")

    def test_runtime_paths_reject_tilde_relative_and_root_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = DoctorFixture(Path(temporary))
            for workspace_root in ("~", "~/robot-workspace", "relative", "/"):
                with self.subTest(workspace_root=workspace_root):
                    with self.assertRaisesRegex(
                        ValueError, "ROBOT_SCOPE_WORKSPACE_ROOT"
                    ):
                        fixture.make_doctor(
                            "observer",
                            environment_updates={
                                "ROBOT_SCOPE_WORKSPACE_ROOT": workspace_root
                            },
                        )

            for sdk_prefix in ("~", "~/livox", "relative", "/"):
                with self.subTest(sdk_prefix=sdk_prefix):
                    doctor = fixture.make_doctor(
                        "go2-xt16",
                        environment_updates={
                            "ROBOT_SCOPE_LIVOX_SDK_PREFIX": sdk_prefix
                        },
                    )
                    with self.assertRaisesRegex(
                        ValueError, "ROBOT_SCOPE_LIVOX_SDK_PREFIX"
                    ):
                        doctor.run()

    def test_architecture_aliases_support_both_host_families(self):
        self.assertEqual(doctor_module.normalized_architecture("amd64"), "x86_64")
        self.assertEqual(doctor_module.normalized_architecture("aarch64"), "arm64")
        self.assertEqual(doctor_module.normalized_architecture("arm64"), "arm64")
        self.assertIsNone(doctor_module.normalized_architecture("riscv64"))


if __name__ == "__main__":
    unittest.main()
