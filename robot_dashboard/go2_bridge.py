"""Pure safety core for the standalone Unitree Go2 ROS 2 control bridge."""

from __future__ import annotations

import json
import math
import secrets
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any, Mapping


API_STOP_MOVE = 1003
API_MOVE = 1008

# This deliberately excludes Damp, flips, jumps, handstands, dances, direct
# motor control, and deprecated sport APIs.
SAFE_ACTION_API_IDS: dict[str, int] = {
    "balance_stand": 1002,
    "stand_up": 1004,
    "stand_down": 1005,
    "recovery_stand": 1006,
    "sit": 1009,
    "rise_sit": 1010,
    "hello": 1016,
    "stretch": 1017,
    "content": 1020,
    "scrape": 1029,
    "heart": 1036,
    "static_walk": 1061,
    "economic_gait": 1063,
    "free_walk": 2045,
}

SAFE_ACTION_GUARD_S: dict[str, float] = {
    "balance_stand": 3.0,
    "stand_up": 5.0,
    "stand_down": 5.0,
    "recovery_stand": 8.0,
    "sit": 5.0,
    "rise_sit": 5.0,
    "hello": 8.0,
    "stretch": 8.0,
    "content": 8.0,
    "scrape": 8.0,
    "heart": 8.0,
    "static_walk": 3.0,
    "economic_gait": 3.0,
    "free_walk": 3.0,
}


class BridgeCommandError(ValueError):
    """Raised when the dashboard sends an unsafe bridge command."""


@dataclass(frozen=True)
class SportRequest:
    api_id: int
    parameter: str = ""
    reason: str = ""


class Go2BridgeCore:
    """Last-line motion watchdog, independent from the web process."""

    HARD_MAX_LINEAR_X = 0.30
    HARD_MAX_LINEAR_Y = 0.20
    HARD_MAX_ANGULAR_Z = 0.50
    HARD_MAX_COMMAND_TIMEOUT_S = 0.20

    def __init__(
        self,
        *,
        max_linear_x: float = HARD_MAX_LINEAR_X,
        max_linear_y: float = HARD_MAX_LINEAR_Y,
        max_angular_z: float = HARD_MAX_ANGULAR_Z,
        command_timeout_s: float = HARD_MAX_COMMAND_TIMEOUT_S,
        telemetry_timeout_s: float = 0.50,
        source_timeout_s: float = 2.0,
    ) -> None:
        self.max_linear_x = self._bounded_limit(
            max_linear_x, self.HARD_MAX_LINEAR_X
        )
        self.max_linear_y = self._bounded_limit(
            max_linear_y, self.HARD_MAX_LINEAR_Y
        )
        self.max_angular_z = self._bounded_limit(
            max_angular_z, self.HARD_MAX_ANGULAR_Z
        )
        # The ROS timer runs every 50 ms.  A 200 ms age limit therefore gives
        # a nominal StopMove dispatch no later than the following timer cycle
        # (<= 250 ms under a normally scheduled executor).
        self.command_timeout_s = max(
            0.10,
            min(float(command_timeout_s), self.HARD_MAX_COMMAND_TIMEOUT_S),
        )
        self.telemetry_timeout_s = max(
            0.20, min(float(telemetry_timeout_s), 1.0)
        )
        self.source_timeout_s = max(0.5, min(float(source_timeout_s), 5.0))
        # A new, unpredictable epoch is created for every bridge process.  A
        # signed command from an earlier process can therefore never be
        # replayed into this instance, even if its timestamp is still fresh.
        self._bridge_epoch = secrets.token_urlsafe(32)

        self._source_id = ""
        self._last_seq_by_source: dict[str, int] = {}
        self._last_received = 0.0
        self._last_drive = 0.0
        self._target = (0.0, 0.0, 0.0)
        self._deadman = False
        self._moving = False
        self._pending_stop = True
        self._pending_action: tuple[str, float] | None = None
        self._action_guard_until = 0.0
        self._action_hold_until = 0.0
        self._action_hold_name = ""
        self._last_stop = 0.0
        self._last_error = ""
        self._last_request: SportRequest | None = None

    @property
    def bridge_epoch(self) -> str:
        return self._bridge_epoch

    @staticmethod
    def _bounded_limit(value: float, ceiling: float) -> float:
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError("control limit must be a positive finite number")
        return min(number, ceiling)

    @staticmethod
    def _source(payload: Mapping[str, Any]) -> str:
        value = payload.get("source_id")
        if not isinstance(value, str) or not 8 <= len(value) <= 128:
            raise BridgeCommandError("source_id is invalid")
        return value

    @staticmethod
    def _sequence(payload: Mapping[str, Any]) -> int:
        value = payload.get("seq")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BridgeCommandError("command sequence is invalid")
        return value

    @staticmethod
    def _finite(value: Any, label: str) -> float:
        if isinstance(value, bool):
            raise BridgeCommandError(f"{label} must be numeric")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise BridgeCommandError(f"{label} must be numeric") from exc
        if not math.isfinite(number):
            raise BridgeCommandError(f"{label} must be finite")
        return number

    def _accept_source(self, source_id: str, seq: int, now: float, kind: str) -> None:
        previous_seq = self._last_seq_by_source.get(source_id, -1)
        if seq <= previous_seq:
            raise BridgeCommandError("replayed or out-of-order command")
        if (
            kind != "stop"
            and self._source_id
            and source_id != self._source_id
            and now - self._last_received <= self.source_timeout_s
        ):
            raise BridgeCommandError("another dashboard source owns the bridge")
        self._last_seq_by_source[source_id] = seq
        if len(self._last_seq_by_source) > 16:
            oldest = next(iter(self._last_seq_by_source))
            if oldest != source_id:
                self._last_seq_by_source.pop(oldest, None)
        self._source_id = source_id
        self._last_received = now

    def accept(
        self,
        payload: Mapping[str, Any],
        *,
        now: float,
        transport_age_s: float = 0.0,
    ) -> None:
        kind = payload.get("type")
        if kind not in {"drive", "stop", "action"}:
            raise BridgeCommandError("unknown bridge command")
        bridge_epoch = payload.get("bridge_epoch")
        if not isinstance(bridge_epoch, str) or not compare_digest(
            bridge_epoch.encode("utf-8"),
            self._bridge_epoch.encode("ascii"),
        ):
            raise BridgeCommandError("bridge epoch does not match")
        source_id = self._source(payload)
        seq = self._sequence(payload)
        transport_age = self._finite(transport_age_s, "transport_age_s")
        if transport_age < 0.0:
            raise BridgeCommandError("transport_age_s must not be negative")
        if kind != "stop" and transport_age > self.command_timeout_s:
            raise BridgeCommandError("bridge command exceeded its transport deadline")
        self._accept_source(source_id, seq, float(now), str(kind))
        self._last_error = ""

        if kind == "stop":
            self.force_stop(str(payload.get("reason", "dashboard stop")))
            return

        if kind == "action":
            if float(now) < self._action_hold_until:
                raise BridgeCommandError("action safety window is still active")
            action_id = payload.get("action_id")
            if not isinstance(action_id, str) or action_id not in SAFE_ACTION_API_IDS:
                raise BridgeCommandError("action is not allowlisted")
            self._target = (0.0, 0.0, 0.0)
            self._deadman = False
            self._pending_stop = True
            self._pending_action = (action_id, float(now) + 0.10)
            self._action_hold_until = float(now) + SAFE_ACTION_GUARD_S[action_id]
            self._action_hold_name = action_id
            # A browser's 20 Hz teleop loop may already have one frame in
            # flight.  Consume its sequence but do not let it cancel the
            # one-shot action before the ROS request has been published.
            self._action_guard_until = float(now) + 0.25
            return

        if float(now) < max(self._action_guard_until, self._action_hold_until):
            return
        deadman = payload.get("deadman")
        if not isinstance(deadman, bool):
            raise BridgeCommandError("deadman must be boolean")
        if not deadman:
            self.force_stop("deadman released")
            return
        x = self._finite(payload.get("linear_x"), "linear_x")
        y = self._finite(payload.get("linear_y"), "linear_y")
        z = self._finite(payload.get("angular_z"), "angular_z")
        self._target = (
            max(-self.max_linear_x, min(self.max_linear_x, x)),
            max(-self.max_linear_y, min(self.max_linear_y, y)),
            max(-self.max_angular_z, min(self.max_angular_z, z)),
        )
        self._deadman = True
        self._last_drive = float(now) - transport_age
        self._pending_action = None
        self._action_guard_until = 0.0

    def force_stop(self, reason: str = "stop") -> None:
        self._target = (0.0, 0.0, 0.0)
        self._deadman = False
        self._moving = False
        self._pending_action = None
        self._pending_stop = True
        self._action_guard_until = 0.0
        self._action_hold_until = 0.0
        self._action_hold_name = ""
        self._last_error = str(reason)[:160]

    @staticmethod
    def _move_request(target: tuple[float, float, float]) -> SportRequest:
        parameter = json.dumps(
            {"x": target[0], "y": target[1], "z": target[2]},
            separators=(",", ":"),
            allow_nan=False,
        )
        return SportRequest(API_MOVE, parameter, "fresh deadman command")

    def tick(
        self,
        *,
        now: float,
        lowstate_age_s: float | None,
        sport_subscribers: int,
        sport_publishers: int,
        lowstate_publishers: int = 1,
    ) -> list[SportRequest]:
        now = float(now)
        telemetry_fresh = (
            lowstate_age_s is not None
            and math.isfinite(float(lowstate_age_s))
            and 0.0 <= float(lowstate_age_s) <= self.telemetry_timeout_s
        )
        ready = (
            telemetry_fresh
            and int(lowstate_publishers) == 1
            and int(sport_subscribers) == 1
            and int(sport_publishers) == 1
        )
        requests: list[SportRequest] = []

        if now < self._action_hold_until and not ready:
            self.force_stop("telemetry unavailable during action")

        if self._pending_stop:
            requests.append(SportRequest(API_STOP_MOVE, "", self._last_error or "stop"))
            self._pending_stop = False
            self._last_stop = now

        if self._pending_action is not None:
            action_id, due_at = self._pending_action
            if not ready:
                self._pending_action = None
                self.force_stop("bridge unavailable before action")
            elif now >= due_at:
                requests.append(
                    SportRequest(
                        SAFE_ACTION_API_IDS[action_id],
                        "",
                        f"allowlisted action: {action_id}",
                    )
                )
                self._pending_action = None
                self._last_request = requests[-1]
                return requests

        # Unitree actions are asynchronous.  Do not let the normal idle
        # StopMove heartbeat truncate the accepted action; explicit software
        # stop, telemetry loss, and bridge shutdown still stop immediately.
        if now < self._action_hold_until:
            return requests

        command_fresh = (
            self._deadman
            and now - self._last_drive <= self.command_timeout_s
            and now - self._last_received <= self.source_timeout_s
        )
        if ready and command_fresh:
            request = self._move_request(self._target)
            requests.append(request)
            self._moving = any(abs(value) > 1e-6 for value in self._target)
            self._last_request = request
            return requests

        if self._moving or now - self._last_stop >= 0.50:
            reason = "telemetry unavailable" if not ready else "command watchdog"
            request = SportRequest(API_STOP_MOVE, "", reason)
            requests.append(request)
            self._moving = False
            self._deadman = False
            self._target = (0.0, 0.0, 0.0)
            self._last_stop = now
            self._last_request = request
        return requests

    def snapshot(
        self,
        *,
        now: float,
        lowstate_age_s: float | None,
        sport_subscribers: int,
        sport_publishers: int,
        lowstate_publishers: int = 1,
    ) -> dict[str, Any]:
        telemetry_fresh = (
            lowstate_age_s is not None
            and math.isfinite(float(lowstate_age_s))
            and 0.0 <= float(lowstate_age_s) <= self.telemetry_timeout_s
        )
        ready = (
            telemetry_fresh
            and int(lowstate_publishers) == 1
            and int(sport_subscribers) == 1
            and int(sport_publishers) == 1
        )
        command_age = None if not self._last_drive else max(0.0, now - self._last_drive)
        action_remaining = max(0.0, self._action_hold_until - now)
        control_ready = ready and action_remaining <= 0.0
        return {
            "ready": control_ready,
            "state": (
                "action"
                if action_remaining > 0.0
                else "moving"
                if self._moving
                else "idle"
                if ready
                else "unavailable"
            ),
            "bridge_epoch": self._bridge_epoch,
            "lowstate_age_ms": (
                None if lowstate_age_s is None else round(float(lowstate_age_s) * 1_000)
            ),
            "lowstate_publishers": max(0, int(lowstate_publishers)),
            "sport_subscribers": max(0, int(sport_subscribers)),
            "sport_publishers": max(0, int(sport_publishers)),
            "command_age_ms": (
                None if command_age is None else round(command_age * 1_000)
            ),
            "last_error": self._last_error,
            "action_guard": {
                "active": action_remaining > 0.0,
                "action": self._action_hold_name or None,
                "remaining_ms": round(action_remaining * 1_000),
            },
            "limits": {
                "max_linear_x": self.max_linear_x,
                "max_linear_y": self.max_linear_y,
                "max_angular_z": self.max_angular_z,
                "command_timeout_ms": round(self.command_timeout_s * 1_000),
            },
        }
