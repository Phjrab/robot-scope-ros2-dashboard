#!/usr/bin/env python3
"""Read-only hardware acceptance recorder for Robot Scope.

The default run performs only fixed, bounded observations.  Supervised checks
are records of an operator-controlled procedure; this program never sends a
motion command, starts a service, launches mapping/navigation, clears an
E-stop, or changes a safety limit.
"""

from __future__ import annotations

import argparse
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
        if not health:
            self.add(
                "runtime.go2_connection",
                "BLOCKED",
                "The agent, ROS interface, pinned target, and Go2 reachability are live.",
                "The health snapshot is unavailable.",
                safety_impact="No robot-dependent check may be treated as current.",
            )
            return
        local_ready = bool(health.get("agent_ready")) and bool(
            health.get("ros_interface_ready")
        )
        target_ready = bool(health.get("robot_target_connected")) and bool(
            health.get("target_matches_startup")
        )
        online = bool(health.get("robot_online"))
        if local_ready and target_ready and online:
            status, observed = "PASS", "The pinned Go2 target is reachable and the local ROS interface is ready."
        elif local_ready:
            status, observed = "BLOCKED", "The local agent is ready but the pinned Go2 target is not live."
        else:
            status, observed = "FAIL", "The local agent or required ROS interface is not ready."
        self.add(
            "runtime.go2_connection",
            status,
            "The agent, ROS interface, pinned target, and Go2 reachability are live.",
            observed,
            evidence=(
                f"agent_ready={bool(health.get('agent_ready'))}",
                f"ros_interface_ready={bool(health.get('ros_interface_ready'))}",
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
        self._collect_control()
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
    parser.add_argument("--supervised-scenario", choices=tuple(SCENARIO_BY_ID))
    parser.add_argument("--supervised-result", choices=STATUSES)
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
