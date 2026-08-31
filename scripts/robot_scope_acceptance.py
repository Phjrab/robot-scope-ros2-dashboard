#!/usr/bin/env python3
"""Read-only hardware acceptance recorder for Robot Scope.

The default run performs only fixed, bounded observations.  Supervised checks
are records of an operator-controlled procedure; this program never sends a
motion command, starts a service, launches mapping/navigation, clears an
E-stop, or changes a safety limit.
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
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from robot_scope_doctor import Doctor, parse_env_file


SCHEMA = "robot-scope.hardware-acceptance"
SCHEMA_VERSION = 1
STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
REPORT_DIR_MODE = 0o700
REPORT_FILE_MODE = 0o600
MAX_HTTP_BYTES = 2 * 1024 * 1024
MAX_SAFE_TEXT = 240
MANIFEST_RESERVE_BYTES = 1024 * 1024
CAMERA_MIN_FPS_HZ = 10.0
CAMERA_MAX_AGE_S = 3.0
PERCEPTION_MAX_RESULT_AGE_S = 2.0
POINTCLOUD_DECIMATED_MAX_POINTS = 60_000
FIXED_DASHBOARD_HOST = "127.0.0.1"
FIXED_UNITS = (
    "robot-scope.service",
    "robot-scope-control-bridge.service",
)
SYSTEMD_PROPERTIES = (
    "LoadState",
    "UnitFileState",
    "ActiveState",
    "SubState",
    "Result",
    "NRestarts",
)
READ_ONLY_ENDPOINTS = (
    "/api/v1/health",
    "/api/v1/control",
    "/api/v1/navigation",
    "/api/v1/mapping/control",
    "/api/v1/datasets/capture",
    "/api/v1/saved-maps",
    "/api/v1/system/service",
    "/api/v1/control/bridge-service",
    "/api/v1/topics",
    "/api/v1/cameras",
    "/api/v1/perception/health",
    "/api/v1/perception/latest",
    "/api/v1/models",
    "/api/v1/competition",
    "/api/v1/pointcloud/settings",
)
SECRET_RE = re.compile(
    r"(?i)(authorization|bearer|bridge[_-]?key|password|secret|token|mac)"
)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:/[A-Za-z0-9._-]+){2,}")


@dataclass(frozen=True)
class AcceptanceCheck:
    id: str
    timestamp: str
    status: str
    expected: str
    observed: str
    evidence: tuple[str, ...]
    manual_action: bool
    safety_impact: str

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError("invalid acceptance status")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,95}", self.id):
            raise ValueError("invalid acceptance check id")
        for value in (self.expected, self.observed, self.safety_impact):
            if not value or len(value) > MAX_SAFE_TEXT:
                raise ValueError("acceptance text is empty or too long")
        if len(self.evidence) > 12:
            raise ValueError("acceptance evidence is not bounded")
        for value in self.evidence:
            if not value or len(value) > MAX_SAFE_TEXT:
                raise ValueError("acceptance evidence is empty or too long")


@dataclass(frozen=True)
class SupervisedScenario:
    id: str
    title: str
    expected: str
    operator_action: str
    safety_impact: str


SUPERVISED_SCENARIOS = (
    SupervisedScenario(
        "supervised.manual_short_stop",
        "Arm, short low-speed drive, and stop",
        "Low-speed motion starts only with deadman held and stops on release.",
        "Use the dashboard in a clear area; ARM, make one short move, release deadman, then DISARM.",
        "Confirms the normal manual motion and stop path without changing limits.",
    ),
    SupervisedScenario(
        "supervised.browser_disconnect_watchdog",
        "Browser disconnect watchdog",
        "Closing or disconnecting the control page causes a bounded signed stop and lease release.",
        "While making a minimal low-speed command, close the controlling page and observe the physical robot stop.",
        "Confirms loss of the browser cannot sustain motion.",
    ),
    SupervisedScenario(
        "supervised.dashboard_process_stop",
        "Dashboard process final stop",
        "A supervised dashboard shutdown emits the final stop before transport teardown.",
        "With the robot stationary and DISARMED, use the approved lifecycle control and observe bridge/lease state.",
        "Confirms shutdown ordering; do not use an ungraceful kill for this check.",
    ),
    SupervisedScenario(
        "supervised.control_bridge_stop",
        "Control bridge stop",
        "Bridge stop is rejected while unsafe and produces no continuing motion when allowed.",
        "With the robot stationary and DISARMED, use the dashboard bridge STOP control and verify signed readiness disappears.",
        "Confirms the standalone watchdog boundary remains fail-closed.",
    ),
    SupervisedScenario(
        "supervised.stale_lowstate",
        "Stale LowState fault",
        "Loss of fresh LowState revokes readiness and prevents or stops motion.",
        "Under the approved lab fault procedure, interrupt only the LowState source and observe the dashboard and robot.",
        "Confirms stale robot telemetry cannot keep a lease active.",
    ),
    SupervisedScenario(
        "supervised.foreign_sport_publisher",
        "Foreign sport publisher fault",
        "Unexpected named sport publishers block signed bridge readiness.",
        "Under the approved isolated-lab procedure, introduce the fixed test publisher and observe fail-closed readiness.",
        "Confirms graph cardinality prevents competing command sources.",
    ),
    SupervisedScenario(
        "supervised.navigation_start_stop",
        "Navigation start and stop",
        "Navigation acquires only its own lease after readiness and STOP releases it before process cleanup.",
        "Select a verified map, START without sending a goal, wait for readiness, then STOP.",
        "Confirms navigation transaction ownership without autonomous travel.",
    ),
    SupervisedScenario(
        "supervised.mapping_warmup_cancel",
        "Cancel navigation during mapping warmup",
        "Cancellation rolls back Nav-owned mapping by exact job identity and leaves no lease.",
        "START navigation from an idle localization pipeline, then use STOP during the documented warmup phase.",
        "Confirms cancellation cannot leave an owned pipeline or motion lease behind.",
    ),
    SupervisedScenario(
        "supervised.nav2_child_crash",
        "Nav2 child crash fault",
        "Unexpected child exit deactivates navigation and cleans up only the exact owned mapping job.",
        "Use the approved fixed fault-injection procedure while no goal is active; observe terminal cleanup.",
        "Confirms process failure cannot leave autonomous output armed.",
    ),
    SupervisedScenario(
        "supervised.xt16_interruption",
        "XT16 stream interruption",
        "Sensor freshness loss blocks navigation and prevents stale cloud replay from enabling motion.",
        "Under the approved lab procedure, interrupt the XT16 stream while no goal is active and observe readiness.",
        "Confirms LiDAR freshness and timestamp fences fail closed.",
    ),
    SupervisedScenario(
        "supervised.dataset_shutdown_blocker",
        "Dataset shutdown blocker",
        "An active capture blocks dashboard lifecycle mutation until capture is finalized.",
        "Start a short non-motion capture, request dashboard restart, then finalize capture before retrying.",
        "Confirms dataset durability is not bypassed by lifecycle control.",
    ),
    SupervisedScenario(
        "supervised.low_disk_rejection",
        "Low disk write rejection",
        "Map and dataset writes reject before crossing their configured disk reserve.",
        "Use only the approved bounded test volume; attempt the documented write and retain the volume afterward for inspection.",
        "Confirms low-disk handling does not publish partial durable artifacts.",
    ),
    SupervisedScenario(
        "supervised.robot_wifi_disconnect",
        "Robot Wi-Fi disconnect",
        "Receiver and perception become stale or offline, and reconnect never restores ARM or AUTO state.",
        "With the robot stationary and the physical stop available, use the approved Wi-Fi isolation procedure and then restore the link.",
        "Confirms management-link loss cannot reuse stale results or restore motion authority.",
    ),
    SupervisedScenario(
        "supervised.realsense_source_stall",
        "RealSense source stall",
        "The source and dependent results become stale, and no incomplete Dataset sample is published.",
        "With no capture or motion active, apply the approved source-stall procedure and observe source, result, and Dataset state.",
        "Confirms a frozen source cannot be presented as live input.",
    ),
    SupervisedScenario(
        "supervised.realsense_relay_restart",
        "RealSense relay restart",
        "The receiver reports a bounded interruption and returns live with one producer and no automatic motion state change.",
        "While stationary, restart only the relay through the approved manual procedure and observe receiver generation and viewers.",
        "Confirms relay recovery does not duplicate producers or affect control authority.",
    ),
    SupervisedScenario(
        "supervised.perception_process_stop",
        "Perception process stop",
        "Perception becomes offline, stale results are not ready, and motion authority remains absent.",
        "While stationary, stop only the shadow process through the approved manual procedure and observe dashboard status.",
        "Confirms optional inference loss cannot bypass the control bridge.",
    ),
    SupervisedScenario(
        "supervised.perception_result_freeze",
        "Perception result freeze",
        "A non-advancing result exceeds its age bound and is explicitly classified stale.",
        "Use the approved fixed freeze fixture while stationary and observe sequence, result age, and readiness.",
        "Confirms cached AI output cannot remain ready.",
    ),
    SupervisedScenario(
        "supervised.model_hash_mismatch",
        "Model hash mismatch",
        "Mismatched runtime model identity is rejected while the old active and previous records remain intact.",
        "Use only the approved invalid model fixture and inspect the local registry and shadow runtime without activating it.",
        "Confirms model identity mismatch fails closed without damaging rollback state.",
    ),
    SupervisedScenario(
        "supervised.model_activation_rollback",
        "Model activation rollback",
        "A validated activation is explicit and rollback restores the exact previous model without auto-resume.",
        "Use the local operator tool with exact confirmations, validate shadow health, then perform the documented rollback.",
        "Confirms active and previous model publication remains atomic and operator-owned.",
    ),
    SupervisedScenario(
        "supervised.preview_consumer_disconnect",
        "Preview consumer disconnect",
        "Disconnect releases exactly one viewer and never leaves an extra receiver or producer.",
        "Open one approved preview, disconnect that consumer, and observe bounded viewer and producer counts.",
        "Confirms preview demand cleanup does not accumulate transport owners.",
    ),
    SupervisedScenario(
        "supervised.decimated_pointcloud_load",
        "Decimated PointCloud load",
        "The bounded diagnostic cloud preserves camera, perception, LowState, and control freshness.",
        "Enable only the approved point and rate limit while stationary, observe priority traffic, then disable the diagnostic stream.",
        "Confirms diagnostic PointCloud stays below the reviewed bound.",
    ),
    SupervisedScenario(
        "supervised.raw_pointcloud_overload_abort",
        "Raw PointCloud overload abort",
        "Any priority-traffic degradation aborts raw PointCloud first and the overload is never recorded as PASS.",
        "Under separate load approval, enable the fixed raw diagnostic briefly and abort immediately on a stop condition.",
        "Confirms optional raw traffic is shed before safety or freshness limits are changed.",
    ),
    SupervisedScenario(
        "supervised.dashboard_receiver_restart",
        "Dashboard receiver restart",
        "The receiver restarts offline, reacquires one generation, and never restores ARM or AUTO automatically.",
        "While stationary and DISARMED, use the approved dashboard lifecycle procedure and observe receiver ownership after recovery.",
        "Confirms receiver restart cannot replay state or create duplicate consumers.",
    ),
    SupervisedScenario(
        "supervised.competition_lock_mutation_rejection",
        "Competition Lock mutation rejection",
        "Competition Lock rejects configuration mutation while STOP and other safety cleanup remain available.",
        "Enable Competition Lock, attempt only the approved harmless configuration change, then verify cleanup controls remain available.",
        "Confirms configuration freeze cannot block fail-safe cleanup.",
    ),
)
SCENARIO_BY_ID = {item.id: item for item in SUPERVISED_SCENARIOS}


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
JsonFetcher = Callable[[str], Mapping[str, Any]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def safe_text(value: Any, *, fallback: str) -> str:
    text = CONTROL_RE.sub(" ", str(value or "")).strip()
    if not text:
        return fallback
    if SECRET_RE.search(text):
        return fallback
    text = ABSOLUTE_PATH_RE.sub("[path]", text)
    return text[:MAX_SAFE_TEXT]


def _safe_evidence(*items: str) -> tuple[str, ...]:
    return tuple(safe_text(item, fallback="redacted diagnostic") for item in items)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _private_ipv4(value: Any) -> str | None:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return None
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or not (address.is_private or address.is_link_local)
        or address.is_loopback
        or address.is_unspecified
        or address.is_multicast
    ):
        return None
    return str(address)


class LocalDashboardClient:
    """Bounded GET-only client for the fixed loopback dashboard."""

    def __init__(self, port: int, *, timeout_s: float = 2.0) -> None:
        if isinstance(port, bool) or not 1 <= int(port) <= 65535:
            raise ValueError("dashboard port must be from 1 to 65535")
        self._origin = f"http://{FIXED_DASHBOARD_HOST}:{int(port)}"
        self._timeout_s = max(0.25, min(float(timeout_s), 5.0))

    def fetch(self, endpoint: str) -> Mapping[str, Any]:
        if endpoint not in READ_ONLY_ENDPOINTS:
            raise ValueError("endpoint is not in the read-only allowlist")
        request = urllib.request.Request(
            self._origin + endpoint,
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_HTTP_BYTES:
                    raise ValueError("dashboard response exceeded the size limit")
                payload = response.read(MAX_HTTP_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("dashboard read-only endpoint unavailable") from exc
        if len(payload) > MAX_HTTP_BYTES:
            raise ValueError("dashboard response exceeded the size limit")
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ValueError("dashboard response must be an object")
        return decoded


class AcceptanceRunner:
    """Collect fixed platform, runtime, and artifact-safety observations."""

    def __init__(
        self,
        *,
        project_dir: Path,
        mode: str = "go2-nav",
        env_file: Path | None = None,
        dashboard_port: int = 8088,
        report_dir: Path | None = None,
        fetch_json: JsonFetcher | None = None,
        command_runner: CommandRunner = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        doctor_factory: Callable[..., Doctor] = Doctor,
        now: Callable[[], str] = utc_now,
    ) -> None:
        self.project_dir = project_dir.resolve(strict=True)
        if (
            self.project_dir == Path("/")
            or not (self.project_dir / "robot_dashboard").is_dir()
            or not (self.project_dir / "scripts" / "robot_scope_doctor.py").is_file()
        ):
            raise ValueError("project directory is not a Robot Scope checkout")
        self.mode = mode
        self.env_file = env_file
        expected_report_dir = self.project_dir / "runtime" / "reports"
        requested_report_dir = report_dir or expected_report_dir
        if requested_report_dir.is_absolute():
            candidate_report_dir = requested_report_dir
        else:
            candidate_report_dir = self.project_dir / requested_report_dir
        self.report_dir = candidate_report_dir.resolve()
        if self.report_dir != expected_report_dir.resolve():
            raise ValueError("acceptance reports must use the fixed runtime report root")
        if self._has_symlink_component(expected_report_dir):
            raise ValueError("acceptance report path must not contain symlinks")
        self.fetch_json = fetch_json or LocalDashboardClient(dashboard_port).fetch
        self.command_runner = command_runner
        self.which = which
        self.doctor_factory = doctor_factory
        self.now = now
        self.checks: list[AcceptanceCheck] = []
        self._responses: dict[str, Mapping[str, Any]] = {}

    def add(
        self,
        check_id: str,
        status: str,
        expected: str,
        observed: str,
        *,
        evidence: Sequence[str] = (),
        manual_action: bool = False,
        safety_impact: str,
    ) -> None:
        self.checks.append(
            AcceptanceCheck(
                id=check_id,
                timestamp=self.now(),
                status=status,
                expected=safe_text(expected, fallback="fixed acceptance condition"),
                observed=safe_text(observed, fallback="no safe observation available"),
                evidence=_safe_evidence(*evidence),
                manual_action=bool(manual_action),
                safety_impact=safe_text(
                    safety_impact, fallback="safety relevance is documented"
                ),
            )
        )

    def _collect_doctor(self) -> None:
        python_version = platform.python_version()
        python_supported = sys.version_info >= (3, 10)
        self.add(
            "platform.python",
            "PASS" if python_supported else "FAIL",
            "Python 3.10 or newer runs the acceptance and dashboard code.",
            (
                "The active Python version satisfies the repository syntax baseline."
                if python_supported
                else "The active Python version is below the repository syntax baseline."
            ),
            evidence=(f"python={python_version}",),
            safety_impact="The acceptance result must use a Python runtime capable of executing the deployed code.",
        )
        try:
            doctor = self.doctor_factory(
                mode=self.mode,
                project_dir=self.project_dir,
                env_file=self.env_file,
                allow_hardware_offline=True,
            )
            doctor_checks = doctor.run()
        except (OSError, ValueError):
            self.add(
                "platform.doctor",
                "FAIL",
                "The fixed installation doctor completes without a configuration error.",
                "The installation doctor could not complete.",
                safety_impact="Installation identity cannot be trusted for later hardware checks.",
            )
            return
        for item in doctor_checks:
            if item.status == "pass":
                status = "PASS"
            elif item.status == "warn":
                status = "BLOCKED"
            else:
                status = "FAIL" if item.required else "BLOCKED"
            self.add(
                f"doctor.{item.id}",
                status,
                "The fixed installation requirement is satisfied.",
                item.summary,
                evidence=(f"mode={self.mode}", f"required={str(item.required).lower()}"),
                safety_impact=(
                    "Required platform and package identity is checked before live acceptance."
                ),
            )

    def _collect_git_identity(self) -> str:
        git = self.which("git")
        if not git:
            self.add(
                "repository.commit",
                "BLOCKED",
                "A 40-character deployed repository commit is recorded.",
                "git is unavailable on the acceptance host.",
                safety_impact="Results cannot be tied to an exact source revision.",
            )
            return "unknown"
        command = [git, "-C", str(self.project_dir), "rev-parse", "HEAD"]
        try:
            result = self.command_runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except (OSError, subprocess.SubprocessError):
            result = subprocess.CompletedProcess(command, 1, "", "")
        commit = str(result.stdout).strip().lower()
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", commit):
            self.add(
                "repository.commit",
                "PASS",
                "A 40-character deployed repository commit is recorded.",
                "The repository commit was resolved.",
                evidence=(f"commit={commit}",),
                safety_impact="Acceptance evidence is attributable to exact code.",
            )
            return commit
        self.add(
            "repository.commit",
            "FAIL",
            "A 40-character deployed repository commit is recorded.",
            "The repository commit could not be resolved.",
            safety_impact="Acceptance evidence is not attributable to exact code.",
        )
        return "unknown"

    def _collect_systemd(self) -> None:
        systemctl = self.which("systemctl")
        if not systemctl:
            for unit in FIXED_UNITS:
                self.add(
                    f"systemd.{unit}",
                    "BLOCKED",
                    "The fixed unit is loaded and its current state is recorded.",
                    "systemd is unavailable on this host.",
                    safety_impact="Live service ownership cannot be confirmed.",
                )
            return
        properties = [f"--property={item}" for item in SYSTEMD_PROPERTIES]
        for unit in FIXED_UNITS:
            command = [systemctl, "show", "--no-pager", *properties, unit]
            try:
                result = self.command_runner(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                )
            except (OSError, subprocess.SubprocessError):
                result = subprocess.CompletedProcess(command, 1, "", "")
            values: dict[str, str] = {}
            if result.returncode == 0:
                for line in str(result.stdout).splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        if key in SYSTEMD_PROPERTIES:
                            values[key] = value[:80]
            if values.get("LoadState") != "loaded":
                status, observed = "FAIL", "The fixed unit is not loaded."
            elif (
                values.get("ActiveState") != "active"
                or values.get("SubState") != "running"
            ):
                status, observed = "BLOCKED", "The fixed unit is not currently active."
            elif values.get("Result") not in {None, "success"}:
                status, observed = "FAIL", "The fixed unit reports an unsuccessful result."
            elif values.get("NRestarts") not in {None, "0"}:
                status, observed = "FAIL", "The fixed unit reports unexpected restarts."
            else:
                status, observed = "PASS", "The fixed unit is loaded and active."
            evidence = tuple(
                f"{key}={values[key]}" for key in SYSTEMD_PROPERTIES if key in values
            )
            self.add(
                f"systemd.{unit}",
                status,
                "The fixed unit is loaded, stable, and its enablement is observed without changing it.",
                observed,
                evidence=evidence,
                safety_impact="Service identity and crash-loop state gate live acceptance.",
            )

    def _fetch_endpoints(self) -> None:
        for endpoint in READ_ONLY_ENDPOINTS:
            try:
                self._responses[endpoint] = self.fetch_json(endpoint)
            except (RuntimeError, ValueError, json.JSONDecodeError):
                continue
        available = len(self._responses)
        self.add(
            "dashboard.read_only_api",
            "PASS" if available == len(READ_ONLY_ENDPOINTS) else "BLOCKED",
            "Every fixed read-only acceptance endpoint returns a bounded JSON object.",
            (
                "All fixed read-only endpoints responded."
                if available == len(READ_ONLY_ENDPOINTS)
                else "One or more fixed read-only endpoints are unavailable."
            ),
            evidence=(f"responses={available}/{len(READ_ONLY_ENDPOINTS)}",),
            safety_impact="Missing runtime truth blocks dependent checks instead of using cached values.",
        )

    def _response(self, endpoint: str) -> Mapping[str, Any] | None:
        value = self._responses.get(endpoint)
        return value if isinstance(value, Mapping) else None

    def _collect_health(self) -> None:
        health = self._response("/api/v1/health")
        expected = "The agent, pinned target, and mode-required Go2 link are live."
        if not health:
            self.add(
                "runtime.go2_connection",
                "BLOCKED",
                expected,
                "The health snapshot is unavailable.",
                safety_impact="No robot-dependent check may be treated as current.",
            )
            return
        agent_ready = bool(health.get("agent_ready"))
        ros_interface_ready = bool(health.get("ros_interface_ready"))
        target_ready = bool(health.get("robot_target_connected")) and bool(
            health.get("target_matches_startup")
        )
        online = bool(health.get("robot_online"))
        link_contract = "direct_ros"
        if self.mode == "go2-control":
            control = self._response("/api/v1/control")
            control = control.get("control") if control else None
            bridge = control.get("bridge") if isinstance(control, Mapping) else None
            status_age = _finite_number(bridge.get("status_age_s")) if isinstance(bridge, Mapping) else None
            lowstate_age_ms = _finite_number(bridge.get("lowstate_age_ms")) if isinstance(bridge, Mapping) else None
            signed_bridge_ready = (
                isinstance(bridge, Mapping)
                and bridge.get("authenticated") is True
                and bridge.get("ready") is True
                and bridge.get("connected") is True
                and status_age is not None
                and 0 <= status_age <= 0.75
                and lowstate_age_ms is not None
                and 0 <= lowstate_age_ms <= 750.0
            )
            link_contract = "signed_bridge"
            if agent_ready and target_ready and signed_bridge_ready:
                status, observed = "PASS", "The pinned Go2 target and signed LowState Bridge are live."
            elif agent_ready:
                status, observed = "BLOCKED", "The local agent is ready but the signed Go2 control link is not live."
            else:
                status, observed = "FAIL", "The local agent is not ready."
        elif agent_ready and ros_interface_ready and target_ready and online:
            status, observed = "PASS", "The pinned Go2 target is reachable and the local ROS interface is ready."
        elif agent_ready and ros_interface_ready:
            status, observed = "BLOCKED", "The local agent is ready but the pinned Go2 target is not live."
        else:
            status, observed = "FAIL", "The local agent or required ROS interface is not ready."
        self.add(
            "runtime.go2_connection",
            status,
            expected,
            observed,
            evidence=(
                f"link_contract={link_contract}",
                f"agent_ready={agent_ready}",
                f"ros_interface_ready={ros_interface_ready}",
                f"target_matches_startup={bool(health.get('target_matches_startup'))}",
                f"robot_online={online}",
            ),
            safety_impact="Robot connectivity is an explicit prerequisite, not inferred from cached telemetry.",
        )
        transport = (
            health.get("ros_transport")
            if isinstance(health.get("ros_transport"), Mapping)
            else {}
        )
        distro = str(health.get("ros_distro", ""))
        rmw = str(health.get("rmw", ""))
        domain = str(health.get("ros_domain_id", ""))
        domain_valid = domain.isdigit() and 0 <= int(domain) <= 232
        identity_ready = (
            distro == "humble"
            and rmw == "rmw_cyclonedds_cpp"
            and domain_valid
            and transport.get("mode") == "go2_interface"
            and transport.get("interface_ready") is True
            and transport.get("dds_uri_configured") is True
            and transport.get("cyclonedds_configured") is True
            and bool(transport.get("interface"))
        )
        offline_viewer = transport.get("mode") == "offline_viewer"
        if identity_ready:
            identity_status = "PASS"
            identity_observed = "The live ROS/DDS identity matches the fixed Go2 deployment contract."
        elif offline_viewer:
            identity_status = "BLOCKED"
            identity_observed = "The dashboard started in offline-viewer mode, so the dedicated DDS binding is not active."
        else:
            identity_status = "FAIL"
            identity_observed = "The live ROS/DDS identity does not match the fixed Go2 deployment contract."
        self.add(
            "runtime.ros_identity",
            identity_status,
            "ROS 2 Humble uses Cyclone DDS with a valid domain and the dedicated Go2 interface.",
            identity_observed,
            evidence=(
                f"ros_distro={distro or 'unavailable'}",
                f"rmw={rmw or 'unavailable'}",
                f"ros_domain_id={domain or 'unavailable'}",
                f"dds_mode={transport.get('mode', 'unavailable')}",
                f"dds_interface={transport.get('interface', 'unavailable')}",
                f"dds_uri_configured={bool(transport.get('dds_uri_configured'))}",
            ),
            safety_impact="A wrong RMW, domain, or interface can discover the wrong graph or hide the intended robot.",
        )

    @staticmethod
    def _camera_source(payload: Mapping[str, Any] | None, source_id: str) -> Mapping[str, Any] | None:
        sources = payload.get("sources") if payload else None
        if not isinstance(sources, list):
            return None
        return next(
            (
                item
                for item in sources
                if isinstance(item, Mapping) and item.get("id") == source_id
            ),
            None,
        )

    def _collect_distributed_identity(self) -> None:
        health = self._response("/api/v1/health")
        hostname = str(health.get("hostname", "")).strip() if health else ""
        machine = str(health.get("platform", "")).strip() if health else ""
        if hostname and machine and len(hostname) <= 253 and len(machine) <= 40:
            dashboard_status = "PASS"
            dashboard_observed = "The dashboard host exposes a bounded runtime identity."
        else:
            dashboard_status = "BLOCKED"
            dashboard_observed = "The dashboard host identity is unavailable."
        self.add(
            "runtime.dashboard_identity",
            dashboard_status,
            "The dashboard host name and machine identity are recorded from the fixed local API.",
            dashboard_observed,
            evidence=(f"hostname={hostname or 'unavailable'}", f"machine={machine or 'unavailable'}"),
            safety_impact="Field evidence must identify the dashboard host that produced it.",
        )

        cameras = self._response("/api/v1/cameras")
        realsense = self._camera_source(cameras, "realsense_color")
        relay_raw = realsense.get("configured_robot_ip") if realsense else None
        perception = self._response("/api/v1/perception/health")
        perception_raw = perception.get("source_ip") if perception else None
        relay_ip = _private_ipv4(relay_raw)
        perception_ip = _private_ipv4(perception_raw)
        malformed = (relay_raw and relay_ip is None) or (perception_raw and perception_ip is None)
        if malformed:
            source_status = "FAIL"
            source_observed = "A configured robot-side source identity is not a private IPv4 address."
        elif relay_ip and perception_ip and relay_ip == perception_ip:
            source_status = "PASS"
            source_observed = "Camera and perception identify the same private robot-side host."
        else:
            source_status = "BLOCKED"
            source_observed = "Both matching robot-side source identities are not available."
        self.add(
            "runtime.robot_source_identity",
            source_status,
            "Camera and perception expose the same explicit private robot-side source identity.",
            source_observed,
            evidence=(
                f"camera_source={relay_ip or 'unavailable'}",
                f"perception_source={perception_ip or 'unavailable'}",
            ),
            safety_impact="Results from an unexpected host must not be accepted as the configured robot source.",
        )

    def _collect_camera_and_link(self) -> None:
        cameras = self._response("/api/v1/cameras")
        source = self._camera_source(cameras, "realsense_color")
        if not source:
            for check_id, expected, impact in (
                (
                    "camera.realsense_source",
                    "The fixed RealSense source is live within its documented FPS and age bounds.",
                    "A missing source must invalidate dependent perception and Dataset evidence.",
                ),
                (
                    "camera.realsense_transport",
                    "The dashboard receives complete JPEG frames within the documented FPS and age bounds.",
                    "A missing receiver must not reuse the last complete image as live.",
                ),
                (
                    "network.robot_wifi",
                    "The robot-side Wi-Fi probe reports a bounded live RSSI and negotiated link rate.",
                    "An unavailable management link blocks distributed camera and perception acceptance.",
                ),
            ):
                self.add(
                    check_id,
                    "BLOCKED",
                    expected,
                    "The RealSense camera catalog entry is unavailable.",
                    safety_impact=impact,
                )
            self._collect_network_quality(None)
            return

        relay = source.get("relay_health") if isinstance(source.get("relay_health"), Mapping) else {}
        state = str(source.get("state", "offline")).lower()
        source_state = str(relay.get("state", state)).lower()
        source_fps = _finite_number(relay.get("fps"))
        source_age = _finite_number(relay.get("last_frame_age_s"))
        if not bool(source.get("configured")) or state in {"disabled", "stopped", "offline", "error", "waiting"}:
            source_status = "BLOCKED"
            source_observed = "The configured RealSense source is not currently live."
        elif source_state == "stale" or state == "stale":
            source_status = "FAIL"
            source_observed = "The RealSense source is explicitly stale."
        elif source_fps is None or source_age is None:
            source_status = "BLOCKED"
            source_observed = "The RealSense source is missing bounded FPS or age evidence."
        elif source_fps < CAMERA_MIN_FPS_HZ or source_age > CAMERA_MAX_AGE_S:
            source_status = "FAIL"
            source_observed = "The RealSense source is outside the documented FPS or age bound."
        elif bool(source.get("live")) and source_state in {"streaming", "ok", "live"}:
            source_status = "PASS"
            source_observed = "The RealSense source is live within the documented bounds."
        else:
            source_status = "FAIL"
            source_observed = "The RealSense source state is inconsistent with its live flag."
        self.add(
            "camera.realsense_source",
            source_status,
            "The fixed RealSense source is live at 10 Hz or more with age no greater than 3 s.",
            source_observed,
            evidence=(
                f"state={source_state}",
                f"fps={source_fps}",
                f"age_s={source_age}",
                f"invalid_frames={relay.get('invalid_frames')}",
                f"producer_generation={relay.get('producer_generation')}",
            ),
            safety_impact="A stale source must invalidate dependent perception and Dataset evidence.",
        )

        receive_fps = _finite_number(source.get("receive_fps"))
        receive_age = _finite_number(source.get("last_complete_jpeg_age_s"))
        receive_bitrate = _finite_number(source.get("receive_bitrate_mbps"))
        if state in {"disabled", "stopped", "offline", "error", "waiting"}:
            transport_status = "BLOCKED"
            transport_observed = "The dashboard receiver is not currently live."
        elif state == "stale":
            transport_status = "FAIL"
            transport_observed = "The dashboard receiver is explicitly stale."
        elif receive_fps is None or receive_age is None or receive_bitrate is None:
            transport_status = "BLOCKED"
            transport_observed = "The receiver is missing bounded FPS, age, or bitrate evidence."
        elif receive_fps < CAMERA_MIN_FPS_HZ or receive_age > CAMERA_MAX_AGE_S:
            transport_status = "FAIL"
            transport_observed = "The receiver is outside the documented FPS or age bound."
        elif bool(source.get("live")):
            transport_status = "PASS"
            transport_observed = "The receiver is live within the documented bounds."
        else:
            transport_status = "FAIL"
            transport_observed = "The receiver state is inconsistent with its live flag."
        self.add(
            "camera.realsense_transport",
            transport_status,
            "The dashboard receives complete JPEG frames at 10 Hz or more with age no greater than 3 s.",
            transport_observed,
            evidence=(
                f"state={state}",
                f"receive_fps={receive_fps}",
                f"receive_age_s={receive_age}",
                f"receive_bitrate_mbps={receive_bitrate}",
                f"restart_count={source.get('restart_count')}",
            ),
            safety_impact="A stalled receiver must not reuse its last complete image as live.",
        )

        wifi = relay.get("wifi") if isinstance(relay.get("wifi"), Mapping) else None
        if not wifi:
            wifi_status = "BLOCKED"
            wifi_observed = "The robot-side Wi-Fi probe is unavailable."
            wifi_state, rssi, link = "UNVERIFIED", None, None
        else:
            wifi_state = str(wifi.get("state", "UNVERIFIED")).upper()
            rssi = _finite_number(wifi.get("rssi_dbm"))
            link = _finite_number(wifi.get("link_mbps"))
            if wifi_state == "LIVE" and rssi is not None and link is not None and link > 0:
                wifi_status = "PASS"
                wifi_observed = "The robot-side Wi-Fi probe reports live bounded metrics."
            elif wifi_state in {"OFFLINE", "UNVERIFIED"}:
                wifi_status = "BLOCKED"
                wifi_observed = "The robot-side Wi-Fi metrics are unavailable."
            else:
                wifi_status = "FAIL"
                wifi_observed = "The robot-side Wi-Fi probe reports degradation or stale metrics."
        self.add(
            "network.robot_wifi",
            wifi_status,
            "The robot-side Wi-Fi probe reports a bounded live RSSI and negotiated link rate.",
            wifi_observed,
            evidence=(
                f"state={wifi_state}",
                f"interface={wifi.get('interface', 'unavailable') if wifi else 'unavailable'}",
                f"rssi_dbm={rssi}",
                f"link_mbps={link}",
            ),
            safety_impact="An unavailable management link blocks distributed camera and perception acceptance.",
        )
        self._collect_network_quality(wifi)

    def _collect_network_quality(self, wifi: Mapping[str, Any] | None) -> None:
        metrics = wifi.get("quality") if wifi and isinstance(wifi.get("quality"), Mapping) else None
        values = {
            key: _finite_number(metrics.get(key)) if metrics else None
            for key in ("rtt_p50_ms", "rtt_p95_ms", "rtt_p99_ms", "loss_percent", "minimum_throughput_mbps")
        }
        if not metrics or any(value is None for value in values.values()):
            status = "BLOCKED"
            observed = "RTT, loss, and minimum observed throughput are not exposed by the fixed API."
        elif values["loss_percent"] < 0 or values["loss_percent"] > 100:
            status = "FAIL"
            observed = "The network-quality metrics are malformed."
        else:
            status = "PASS"
            observed = "The fixed API exposes one bounded network-quality observation set."
        self.add(
            "network.quality_observation",
            status,
            "One measured interval records RTT p50/p95/p99, loss, and minimum observed throughput.",
            observed,
            evidence=tuple(f"{key}={value}" for key, value in values.items()),
            safety_impact="Link-rate branding or one ping must not substitute for measured competition-link evidence.",
        )

    def _collect_control(self) -> None:
        payload = self._response("/api/v1/control")
        control = payload.get("control") if payload else None
        if not isinstance(control, Mapping):
            self.add(
                "control.signed_bridge",
                "BLOCKED",
                "The signed bridge is authenticated, fresh, and graph cardinality is exact.",
                "The control snapshot is unavailable.",
                safety_impact="Motion acceptance cannot proceed without signed bridge truth.",
            )
            return
        bridge = control.get("bridge") if isinstance(control.get("bridge"), Mapping) else {}
        counts = {
            key: bridge.get(key)
            for key in (
                "sport_subscribers",
                "own_sport_publishers",
                "foreign_named_sport_publishers",
                "bare_unitree_sport_publishers",
                "expected_bare_sport_publishers",
                "total_sport_publishers",
                "lowstate_publishers",
            )
        }
        counts_are_integers = all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in counts.values()
        )
        cardinality_ok = (
            counts_are_integers
            and counts["sport_subscribers"] == 1
            and counts["own_sport_publishers"] == 1
            and counts["foreign_named_sport_publishers"] == 0
            and counts["bare_unitree_sport_publishers"]
            == counts["expected_bare_sport_publishers"]
            and counts["total_sport_publishers"]
            == counts["own_sport_publishers"]
            + counts["foreign_named_sport_publishers"]
            + counts["bare_unitree_sport_publishers"]
            and counts["lowstate_publishers"] == 1
        )
        status_age = _finite_number(bridge.get("status_age_s"))
        fresh = status_age is not None and 0 <= status_age <= 0.75
        lowstate_age_ms = _finite_number(bridge.get("lowstate_age_ms"))
        lowstate_fresh = lowstate_age_ms is not None and 0 <= lowstate_age_ms <= 750.0
        authenticated = bool(bridge.get("authenticated"))
        if any(value is not None for value in counts.values()) and (
            not cardinality_ok or not lowstate_fresh
        ):
            status, observed = "FAIL", "Signed bridge graph cardinality is unsafe."
        elif authenticated and bool(bridge.get("ready")) and fresh:
            status, observed = "PASS", "The signed bridge is authenticated, ready, and fresh."
        else:
            status, observed = "BLOCKED", "The signed bridge is not currently ready and fresh."
        evidence = [
            f"authenticated={authenticated}",
            f"ready={bool(bridge.get('ready'))}",
            f"status_fresh={fresh}",
            f"lowstate_age_ms={lowstate_age_ms}",
        ]
        evidence.extend(f"{key}={value}" for key, value in counts.items())
        self.add(
            "control.signed_bridge",
            status,
            "The signed bridge is authenticated, fresh, and graph cardinality is exact.",
            observed,
            evidence=evidence,
            safety_impact="Unexpected publishers, stale LowState, or unauthenticated status must block motion.",
        )

    def _collect_perception(self) -> None:
        health = self._response("/api/v1/perception/health")
        if not health:
            self.add(
                "perception.runtime",
                "BLOCKED",
                "Shadow perception is observable and has no motion authority or command publishers.",
                "The perception health snapshot is unavailable.",
                safety_impact="Mission readiness cannot infer AI availability from cached results.",
            )
        else:
            state = str(health.get("state", "OFFLINE")).upper()
            authority = health.get("motion_authority")
            command_publishers = health.get("command_publishers", 0)
            unsafe_authority = authority not in {False, "NONE"} or command_publishers not in {0, None}
            if unsafe_authority or str(health.get("mode", "")).upper() != "SHADOW":
                status = "FAIL"
                observed = "Perception does not satisfy the SHADOW and zero-authority contract."
            elif state == "LIVE":
                status = "PASS"
                observed = "Shadow perception is live with no motion authority."
            elif state in {"OFFLINE", "WAITING", "UNAVAILABLE"}:
                status = "BLOCKED"
                observed = "Shadow perception is not currently live."
            else:
                status = "FAIL"
                observed = "Shadow perception reports a failed or degraded runtime."
            self.add(
                "perception.runtime",
                status,
                "Shadow perception is observable and has no motion authority or command publishers.",
                observed,
                evidence=(
                    f"mode={health.get('mode', 'unavailable')}",
                    f"state={state}",
                    f"motion_authority={authority}",
                    f"command_publishers={command_publishers}",
                    f"last_success_age_s={health.get('last_success_age_s')}",
                ),
                safety_impact="Optional AI must never publish commands or bypass the control bridge.",
            )

        latest = self._response("/api/v1/perception/latest")
        results = latest.get("results") if latest else None
        transport = str(latest.get("transport_state", "OFFLINE")).upper() if latest else "OFFLINE"
        if not isinstance(results, list) or not results:
            result_status = "BLOCKED"
            result_observed = "No bounded perception result is available."
            result_evidence = (f"transport={transport}", "results=0")
        else:
            fresh = 0
            stale_closed = 0
            unsafe = 0
            for result in results:
                if not isinstance(result, Mapping):
                    unsafe += 1
                    continue
                age = _finite_number(result.get("last_receive_age"))
                state = str(result.get("result_status", "")).upper()
                if state == "LIVE" and transport == "LIVE" and age is not None and age <= PERCEPTION_MAX_RESULT_AGE_S:
                    fresh += 1
                elif state == "STALE" and (transport != "LIVE" or age is None or age > PERCEPTION_MAX_RESULT_AGE_S):
                    stale_closed += 1
                else:
                    unsafe += 1
            if unsafe:
                result_status = "FAIL"
                result_observed = "One or more perception results has an unsafe freshness classification."
            else:
                result_status = "PASS"
                result_observed = (
                    "All current results are fresh."
                    if fresh
                    else "All retained results are explicitly stale and cannot be ready."
                )
            result_evidence = (
                f"transport={transport}",
                f"results={len(results)}",
                f"fresh={fresh}",
                f"stale_fail_closed={stale_closed}",
                f"unsafe={unsafe}",
            )
        self.add(
            "perception.result_freshness",
            result_status,
            "Results at or below 2 s are LIVE; older, frozen, or disconnected results are explicitly STALE.",
            result_observed,
            evidence=result_evidence,
            safety_impact="A stale or frozen AI result must never satisfy motion or Mission readiness.",
        )

        verified = [
            result.get("clock_domain_verified") is True
            for result in results
            if isinstance(results, list) and isinstance(result, Mapping)
        ] if isinstance(results, list) else []
        self.add(
            "perception.clock_domain",
            "PASS" if verified and all(verified) else "BLOCKED",
            "Every accepted cross-host result has an explicitly verified clock domain.",
            (
                "All observed results have a verified clock domain."
                if verified and all(verified)
                else "Cross-host result timing remains explicitly unverified."
            ),
            evidence=(f"verified={sum(verified)}", f"observed={len(verified)}"),
            safety_impact="Unverified clocks must not produce synthetic end-to-end latency or hide stale input.",
        )
        self._collect_compute_metrics(health)

    def _collect_compute_metrics(self, health: Mapping[str, Any] | None) -> None:
        compute = health.get("compute") if health and isinstance(health.get("compute"), Mapping) else None
        if not compute:
            self.add(
                "perception.compute_metrics",
                "BLOCKED",
                "CPU, GPU, RAM, temperature, and throttling availability are recorded together.",
                "The fixed dashboard API does not expose the complete compute metric set.",
                safety_impact="An unobserved resource or thermal limit cannot support workload acceptance.",
            )
            return
        cpu = _finite_number(compute.get("cpu_percent"))
        gpu = _finite_number(compute.get("gpu_percent"))
        ram_used = _finite_number(compute.get("ram_used_bytes"))
        ram_total = _finite_number(compute.get("ram_total_bytes"))
        temperature = _finite_number(compute.get("temperature_c"))
        throttling = compute.get("throttling")
        valid = (
            cpu is not None
            and 0 <= cpu <= 100
            and gpu is not None
            and 0 <= gpu <= 100
            and ram_used is not None
            and ram_total is not None
            and 0 <= ram_used <= ram_total
            and temperature is not None
            and -50 <= temperature <= 150
            and isinstance(throttling, bool)
        )
        if not valid:
            status = "FAIL"
            observed = "One or more compute metrics is malformed or unavailable."
        elif throttling:
            status = "FAIL"
            observed = "The workload reports thermal or power throttling."
        else:
            status = "PASS"
            observed = "The complete compute metric set is available without throttling."
        self.add(
            "perception.compute_metrics",
            status,
            "CPU, GPU, RAM, temperature, and throttling availability are recorded together.",
            observed,
            evidence=(
                f"cpu_percent={cpu}",
                f"gpu_percent={gpu}",
                f"ram_used_bytes={ram_used}",
                f"ram_total_bytes={ram_total}",
                f"temperature_c={temperature}",
                f"throttling={throttling}",
            ),
            safety_impact="A throttled or unobservable workload cannot be accepted for competition use.",
        )

    def _collect_models(self) -> None:
        registry = self._response("/api/v1/models")
        latest = self._response("/api/v1/perception/latest")
        raw_models = registry.get("models") if registry else None
        active = registry.get("active") if registry else None
        previous = registry.get("previous") if registry else None
        results = latest.get("results") if latest else None
        if not isinstance(raw_models, list) or not isinstance(active, Mapping) or not isinstance(previous, Mapping):
            self.add(
                "models.registry_identity",
                "BLOCKED",
                "Active and previous model IDs resolve to bounded ONNX and engine SHA-256 identities.",
                "The model registry snapshot is unavailable.",
                safety_impact="Runtime results cannot be tied to validated rollback-capable model artifacts.",
            )
            self.add(
                "models.runtime_match",
                "BLOCKED",
                "Every runtime result matches the active model ID and backend artifact SHA-256 for its task.",
                "Model identity comparison is unavailable.",
                safety_impact="A mismatched runtime model must not be treated as active or ready.",
            )
            return
        records = {
            str(item.get("model_id")): item
            for item in raw_models
            if isinstance(item, Mapping) and item.get("model_id")
        }
        identities: list[str] = []
        malformed = False
        for label, mapping in (("active", active), ("previous", previous)):
            for task, model_id in mapping.items():
                record = records.get(str(model_id))
                onnx_digest = str(record.get("onnx_sha256", "")) if record else ""
                engine = record.get("engine") if record and isinstance(record.get("engine"), Mapping) else None
                engine_digest = str(engine.get("sha256", "")) if engine else ""
                if (
                    not record
                    or not re.fullmatch(r"[0-9a-f]{64}", onnx_digest)
                    or not re.fullmatch(r"[0-9a-f]{64}", engine_digest)
                ):
                    malformed = True
                    continue
                identities.append(
                    f"{label}.{task}={model_id}:onnx={onnx_digest}:engine={engine_digest}"
                )
        if not active:
            registry_status = "BLOCKED"
            registry_observed = "No active model is recorded."
        elif malformed:
            registry_status = "FAIL"
            registry_observed = "An active or previous model does not resolve to a bounded hash identity."
        else:
            registry_status = "PASS"
            registry_observed = "Active and previous model identities resolve in the local registry."
        self.add(
            "models.registry_identity",
            registry_status,
            "Active and previous model IDs resolve to bounded ONNX and engine SHA-256 identities.",
            registry_observed,
            evidence=identities[:12] or ("active_models=0",),
            safety_impact="Rollback depends on intact active and previous artifact identity.",
        )

        if not isinstance(results, list) or not results or not active:
            runtime_status = "BLOCKED"
            runtime_observed = "There are no live runtime results and active identities to compare."
            compared = 0
            mismatches = 0
            missing_count = len(active)
        else:
            compared = 0
            mismatches = 0
            seen_tasks: set[str] = set()
            for result in results:
                if not isinstance(result, Mapping):
                    mismatches += 1
                    continue
                task = str(result.get("task", ""))
                if task in seen_tasks:
                    mismatches += 1
                    continue
                seen_tasks.add(task)
                model_id = str(result.get("model_id", ""))
                digest = str(result.get("model_sha256", ""))
                backend = str(result.get("backend", ""))
                expected_id = str(active.get(task, ""))
                expected = records.get(expected_id)
                if backend == "onnx" and expected:
                    expected_digest = str(expected.get("onnx_sha256", ""))
                elif backend == "tensorrt" and expected and isinstance(expected.get("engine"), Mapping):
                    expected_digest = str(expected["engine"].get("sha256", ""))
                else:
                    expected_digest = ""
                compared += 1
                if (
                    model_id != expected_id
                    or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or digest != expected_digest
                ):
                    mismatches += 1
            missing_tasks = set(str(task) for task in active) - seen_tasks
            missing_count = len(missing_tasks)
            if mismatches:
                runtime_status = "FAIL"
                runtime_observed = "One or more runtime results does not match the active model identity."
            elif missing_tasks:
                runtime_status = "BLOCKED"
                runtime_observed = "One or more active tasks has no runtime result to compare."
            else:
                runtime_status = "PASS"
                runtime_observed = "Every runtime result matches its active model identity."
        self.add(
            "models.runtime_match",
            runtime_status,
            "Every runtime result matches the active model ID and backend artifact SHA-256 for its task.",
            runtime_observed,
            evidence=(
                f"compared={compared}",
                f"mismatches={mismatches}",
                f"missing_active_tasks={missing_count}",
            ),
            safety_impact="A mismatched runtime model must not be treated as active or ready.",
        )

    def _collect_competition(self) -> None:
        competition = self._response("/api/v1/competition")
        if not competition:
            status = "BLOCKED"
            observed = "Competition state is unavailable."
            evidence = ()
        else:
            mode = str(competition.get("operation_mode", "UNKNOWN")).upper()
            authority = str(competition.get("motion_authority", "UNKNOWN")).upper()
            locked = competition.get("locked")
            physical = competition.get("lock_is_physical_safety")
            if authority != "NONE" or physical is not False or mode in {"ASSISTED", "AUTO"}:
                status = "FAIL"
                observed = "Competition state grants unaccepted authority or misrepresents the software lock."
            elif locked is True and mode in {"MANUAL", "SHADOW", "SAFE_STOP"}:
                status = "PASS"
                observed = "Competition Lock is enabled with no AI motion authority."
            elif locked is False:
                status = "FAIL"
                observed = "Competition Lock is not enabled for this acceptance observation."
            else:
                status = "BLOCKED"
                observed = "Competition Lock state is malformed or unavailable."
            evidence = (
                f"mode={mode}",
                f"locked={locked}",
                f"motion_authority={authority}",
                f"lock_is_physical_safety={physical}",
            )
        self.add(
            "competition.lock_and_authority",
            status,
            "Competition Lock is enabled, is explicitly non-physical, and AI motion authority is NONE.",
            observed,
            evidence=evidence,
            safety_impact="Configuration freeze must not be confused with the physical stop or grant AI control.",
        )

    def _collect_pointcloud(self) -> None:
        latest = self._response("/api/v1/perception/latest")
        transport = str(latest.get("transport_state", "OFFLINE")).upper() if latest else "OFFLINE"
        results = latest.get("results") if latest else None
        depth = next(
            (
                item
                for item in results
                if isinstance(item, Mapping) and item.get("task") == "depth_summary"
            ),
            None,
        ) if isinstance(results, list) else None
        if depth and depth.get("result_status") == "LIVE" and transport == "LIVE":
            mode_status = "PASS"
            mode_observed = "The active robot-side PointCloud product is the typed SUMMARY result."
            mode = "SUMMARY"
        elif transport == "LIVE" and depth is None:
            mode_status = "PASS"
            mode_observed = "No robot-side PointCloud result is active."
            mode = "OFF"
        else:
            mode_status = "BLOCKED"
            mode_observed = "Robot-side PointCloud mode cannot be established from a live result."
            mode = "UNAVAILABLE"
        self.add(
            "pointcloud.robot_side_mode",
            mode_status,
            "Robot-side management-Wi-Fi PointCloud mode is OFF or a fresh typed SUMMARY result.",
            mode_observed,
            evidence=(f"mode={mode}", f"transport={transport}"),
            safety_impact="A stale summary or implicit raw cloud must not become motion-ready input.",
        )

        settings = self._response("/api/v1/pointcloud/settings")
        if not settings:
            budget_status = "BLOCKED"
            budget_observed = "The dashboard PointCloud renderer budget is unavailable."
            limit = None
            all_points = None
        else:
            limit = settings.get("max_points")
            all_points = settings.get("all_points")
            if all_points is True and limit is None:
                budget_status = "BLOCKED"
                budget_observed = "Raw all-points mode requires a separate supervised load approval."
            elif isinstance(limit, int) and not isinstance(limit, bool) and 1_000 <= limit <= POINTCLOUD_DECIMATED_MAX_POINTS:
                budget_status = "PASS"
                budget_observed = "The renderer uses a bounded decimated point budget."
            else:
                budget_status = "FAIL"
                budget_observed = "The renderer point budget is malformed or exceeds the reviewed bound."
        self.add(
            "pointcloud.dashboard_budget",
            budget_status,
            "Dashboard diagnostic PointCloud is bounded to 60,000 points or raw mode remains supervised-only.",
            budget_observed,
            evidence=(
                f"max_points={limit}",
                f"all_points={all_points}",
                f"frame_interval_s={settings.get('frame_interval_s') if settings else None}",
            ),
            safety_impact="Raw or oversized diagnostic traffic must never be accepted without overload-abort evidence.",
        )

    def _topic_check(
        self,
        *,
        check_id: str,
        topic: str,
        minimum_hz: float,
        maximum_age_s: float,
        maximum_jitter_ms: float | None,
        safety_impact: str,
    ) -> None:
        payload = self._response("/api/v1/topics")
        rows = payload.get("topics") if payload else None
        row = None
        if isinstance(rows, list):
            row = next(
                (
                    item
                    for item in rows
                    if isinstance(item, Mapping) and item.get("name") == topic
                ),
                None,
            )
        expected = (
            f"{topic} has exactly one publisher, at least {minimum_hz:g} Hz, "
            f"and age no greater than {maximum_age_s:g} s."
        )
        if not isinstance(row, Mapping):
            self.add(
                check_id,
                "BLOCKED",
                expected,
                "The required topic is absent from the graph snapshot.",
                evidence=(f"topic={topic}",),
                safety_impact=safety_impact,
            )
            return
        publishers = row.get("publishers")
        hz = _finite_number(row.get("hz"))
        age = _finite_number(row.get("age_s"))
        jitter = _finite_number(row.get("jitter_ms"))
        if isinstance(publishers, bool) or not isinstance(publishers, int):
            status, observed = "FAIL", "The topic publisher count is malformed."
        elif publishers > 1:
            status, observed = "FAIL", "The topic has more than one publisher."
        elif publishers != 1 or hz is None or age is None:
            status, observed = "BLOCKED", "The topic is not producing a complete live observation."
        elif hz < minimum_hz or age > maximum_age_s:
            status, observed = "FAIL", "The live topic is outside the fixed rate or freshness bound."
        elif maximum_jitter_ms is not None and (
            jitter is None or jitter > maximum_jitter_ms
        ):
            status, observed = "FAIL", "The live topic is outside the fixed jitter bound."
        else:
            status, observed = "PASS", "The live topic satisfies the fixed bounds."
        self.add(
            check_id,
            status,
            expected,
            observed,
            evidence=(
                f"topic={topic}",
                f"publishers={publishers}",
                f"hz={hz}",
                f"age_s={age}",
                f"jitter_ms={jitter}",
            ),
            safety_impact=safety_impact,
        )

    def _collect_topics(self) -> None:
        self._topic_check(
            check_id="ros.lowstate",
            topic="/lowstate",
            minimum_hz=10.0,
            maximum_age_s=0.75,
            maximum_jitter_ms=100.0,
            safety_impact="Stale or ambiguous LowState must revoke control readiness.",
        )
        self._topic_check(
            check_id="lidar.hesai_raw",
            topic="/lidar_points",
            minimum_hz=4.0,
            maximum_age_s=1.0,
            maximum_jitter_ms=300.0,
            safety_impact="Raw LiDAR continuity is required before timestamp conversion can be trusted.",
        )
        self._topic_check(
            check_id="lidar.xt16_converted",
            topic="/velodyne_points",
            minimum_hz=4.0,
            maximum_age_s=0.5,
            maximum_jitter_ms=300.0,
            safety_impact="Converted clouds must be current before localization or navigation can proceed.",
        )
        self._topic_check(
            check_id="localization.fast_lio_odom",
            topic="/Odometry",
            minimum_hz=5.0,
            maximum_age_s=1.5,
            maximum_jitter_ms=200.0,
            safety_impact="Fresh host-domain FAST-LIO odometry gates navigation activation.",
        )

    def _collect_navigation(self) -> None:
        nav = self._response("/api/v1/navigation")
        if not nav:
            self.add(
                "navigation.tf_and_timestamp",
                "BLOCKED",
                "The running navigation runtime validates scan, odometry, TF, and timestamp freshness.",
                "The navigation snapshot is unavailable.",
                safety_impact="Timestamp and TF acceptance cannot be inferred from topic arrival alone.",
            )
            return
        pipeline = nav.get("pipeline") if isinstance(nav.get("pipeline"), Mapping) else {}
        readiness = nav.get("readiness") if isinstance(nav.get("readiness"), Mapping) else {}
        state = str(pipeline.get("state", "idle"))
        relevant = all(bool(readiness.get(key)) for key in ("scan", "odometry", "tf"))
        if state == "running" and relevant:
            status, observed = "PASS", "The running navigation runtime reports scan, odometry, and TF ready."
        elif state in {"starting", "running", "stopping"}:
            status, observed = "FAIL", "The active navigation runtime does not satisfy scan, odometry, and TF readiness."
        else:
            status, observed = "BLOCKED", "Navigation is idle, so runtime timestamp and TF gates were not exercised."
        self.add(
            "navigation.tf_and_timestamp",
            status,
            "The running navigation runtime validates scan, odometry, TF, and timestamp freshness.",
            observed,
            evidence=(
                f"pipeline_state={state}",
                f"scan_ready={bool(readiness.get('scan'))}",
                f"odometry_ready={bool(readiness.get('odometry'))}",
                f"tf_ready={bool(readiness.get('tf'))}",
            ),
            safety_impact="Navigation must stay fail-closed when timestamp domains or transforms are invalid.",
        )
        health = (
            nav.get("localization_health")
            if isinstance(nav.get("localization_health"), Mapping)
            else {}
        )
        health_state = str(health.get("state", "UNAVAILABLE"))
        reason_code = str(health.get("reason_code", "TELEMETRY_UNAVAILABLE"))
        metrics = health.get("metrics") if isinstance(health.get("metrics"), Mapping) else {}
        if state != "running":
            health_status = "BLOCKED"
            health_observed = "Navigation is idle, so localization health was not exercised."
        elif health_state == "READY":
            health_status = "PASS"
            health_observed = "The bounded localization health model reports READY."
        elif health_state == "DEGRADED" and reason_code == "INITIAL_POSE_REQUIRED":
            health_status = "BLOCKED"
            health_observed = "Navigation is waiting for the supervised initial-pose step."
        else:
            health_status = "FAIL"
            health_observed = "The running localization health model reports a non-ready condition."
        self.add(
            "navigation.localization_health",
            health_status,
            "Bounded cloud, odometry, TF and progress telemetry satisfies the configured Phase 14 thresholds.",
            health_observed,
            evidence=(
                f"health_state={health_state}",
                f"reason_code={reason_code}",
                f"cloud_hz={metrics.get('cloud_frequency_hz')}",
                f"cloud_age_s={metrics.get('cloud_age_s')}",
                f"odometry_hz={metrics.get('odometry_frequency_hz')}",
                f"odometry_age_s={metrics.get('odometry_age_s')}",
                f"tf_age_s={metrics.get('tf_age_s')}",
                f"fresh_sequence_count={metrics.get('fresh_sequence_count')}",
            ),
            safety_impact="A cached or discontinuous localization stream must never be reported as READY.",
        )

    def _collect_maps(self) -> None:
        payload = self._response("/api/v1/saved-maps")
        maps = payload.get("maps") if payload else None
        if not isinstance(maps, list):
            status, observed, count = "BLOCKED", "The managed map catalog is unavailable.", 0
        else:
            count = len(maps)
            eligible = sum(
                1
                for item in maps
                if isinstance(item, Mapping)
                and str(item.get("format", "")) in {"map-server-pgm", "occupancy2d"}
            )
            if eligible:
                status, observed = "PASS", "The catalog contains a managed 2D navigation map."
            else:
                status, observed = "BLOCKED", "No managed 2D navigation map is currently available."
        self.add(
            "artifacts.map_catalog",
            status,
            "The opaque managed-map catalog is readable and contains a Nav2-compatible 2D map.",
            observed,
            evidence=(f"managed_maps={count}",),
            safety_impact="Navigation must use a revision-pinned managed map, never an arbitrary path.",
        )

    def _collect_dataset_and_disk(self) -> None:
        capture = self._response("/api/v1/datasets/capture")
        if not capture:
            self.add(
                "artifacts.dataset_reserve",
                "BLOCKED",
                "Dataset free space exceeds the configured reserve plus one bounded manifest.",
                "The dataset snapshot is unavailable.",
                safety_impact="Dataset writes cannot be accepted without a current disk reserve.",
            )
            return
        free_bytes = capture.get("free_bytes")
        minimum = capture.get("minimum_free_bytes")
        quota = capture.get("session_quota_bytes")
        values_valid = all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (free_bytes, minimum, quota)
        )
        if not values_valid:
            status, observed = "FAIL", "The dataset reserve snapshot is malformed."
        elif free_bytes < minimum + MANIFEST_RESERVE_BYTES:
            status, observed = "BLOCKED", "Current free space is below the configured write reserve."
        else:
            status, observed = "PASS", "Current free space satisfies the configured write reserve."
        self.add(
            "artifacts.dataset_reserve",
            status,
            "Dataset free space exceeds the configured reserve plus one bounded manifest.",
            observed,
            evidence=(
                f"free_bytes={free_bytes}",
                f"minimum_free_bytes={minimum}",
                f"session_quota_bytes={quota}",
            ),
            safety_impact="Low disk space must reject new writes before publishing partial artifacts.",
        )

    @staticmethod
    def _has_symlink_component(path: Path) -> bool:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            if current.exists() and current.is_symlink():
                return True
        return False

    def _configured_runtime_paths(self) -> tuple[tuple[str, Path, bool], ...]:
        values: dict[str, str] = {}
        if self.env_file is not None and self.env_file.exists():
            values.update(parse_env_file(self.env_file))
        values.update(os.environ)

        def configured(key: str, fallback: Path) -> Path:
            raw = str(values.get(key, "")).strip()
            candidate = Path(raw).expanduser() if raw else fallback
            if not candidate.is_absolute() or candidate == Path("/"):
                raise ValueError(f"{key} is not an absolute non-root path")
            return candidate

        workspace = configured("ROBOT_SCOPE_WORKSPACE_ROOT", Path.home())
        runtime = configured("ROBOT_SCOPE_RUNTIME_DIR", self.project_dir / "runtime")
        return (
            (
                "filesystem.datasets",
                configured("ROBOT_SCOPE_DATASET_DIR", runtime / "datasets"),
                True,
            ),
            (
                "filesystem.maps",
                configured("ROBOT_SCOPE_MAPS_DIR", workspace / "ws" / "go2_3d" / "maps"),
                False,
            ),
            (
                "filesystem.mapping_logs",
                configured("ROBOT_SCOPE_MAPPING_LOG_DIR", workspace / "ws" / "go2_3d"),
                False,
            ),
            (
                "filesystem.ros_logs",
                configured("ROS_LOG_DIR", runtime / "logs" / "ros"),
                False,
            ),
            ("filesystem.reports", self.report_dir, True),
        )

    def _collect_fixed_permissions(self) -> None:
        try:
            targets = self._configured_runtime_paths()
        except (OSError, ValueError):
            self.add(
                "filesystem.configuration",
                "FAIL",
                "Runtime dataset, map, log, and report roots are absolute non-root paths.",
                "One or more configured runtime paths is invalid.",
                safety_impact="Untrusted runtime roots can escape artifact and log safety boundaries.",
            )
            return
        for check_id, path, private in targets:
            if not path.exists():
                self.add(
                    check_id,
                    "NOT_RUN",
                    "The fixed runtime directory is real, private, and not a symlink.",
                    "The runtime directory does not exist on this host.",
                    safety_impact="Permissions must be verified on the deployment host before use.",
                )
                continue
            try:
                mode = stat.S_IMODE(path.lstat().st_mode)
                safe = (
                    path.is_dir()
                    and not self._has_symlink_component(path)
                    and not bool(mode & 0o022)
                    and (not private or mode == 0o700)
                )
            except OSError:
                safe = False
                mode = -1
            self.add(
                check_id,
                "PASS" if safe else "FAIL",
                "The fixed runtime directory is real, private, and not a symlink.",
                (
                    "The runtime directory has the expected private ownership mode."
                    if safe
                    else "The runtime directory is missing a required private-mode invariant."
                ),
                evidence=(f"mode={mode:04o}" if mode >= 0 else "mode=unavailable",),
                safety_impact="Private runtime artifacts and acceptance evidence must not be broadly readable.",
            )

    def prepare_report_directory(self) -> None:
        """Create only the fixed private report directory before observation."""

        self.report_dir.mkdir(parents=True, exist_ok=True, mode=REPORT_DIR_MODE)
        if self.report_dir.is_symlink() or not self.report_dir.is_dir():
            raise ValueError("acceptance report directory must be a real directory")
        os.chmod(self.report_dir, REPORT_DIR_MODE)

    def collect_read_only(self) -> str:
        commit = self._collect_git_identity()
        self._collect_doctor()
        self._collect_systemd()
        self._fetch_endpoints()
        self._collect_health()
        self._collect_distributed_identity()
        self._collect_camera_and_link()
        self._collect_control()
        self._collect_perception()
        self._collect_models()
        self._collect_competition()
        self._collect_pointcloud()
        self._collect_topics()
        self._collect_navigation()
        self._collect_maps()
        self._collect_dataset_and_disk()
        self._collect_fixed_permissions()
        return commit

    def add_supervised_results(
        self,
        *,
        selected_scenario: str | None,
        selected_status: str | None,
    ) -> None:
        for scenario in SUPERVISED_SCENARIOS:
            if scenario.id != selected_scenario:
                status = "NOT_RUN"
                observed = "This supervised scenario was not selected for this run."
                evidence = ("operator_recorded=false",)
                manual = False
            else:
                if selected_status not in STATUSES:
                    raise ValueError("selected supervised status is invalid")
                status = selected_status
                manual = selected_status in {"PASS", "FAIL"}
                observed = {
                    "PASS": "The present operator recorded the expected fixed outcome.",
                    "FAIL": "The present operator recorded behavior outside the fixed expectation.",
                    "BLOCKED": "A prerequisite blocked the operator from performing the scenario.",
                    "NOT_RUN": "The operator deliberately did not perform the scenario.",
                }[selected_status]
                evidence = (
                    f"operator_recorded={str(manual).lower()}",
                    f"result={selected_status}",
                )
            self.add(
                scenario.id,
                status,
                scenario.expected,
                observed,
                evidence=evidence,
                manual_action=manual,
                safety_impact=scenario.safety_impact,
            )

    def report(self, *, commit: str, supervised_requested: bool) -> dict[str, Any]:
        counts = {status: 0 for status in STATUSES}
        for item in self.checks:
            counts[item.status] += 1
        return {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.now(),
            "commit": commit,
            "mode": self.mode,
            "scope": "supervised_record" if supervised_requested else "read_only",
            "script_hardware_side_effects": False,
            "summary": counts,
            "checks": [asdict(item) for item in self.checks],
        }

    def write_report(self, report: Mapping[str, Any]) -> tuple[Path, Path]:
        self.prepare_report_directory()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        json_path = self.report_dir / f"acceptance-{stamp}.json"
        markdown_path = self.report_dir / f"acceptance-{stamp}.md"
        json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        markdown_text = render_markdown(report)
        _write_private_file(json_path, json_text)
        _write_private_file(markdown_path, markdown_text)
        return json_path, markdown_path


def _write_private_file(path: Path, text: str) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        REPORT_FILE_MODE,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Robot Scope hardware acceptance report",
        "",
        f"- Generated: `{report.get('generated_at', 'unknown')}`",
        f"- Commit: `{report.get('commit', 'unknown')}`",
        f"- Mode: `{report.get('mode', 'unknown')}`",
        f"- Scope: `{report.get('scope', 'unknown')}`",
        "- Script hardware side effects: `false`",
        "- Summary: " + ", ".join(f"{key}={summary.get(key, 0)}" for key in STATUSES),
        "",
        "| Status | Check | Expected | Observed | Manual |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.get("checks", []):
        if not isinstance(item, Mapping):
            continue
        values = [
            str(item.get("status", "")),
            str(item.get("id", "")),
            str(item.get("expected", "")),
            str(item.get("observed", "")),
            str(bool(item.get("manual_action", False))).lower(),
        ]
        escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.extend(
        [
            "",
            "## Safety note",
            "",
            "This recorder issued no motion, lifecycle, mapping, navigation, E-stop, map, or dataset mutation request. It wrote only these private report artifacts; supervised rows are operator records only.",
            "",
        ]
    )
    return "\n".join(lines)


class SingleValueAction(argparse.Action):
    """Reject repeated safety-critical selectors instead of using the last value."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest, None) is not None:
            raise argparse.ArgumentError(self, f"{option_string} may be provided only once")
        setattr(namespace, self.dest, values)


def build_parser() -> argparse.ArgumentParser:
    project_default = Path(__file__).resolve().parents[1]
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    parser = argparse.ArgumentParser(
        description="Record fixed Robot Scope hardware acceptance checks without changing the robot."
    )
    parser.add_argument("--mode", choices=("go2", "go2-control", "go2-xt16", "go2-nav"), default="go2-nav")
    parser.add_argument("--project-dir", type=Path, default=project_default)
    parser.add_argument("--env-file", type=Path, default=config_home / "robot-scope" / "robot-scope.env")
    parser.add_argument("--dashboard-port", type=int, default=8088)
    parser.add_argument("--list-supervised-scenarios", action="store_true")
    parser.add_argument("--allow-supervised-motion", action="store_true")
    parser.add_argument("--confirm-estop-ready", action="store_true")
    parser.add_argument("--confirm-clear-area", action="store_true")
    parser.add_argument("--confirm-low-speed-limits", action="store_true")
    parser.add_argument("--confirm-operator-present", action="store_true")
    parser.add_argument(
        "--supervised-scenario",
        choices=tuple(SCENARIO_BY_ID),
        action=SingleValueAction,
    )
    parser.add_argument(
        "--supervised-result",
        choices=STATUSES,
        action=SingleValueAction,
    )
    return parser


def validate_supervised_args(args: argparse.Namespace) -> None:
    selected = args.supervised_scenario is not None or args.supervised_result is not None
    confirmations = (
        args.allow_supervised_motion,
        args.confirm_estop_ready,
        args.confirm_clear_area,
        args.confirm_low_speed_limits,
        args.confirm_operator_present,
    )
    if selected and (args.supervised_scenario is None or args.supervised_result is None):
        raise ValueError("a supervised scenario and result must be provided together")
    if selected and not all(confirmations):
        raise ValueError("every supervised safety confirmation is required")
    if not selected and any(confirmations):
        raise ValueError("supervised safety flags require one fixed scenario and result")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_supervised_scenarios:
        for item in SUPERVISED_SCENARIOS:
            print(f"{item.id}: {item.title}")
        return 0
    try:
        validate_supervised_args(args)
        runner = AcceptanceRunner(
            project_dir=args.project_dir,
            mode=args.mode,
            env_file=args.env_file,
            dashboard_port=args.dashboard_port,
        )
        runner.prepare_report_directory()
        commit = runner.collect_read_only()
        runner.add_supervised_results(
            selected_scenario=args.supervised_scenario,
            selected_status=args.supervised_result,
        )
        report = runner.report(
            commit=commit,
            supervised_requested=args.supervised_scenario is not None,
        )
        json_path, markdown_path = runner.write_report(report)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Robot Scope acceptance configuration error: {safe_text(exc, fallback='operation failed')}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    print("Summary: " + " ".join(f"{key}={summary[key]}" for key in STATUSES))
    if summary["FAIL"]:
        return 1
    if summary["BLOCKED"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
