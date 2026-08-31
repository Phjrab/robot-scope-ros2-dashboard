import os
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_ubuntu.sh"


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


class InstallerFixture:
    def __init__(self, base: Path):
        self.project = base / "project with spaces"
        self.config = base / "config with spaces"
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "deploy").mkdir()
        (self.project / "config").mkdir()
        shutil.copy2(INSTALLER, self.project / "scripts" / "install_ubuntu.sh")
        (self.project / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (self.project / "deploy" / "robot-scope.env.example").write_text(
            "ROBOT_SCOPE_CONTROL_ENABLED=0\n", encoding="utf-8"
        )
        self.os_release = base / "os-release"
        self.os_release.write_text(
            'ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04 LTS"\n',
            encoding="utf-8",
        )
        for distro, codename in (("humble", "jammy"), ("jazzy", "noble")):
            (self.project / "config" / f"ros_dependencies_{distro}.json").write_text(
                json.dumps(
                    {
                        "ros_distro": distro,
                        "ubuntu_codename": codename,
                        "ros_apt_source": {
                            "version": "1.2.0",
                            "url": (
                                "https://github.com/ros-infrastructure/ros-apt-source/"
                                "releases/download/1.2.0/"
                                f"ros2-apt-source_1.2.0.{codename}_all.deb"
                            ),
                            "sha256": "a" * 64,
                        },
                        "apt_groups": {
                            "base": ["python3-venv", "iproute2", "libssl-dev"],
                            "ros": [f"ros-{distro}-ros-base"],
                            "camera": ["gstreamer1.0-tools"],
                            "navigation": [f"ros-{distro}-navigation2"],
                        },
                    }
                ),
                encoding="utf-8",
            )
        write_executable(
            self.project / "scripts" / "bootstrap_ros_dependencies.sh",
            "#!/usr/bin/env bash\n"
            "printf 'bootstrap:%s\\n' \"$*\"\n"
            "printf 'livox:%s\\n' \"${ROBOT_SCOPE_LIVOX_SDK_PREFIX:-}\"\n",
        )
        write_executable(
            self.project / "scripts" / "robot_scope_doctor.py",
            "#!/usr/bin/env python3\nimport sys\nprint('doctor:' + ' '.join(sys.argv[1:]))\nraise SystemExit(1)\n",
        )
        shutil.copy2(
            ROOT / "scripts" / "robot_scope_dashboard_service.py",
            self.project / "scripts" / "robot_scope_dashboard_service.py",
        )
        (self.project / "scripts" / "robot_scope_dashboard_service.py").chmod(0o755)

    def run(self, *extra):
        return subprocess.run(
            [
                str(self.project / "scripts" / "install_ubuntu.sh"),
                "--project-dir",
                str(self.project),
                "--config-dir",
                str(self.config),
                "--os-release",
                str(self.os_release),
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=10,
        )


class UbuntuInstallerTests(unittest.TestCase):
    def test_default_is_read_only_dry_run_and_propagates_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            result = fixture.run("--mode", "go2-nav")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DRY RUN", result.stdout)
            self.assertIn("bootstrap:--mode go2-nav --manifest", result.stdout)
            self.assertIn("--dry-run", result.stdout)
            self.assertIn("doctor:--mode go2-nav", result.stdout)
            self.assertIn("--allow-hardware-offline", result.stdout)
            self.assertIn("current doctor status=1", result.stdout)
            self.assertFalse(fixture.config.exists())
            self.assertFalse((fixture.project / ".venv").exists())

    def test_existing_user_paths_are_only_reported_during_dry_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            fixture.config.mkdir()
            env_file = fixture.config / "robot-scope.env"
            env_file.write_text("USER_VALUE=keep\n", encoding="utf-8")
            venv = fixture.project / ".venv"
            venv.mkdir()
            marker = venv / "user-data"
            marker.write_text("keep", encoding="utf-8")
            result = fixture.run("--mode", "observer", "--skip-python-deps")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("preserve existing environment file", result.stdout)
            self.assertIn("preserve and reuse existing venv", result.stdout)
            self.assertEqual(env_file.read_text(encoding="utf-8"), "USER_VALUE=keep\n")
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_workspace_root_from_env_is_forwarded_without_sourcing(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            fixture.config.mkdir()
            workspace = Path(temporary) / "custom workspace"
            livox_prefix = Path(temporary) / "custom livox sdk"
            env_file = fixture.config / "robot-scope.env"
            env_file.write_text(
                f"ROBOT_SCOPE_WORKSPACE_ROOT='{workspace}'\n"
                f"ROBOT_SCOPE_LIVOX_SDK_PREFIX='{livox_prefix}'\n",
                encoding="utf-8",
            )
            marker = Path(temporary) / "must-not-run"
            env_file.write_text(
                env_file.read_text(encoding="utf-8")
                + f"UNRELATED=$(touch {marker})\n",
                encoding="utf-8",
            )
            result = fixture.run("--mode", "go2")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"workspace-root={workspace}", result.stdout)
            self.assertIn(f"livox-sdk-prefix={livox_prefix}", result.stdout)
            self.assertIn(f"--workspace-root {workspace}", result.stdout)
            self.assertIn(f"livox:{livox_prefix}", result.stdout)
            self.assertFalse(marker.exists())

    def test_systemd_environment_paths_reject_unexpanded_tilde(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            fixture.config.mkdir()
            env_file = fixture.config / "robot-scope.env"
            env_file.write_text(
                "ROBOT_SCOPE_WORKSPACE_ROOT=~/robot-workspaces\n",
                encoding="utf-8",
            )
            result = fixture.run("--mode", "go2")
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be blank or absolute", result.stderr)

    def test_missing_pinned_bootstrap_is_a_packaging_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            (fixture.project / "scripts" / "bootstrap_ros_dependencies.sh").unlink()
            result = fixture.run("--mode", "observer")
            self.assertEqual(result.returncode, 2)
            self.assertIn("pinned dependency bootstrap is missing", result.stderr)
            self.assertFalse(fixture.config.exists())

    def test_unknown_mode_fails_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            result = fixture.run("--mode", "unsafe")
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported mode", result.stderr)
            self.assertFalse(fixture.config.exists())

    def test_help_states_platform_and_mutation_gate(self):
        result = subprocess.run(
            [str(INSTALLER), "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ubuntu 22.04/Humble", result.stdout)
        self.assertIn("Ubuntu 24.04/Jazzy", result.stdout)
        self.assertIn("--apply", result.stdout)
        self.assertIn("Jetson is optional", result.stdout)
        self.assertIn("never writes deployment IPs or credentials", result.stdout)
        self.assertIn("never enables or starts that relay", result.stdout)

    def test_privileged_options_only_print_during_dry_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            fake_bin = Path(temporary) / "fake-bin"
            fake_bin.mkdir()
            marker = Path(temporary) / "sudo-was-executed"
            write_executable(
                fake_bin / "sudo",
                f"#!/usr/bin/env bash\ntouch {marker!s}\nexit 91\n",
            )
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            result = subprocess.run(
                [
                    str(fixture.project / "scripts" / "install_ubuntu.sh"),
                    "--project-dir",
                    str(fixture.project),
                    "--config-dir",
                    str(fixture.config),
                    "--os-release",
                    str(fixture.os_release),
                    "--mode",
                    "go2-nav",
                    "--install-system-packages",
                    "--install-service",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("libssl-dev", result.stdout)
            self.assertIn("would verify ROS apt source SHA-256", result.stdout)
            self.assertIn("would render and verify robot-scope.service", result.stdout)
            self.assertIn(
                "would render and verify robot-scope-control-bridge.service",
                result.stdout,
            )
            self.assertIn("/usr/local/bin/robot-scope-dashboard", result.stdout)
            self.assertIn("would leave Robot Scope services disabled and stopped", result.stdout)
            self.assertIn("would generate private control secret file", result.stdout)
            self.assertFalse(marker.exists(), "dry-run executed sudo")
            self.assertFalse(fixture.config.exists())

    def test_manifest_groups_follow_mode_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            observer = fixture.run("--mode", "observer")
            go2 = fixture.run("--mode", "go2")
            nav = fixture.run("--mode", "go2-nav")
            self.assertEqual(observer.returncode, 0, observer.stderr)
            self.assertEqual(go2.returncode, 0, go2.stderr)
            self.assertEqual(nav.returncode, 0, nav.stderr)
            observer_guidance = next(
                line for line in observer.stdout.splitlines() if "package guidance" in line
            )
            go2_guidance = next(
                line for line in go2.stdout.splitlines() if "package guidance" in line
            )
            nav_guidance = next(
                line for line in nav.stdout.splitlines() if "package guidance" in line
            )
            self.assertNotIn("gstreamer1.0-tools", observer_guidance)
            self.assertIn("gstreamer1.0-tools", go2_guidance)
            self.assertNotIn("ros-humble-navigation2", go2_guidance)
            self.assertIn("ros-humble-navigation2", nav_guidance)

    def test_noble_selects_jazzy_manifest_for_observer(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            fixture.os_release.write_text(
                'ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04 LTS"\n',
                encoding="utf-8",
            )
            result = fixture.run("--mode", "observer")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("platform=Ubuntu 24.04 / ROS 2 jazzy", result.stdout)
            guidance = next(
                line for line in result.stdout.splitlines() if "package guidance" in line
            )
            self.assertIn("ros-jazzy-ros-base", guidance)
            self.assertNotIn("ros-humble-ros-base", guidance)

    def test_noble_rejects_unverified_go2_modes_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            fixture.os_release.write_text(
                'ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04 LTS"\n',
                encoding="utf-8",
            )
            result = fixture.run("--mode", "go2")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Jazzy currently supports observer mode only", result.stderr)
            self.assertFalse(fixture.config.exists())

    def test_manifest_apt_source_must_match_ubuntu_codename(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            manifest_path = fixture.project / "config" / "ros_dependencies_humble.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["ros_apt_source"]["url"] = manifest["ros_apt_source"][
                "url"
            ].replace(".jammy_all.deb", ".noble_all.deb")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = fixture.run("--mode", "observer")
            self.assertEqual(result.returncode, 2)
            self.assertIn("ROS apt source metadata is incomplete", result.stderr)

    def test_apply_rejects_non_host_os_release_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = InstallerFixture(Path(temporary))
            host_release_path = Path("/etc/os-release")
            host_release = (
                host_release_path.read_text(encoding="utf-8")
                if host_release_path.is_file()
                else ""
            )
            host_version = next(
                (
                    line.split("=", 1)[1].strip().strip('"')
                    for line in host_release.splitlines()
                    if line.startswith("VERSION_ID=")
                ),
                "",
            )
            fake_version = "24.04" if host_version == "22.04" else "22.04"
            fixture.os_release.write_text(
                f'ID=ubuntu\nVERSION_ID="{fake_version}"\n'
                f'PRETTY_NAME="Ubuntu {fake_version} LTS"\n',
                encoding="utf-8",
            )
            result = fixture.run("--mode", "observer", "--apply")
            self.assertEqual(result.returncode, 2)
            expected = (
                "override must match the running host"
                if os.uname().sysname == "Linux"
                else "--apply is supported only on Ubuntu Linux"
            )
            self.assertIn(expected, result.stderr)
            self.assertFalse(fixture.config.exists())

    def test_service_and_ros_source_contract_is_fail_closed(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("ROS apt source checksum mismatch", source)
        system_package_body = source.split("install_system_packages() {", 1)[1].split(
            "doctor_command=(", 1
        )[0]
        self.assertNotIn("/opt/ros/humble/setup.bash", system_package_body)
        self.assertIn("systemd-analyze verify", source)
        self.assertIn('EnvironmentFile=-$ENV_FILE', source)
        self.assertIn('EnvironmentFile=-$CONTROL_ENV_FILE', source)
        self.assertIn('EnvironmentFile=$CONTROL_ENV_FILE', source)
        self.assertIn("sudo systemctl daemon-reload", source)
        self.assertNotIn("sudo systemctl enable", source)
        self.assertIn("refusing to overwrite existing systemd unit", source)
        self.assertIn("refusing unmanaged dashboard SSH operator helper", source)
        self.assertIn("sudo install -o root -g root -m 0755", source)
        self.assertIn("/usr/local/bin/robot-scope-dashboard", source)
        self.assertIn("/etc/robot-scope-dashboard-operator.port", source)
        self.assertNotIn("curl |", source)
        self.assertNotIn("robot-scope-service-lifecycle.sudoers", source)
        self.assertNotIn("robot-scope-xt16-relay.service", source)


if __name__ == "__main__":
    unittest.main()
