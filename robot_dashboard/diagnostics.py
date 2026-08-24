"""Deterministic, bounded, redacted diagnostics bundle construction."""

from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import shutil
import socket
import stat
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping

from .operator_events import OperatorEventTimeline
from .public_diagnostics import public_diagnostic


DIAGNOSTICS_SCHEMA = "robot-scope.diagnostics.v1"
DIAGNOSTICS_MAX_ZIP_BYTES = 2 * 1024 * 1024
DIAGNOSTICS_MAX_UNCOMPRESSED_BYTES = 3 * 1024 * 1024
DIAGNOSTICS_MAX_JSON_BYTES = 256 * 1024
DIAGNOSTICS_MAX_EVENT_LINES = 256
DIAGNOSTICS_MAX_EVENT_LINE_BYTES = 1_024

_HEX_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,64}$")
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{0,64}$")
_ACCEPTANCE_RE = re.compile(r"^acceptance-([0-9]{8}T[0-9]{6}(?:\.[0-9]{1,6})?Z)\.json$")
_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_MAP_ID_RE = re.compile(r"^[0-9a-f]{24}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_TEXT_RE = re.compile(r"^[0-9TZ:+. -]{1,64}$")
_LICENSE_RE = re.compile(r"^[A-Za-z0-9 .()+-]{1,64}$")
_SENSITIVE_PROFILE_KEY_RE = re.compile(
    r"(?:auth|credential|key|password|secret|token)", re.IGNORECASE
)

_BUNDLE_ORDER = (
    "summary.json",
    "versions.json",
    "health.json",
    "ros-graph-summary.json",
    "network-summary.json",
    "mapping-events.jsonl",
    "navigation-events.jsonl",
    "operator-events.jsonl",
    "redaction-report.json",
)


class DiagnosticsUnavailable(RuntimeError):
    """The bounded public bundle could not be produced safely."""


@dataclass(frozen=True)
class DiagnosticsBundle:
    filename: str
    payload: bytes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _object(value: object) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _bounded_number(value: object, *, minimum: float = 0.0, maximum: float = 1e15) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not minimum <= number <= maximum:
        return None
    return round(number, 3)


def _bounded_int(value: object, *, maximum: int = 9_007_199_254_740_991) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(number, maximum))


def _identifier(value: object, *, default: str = "") -> str:
    candidate = str(value or "")[:64]
    return candidate if _IDENTIFIER_RE.fullmatch(candidate) else default


def _timestamp_text(value: object) -> str:
    candidate = str(value or "")[:64]
    return candidate if _TIMESTAMP_TEXT_RE.fullmatch(candidate) else ""


def _profile_fingerprint_projection(value: object, *, depth: int = 0) -> object:
    """Remove credential-bearing keys before hashing the active profile."""

    if depth > 8:
        return None
    if isinstance(value, Mapping):
        result: Dict[str, object] = {}
        for raw_key, raw_value in sorted(value.items(), key=lambda item: str(item[0]))[:256]:
            key = str(raw_key)[:64]
            if not _IDENTIFIER_RE.fullmatch(key) or _SENSITIVE_PROFILE_KEY_RE.search(key):
                continue
            result[key] = _profile_fingerprint_projection(raw_value, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _profile_fingerprint_projection(item, depth=depth + 1)
            for item in list(value)[:256]
        ]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:512]


def _canonical_json(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise DiagnosticsUnavailable("diagnostics projection is not JSON-safe") from exc
    if len(encoded) > DIAGNOSTICS_MAX_JSON_BYTES:
        raise DiagnosticsUnavailable("diagnostics section exceeds size budget")
    return encoded


def _json_lines(values: Iterable[Mapping[str, object]]) -> bytes:
    lines: list[bytes] = []
    for value in list(values)[-DIAGNOSTICS_MAX_EVENT_LINES:]:
        line = _canonical_json(dict(value))
        if len(line) > DIAGNOSTICS_MAX_EVENT_LINE_BYTES:
            continue
        lines.append(line)
    return b"".join(lines)


def _fixed_git_identity(project_dir: Path) -> Dict[str, str]:
    identity = {"commit": "unknown", "tag": ""}
    git = Path("/usr/bin/git")
    if not git.is_file():
        return identity
    commands = (("commit", "rev-parse", "HEAD"), ("tag", "describe", "--tags", "--exact-match"))
    for key, *arguments in commands:
        try:
            result = subprocess.run(
                [str(git), "-C", str(project_dir), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=0.75,
                text=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            )
        except (OSError, subprocess.SubprocessError):
            continue
        value = result.stdout.strip()[:128] if result.returncode == 0 else ""
        if key == "commit" and _HEX_COMMIT_RE.fullmatch(value):
            identity[key] = value
        elif key == "tag" and _TAG_RE.fullmatch(value):
            identity[key] = value
    return identity


def _dependency_revisions(path: Path) -> Dict[str, Dict[str, str]]:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_size > 1024 * 1024:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    repositories = payload.get("repositories", {}) if isinstance(payload, dict) else {}
    result: Dict[str, Dict[str, str]] = {}
    if not isinstance(repositories, dict):
        return result
    for name, raw in sorted(repositories.items())[:32]:
        if not _PROFILE_ID_RE.fullmatch(str(name)) or not isinstance(raw, dict):
            continue
        commit = str(raw.get("commit", ""))
        submodule = str(raw.get("submodule_commit", ""))
        license_name = str(raw.get("license", ""))[:64]
        if not _HEX_COMMIT_RE.fullmatch(commit):
            continue
        if not _LICENSE_RE.fullmatch(license_name):
            license_name = "unknown"
        entry = {"commit": commit, "license": license_name}
        if _HEX_COMMIT_RE.fullmatch(submodule):
            entry["submodule_commit"] = submodule
        result[str(name)] = entry
    return result


def _acceptance_reference(root: Path) -> Dict[str, str] | None:
    try:
        if root.is_symlink() or not root.is_dir():
            return None
        candidates = []
        for path in root.iterdir():
            match = _ACCEPTANCE_RE.fullmatch(path.name)
            if not match:
                continue
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and info.st_size <= 1024 * 1024:
                candidates.append((match.group(1), path.stem))
        if not candidates:
            return None
        stamp, report_id = max(candidates)
        return {"report_id": report_id, "timestamp": stamp}
    except OSError:
        return None


def _health_projection(health: Mapping[str, object], control: Mapping[str, object]) -> Dict[str, Any]:
    bridge = _object(control.get("bridge"))
    return {
        "agent_ready": health.get("agent_ready") is True,
        "robot_target_connected": health.get("robot_target_connected") is True,
        "robot_online": health.get("robot_online") is True,
        "ros_interface_ready": health.get("ros_interface_ready") is True,
        "offline_viewer": health.get("ros_offline_viewer") is True,
        "robot_type": _identifier(health.get("robot_type", "")),
        "target_matches_startup": health.get("target_matches_startup") is True,
        "restart_required": health.get("restart_required") is True,
        "topic_count": _bounded_int(health.get("topic_count"), maximum=100_000),
        "last_error": public_diagnostic(health.get("last_error", "")),
        "control_bridge": {
            "authenticated_ready": bridge.get("authenticated") is True and bridge.get("ready") is True,
            "status_age_s": _bounded_number(bridge.get("status_age_s"), maximum=86_400.0),
        },
    }


def _source_projection(sources: Mapping[str, object]) -> Dict[str, Any]:
    selected = _object(sources.get("selected"))
    descriptors = _object(sources.get("selected_descriptors"))
    result: Dict[str, Any] = {}
    for category in ("camera", "pointcloud", "odometry", "occupancy_grid"):
        value = selected.get(category)
        descriptor = _object(descriptors.get(category))
        result[category] = {
            "selected": bool(value),
            "sensor_id": _identifier(descriptor.get("sensor_id", "")),
            "pipeline_stage": _identifier(descriptor.get("pipeline_stage", "")),
            "state": _identifier(
                descriptor.get("state", descriptor.get("sample_state", ""))
            ),
            "hz": _bounded_number(descriptor.get("hz"), maximum=100_000.0),
            "age_s": _bounded_number(descriptor.get("age_s"), maximum=86_400.0),
        }
    return result


def _graph_projection(topics: object) -> Dict[str, Any]:
    rows = []
    values = topics if isinstance(topics, list) else []
    for raw in values[:512]:
        item = _object(raw)
        rows.append({
            "category": _identifier(item.get("category"), default="unknown"),
            "publishers": _bounded_int(item.get("publishers"), maximum=1_000),
            "subscribers": _bounded_int(item.get("subscribers"), maximum=1_000),
            "selected": item.get("selected") is True,
            "state": _identifier(item.get("state"), default="waiting"),
            "hz": _bounded_number(item.get("hz"), maximum=100_000.0),
            "age_s": _bounded_number(item.get("age_s"), maximum=86_400.0),
        })
    cardinality: Dict[str, int] = {}
    for row in rows:
        category = row["category"]
        cardinality[category] = cardinality.get(category, 0) + 1
    return {"topic_count": len(rows), "category_cardinality": cardinality, "topics": rows}


def _runtime_events(snapshot: Mapping[str, object], *, source: str) -> list[Dict[str, Any]]:
    values = snapshot.get("logs") if source == "mapping" else snapshot.get("entries")
    if not isinstance(values, list):
        return []
    result = []
    for raw in values[-DIAGNOSTICS_MAX_EVENT_LINES:]:
        entry = _object(raw)
        message = public_diagnostic(entry.get("message", ""))
        result.append({
            "seq": _bounded_int(entry.get("seq")),
            "timestamp": _timestamp_text(
                entry.get("timestamp", entry.get("time", ""))
            ),
            "source": source,
            "phase": _identifier(entry.get("phase", entry.get("source", ""))),
            "message": message,
        })
    return result


class DiagnosticsBundleService:
    """Build one read-only bundle from bounded public snapshot providers."""

    def __init__(
        self,
        *,
        project_dir: Path,
        profile_provider: Callable[[], Mapping[str, object]],
        health_provider: Callable[[], Mapping[str, object]],
        topics_provider: Callable[[], object],
        sources_provider: Callable[[], Mapping[str, object]],
        control_provider: Callable[[], Mapping[str, object]],
        mapping_provider: Callable[[], Mapping[str, object]],
        navigation_provider: Callable[[], Mapping[str, object]],
        navigation_events_provider: Callable[[], Mapping[str, object]],
        dataset_provider: Callable[[], Mapping[str, object]],
        operator_events: OperatorEventTimeline,
        disk_roots: Mapping[str, Path],
        clock: Callable[[], datetime] = _utc_now,
        identity_provider: Callable[[], Mapping[str, str]] | None = None,
        disk_usage_provider: Callable[[Path], object] = shutil.disk_usage,
    ) -> None:
        self._project_dir = Path(project_dir).resolve()
        self._profile_provider = profile_provider
        self._health_provider = health_provider
        self._topics_provider = topics_provider
        self._sources_provider = sources_provider
        self._control_provider = control_provider
        self._mapping_provider = mapping_provider
        self._navigation_provider = navigation_provider
        self._navigation_events_provider = navigation_events_provider
        self._dataset_provider = dataset_provider
        self._operator_events = operator_events
        self._disk_roots = {str(key): Path(value) for key, value in disk_roots.items()}
        self._clock = clock
        self._identity_provider = identity_provider or (lambda: _fixed_git_identity(self._project_dir))
        self._disk_usage_provider = disk_usage_provider

    def _disk_summary(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for label, root in sorted(self._disk_roots.items())[:8]:
            if not _PROFILE_ID_RE.fullmatch(label):
                continue
            try:
                usage = self._disk_usage_provider(root)
                total = int(getattr(usage, "total"))
                used = int(getattr(usage, "used"))
                free = int(getattr(usage, "free"))
            except (AttributeError, OSError, TypeError, ValueError):
                result[label] = {"available": False}
                continue
            result[label] = {
                "available": True,
                "total_bytes": max(0, total),
                "used_bytes": max(0, used),
                "free_bytes": max(0, free),
            }
        return result

    @staticmethod
    def _network_summary(health: Mapping[str, object]) -> Dict[str, Any]:
        interfaces = []
        try:
            interfaces = sorted(
                name for _, name in socket.if_nameindex() if _INTERFACE_RE.fullmatch(name)
            )[:16]
        except OSError:
            pass
        transport = _object(health.get("ros_transport"))
        route_state = (
            "reachable"
            if health.get("robot_online") is True
            else "unreachable"
            if health.get("robot_target_connected") is True
            else "not_selected"
        )
        return {
            "interfaces": interfaces,
            "ros_interface_ready": health.get("ros_interface_ready") is True,
            "offline_viewer": health.get("ros_offline_viewer") is True,
            "interface_configured": bool(transport.get("interface")),
            "transport_mode": _identifier(transport.get("mode"), default="unknown"),
            "route": {"state": route_state, "address": "withheld"},
        }

    def build(self) -> DiagnosticsBundle:
        try:
            return self._build()
        except DiagnosticsUnavailable:
            raise
        except Exception as exc:
            raise DiagnosticsUnavailable("diagnostics snapshot unavailable") from exc

    def _build(self) -> DiagnosticsBundle:
        generated = self._clock()
        health = _object(self._health_provider())
        control = _object(self._control_provider())
        mapping = _object(self._mapping_provider())
        navigation = _object(self._navigation_provider())
        dataset = _object(self._dataset_provider())
        sources = _object(self._sources_provider())
        profile = _object(self._profile_provider())
        profile_hash = hashlib.sha256(
            _canonical_json(_profile_fingerprint_projection(profile))
        ).hexdigest()
        identity = _object(self._identity_provider())
        commit = str(identity.get("commit", "unknown"))
        tag = str(identity.get("tag", ""))
        if commit != "unknown" and not _HEX_COMMIT_RE.fullmatch(commit):
            commit = "unknown"
        if tag and not _TAG_RE.fullmatch(tag):
            tag = ""
        profile_id = str(profile.get("robot_type", profile.get("name", "")))[:64]
        if not _PROFILE_ID_RE.fullmatch(profile_id):
            profile_id = ""
        acceptance = _acceptance_reference(self._project_dir / "runtime" / "reports")
        mapping_pipeline = _object(mapping.get("pipeline"))
        navigation_pipeline = _object(navigation.get("pipeline"))
        map_info = _object(navigation.get("map"))
        dataset_queue = _object(dataset.get("queue"))
        summary = {
            "schema": DIAGNOSTICS_SCHEMA,
            "generated_at": _timestamp(generated),
            "robot_scope": {"commit": commit, "tag": tag},
            "profile": {"id": profile_id, "sha256": profile_hash},
            "states": {
                "mapping": _identifier(mapping_pipeline.get("state"), default="unknown"),
                "navigation": _identifier(
                    navigation_pipeline.get("state"), default="unknown"
                ),
                "dataset": _identifier(dataset.get("state"), default="unknown"),
            },
            "active_map": {
                "id": (
                    str(map_info.get("id"))
                    if _MAP_ID_RE.fullmatch(str(map_info.get("id", "")))
                    else ""
                ),
                "revision": (
                    str(map_info.get("revision"))
                    if _REVISION_RE.fullmatch(str(map_info.get("revision", "")))
                    else ""
                ),
            },
            "dataset": {
                "saved": _bounded_int(dataset.get("saved")),
                "dropped": _bounded_int(dataset.get("dropped")),
                "queue_depth": _bounded_int(dataset_queue.get("depth")),
                "free_bytes": _bounded_int(dataset.get("free_bytes")),
                "minimum_free_bytes": _bounded_int(
                    dataset.get("minimum_free_bytes")
                ),
            },
            "disk": self._disk_summary(),
            "selected_sources": _source_projection(sources),
            "acceptance_report": acceptance,
        }
        ros_distro = _identifier(health.get("ros_distro"), default="unknown")
        dependency_manifest = (
            self._project_dir / "config" / f"ros_dependencies_{ros_distro}.json"
        )
        versions = {
            "schema": DIAGNOSTICS_SCHEMA,
            "robot_scope": {"commit": commit, "tag": tag},
            "python": platform.python_version(),
            "ros_distro": ros_distro,
            "rmw": _identifier(health.get("rmw"), default="unknown"),
            "external_dependencies": _dependency_revisions(
                dependency_manifest
            ),
        }
        operator_entries = self._operator_events.recent(DIAGNOSTICS_MAX_EVENT_LINES)
        sections: Dict[str, bytes] = {
            "summary.json": _canonical_json(summary),
            "versions.json": _canonical_json(versions),
            "health.json": _canonical_json(_health_projection(health, control)),
            "ros-graph-summary.json": _canonical_json(_graph_projection(self._topics_provider())),
            "network-summary.json": _canonical_json(self._network_summary(health)),
            "mapping-events.jsonl": _json_lines(_runtime_events(mapping, source="mapping")),
            "navigation-events.jsonl": _json_lines(
                _runtime_events(_object(self._navigation_events_provider()), source="navigation")
            ),
            "operator-events.jsonl": _json_lines(operator_entries),
        }
        sections["redaction-report.json"] = _canonical_json({
            "schema": DIAGNOSTICS_SCHEMA,
            "policy": "public_diagnostic.v1",
            "entries": {name: len(payload) for name, payload in sorted(sections.items())},
            "omitted": [
                "absolute_paths", "authorization", "bridge_key", "credentials",
                "environment", "ip_addresses", "raw_argv", "raw_process_output",
                "raw_ros_messages", "ssh_keys",
            ],
            "operator_identity": "browser session only; no verified human identity",
        })
        if tuple(sections) != _BUNDLE_ORDER:
            sections = {name: sections[name] for name in _BUNDLE_ORDER}
        if sum(len(value) for value in sections.values()) > DIAGNOSTICS_MAX_UNCOMPRESSED_BYTES:
            raise DiagnosticsUnavailable("diagnostics bundle exceeds uncompressed budget")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in _BUNDLE_ORDER:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                archive.writestr(info, sections[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        payload = output.getvalue()
        if len(payload) > DIAGNOSTICS_MAX_ZIP_BYTES:
            raise DiagnosticsUnavailable("diagnostics bundle exceeds compressed budget")
        filename_stamp = generated.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return DiagnosticsBundle(
            filename=f"robot-scope-diagnostics-{filename_stamp}.zip",
            payload=payload,
        )
