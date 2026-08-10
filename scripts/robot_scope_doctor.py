#!/usr/bin/env python3
"""Read-only platform and dependency checks for Robot Scope installations.

The doctor never sources shell setup files.  It checks their presence and runs
fixed, argument-vector-only probes so that a user-controlled dotenv value is
never evaluated as shell code.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


MODES = ("observer", "go2", "go2-control", "go2-xt16", "go2-nav")
MODE_FEATURES = {
    "observer": frozenset({"core"}),
    "go2": frozenset({"core", "go2"}),
    "go2-control": frozenset({"core", "go2", "control"}),
    "go2-xt16": frozenset({"core", "go2", "xt16"}),
    # Navigation starts the shared XT16/FAST-LIO pipeline and uses the signed
    # Go2 motion bridge, so a useful navigation installation needs both.
    "go2-nav": frozenset({"core", "go2", "control", "xt16", "nav"}),
}
SUPPORTED_ARCHITECTURES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
}
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    required: bool
    summary: str
    detail: str = ""
    remedy: str = ""


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a deliberately small dotenv subset without executing anything."""

    values: dict[str, str] = {}
    if not path.exists():
        return values
    if not path.is_file():
        raise ValueError(f"environment path is not a regular file: {path}")
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid environment line {line_number}: missing =")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ENV_KEY_RE.fullmatch(key):
            raise ValueError(f"invalid environment key on line {line_number}")
        if value[:1] in {"'", '"'}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise ValueError(
                    f"unterminated quoted value on environment line {line_number}"
                )
            value = value[1:-1]
        values[key] = value
    return values


def parse_os_release(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if key not in {"ID", "VERSION_ID", "PRETTY_NAME"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def normalized_architecture(machine: str) -> str | None:
    return SUPPORTED_ARCHITECTURES.get(str(machine).strip().casefold())


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


class Doctor:
    """Collect mode-aware, read-only installation checks."""

    GSTREAMER_ELEMENTS = (
        "udpsrc",
        "rtpjitterbuffer",
        "rtph264depay",
        "h264parse",
        "avdec_h264",
        "videoconvert",
        "videoscale",
        "videorate",
        "jpegenc",
        "fdsink",
    )
    NAV2_EXECUTABLES = (
        "nav2_map_server/map_server",
        "nav2_map_server/map_saver_cli",
        "nav2_controller/controller_server",
        "nav2_planner/planner_server",
        "nav2_behaviors/behavior_server",
        "nav2_bt_navigator/bt_navigator",
        "nav2_lifecycle_manager/lifecycle_manager",
    )

    def __init__(
        self,
        *,
        mode: str,
        project_dir: Path,
        env_file: Path | None,
        os_release_file: Path = Path("/etc/os-release"),
        architecture: str | None = None,
        environment: Mapping[str, str] | None = None,
        allow_hardware_offline: bool = False,
        command_runner: CommandRunner = subprocess.run,
        which: Which = shutil.which,
        ros_prefix: Path = Path("/opt/ros/humble"),
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode
        self.features = MODE_FEATURES[mode]
        self.project_dir = project_dir.resolve()
        self.env_file = env_file
        file_values = parse_env_file(env_file) if env_file is not None else {}
        self.control_env_file = (
            env_file.with_name("control.env") if env_file is not None else None
        )
        if (
            self.control_env_file is not None
            and self.control_env_file != env_file
            and self.control_env_file.exists()
        ):
            file_values.update(parse_env_file(self.control_env_file))
        self.environment = dict(file_values)
        self.environment.update(dict(environment if environment is not None else os.environ))
        self.os_release_file = os_release_file
        self.architecture = architecture or platform.machine()
        self.command_runner = command_runner
        self.which = which
        self.ros_prefix = ros_prefix
        self.allow_hardware_offline = bool(allow_hardware_offline)
        self.home = Path(self.environment.get("HOME", str(Path.home())))
        if not self.home.is_absolute() or self.home == Path("/"):
            raise ValueError("HOME must be an absolute non-root path")
        workspace_root = self.environment.get("ROBOT_SCOPE_WORKSPACE_ROOT", "").strip()
        if not workspace_root:
            self.workspace_root = self.home
        else:
            self.workspace_root = Path(workspace_root)
            if not self.workspace_root.is_absolute() or self.workspace_root == Path("/"):
                raise ValueError(
                    "ROBOT_SCOPE_WORKSPACE_ROOT must be blank or an absolute non-root path"
                )
        self.checks: list[Check] = []

    def add(
        self,
        check_id: str,
        status: str,
        summary: str,
        *,
        required: bool = True,
        detail: str = "",
        remedy: str = "",
    ) -> None:
        self.checks.append(
            Check(
                id=check_id,
                status=status,
                required=required,
                summary=summary,
                detail=detail,
                remedy=remedy,
            )
        )

    def check_file(
        self,
        check_id: str,
        label: str,
        path: Path,
        *,
        required: bool = True,
        executable: bool = False,
        remedy: str = "",
    ) -> bool:
        ready = path.is_file() and (not executable or os.access(path, os.X_OK))
        if ready:
            self.add(check_id, "pass", f"{label} found", required=required, detail=str(path))
        else:
            self.add(
                check_id,
                "fail" if required else "warn",
                f"{label} missing",
                required=required,
                detail=str(path),
                remedy=remedy,
            )
        return ready

    def run_command(self, command: Sequence[str], *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
        return self.command_runner(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    def configured_path(self, key: str, default: Path) -> Path:
        raw = self.environment.get(key, "").strip()
        if not raw:
            return default
        path = Path(raw)
        if not path.is_absolute() or path == Path("/"):
            raise ValueError(f"{key} must be blank or an absolute non-root path")
        return path

    def run(self) -> list[Check]:
        self._check_platform()
        self._check_core()
        if "go2" in self.features:
            self._check_go2()
        if "control" in self.features:
            self._check_control()
        if "xt16" in self.features:
            self._check_xt16()
        if "nav" in self.features:
            self._check_nav()
        return list(self.checks)

    def _check_platform(self) -> None:
        release = parse_os_release(self.os_release_file)
        if release.get("ID", "").casefold() == "ubuntu" and release.get("VERSION_ID") == "22.04":
            self.add(
                "platform.os",
                "pass",
                "Ubuntu 22.04 detected",
                detail=release.get("PRETTY_NAME", "Ubuntu 22.04"),
            )
        else:
            detected = release.get("PRETTY_NAME") or "unknown operating system"
            self.add(
                "platform.os",
                "fail",
                "Ubuntu 22.04 is required by the supported installer",
                detail=detected,
                remedy="Use an Ubuntu 22.04 ROS 2 host; Jetson is optional.",
            )

        normalized = normalized_architecture(self.architecture)
        if normalized:
            self.add(
                "platform.arch",
                "pass",
                f"supported {normalized} architecture",
                detail=self.architecture,
            )
        else:
            self.add(
                "platform.arch",
                "fail",
                "unsupported CPU architecture",
                detail=self.architecture,
                remedy="Use an x86_64 or arm64 Ubuntu 22.04 host.",
            )

    def _check_core(self) -> None:
        self.check_file(
            "core.ros_setup",
            "ROS 2 Humble setup",
            self.ros_prefix / "setup.bash",
            remedy="Install ROS 2 Humble before running the dashboard installer.",
        )
        requirements = self.project_dir / "requirements.txt"
        self.check_file("core.requirements", "Python requirements file", requirements)

        python = self.project_dir / ".venv" / "bin" / "python"
        if not (python.is_file() and os.access(python, os.X_OK)):
            python = Path(sys.executable)
        ros_setup = self.ros_prefix / "setup.bash"
        try:
            result = self.run_command(
                [
                    "/bin/bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    'set -eo pipefail\nsource "$1"\nshift\nexec "$@"',
                    "robot-scope-doctor",
                    str(ros_setup),
                    str(python),
                    "-c",
                    "import fastapi, numpy, rclpy, uvicorn, websockets, yaml",
                ],
                timeout=15.0,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.add(
                "core.python_modules",
                "fail",
                "Python/ROS modules could not be checked",
                detail=str(exc),
                remedy="Create the system-site-packages venv and install requirements.txt.",
            )
        else:
            if result.returncode == 0:
                self.add(
                    "core.python_modules",
                    "pass",
                    "Python and ROS modules import successfully",
                    detail=str(python),
                )
            else:
                detail = (result.stderr or result.stdout).strip()[-500:]
                self.add(
                    "core.python_modules",
                    "fail",
                    "Python or ROS modules are missing",
                    detail=detail,
                    remedy="Run install_ubuntu.sh --apply and rerun this doctor.",
                )

        ip_binary = self.which("ip")
        if ip_binary:
            self.add("core.iproute2", "pass", "iproute2 is available", detail=ip_binary)
        else:
            self.add(
                "core.iproute2",
                "fail",
                "ip command is missing",
                remedy="Install the Ubuntu iproute2 package.",
            )

        self._check_gstreamer(required=False)

    def _check_gstreamer(self, *, required: bool) -> None:
        gst_launch = self.which("gst-launch-1.0")
        gst_inspect = self.which("gst-inspect-1.0")
        if not gst_launch or not gst_inspect:
            self.add(
                "camera.gstreamer",
                "fail" if required else "warn",
                "GStreamer camera runtime is incomplete",
                required=required,
                remedy=(
                    "Install gstreamer1.0-tools, plugins-good, plugins-bad, and "
                    "gstreamer1.0-libav."
                ),
            )
            return
        missing: list[str] = []
        for element in self.GSTREAMER_ELEMENTS:
            try:
                result = self.run_command([gst_inspect, element], timeout=5.0)
            except (OSError, subprocess.SubprocessError):
                missing.append(element)
                continue
            if result.returncode != 0:
                missing.append(element)
        if missing:
            self.add(
                "camera.gstreamer",
                "fail" if required else "warn",
                "GStreamer plugins are missing",
                required=required,
                detail=", ".join(missing),
                remedy="Install the Ubuntu good, bad, and libav GStreamer plugin sets.",
            )
        else:
            self.add(
                "camera.gstreamer",
                "pass",
                "GStreamer camera pipeline is available",
                required=required,
                detail=gst_launch,
            )

    def _check_go2(self) -> None:
        helper = self.project_dir / "scripts" / "setup_go2_ros2_humble.sh"
        self.check_file(
            "go2.setup_helper",
            "repository Go2 ROS 2 environment helper",
            helper,
            remedy="Restore scripts/setup_go2_ros2_humble.sh from the repository.",
        )
        cyclone_workspace = (
            self.workspace_root
            / "unitree_ros2"
            / "cyclonedds_ws"
            / "install"
            / "setup.bash"
        )
        self.check_file(
            "go2.unitree_workspace",
            "Unitree CycloneDDS workspace setup",
            cyclone_workspace,
            remedy="Run the pinned Go2 dependency bootstrap for this user.",
        )

        self._check_go2_interface()
        # Direct Go2 video is an optional feature; lack of GStreamer does not
        # prevent ROS telemetry or point-cloud observation.

    def _check_go2_interface(self) -> None:
        interface = self.environment.get("ROBOT_SCOPE_GO2_INTERFACE", "eno1").strip()
        cidr = self.environment.get(
            "ROBOT_SCOPE_GO2_INTERFACE_CIDR", "192.168.123.99/24"
        ).strip()
        if not INTERFACE_RE.fullmatch(interface):
            self.add(
                "go2.interface",
                "fail",
                "Go2 network interface label is invalid",
                detail=interface,
                remedy="Set ROBOT_SCOPE_GO2_INTERFACE to one existing wired interface.",
            )
            return
        try:
            parsed_cidr = ipaddress.ip_interface(cidr)
            if parsed_cidr.version != 4:
                raise ValueError("IPv4 required")
        except ValueError:
            self.add(
                "go2.interface",
                "fail",
                "Go2 interface CIDR is invalid",
                detail=cidr,
                remedy="Set ROBOT_SCOPE_GO2_INTERFACE_CIDR to an IPv4 address/prefix.",
            )
            return
        ip_binary = self.which("ip")
        if not ip_binary:
            return
        try:
            link = self.run_command([ip_binary, "-o", "link", "show", "dev", interface])
            addresses = self.run_command(
                [ip_binary, "-o", "-4", "addr", "show", "dev", interface, "scope", "global"]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.add(
                "go2.interface",
                "fail",
                "Go2 interface could not be inspected",
                detail=str(exc),
            )
            return
        if link.returncode != 0:
            self.add(
                "go2.interface",
                "warn" if self.allow_hardware_offline else "fail",
                "configured Go2 interface does not exist",
                required=not self.allow_hardware_offline,
                detail=interface,
                remedy="Choose the wired NIC connected to the Go2 network.",
            )
            return
        address_tokens = {
            token
            for line in addresses.stdout.splitlines()
            for token in line.split()
            if "/" in token
        }
        if addresses.returncode != 0 or cidr not in address_tokens:
            self.add(
                "go2.interface",
                "warn" if self.allow_hardware_offline else "fail",
                "configured Go2 address is not assigned",
                required=not self.allow_hardware_offline,
                detail=f"{interface} expects {cidr}",
                remedy="Assign the configured static CIDR without replacing user network settings.",
            )
            return
        carrier = "LOWER_UP" in link.stdout
        self.add(
            "go2.interface",
            "pass",
            "Go2 interface and address are configured",
            detail=f"{interface} {cidr}",
        )
        if not carrier:
            self.add(
                "go2.carrier",
                "warn",
                "Go2 interface has no active carrier",
                required=False,
                detail=interface,
                remedy="Connect the robot cable before starting live ROS/DDS features.",
            )

        camera_interface = self.environment.get(
            "ROBOT_SCOPE_CAMERA_INTERFACE", interface
        ).strip()
        profile_path = self.project_dir / "config" / "go2.json"
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            allowed = profile.get("direct_camera", {}).get("allowed_interfaces", [])
        except (OSError, ValueError, TypeError):
            allowed = []
        if camera_interface == interface:
            self.add(
                "go2.camera_interface",
                "pass",
                "Go2 camera uses the trusted Go2 host interface",
                required=False,
                detail=camera_interface,
            )
        elif camera_interface not in allowed:
            self.add(
                "go2.camera_interface",
                "warn",
                "selected camera interface is not in the Go2 profile allowlist",
                required=False,
                detail=camera_interface,
                remedy="Add the selected wired NIC to direct_camera.allowed_interfaces.",
            )
        else:
            self.add(
                "go2.camera_interface",
                "pass",
                "Go2 camera interface is allowlisted",
                required=False,
                detail=camera_interface,
            )

    def _check_control(self) -> None:
        enabled = self.environment.get("ROBOT_SCOPE_CONTROL_ENABLED", "0") == "1"
        key = self.environment.get("ROBOT_SCOPE_CONTROL_BRIDGE_KEY", "")
        if enabled and len(key) >= 32:
            self.add(
                "control.configuration",
                "pass",
                "Go2 control is explicitly enabled with a bridge key",
            )
        else:
            self.add(
                "control.configuration",
                "fail",
                "Go2 control is not fully configured",
                remedy=(
                    "Set ROBOT_SCOPE_CONTROL_ENABLED=1 and a random bridge key of at "
                    "least 32 characters in the private environment file."
                ),
            )
        secret_file = (
            self.control_env_file
            if self.control_env_file is not None and self.control_env_file.exists()
            else self.env_file
        )
        if secret_file and secret_file.exists():
            permissions = stat.S_IMODE(secret_file.stat().st_mode)
            if permissions & 0o077:
                self.add(
                    "control.env_permissions",
                    "fail",
                    "control environment file is readable by group or others",
                    detail=oct(permissions),
                    remedy=f"Run chmod 600 {secret_file}",
                )
            else:
                self.add(
                    "control.env_permissions",
                    "pass",
                    "control environment file permissions are private",
                    detail=oct(permissions),
                )
        else:
            self.add(
                "control.env_permissions",
                "fail",
                "private control environment file is missing",
                detail=str(secret_file or "not configured"),
            )

    def _check_xt16(self) -> None:
        livox_sdk_prefix = self.configured_path(
            "ROBOT_SCOPE_LIVOX_SDK_PREFIX",
            self.workspace_root / "ws" / "livox" / "sdk2_install",
        )
        paths = (
            (
                "xt16.hesai_workspace",
                "Hesai ROS 2 workspace",
                self.workspace_root / "ws" / "hesai_ws" / "install" / "setup.bash",
            ),
            (
                "xt16.livox_workspace",
                "Livox message workspace",
                self.workspace_root
                / "ws"
                / "livox"
                / "ws_livox"
                / "install"
                / "setup.bash",
            ),
            (
                "xt16.fastlio_workspace",
                "FAST-LIO workspace",
                self.workspace_root / "ws" / "fastlio_ws" / "install" / "setup.bash",
            ),
            (
                "xt16.livox_sdk_library",
                "private-prefix Livox SDK2 shared library",
                livox_sdk_prefix / "lib" / "liblivox_lidar_sdk_shared.so",
            ),
            (
                "xt16.livox_sdk_header",
                "private-prefix Livox SDK2 API header",
                livox_sdk_prefix / "include" / "livox_lidar_api.h",
            ),
            (
                "xt16.bridge",
                "repository XT16 PointCloud bridge",
                self.project_dir / "scripts" / "xt16_fastlio_bridge.py",
            ),
            (
                "xt16.map_saver",
                "repository FAST-LIO map saver",
                self.project_dir / "scripts" / "save_map.py",
            ),
            (
                "xt16.map_converter",
                "repository PCD-to-2D map converter",
                self.project_dir / "scripts" / "convert_pcd_to_occupancy.py",
            ),
            (
                "xt16.hesai_config",
                "repository Hesai driver configuration",
                self.project_dir / "config" / "hesai_xt16.yaml",
            ),
            (
                "xt16.fastlio_config",
                "repository FAST-LIO configuration",
                self.project_dir / "config" / "fastlio_xt16.yaml",
            ),
        )
        for check_id, label, path in paths:
            self.check_file(
                check_id,
                label,
                path,
                remedy=(
                    "Restore repository helpers or run the pinned XT16/FAST-LIO "
                    "dependency bootstrap for external workspaces."
                ),
            )
        self._check_xt16_relay_host()

    def _check_xt16_relay_host(self) -> None:
        """Probe the optional robot-mounted relay host without authenticating."""

        host = self.environment.get(
            "ROBOT_SCOPE_XT16_RELAY_HOST", "192.168.123.18"
        ).strip()
        try:
            address = ipaddress.ip_address(host)
            if address.version != 4 or not address.is_private:
                raise ValueError("private IPv4 required")
        except ValueError:
            self.add(
                "xt16.relay_host",
                "warn",
                "XT16 relay host address is invalid",
                required=False,
                detail=host,
                remedy="Set ROBOT_SCOPE_XT16_RELAY_HOST to the relay host's private IPv4.",
            )
            return
        ping = self.which("ping")
        if not ping:
            self.add(
                "xt16.relay_host",
                "warn",
                "XT16 relay host reachability was not checked",
                required=False,
                detail="ping command is unavailable",
            )
            return
        try:
            result = self.run_command([ping, "-c", "1", "-W", "1", host], timeout=3.0)
        except (OSError, subprocess.SubprocessError) as exc:
            result = subprocess.CompletedProcess([ping], 1, "", str(exc))
        if result.returncode == 0:
            self.add(
                "xt16.relay_host",
                "pass",
                "XT16 relay host is reachable without authentication",
                required=False,
                detail=host,
            )
        else:
            self.add(
                "xt16.relay_host",
                "warn",
                "XT16 relay host is currently unreachable",
                required=False,
                detail=host,
                remedy="Connect or power the robot host; no password was requested or stored.",
            )

    def _check_nav(self) -> None:
        for relative in self.NAV2_EXECUTABLES:
            executable = self.ros_prefix / "lib" / relative
            check_id = "nav." + relative.replace("/", ".")
            self.check_file(
                check_id,
                f"Nav2 executable {relative.rsplit('/', 1)[-1]}",
                executable,
                executable=True,
                remedy="Install ros-humble-navigation2 and ros-humble-nav2-bringup.",
            )
        self.check_file(
            "nav.parameters",
            "Robot Scope Nav2 parameter base",
            self.project_dir / "config" / "nav2_params_go2_humble.yaml",
        )

    @property
    def exit_code(self) -> int:
        return 1 if any(c.required and c.status == "fail" for c in self.checks) else 0


def build_parser() -> argparse.ArgumentParser:
    project_default = Path(__file__).resolve().parents[1]
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    )
    parser = argparse.ArgumentParser(
        description="Check a Robot Scope Ubuntu 22.04 installation without changing it."
    )
    parser.add_argument("--mode", choices=MODES, default="observer")
    parser.add_argument("--project-dir", type=Path, default=project_default)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=config_home / "robot-scope" / "robot-scope.env",
    )
    parser.add_argument("--os-release", type=Path, default=Path("/etc/os-release"))
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--allow-hardware-offline",
        action="store_true",
        help="treat missing robot NIC/carrier as install-time warnings",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        doctor = Doctor(
            mode=args.mode,
            project_dir=args.project_dir,
            env_file=args.env_file,
            os_release_file=args.os_release,
            allow_hardware_offline=args.allow_hardware_offline,
        )
        checks = doctor.run()
    except (OSError, ValueError) as exc:
        print(f"Robot Scope doctor configuration error: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        payload = {
            "mode": doctor.mode,
            "features": sorted(doctor.features),
            "supported_platform": "Ubuntu 22.04 x86_64/arm64",
            "jetson_required": False,
            "checks": [asdict(check) for check in checks],
            "ok": doctor.exit_code == 0,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"Robot Scope doctor | mode={doctor.mode} | "
            "platform=Ubuntu 22.04 x86_64/arm64 (Jetson optional)"
        )
        for check in checks:
            requirement = "required" if check.required else "optional"
            print(f"{check.status.upper():4} [{requirement}] {check.id}: {check.summary}")
            if check.detail:
                print(f"     {check.detail}")
            if check.remedy and check.status != "pass":
                print(f"     remedy: {check.remedy}")
        failures = sum(c.required and c.status == "fail" for c in checks)
        warnings = sum(c.status == "warn" for c in checks)
        print(f"Summary: required_failures={failures} warnings={warnings}")
    return doctor.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
