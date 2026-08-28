"""Server-authoritative, revision-pinned annotation mission sequencing."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import stat
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol


MISSION_SCHEMA_VERSION = 1
MISSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAP_ID_RE = re.compile(r"^[0-9a-f]{24}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
GOAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MISSION_STATES = frozenset(
    {
        "idle",
        "ready",
        "starting",
        "running",
        "pausing",
        "paused",
        "retrying",
        "skipping",
        "canceling",
        "completed",
        "failed",
    }
)
ACTIVE_STATES = frozenset(
    {"starting", "running", "pausing", "paused", "retrying", "skipping", "canceling"}
)
GOAL_ACTIVE_STATES = frozenset({"pending", "active", "canceling"})
GOAL_TERMINAL_STATES = frozenset({"idle", "succeeded", "failed", "canceled"})
MAX_MISSIONS = 32
MAX_WAYPOINTS = 32
MAX_LABEL_CHARS = 64
MAX_HOLD_SECONDS = 300.0
MAX_LOG_ENTRIES = 200
MAX_STATE_BYTES = 512 * 1024


class MissionError(RuntimeError):
    """Base mission error with a bounded public message."""


class MissionNotFound(MissionError):
    pass


class MissionConflict(MissionError):
    pass


class MissionValidationError(MissionError):
    pass


class MissionUnavailable(MissionError):
    pass


class NavigationPort(Protocol):
    def view(self) -> dict[str, Any]: ...

    async def send_annotation_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        annotation_revision: str,
        annotation_id: str,
        confirmed: bool,
    ) -> dict[str, Any]: ...

    async def cancel_goal(self, *, goal_id: str) -> dict[str, Any]: ...


class SavedMapsPort(Protocol):
    def annotations(self, map_id: str) -> dict[str, Any]: ...


def _timestamp(epoch: float | None = None) -> str:
    current = datetime.fromtimestamp(epoch or time.time(), timezone.utc)
    return current.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _label(value: object, field: str = "mission label") -> str:
    if not isinstance(value, str):
        raise MissionValidationError(f"{field} must be text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > MAX_LABEL_CHARS:
        raise MissionValidationError(f"{field} must contain 1 to {MAX_LABEL_CHARS} characters")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise MissionValidationError(f"{field} contains unsupported characters")
    return normalized


def _bounded_token(value: object, field: str, maximum: int) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not re.fullmatch(rf"[a-z][a-z0-9_]{{0,{maximum - 1}}}", value):
        raise MissionUnavailable(f"mission {field} is invalid")
    return value


def _bounded_timestamp(value: object, field: str) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > 32 or any(
        unicodedata.category(character).startswith("C") for character in value
    ):
        raise MissionUnavailable(f"mission {field} is invalid")
    return value


def _bounded_number(value: object, field: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionUnavailable(f"mission {field} is invalid")
    number = float(value)
    if not minimum <= number <= 10_000_000_000.0:
        raise MissionUnavailable(f"mission {field} is invalid")
    return number


def _safe_root(root: Path) -> Path:
    requested = Path(root)
    if not requested.is_absolute():
        raise MissionUnavailable("mission state root must be absolute")
    normalized = Path(os.path.abspath(str(requested)))
    if normalized == Path("/"):
        raise MissionUnavailable("mission state root cannot be filesystem root")
    probe = normalized
    missing: list[Path] = []
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            raise MissionUnavailable("mission state root has no existing parent")
        probe = probe.parent
    if probe.is_symlink() or probe.resolve(strict=True) != probe:
        raise MissionUnavailable("mission state root cannot contain symlinks")
    for path in reversed(missing):
        path.mkdir(mode=0o700)
    if normalized.is_symlink() or normalized.resolve(strict=True) != normalized:
        raise MissionUnavailable("mission state root cannot contain symlinks")
    info = normalized.stat()
    if info.st_uid != os.geteuid():
        raise MissionUnavailable("mission state root must be owned by the service user")
    if missing:
        os.chmod(normalized, 0o700)
    elif stat.S_IMODE(info.st_mode) != 0o700:
        raise MissionUnavailable("existing mission state root must have mode 0700")
    return normalized


class MissionStateStore:
    """One private, bounded, atomically replaced mission state document."""

    def __init__(self, root: Path) -> None:
        self.root = _safe_root(Path(root))
        self.path = self.root / "missions.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": MISSION_SCHEMA_VERSION, "missions": [], "active_mission_id": None}
        if self.path.is_symlink():
            raise MissionUnavailable("mission state file cannot be a symlink")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise MissionUnavailable("mission state file must be a private regular file")
        if info.st_size > MAX_STATE_BYTES:
            raise MissionUnavailable("mission state file exceeds the bounded size")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MissionUnavailable("mission state file is unreadable") from exc
        if not isinstance(value, dict) or set(value) != {"schema_version", "missions", "active_mission_id"}:
            raise MissionUnavailable("mission state document is invalid")
        return value

    def save(self, document: Mapping[str, Any]) -> None:
        encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_STATE_BYTES:
            raise MissionUnavailable("mission state exceeds the bounded size")
        temporary = self.root / f".missions.{secrets.token_hex(8)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


class MissionCoordinator:
    """Own exactly one mission transaction while delegating every goal to Nav."""

    def __init__(
        self,
        navigation: NavigationPort,
        saved_maps: SavedMapsPort,
        state_root: Path,
        *,
        poll_interval_s: float = 0.25,
        cancel_timeout_s: float = 5.0,
        now: Any = time.time,
        monotonic: Any = time.monotonic,
    ) -> None:
        self._navigation = navigation
        self._saved_maps = saved_maps
        self._store: MissionStateStore | None = None
        self._storage_error = ""
        try:
            self._store = MissionStateStore(Path(state_root))
            document = self._store.load()
            self._missions, self._active_id = self._validate_document(document)
        except MissionError:
            self._missions, self._active_id = [], None
            self._storage_error = "mission state storage is unavailable"
        self._poll_interval_s = max(0.05, min(float(poll_interval_s), 2.0))
        self._cancel_timeout_s = max(0.1, min(float(cancel_timeout_s), 15.0))
        self._now = now
        self._monotonic = monotonic
        self._operation_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._generation = 0
        self._recover_interrupted()

    @staticmethod
    def _normalize_waypoint(value: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {"annotation_id", "arrival_tolerance", "hold_seconds", "requires_operator_confirmation", "label", "status", "goal_id", "attempts"}
        if not isinstance(value, Mapping) or set(value) - allowed:
            raise MissionValidationError("mission waypoint contains unsupported fields")
        annotation_id = value.get("annotation_id")
        if not isinstance(annotation_id, str) or not MAP_ID_RE.fullmatch(annotation_id):
            raise MissionValidationError("mission waypoint annotation_id is invalid")
        tolerance = value.get("arrival_tolerance")
        if tolerance is not None:
            if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not 0.05 <= float(tolerance) <= 2.0:
                raise MissionValidationError("arrival_tolerance is outside the supported range")
            tolerance = round(float(tolerance), 3)
        hold = value.get("hold_seconds", 0.0)
        if isinstance(hold, bool) or not isinstance(hold, (int, float)) or not 0.0 <= float(hold) <= MAX_HOLD_SECONDS:
            raise MissionValidationError("hold_seconds is outside the supported range")
        confirmation = value.get("requires_operator_confirmation", False)
        if not isinstance(confirmation, bool):
            raise MissionValidationError("requires_operator_confirmation must be boolean")
        return {
            "annotation_id": annotation_id,
            "arrival_tolerance": tolerance,
            "hold_seconds": round(float(hold), 3),
            "requires_operator_confirmation": confirmation,
            "label": _label(value.get("label", "Waypoint"), "waypoint label"),
            "status": "pending",
            "goal_id": None,
            "attempts": 0,
        }

    def _validate_document(self, document: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        if document.get("schema_version") != MISSION_SCHEMA_VERSION:
            raise MissionUnavailable("mission state schema is unsupported")
        raw_missions = document.get("missions")
        if not isinstance(raw_missions, list) or len(raw_missions) > MAX_MISSIONS:
            raise MissionUnavailable("mission state catalog is invalid")
        missions: list[dict[str, Any]] = []
        identifiers: set[str] = set()
        for raw in raw_missions:
            if not isinstance(raw, dict):
                raise MissionUnavailable("mission state entry is invalid")
            identifier = raw.get("id")
            state = raw.get("state")
            if not isinstance(identifier, str) or not MISSION_ID_RE.fullmatch(identifier) or identifier in identifiers or state not in MISSION_STATES:
                raise MissionUnavailable("mission state identity is invalid")
            if not isinstance(raw.get("map_id"), str) or not MAP_ID_RE.fullmatch(raw["map_id"]):
                raise MissionUnavailable("mission map pin is invalid")
            if any(not isinstance(raw.get(key), str) or not REVISION_RE.fullmatch(raw[key]) for key in ("map_revision", "annotation_revision")):
                raise MissionUnavailable("mission revision pin is invalid")
            raw_waypoints = raw.get("waypoints")
            if not isinstance(raw_waypoints, list) or not 1 <= len(raw_waypoints) <= MAX_WAYPOINTS:
                raise MissionUnavailable("mission waypoint catalog is invalid")
            waypoints = []
            for waypoint in raw_waypoints:
                normalized = self._normalize_waypoint(waypoint)
                status_value = waypoint.get("status", "pending")
                goal_id = waypoint.get("goal_id")
                attempts = waypoint.get("attempts", 0)
                if status_value not in {"pending", "running", "completed", "skipped", "failed"}:
                    raise MissionUnavailable("mission waypoint state is invalid")
                if goal_id is not None and (not isinstance(goal_id, str) or not GOAL_ID_RE.fullmatch(goal_id)):
                    raise MissionUnavailable("mission waypoint goal identity is invalid")
                if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= 1000:
                    raise MissionUnavailable("mission waypoint attempts are invalid")
                normalized.update(status=status_value, goal_id=goal_id, attempts=attempts)
                waypoints.append(normalized)
            current_index = raw.get("current_index", 0)
            if isinstance(current_index, bool) or not isinstance(current_index, int) or not 0 <= current_index <= len(waypoints):
                raise MissionUnavailable("mission waypoint cursor is invalid")
            identifiers.add(identifier)
            raw_logs = raw.get("logs") or []
            if not isinstance(raw_logs, list) or len(raw_logs) > MAX_LOG_ENTRIES:
                raise MissionUnavailable("mission log is invalid")
            logs: list[dict[str, Any]] = []
            for entry in raw_logs:
                if not isinstance(entry, dict) or set(entry) != {"seq", "timestamp", "event", "waypoint_index"}:
                    raise MissionUnavailable("mission log entry is invalid")
                sequence = entry.get("seq")
                waypoint_index = entry.get("waypoint_index")
                if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                    raise MissionUnavailable("mission log sequence is invalid")
                if waypoint_index is not None and (isinstance(waypoint_index, bool) or not isinstance(waypoint_index, int) or not 0 <= waypoint_index < len(waypoints)):
                    raise MissionUnavailable("mission log waypoint is invalid")
                event = entry.get("event")
                timestamp = entry.get("timestamp")
                if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", event) or not isinstance(timestamp, str) or len(timestamp) > 32:
                    raise MissionUnavailable("mission log value is invalid")
                logs.append({"seq": sequence, "timestamp": timestamp, "event": event, "waypoint_index": waypoint_index})
            log_seq = raw.get("log_seq", 0)
            if isinstance(log_seq, bool) or not isinstance(log_seq, int) or not 0 <= log_seq <= 1_000_000:
                raise MissionUnavailable("mission log cursor is invalid")
            missions.append(
                {
                    "id": identifier,
                    "label": _label(raw.get("label")),
                    "map_id": raw["map_id"],
                    "map_revision": raw["map_revision"],
                    "annotation_revision": raw["annotation_revision"],
                    "state": state,
                    "outcome": _bounded_token(raw.get("outcome"), "outcome", 32),
                    "error": _bounded_token(raw.get("error"), "error", 96),
                    "created_at": _bounded_timestamp(raw.get("created_at"), "created timestamp"),
                    "started_at": _bounded_timestamp(raw.get("started_at"), "started timestamp"),
                    "completed_at": _bounded_timestamp(raw.get("completed_at"), "completed timestamp"),
                    "started_epoch": _bounded_number(raw.get("started_epoch", 0.0), "started epoch"),
                    "completed_epoch": _bounded_number(raw.get("completed_epoch", 0.0), "completed epoch"),
                    "current_index": current_index,
                    "waypoints": waypoints,
                    "hold_until_epoch": _bounded_number(raw.get("hold_until_epoch", 0.0), "hold deadline"),
                    "pause_reason": _bounded_token(raw.get("pause_reason"), "pause reason", 48),
                    "logs": logs,
                    "log_seq": log_seq,
                }
            )
        active_id = document.get("active_mission_id")
        if active_id is not None and active_id not in identifiers:
            raise MissionUnavailable("active mission identity is invalid")
        if active_id is not None and not any(mission["id"] == active_id and mission["state"] in ACTIVE_STATES for mission in missions):
            raise MissionUnavailable("active mission state is invalid")
        return missions, active_id

    def _recover_interrupted(self) -> None:
        changed = False
        for mission in self._missions:
            if mission["state"] in ACTIVE_STATES and mission["state"] != "paused":
                mission.update(state="failed", outcome="interrupted", error="server_restart_interrupted", completed_at=_timestamp(self._now()), completed_epoch=self._now())
                for waypoint in mission["waypoints"]:
                    if waypoint["status"] == "running":
                        waypoint.update(status="failed", goal_id=None)
                self._record(mission, "mission_interrupted")
                changed = True
        if self._active_id and not any(m["id"] == self._active_id and m["state"] == "paused" for m in self._missions):
            self._active_id = None
            changed = True
        if changed:
            self._save()

    def _document(self) -> dict[str, Any]:
        return {"schema_version": MISSION_SCHEMA_VERSION, "missions": self._missions, "active_mission_id": self._active_id}

    def _save(self) -> None:
        if self._storage_error or self._store is None:
            raise MissionUnavailable(self._storage_error or "mission state storage is unavailable")
        self._store.save(self._document())

    def _record(self, mission: dict[str, Any], event: str, waypoint_index: int | None = None) -> None:
        mission["log_seq"] += 1
        mission["logs"].append({"seq": mission["log_seq"], "timestamp": _timestamp(self._now()), "event": event[:48], "waypoint_index": waypoint_index})
        mission["logs"] = mission["logs"][-MAX_LOG_ENTRIES:]

    def _mission(self, mission_id: str) -> dict[str, Any]:
        if not isinstance(mission_id, str) or not MISSION_ID_RE.fullmatch(mission_id):
            raise MissionNotFound("mission was not found")
        for mission in self._missions:
            if mission["id"] == mission_id:
                return mission
        raise MissionNotFound("mission was not found")

    def _public(self, mission: Mapping[str, Any]) -> dict[str, Any]:
        started_epoch = float(mission.get("started_epoch") or 0.0)
        terminal = mission.get("state") in {"completed", "failed"}
        elapsed = max(0.0, (float(mission.get("completed_epoch") or self._now()) - started_epoch)) if started_epoch else 0.0
        waypoints = [dict(item) for item in mission["waypoints"]]
        completed = sum(item["status"] == "completed" for item in waypoints)
        return {
            "id": mission["id"], "label": mission["label"], "map_id": mission["map_id"],
            "map_revision": mission["map_revision"], "annotation_revision": mission["annotation_revision"],
            "state": mission["state"], "outcome": mission.get("outcome") or None, "error": mission.get("error") or None,
            "created_at": mission["created_at"], "started_at": mission.get("started_at") or None,
            "completed_at": mission.get("completed_at") or None, "elapsed_seconds": round(elapsed, 3),
            "current_index": mission["current_index"], "completed_count": completed,
            "remaining_count": max(0, len(waypoints) - completed - sum(item["status"] == "skipped" for item in waypoints)),
            "current_waypoint": waypoints[mission["current_index"]] if mission["current_index"] < len(waypoints) else None,
            "waypoints": waypoints, "pause_reason": mission.get("pause_reason") or None,
            "hold_remaining": round(max(0.0, float(mission.get("hold_until_epoch") or 0.0) - self._now()), 3),
            "logs": [dict(entry) for entry in mission["logs"][-MAX_LOG_ENTRIES:]],
            "ownership_active": mission["id"] == self._active_id and mission["state"] in ACTIVE_STATES,
            "terminal": terminal,
        }

    def snapshot(self, mission_id: str | None = None) -> dict[str, Any]:
        if mission_id is not None:
            return {"available": not bool(self._storage_error), "mission": self._public(self._mission(mission_id)), "limits": self.limits()}
        return {
            "available": not bool(self._storage_error), "error": self._storage_error or None,
            "active_mission_id": self._active_id,
            "missions": [self._public(mission) for mission in reversed(self._missions)], "limits": self.limits(),
        }

    @staticmethod
    def limits() -> dict[str, Any]:
        return {"max_missions": MAX_MISSIONS, "max_waypoints": MAX_WAYPOINTS, "max_label_chars": MAX_LABEL_CHARS, "max_hold_seconds": MAX_HOLD_SECONDS, "max_log_entries": MAX_LOG_ENTRIES}

    def blocks_navigation_goal(self) -> bool:
        return self._active_id is not None

    async def _validated_annotations(self, mission: Mapping[str, Any]) -> dict[str, Any]:
        try:
            document = await asyncio.to_thread(self._saved_maps.annotations, mission["map_id"])
        except Exception as exc:
            raise MissionConflict("mission map annotations are unavailable") from exc
        if document.get("map_id") != mission["map_id"] or document.get("map_revision") != mission["map_revision"] or document.get("annotation_revision") != mission["annotation_revision"]:
            raise MissionConflict("mission map or annotations changed; recreate the mission")
        available = {item.get("id") for item in document.get("points", []) if item.get("type") in {"HOME", "POI", "DOCK", "INSPECTION_POINT"}}
        if any(item["annotation_id"] not in available for item in mission["waypoints"]):
            raise MissionConflict("mission waypoint annotation is no longer available")
        return document

    async def create(self, *, label: str, map_id: str, map_revision: str, annotation_revision: str, waypoints: list[Mapping[str, Any]]) -> dict[str, Any]:
        async with self._operation_lock:
            if len(self._missions) >= MAX_MISSIONS:
                raise MissionConflict("mission catalog limit reached")
            if not isinstance(map_id, str) or not MAP_ID_RE.fullmatch(map_id) or not isinstance(map_revision, str) or not REVISION_RE.fullmatch(map_revision) or not isinstance(annotation_revision, str) or not REVISION_RE.fullmatch(annotation_revision):
                raise MissionValidationError("mission revision pins are invalid")
            if not isinstance(waypoints, list) or not 1 <= len(waypoints) <= MAX_WAYPOINTS:
                raise MissionValidationError("mission must contain 1 to 32 waypoints")
            mission = {
                "id": secrets.token_hex(16), "label": _label(label), "map_id": map_id, "map_revision": map_revision,
                "annotation_revision": annotation_revision, "state": "ready", "outcome": "", "error": "",
                "created_at": _timestamp(self._now()), "started_at": "", "completed_at": "", "started_epoch": 0.0, "completed_epoch": 0.0,
                "current_index": 0, "waypoints": [self._normalize_waypoint(item) for item in waypoints],
                "hold_until_epoch": 0.0, "pause_reason": "", "logs": [], "log_seq": 0,
            }
            await self._validated_annotations(mission)
            self._record(mission, "mission_created")
            self._missions.append(mission)
            self._save()
            return {"mission": self._public(mission)}

    def _navigation_ready(self, mission: Mapping[str, Any]) -> dict[str, Any]:
        navigation = self._navigation.view()
        pipeline = navigation.get("pipeline") if isinstance(navigation.get("pipeline"), Mapping) else {}
        nav_map = navigation.get("map") if isinstance(navigation.get("map"), Mapping) else {}
        localization = navigation.get("localization") if isinstance(navigation.get("localization"), Mapping) else {}
        safety = navigation.get("safety") if isinstance(navigation.get("safety"), Mapping) else {}
        goal = navigation.get("goal") if isinstance(navigation.get("goal"), Mapping) else {}
        if pipeline.get("state") != "running" or nav_map.get("id") != mission["map_id"] or nav_map.get("revision") != mission["map_revision"]:
            raise MissionConflict("navigation is not running on the mission map revision")
        if localization.get("state") != "localized" or safety.get("can_send_goal") is not True:
            raise MissionConflict("navigation localization is not ready for the mission")
        if str(goal.get("state") or "idle") not in GOAL_TERMINAL_STATES:
            raise MissionConflict("another navigation goal is active")
        return navigation

    async def _dispatch_current_locked(self, mission: dict[str, Any], *, operator_confirmed: bool) -> None:
        if mission["current_index"] >= len(mission["waypoints"]):
            self._complete_locked(mission)
            return
        waypoint = mission["waypoints"][mission["current_index"]]
        if waypoint["requires_operator_confirmation"] and not operator_confirmed:
            mission.update(state="paused", pause_reason="operator_confirmation", hold_until_epoch=0.0)
            self._record(mission, "operator_confirmation_required", mission["current_index"])
            self._save()
            return
        try:
            await self._validated_annotations(mission)
            self._navigation_ready(mission)
        except Exception as exc:
            waypoint.update(status="failed", goal_id=None)
            mission.update(state="failed", outcome="goal_start_failed", error="waypoint_preflight_failed", completed_at=_timestamp(self._now()), completed_epoch=self._now())
            self._active_id = None
            self._record(mission, "waypoint_preflight_failed", mission["current_index"])
            self._save()
            if isinstance(exc, MissionError):
                raise
            raise MissionConflict("mission waypoint preflight failed") from exc
        waypoint.update(status="running", goal_id=None, attempts=waypoint["attempts"] + 1)
        mission.update(state="running", pause_reason="", error="", outcome="", hold_until_epoch=0.0)
        self._record(mission, "waypoint_dispatching", mission["current_index"])
        self._save()
        try:
            response = await self._navigation.send_annotation_goal(
                map_id=mission["map_id"], map_revision=mission["map_revision"], annotation_revision=mission["annotation_revision"],
                annotation_id=waypoint["annotation_id"], confirmed=True,
            )
            goal = ((response.get("navigation") or {}).get("goal") or {}) if isinstance(response, Mapping) else {}
            goal_id = goal.get("goal_id")
            if goal.get("state") not in GOAL_ACTIVE_STATES or not isinstance(goal_id, str) or not GOAL_ID_RE.fullmatch(goal_id):
                raise MissionConflict("navigation did not publish one owned goal")
            waypoint["goal_id"] = goal_id
            self._record(mission, "waypoint_started", mission["current_index"])
            self._save()
        except Exception as exc:
            waypoint.update(status="failed", goal_id=None)
            mission.update(state="failed", outcome="goal_start_failed", error="waypoint_goal_start_failed", completed_at=_timestamp(self._now()), completed_epoch=self._now())
            self._active_id = None
            self._record(mission, "waypoint_start_failed", mission["current_index"])
            self._save()
            if isinstance(exc, MissionError):
                raise
            raise MissionConflict("mission waypoint could not start") from exc

    def _complete_locked(self, mission: dict[str, Any]) -> None:
        mission.update(state="completed", outcome="completed", error="", completed_at=_timestamp(self._now()), completed_epoch=self._now(), hold_until_epoch=0.0, pause_reason="")
        self._active_id = None
        self._record(mission, "mission_completed")
        self._save()

    def _start_monitor_locked(self, mission: dict[str, Any]) -> None:
        self._generation += 1
        generation = self._generation
        self._task = asyncio.create_task(self._monitor(mission["id"], generation), name="mission-waypoint-monitor")

    async def start(self, mission_id: str) -> dict[str, Any]:
        async with self._operation_lock:
            mission = self._mission(mission_id)
            if mission["state"] in {"starting", "running"} and self._active_id == mission_id:
                return {"mission": self._public(mission)}
            if mission["state"] != "ready":
                raise MissionConflict("only a ready mission can start")
            if self._active_id and self._active_id != mission_id:
                raise MissionConflict("another mission owns navigation")
            self._active_id = mission_id
            mission.update(state="starting", started_at=_timestamp(self._now()), started_epoch=self._now(), completed_at="", completed_epoch=0.0, error="", outcome="")
            self._record(mission, "mission_starting")
            self._save()
            await self._dispatch_current_locked(mission, operator_confirmed=True)
            if mission["state"] == "running":
                self._start_monitor_locked(mission)
            return {"mission": self._public(mission)}

    async def _cancel_current_locked(self, mission: dict[str, Any]) -> str:
        waypoint = mission["waypoints"][mission["current_index"]] if mission["current_index"] < len(mission["waypoints"]) else None
        goal_id = waypoint.get("goal_id") if waypoint else None
        if not goal_id:
            return "idle"
        navigation = self._navigation.view()
        goal = navigation.get("goal") if isinstance(navigation.get("goal"), Mapping) else {}
        if goal.get("goal_id") not in {None, goal_id} and goal.get("state") in GOAL_ACTIVE_STATES:
            raise MissionConflict("navigation goal ownership changed during mission cleanup")
        if goal.get("goal_id") == goal_id and goal.get("state") in GOAL_ACTIVE_STATES:
            await self._navigation.cancel_goal(goal_id=goal_id)
        deadline = self._monotonic() + self._cancel_timeout_s
        while self._monotonic() <= deadline:
            navigation = self._navigation.view()
            goal = navigation.get("goal") if isinstance(navigation.get("goal"), Mapping) else {}
            state = str(goal.get("state") or "idle")
            if goal.get("goal_id") not in {None, goal_id} and state in GOAL_ACTIVE_STATES:
                raise MissionConflict("navigation goal ownership changed during mission cleanup")
            if state in GOAL_TERMINAL_STATES:
                waypoint["goal_id"] = None
                return state
            await asyncio.sleep(self._poll_interval_s)
        raise MissionConflict("mission goal cancellation was not confirmed")

    async def _stop_monitor_locked(self) -> None:
        self._generation += 1
        task = self._task
        self._task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def pause(self, mission_id: str) -> dict[str, Any]:
        async with self._operation_lock:
            mission = self._mission(mission_id)
            if mission["state"] == "paused":
                return {"mission": self._public(mission)}
            if mission["state"] not in {"starting", "running"} or self._active_id != mission_id:
                raise MissionConflict("only the active mission can pause")
            await self._stop_monitor_locked()
            mission["state"] = "pausing"
            self._record(mission, "mission_pausing")
            self._save()
            terminal = await self._cancel_current_locked(mission)
            waypoint = mission["waypoints"][mission["current_index"]] if mission["current_index"] < len(mission["waypoints"]) else None
            if waypoint and terminal == "succeeded":
                waypoint["status"] = "completed"
                mission["current_index"] += 1
            elif waypoint:
                waypoint["status"] = "pending"
            mission.update(state="paused", pause_reason="operator_pause", hold_until_epoch=0.0)
            self._record(mission, "mission_paused")
            self._save()
            return {"mission": self._public(mission)}

    async def resume(self, mission_id: str) -> dict[str, Any]:
        async with self._operation_lock:
            mission = self._mission(mission_id)
            if mission["state"] != "paused" or self._active_id != mission_id:
                raise MissionConflict("only the active paused mission can resume")
            await self._dispatch_current_locked(mission, operator_confirmed=True)
            if mission["state"] == "running":
                self._start_monitor_locked(mission)
            return {"mission": self._public(mission)}

    async def skip(self, mission_id: str) -> dict[str, Any]:
        async with self._operation_lock:
            mission = self._mission(mission_id)
            if mission["state"] not in {"running", "paused", "failed"}:
                raise MissionConflict("mission waypoint cannot be skipped in this state")
            if self._active_id not in {None, mission_id}:
                raise MissionConflict("another mission owns navigation")
            self._active_id = mission_id
            await self._stop_monitor_locked()
            mission["state"] = "skipping"
            self._record(mission, "waypoint_skipping", mission["current_index"])
            self._save()
            await self._cancel_current_locked(mission)
            if mission["current_index"] < len(mission["waypoints"]):
                mission["waypoints"][mission["current_index"]].update(status="skipped", goal_id=None)
                mission["current_index"] += 1
            if mission["current_index"] >= len(mission["waypoints"]):
                self._complete_locked(mission)
            else:
                await self._dispatch_current_locked(mission, operator_confirmed=False)
                if mission["state"] == "running":
                    self._start_monitor_locked(mission)
            return {"mission": self._public(mission)}

    async def retry(self, mission_id: str) -> dict[str, Any]:
        async with self._operation_lock:
            mission = self._mission(mission_id)
            if mission["state"] != "failed":
                raise MissionConflict("only a failed mission waypoint can retry")
            if self._active_id and self._active_id != mission_id:
                raise MissionConflict("another mission owns navigation")
            self._active_id = mission_id
            mission.update(state="retrying", completed_at="", completed_epoch=0.0, error="", outcome="")
            if mission["current_index"] < len(mission["waypoints"]):
                mission["waypoints"][mission["current_index"]].update(status="pending", goal_id=None)
            self._record(mission, "waypoint_retrying", mission["current_index"])
            self._save()
            await self._dispatch_current_locked(mission, operator_confirmed=True)
            if mission["state"] == "running":
                self._start_monitor_locked(mission)
            return {"mission": self._public(mission)}

    async def abort(self, mission_id: str, *, reason: str = "operator_abort") -> dict[str, Any]:
        async with self._operation_lock:
            mission = self._mission(mission_id)
            if mission["state"] in {"completed", "failed"} and self._active_id != mission_id:
                return {"mission": self._public(mission)}
            await self._stop_monitor_locked()
            mission["state"] = "canceling"
            self._record(mission, "mission_canceling")
            self._save()
            await self._cancel_current_locked(mission)
            if mission["current_index"] < len(mission["waypoints"]):
                waypoint = mission["waypoints"][mission["current_index"]]
                if waypoint["status"] == "running": waypoint.update(status="failed", goal_id=None)
            mission.update(state="failed", outcome="aborted", error=str(reason)[:48], completed_at=_timestamp(self._now()), completed_epoch=self._now(), hold_until_epoch=0.0, pause_reason="")
            self._active_id = None
            self._record(mission, "mission_aborted")
            self._save()
            return {"mission": self._public(mission)}

    async def abort_active(self, *, reason: str = "manual_takeover") -> dict[str, Any] | None:
        identifier = self._active_id
        return await self.abort(identifier, reason=reason) if identifier else None

    async def _monitor(self, mission_id: str, generation: int) -> None:
        try:
            while generation == self._generation:
                await asyncio.sleep(self._poll_interval_s)
                async with self._operation_lock:
                    if generation != self._generation:
                        return
                    mission = self._mission(mission_id)
                    if mission["state"] != "running" or self._active_id != mission_id:
                        return
                    if mission.get("hold_until_epoch", 0.0) > self._now():
                        continue
                    if mission.get("hold_until_epoch", 0.0):
                        mission["hold_until_epoch"] = 0.0
                        await self._dispatch_current_locked(mission, operator_confirmed=False)
                        if mission["state"] != "running":
                            return
                        continue
                    waypoint = mission["waypoints"][mission["current_index"]]
                    navigation = self._navigation.view()
                    goal = navigation.get("goal") if isinstance(navigation.get("goal"), Mapping) else {}
                    if goal.get("goal_id") != waypoint.get("goal_id"):
                        if goal.get("state") in GOAL_ACTIVE_STATES:
                            mission.update(state="failed", outcome="goal_ownership_lost", error="navigation_goal_ownership_changed", completed_at=_timestamp(self._now()), completed_epoch=self._now())
                            waypoint["status"] = "failed"
                            self._active_id = None
                            self._record(mission, "goal_ownership_lost", mission["current_index"])
                            self._save()
                            return
                    state = str(goal.get("state") or "idle")
                    if state in GOAL_ACTIVE_STATES:
                        continue
                    if state == "succeeded":
                        waypoint.update(status="completed", goal_id=None)
                        mission["current_index"] += 1
                        self._record(mission, "waypoint_completed", mission["current_index"] - 1)
                        if mission["current_index"] >= len(mission["waypoints"]):
                            self._complete_locked(mission)
                            return
                        hold = float(waypoint.get("hold_seconds") or 0.0)
                        if hold > 0:
                            mission["hold_until_epoch"] = self._now() + hold
                            self._save()
                            continue
                        await self._dispatch_current_locked(mission, operator_confirmed=False)
                        if mission["state"] != "running":
                            return
                    else:
                        waypoint.update(status="failed", goal_id=None)
                        mission.update(state="failed", outcome="waypoint_failed", error=f"navigation_goal_{state}", completed_at=_timestamp(self._now()), completed_epoch=self._now())
                        self._active_id = None
                        self._record(mission, "waypoint_failed", mission["current_index"])
                        self._save()
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            async with self._operation_lock:
                try:
                    mission = self._mission(mission_id)
                    if mission["state"] in ACTIVE_STATES:
                        mission.update(state="failed", outcome="monitor_failed", error="mission_monitor_failed", completed_at=_timestamp(self._now()), completed_epoch=self._now())
                        self._active_id = None
                        self._record(mission, "mission_monitor_failed")
                        self._save()
                except MissionError:
                    pass

    async def close(self) -> None:
        async with self._operation_lock:
            await self._stop_monitor_locked()
            if self._active_id:
                mission = self._mission(self._active_id)
                if mission["state"] != "paused":
                    try:
                        await self._cancel_current_locked(mission)
                    except MissionError:
                        pass
                    mission.update(state="failed", outcome="interrupted", error="server_shutdown_interrupted", completed_at=_timestamp(self._now()), completed_epoch=self._now())
                    self._active_id = None
                    self._record(mission, "mission_interrupted")
                    self._save()


__all__ = [
    "MissionConflict", "MissionCoordinator", "MissionError", "MissionNotFound",
    "MissionStateStore", "MissionUnavailable", "MissionValidationError",
]
