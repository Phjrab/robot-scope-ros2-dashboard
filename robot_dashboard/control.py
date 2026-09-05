"""Fail-closed control state machine for the Robot Scope web API.

This module intentionally has no ROS imports.  It validates browser input and
produces small output envelopes which a ROS-specific bridge can publish.
"""

from __future__ import annotations

import hmac
import math
import os
import secrets
import threading
import time
from collections import deque
from collections.abc import Mapping
from typing import Any, Callable


class ControlError(RuntimeError):
    """Base class for errors that are safe to translate to API responses."""


class ControlDisabled(ControlError):
    pass


class ControlNotReady(ControlError):
    pass


class ControlClosed(ControlError):
    pass


class LeaseBusy(ControlError):
    pass


class LeaseInvalid(ControlError):
    pass


class LeaseBindingError(ControlError):
    pass


class SequenceError(ControlError):
    pass


class CommandValidationError(ControlError):
    pass


class EmergencyStopLatched(ControlError):
    pass


SAFE_ACTIONS: dict[str, int] = {
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

# Conservative no-teleop windows after sending an asynchronous Unitree action.
# These are safety holds, not claims that the robot has completed the action.
ACTION_GUARD_S: dict[str, float] = {
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

ACTION_METADATA: dict[str, dict[str, str]] = {
    "balance_stand": {
        "label": "Balance stand",
        "category": "posture",
        "description": "균형 서기 모드로 전환합니다.",
    },
    "stand_up": {
        "label": "Stand up",
        "category": "posture",
        "description": "바닥 자세에서 일어섭니다.",
    },
    "stand_down": {
        "label": "Stand down",
        "category": "posture",
        "description": "몸을 낮춰 엎드린 자세로 전환합니다.",
    },
    "recovery_stand": {
        "label": "Recovery stand",
        "category": "recovery",
        "description": "넘어진 상태에서 복구 서기를 시도합니다.",
    },
    "sit": {
        "label": "Sit",
        "category": "posture",
        "description": "앉기 동작을 실행합니다.",
    },
    "rise_sit": {
        "label": "Rise from sit",
        "category": "posture",
        "description": "앉은 자세에서 일어납니다.",
    },
    "hello": {
        "label": "Hello",
        "category": "gesture",
        "description": "Go2의 인사 동작을 실행합니다.",
    },
    "stretch": {
        "label": "Stretch",
        "category": "gesture",
        "description": "스트레칭 동작을 실행합니다.",
    },
    "content": {
        "label": "Content",
        "category": "gesture",
        "description": "Go2의 기쁨 표현 동작을 실행합니다.",
    },
    "scrape": {
        "label": "Scrape",
        "category": "gesture",
        "description": "앞발 긁기 동작을 실행합니다.",
    },
    "heart": {
        "label": "Heart",
        "category": "gesture",
        "description": "하트 제스처를 실행합니다.",
    },
    "static_walk": {
        "label": "Static walk",
        "category": "gait",
        "description": "정적 보행 모드로 전환합니다.",
    },
    "economic_gait": {
        "label": "Economic gait",
        "category": "gait",
        "description": "에너지 절약 보행 모드로 전환합니다.",
    },
    "free_walk": {
        "label": "Free walk",
        "category": "gait",
        "description": "자유 보행 모드로 전환합니다.",
    },
}

CONFIRM_ACTIONS = frozenset(SAFE_ACTIONS)

INPUT_SOURCES = frozenset({"keyboard", "gamepad"})
INTERNAL_NAVIGATION_SOURCE = "navigation"


class ClientFrameClock:
    """Reject browser control frames that became stale in a WebSocket queue.

    Browser timestamps use the wall clock while server safety timers use a
    monotonic clock.  A per-connection offset captured by the bind frame lets
    us compare ages without requiring the Jetson and browser clocks to agree.
    The offset never moves afterward, so a network stall cannot make queued
    deadman frames look fresh when the connection recovers.
    """

    MAX_AGE_MS = 200.0
    MAX_FUTURE_MS = 500.0

    def __init__(self, client_time_ms: object, server_time_ms: float) -> None:
        client = self._finite_ms(client_time_ms)
        server = self._finite_ms(server_time_ms)
        self._offset_ms = server - client
        self._last_client_ms = client
        self._last_server_ms = server

    @staticmethod
    def _finite_ms(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CommandValidationError("client_time_ms must be a finite number")
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise CommandValidationError("client_time_ms must be a finite number")
        return number

    def validate(self, client_time_ms: object, server_time_ms: float) -> float:
        client = self._finite_ms(client_time_ms)
        server = self._finite_ms(server_time_ms)
        client_elapsed = client - self._last_client_ms
        server_elapsed = server - self._last_server_ms
        if client_elapsed < 0.0 or server_elapsed < 0.0:
            raise CommandValidationError("control clock moved backwards; re-arm is required")
        if server_elapsed - client_elapsed > self.MAX_AGE_MS:
            raise CommandValidationError("queued control frame; re-arm is required")
        age_ms = server - (client + self._offset_ms)
        if age_ms > self.MAX_AGE_MS:
            raise CommandValidationError("stale control frame; re-arm is required")
        if age_ms < -self.MAX_FUTURE_MS:
            raise CommandValidationError("client clock changed; re-arm is required")
        self._last_client_ms = client
        self._last_server_ms = server
        return age_ms


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bounded_float(value: object, *, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(low, min(parsed, high))


class ControlManager:
    """Validate one control lease and emit ROS-agnostic command envelopes.

    The constructor is deliberately fail-closed.  Both the selected profile and
    the process environment must opt in.  Callers should use one monotonically
    increasing sequence number across heartbeat, drive, and action messages.
    """

    ENV_ENABLED = "ROBOT_SCOPE_CONTROL_ENABLED"
    # The ROS watchdog runs every 50 ms.  Expiring the browser intent after
    # 200 ms leaves one watchdog cycle to dispatch StopMove near 250 ms.
    COMMAND_TIMEOUT_S = 0.20
    LEASE_HEARTBEAT_S = 2.0
    # An unbound lease cannot issue commands.  Give the browser enough time to
    # complete its WebSocket handshake, then switch to the shorter heartbeat
    # timeout as soon as the lease is bound.
    LEASE_BIND_S = 4.0

    VX_LIMIT = 0.30
    VY_LIMIT = 0.20
    WZ_LIMIT = 0.50
    MIN_SPEED_SCALE = 0.10
    MAX_SPEED_SCALE = 1.0

    def __init__(
        self,
        profile: Mapping[str, Any] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        profile = profile or {}
        control = profile.get("control", {})
        if not isinstance(control, Mapping):
            control = {}
        env = os.environ if environ is None else environ

        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._lock = threading.RLock()
        self._closed = False

        self._profile_enabled = control.get("enabled") is True
        self._startup_enabled = _truthy(env.get(self.ENV_ENABLED, ""))
        self._enabled = self._profile_enabled and self._startup_enabled
        self._configured = self._enabled

        self._vx_limit = _bounded_float(
            control.get("max_linear_x"), default=self.VX_LIMIT, low=0.01, high=self.VX_LIMIT
        )
        self._vy_limit = _bounded_float(
            control.get("max_linear_y"), default=self.VY_LIMIT, low=0.01, high=self.VY_LIMIT
        )
        self._wz_limit = _bounded_float(
            control.get("max_angular_z"), default=self.WZ_LIMIT, low=0.05, high=self.WZ_LIMIT
        )
        self._default_speed_scale = _bounded_float(
            control.get("default_speed_scale"),
            default=0.35,
            low=self.MIN_SPEED_SCALE,
            high=self.MAX_SPEED_SCALE,
        )
        self._command_timeout_s = _bounded_float(
            control.get("command_timeout_s"),
            default=self.COMMAND_TIMEOUT_S,
            low=0.10,
            high=self.COMMAND_TIMEOUT_S,
        )
        self._lease_heartbeat_s = _bounded_float(
            control.get("lease_timeout_s"),
            default=self.LEASE_HEARTBEAT_S,
            low=0.5,
            high=self.LEASE_HEARTBEAT_S,
        )
        self._lease_bind_s = _bounded_float(
            control.get("bind_timeout_s"),
            default=self.LEASE_BIND_S,
            low=2.5,
            high=5.0,
        )

        self._bridge_stale_s = _bounded_float(
            control.get("bridge_status_timeout_s", control.get("bridge_stale_after_s")),
            default=0.75,
            low=0.1,
            high=2.0,
        )
        self._lowstate_stale_s = _bounded_float(
            control.get("telemetry_timeout_s", control.get("lowstate_stale_after_s")),
            default=0.5,
            low=0.1,
            high=1.0,
        )
        self._linear_slew = _bounded_float(
            control.get("max_linear_accel", control.get("linear_slew_mps2")),
            default=0.75,
            low=0.05,
            high=2.0,
        )
        self._lateral_slew = _bounded_float(
            control.get("max_lateral_accel", control.get("linear_slew_mps2")),
            default=0.60,
            low=0.05,
            high=2.0,
        )
        self._angular_slew = _bounded_float(
            control.get("max_angular_accel", control.get("angular_slew_rps2")),
            default=1.5,
            low=0.1,
            high=4.0,
        )
        configured_actions = control.get("allowed_actions")
        if isinstance(configured_actions, list):
            self._allowed_actions = {
                name: SAFE_ACTIONS[name]
                for raw_name in configured_actions
                if (name := str(raw_name).strip().lower()) in SAFE_ACTIONS
            }
        else:
            self._allowed_actions = dict(SAFE_ACTIONS)

        self._lease: dict[str, Any] | None = None
        self._bridge_seen: float | None = None
        self._lowstate_seen: float | None = None
        self._estop_latched = False
        self._estop_reason = ""
        self._action_guard_until = 0.0
        self._action_guard_name = ""

        self._drive: dict[str, Any] | None = None
        self._actions: deque[dict[str, Any]] = deque()
        self._outputs: deque[dict[str, Any]] = deque()
        self._last_velocity = {"vx": 0.0, "vy": 0.0, "wz": 0.0}
        self._last_command_source: str | None = None
        self._last_command_deadman = False
        self._last_tick: float | None = None
        self._motion_active = False
        self._stop_emitted = True

    def _now(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value):
            raise RuntimeError("control clock returned a non-finite value")
        return value

    def _ensure_open(self) -> None:
        if self._closed:
            raise ControlClosed("control manager is closed")

    def _ensure_configured(self) -> None:
        self._ensure_open()
        if not self._enabled:
            raise ControlDisabled("robot control is disabled")
        if not self._configured:
            raise ControlDisabled("robot control is not configured")

    def _ready_at(self, now: float) -> bool:
        return (
            self._configured
            and not self._closed
            and self._bridge_seen is not None
            and now - self._bridge_seen < self._bridge_stale_s
            and self._lowstate_seen is not None
            and now - self._lowstate_seen < self._lowstate_stale_s
            and self._action_guard_remaining(now) <= 0.0
        )

    def _action_guard_remaining(self, now: float) -> float:
        remaining = max(0.0, self._action_guard_until - now)
        if remaining <= 0.0:
            self._action_guard_until = 0.0
            self._action_guard_name = ""
        return remaining

    def note_bridge(self, ready: bool = True) -> None:
        with self._lock:
            self._ensure_open()
            self._bridge_seen = self._now() if ready else None
            if not ready:
                self._fail_closed("bridge_not_ready")

    def note_lowstate(self, fresh: bool = True) -> None:
        with self._lock:
            self._ensure_open()
            self._lowstate_seen = self._now() if fresh else None
            if not fresh:
                self._fail_closed("lowstate_not_ready")

    def set_readiness(self, *, bridge_ready: bool, lowstate_ready: bool) -> None:
        """Convenience method for integrations that receive one health snapshot."""

        with self._lock:
            self._ensure_open()
            now = self._now()
            self._bridge_seen = now if bridge_ready else None
            self._lowstate_seen = now if lowstate_ready else None
            if not bridge_ready or not lowstate_ready:
                self._fail_closed("readiness_lost")

    def _acquire_lease(
        self,
        input_source: str,
        *,
        allow_navigation: bool,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_configured()
            now = self._now()
            self._expire_if_needed(now)
            if self._estop_latched:
                raise EmergencyStopLatched("dashboard software stop is latched")
            action_wait = self._action_guard_remaining(now)
            if action_wait > 0.0:
                raise ControlNotReady(
                    f"wait {action_wait:.1f}s for the action safety window before re-arming"
                )
            if not self._ready_at(now):
                raise ControlNotReady("bridge and lowstate must both be fresh")
            source = str(input_source).strip().lower()
            allowed = source in INPUT_SOURCES or (
                allow_navigation and source == INTERNAL_NAVIGATION_SOURCE
            )
            if not allowed:
                raise CommandValidationError("input_source must be keyboard or gamepad")
            if self._lease is not None:
                raise LeaseBusy("another controller already owns the robot")
            token = self._token_factory()
            if not isinstance(token, str) or len(token) < 16:
                raise RuntimeError("token factory returned an unsafe token")
            self._lease = {
                "token": token,
                "input_source": source,
                "binding": None,
                "acquired_at": now,
                "heartbeat_at": now,
                "last_seq": -1,
            }
            return {"token": token, "lease": self._lease_public(now)}

    def acquire_lease(self, input_source: str) -> dict[str, Any]:
        """Acquire a browser lease for one allowlisted human input source."""

        return self._acquire_lease(input_source, allow_navigation=False)

    def acquire_navigation_lease(self) -> dict[str, Any]:
        """Acquire the internal Nav2 lease without widening the HTTP contract.

        Only the in-process ROS integration calls this method.  Browser ARM
        remains limited to keyboard/gamepad, while the shared lease guarantees
        that autonomous navigation and manual control can never own motion at
        the same time.
        """

        return self._acquire_lease(
            INTERNAL_NAVIGATION_SOURCE,
            allow_navigation=True,
        )

    def bind_lease(self, token: str, binding: str) -> dict[str, Any]:
        """Bind a lease once to a WebSocket/session identifier."""

        with self._lock:
            now = self._now()
            lease = self._require_lease(token, now)
            value = str(binding).strip()
            if not value or len(value) > 256:
                raise LeaseBindingError("binding must be 1 to 256 characters")
            current = lease["binding"]
            if current is None:
                lease["binding"] = value
                # The acquisition-to-WebSocket handshake uses the longer,
                # non-commanding bind TTL.  Start the normal heartbeat window
                # only after this session has been authenticated and bound.
                lease["heartbeat_at"] = now
            elif not hmac.compare_digest(current, value):
                raise LeaseBindingError("lease is bound to another session")
            return self._lease_public(now)

    def _require_lease(
        self,
        token: str,
        now: float,
        binding: str | None = None,
        *,
        require_ready: bool = True,
    ) -> dict[str, Any]:
        self._ensure_configured()
        self._expire_if_needed(now)
        self._expire_command_if_needed(now)
        if self._lease is None or not hmac.compare_digest(
            str(token), str(self._lease["token"])
        ):
            raise LeaseInvalid("invalid or expired control lease")
        if binding is not None:
            expected = self._lease["binding"]
            if expected is None:
                raise LeaseBindingError("lease must be bound before use")
            if not hmac.compare_digest(str(binding), str(expected)):
                raise LeaseBindingError("lease is bound to another session")
        if require_ready and not self._ready_at(now):
            self._fail_closed("readiness_stale")
            raise ControlNotReady("bridge and lowstate must both be fresh")
        return self._lease

    @staticmethod
    def _validate_seq(lease: dict[str, Any], seq: object) -> int:
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            raise SequenceError("seq must be a non-negative integer")
        if seq <= lease["last_seq"]:
            raise SequenceError("seq must be strictly increasing")
        lease["last_seq"] = seq
        return seq

    def heartbeat(self, token: str, binding: str, seq: int) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            lease = self._require_lease(token, now, binding)
            self._validate_seq(lease, seq)
            lease["heartbeat_at"] = now
            return self._lease_public(now)

    @staticmethod
    def _normalized(value: object, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CommandValidationError(f"{name} must be a finite number")
        result = float(value)
        if not math.isfinite(result):
            raise CommandValidationError(f"{name} must be a finite number")
        if result < -1.0 or result > 1.0:
            raise CommandValidationError(f"{name} must be normalized to [-1, 1]")
        return result

    @classmethod
    def _speed_scale(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CommandValidationError("speed_scale must be a finite number")
        scale = float(value)
        if not math.isfinite(scale):
            raise CommandValidationError("speed_scale must be a finite number")
        # The server clamps otherwise-valid preferences to its safe range.
        return max(cls.MIN_SPEED_SCALE, min(scale, cls.MAX_SPEED_SCALE))

    def submit_drive(
        self,
        token: str,
        binding: str,
        seq: int,
        *,
        vx: object,
        vy: object,
        wz: object,
        speed_scale: object = 1.0,
        deadman: bool,
        client_age_s: object = 0.0,
    ) -> dict[str, Any]:
        """Coalesce the latest drive intent; :meth:`tick` emits the command."""

        with self._lock:
            now = self._now()
            if self._estop_latched:
                raise EmergencyStopLatched("dashboard software stop is latched")
            lease = self._require_lease(token, now, binding)
            if not isinstance(deadman, bool):
                raise CommandValidationError("deadman must be a boolean")
            values = {
                "vx": self._normalized(vx, "vx"),
                "vy": self._normalized(vy, "vy"),
                "wz": self._normalized(wz, "wz"),
            }
            scale = self._speed_scale(speed_scale)
            if isinstance(client_age_s, bool) or not isinstance(client_age_s, (int, float)):
                raise CommandValidationError("client_age_s must be a finite number")
            command_age = float(client_age_s)
            if (
                not math.isfinite(command_age)
                or command_age < 0.0
                or command_age > self._command_timeout_s
            ):
                raise CommandValidationError("client_age_s exceeds the command timeout")
            self._validate_seq(lease, seq)
            self._drive = {
                "seq": seq,
                # Preserve the browser intent's age instead of granting a new
                # full watchdog period when a delayed frame reaches the server.
                "at": now - command_age,
                "deadman": deadman,
                "velocity": {
                    "vx": max(-self._vx_limit, min(values["vx"] * self._vx_limit * scale, self._vx_limit)),
                    "vy": max(-self._vy_limit, min(values["vy"] * self._vy_limit * scale, self._vy_limit)),
                    "wz": max(-self._wz_limit, min(values["wz"] * self._wz_limit * scale, self._wz_limit)),
                },
                "speed_scale": scale,
                "input_source": lease["input_source"],
            }
            if not deadman:
                self._emit_stop("deadman_released", now, force=True)
            return {
                "accepted": True,
                "seq": seq,
                "speed_scale": scale,
                "deadman": deadman,
            }

    def _resolve_action(self, action: str | int) -> tuple[str, int]:
        if isinstance(action, bool):
            raise CommandValidationError("action is not allowlisted")
        if isinstance(action, int):
            for name, action_id in self._allowed_actions.items():
                if action == action_id:
                    return name, action_id
        else:
            name = str(action).strip().lower()
            if name in self._allowed_actions:
                return name, self._allowed_actions[name]
        raise CommandValidationError("action is not allowlisted")

    def request_action(
        self,
        token: str,
        binding: str,
        seq: int,
        action: str | int,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            if self._estop_latched:
                raise EmergencyStopLatched("dashboard software stop is latched")
            lease = self._require_lease(token, now, binding)
            if self._motion_active or bool(self._drive and self._drive.get("deadman")):
                raise CommandValidationError("release the deadman before running an action")
            name, action_id = self._resolve_action(action)
            if name in CONFIRM_ACTIONS and confirm is not True:
                raise CommandValidationError(f"{name} requires explicit confirmation")
            self._validate_seq(lease, seq)
            self._drive = None
            self._emit_stop("action_prepare", now, force=True)
            envelope = {
                "type": "action",
                "action": name,
                "action_id": action_id,
                "seq": seq,
                "created_at": now,
            }
            # A one-shot motion consumes the lease.  Without a trustworthy
            # Unitree completion signal, teleoperation must never resume on a
            # guessed timer while Sit/Stand/Stretch may still be running.
            self._outputs.append(envelope)
            self._lease = None
            self._drive = None
            self._actions.clear()
            self._action_guard_name = name
            self._action_guard_until = now + ACTION_GUARD_S[name]
            return {
                "accepted": True,
                "action": name,
                "action_id": action_id,
                "seq": seq,
                "lease_released": True,
            }

    def _lease_public(self, now: float) -> dict[str, Any]:
        if self._lease is None:
            return {
                "active": False,
                "input_source": None,
                "bound": False,
                "last_seq": None,
                "heartbeat_age_s": None,
            }
        return {
            "active": True,
            "input_source": self._lease["input_source"],
            "bound": self._lease["binding"] is not None,
            "last_seq": self._lease["last_seq"],
            "heartbeat_age_s": round(max(0.0, now - self._lease["heartbeat_at"]), 3),
        }

    def _expire_if_needed(self, now: float) -> bool:
        if self._lease is None:
            return False
        timeout_s = (
            self._lease_bind_s
            if self._lease["binding"] is None
            else self._lease_heartbeat_s
        )
        if now - self._lease["heartbeat_at"] < timeout_s:
            return False
        self._lease = None
        self._drive = None
        self._actions.clear()
        self._emit_stop("lease_expired", now, force=True)
        return True

    def _expire_command_if_needed(self, now: float) -> bool:
        drive = self._drive
        if (
            self._lease is None
            or drive is None
            or not drive.get("deadman")
            or now - float(drive["at"]) < self._command_timeout_s
        ):
            return False
        self._lease = None
        self._drive = None
        self._actions.clear()
        self._emit_stop("command_timeout", now, force=True)
        return True

    def release_lease(self, token: str, binding: str | None = None) -> dict[str, Any]:
        """Release by bearer token, optionally enforcing its WebSocket binding.

        The optional form is used by the same-origin REST disarm fallback when
        the browser closes before a WebSocket has finished binding.
        """

        with self._lock:
            now = self._now()
            self._require_lease(token, now, binding, require_ready=False)
            self._lease = None
            self._drive = None
            self._actions.clear()
            self._emit_stop("lease_released", now, force=True)
            return self._lease_public(now)

    def emergency_stop(self, reason: str = "operator_estop") -> dict[str, Any]:
        """Latch the dashboard software stop without requiring a lease."""

        with self._lock:
            self._ensure_open()
            now = self._now()
            self._estop_latched = True
            self._estop_reason = str(reason).strip()[:128] or "operator_estop"
            self._lease = None
            self._drive = None
            self._actions.clear()
            self._action_guard_until = 0.0
            self._action_guard_name = ""
            self._emit_stop("emergency_stop", now, force=True)
            return self.snapshot()

    def clear_emergency_stop(self, *, confirm: bool) -> dict[str, Any]:
        with self._lock:
            self._ensure_configured()
            # A delayed duplicate clear must not revoke a newly acquired lease.
            # Treat it as an idempotent no-op before readiness mutation.
            if not self._estop_latched:
                return self.snapshot()
            if confirm is not True:
                raise CommandValidationError("clearing dashboard stop requires explicit confirmation")
            now = self._now()
            if not self._ready_at(now):
                raise ControlNotReady("bridge and lowstate must both be fresh")
            self._estop_latched = False
            self._estop_reason = ""
            # Clearing never restores an old lease.  A new lease and deadman
            # command are required before motion can resume.
            self._lease = None
            self._drive = None
            return self.snapshot()

    def _fail_closed(self, reason: str) -> None:
        now = self._now()
        if self._lease is not None or self._motion_active:
            self._lease = None
            self._drive = None
            self._actions.clear()
            self._emit_stop(reason, now, force=True)

    @staticmethod
    def _slew(current: float, target: float, delta: float) -> float:
        return max(current - delta, min(target, current + delta))

    def _emit_stop(self, reason: str, now: float, *, force: bool = False) -> None:
        self._last_velocity = {"vx": 0.0, "vy": 0.0, "wz": 0.0}
        self._last_command_deadman = False
        self._motion_active = False
        if force or not self._stop_emitted:
            self._outputs.append(
                {
                    "type": "stop",
                    "reason": reason,
                    "velocity": dict(self._last_velocity),
                    "created_at": now,
                }
            )
        self._stop_emitted = True

    def tick(self) -> list[dict[str, Any]]:
        """Advance safety timers and emit at most one coalesced drive command."""

        with self._lock:
            self._ensure_open()
            now = self._now()
            elapsed = 0.02 if self._last_tick is None else max(0.0, min(now - self._last_tick, 0.25))
            self._last_tick = now

            if self._expire_if_needed(now):
                return self.drain_outputs()
            if self._lease is not None and not self._ready_at(now):
                self._fail_closed("readiness_stale")
                return self.drain_outputs()
            if self._estop_latched:
                self._emit_stop("emergency_stop", now)
                return self.drain_outputs()
            if self._lease is None:
                return self.drain_outputs()

            while self._actions:
                self._outputs.append(self._actions.popleft())

            drive = self._drive
            if drive is None:
                return self.drain_outputs()
            if not drive["deadman"]:
                self._emit_stop("deadman_released", now)
                return self.drain_outputs()
            if self._expire_command_if_needed(now):
                return self.drain_outputs()

            target = drive["velocity"]
            velocity = {
                "vx": self._slew(
                    self._last_velocity["vx"], target["vx"], self._linear_slew * elapsed
                ),
                "vy": self._slew(
                    self._last_velocity["vy"], target["vy"], self._lateral_slew * elapsed
                ),
                "wz": self._slew(
                    self._last_velocity["wz"], target["wz"], self._angular_slew * elapsed
                ),
            }
            self._last_velocity = velocity
            self._last_command_source = str(drive["input_source"])
            self._last_command_deadman = True
            self._motion_active = any(abs(value) > 1e-9 for value in velocity.values())
            self._stop_emitted = not self._motion_active
            self._outputs.append(
                {
                    "type": "drive",
                    "seq": drive["seq"],
                    "input_source": drive["input_source"],
                    "velocity": dict(velocity),
                    "created_at": now,
                }
            )
            return self.drain_outputs()

    def drain_outputs(self) -> list[dict[str, Any]]:
        with self._lock:
            result = list(self._outputs)
            self._outputs.clear()
            return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            self._expire_if_needed(now)
            self._expire_command_if_needed(now)
            bridge_fresh = (
                self._bridge_seen is not None
                and now - self._bridge_seen < self._bridge_stale_s
            )
            lowstate_fresh = (
                self._lowstate_seen is not None
                and now - self._lowstate_seen < self._lowstate_stale_s
            )
            return {
                "enabled": self._enabled,
                "configured": self._configured,
                "ready": self._ready_at(now),
                "closed": self._closed,
                "estop": {
                    "latched": self._estop_latched,
                    "reason": self._estop_reason or None,
                },
                "readiness": {
                    "bridge_fresh": bridge_fresh,
                    "lowstate_fresh": lowstate_fresh,
                },
                "action_guard": {
                    "active": self._action_guard_remaining(now) > 0.0,
                    "action": self._action_guard_name or None,
                    "remaining_s": round(self._action_guard_remaining(now), 2),
                },
                "lease": self._lease_public(now),
                "command": {
                    "source": self._last_command_source,
                    "deadman": self._last_command_deadman,
                    "linear_x": self._last_velocity["vx"],
                    "linear_y": self._last_velocity["vy"],
                    "angular_z": self._last_velocity["wz"],
                },
                "limits": {
                    "vx_mps": self._vx_limit,
                    "vy_mps": self._vy_limit,
                    "wz_rps": self._wz_limit,
                    "default_speed_scale": self._default_speed_scale,
                    "speed_scale": [self.MIN_SPEED_SCALE, self.MAX_SPEED_SCALE],
                    "command_timeout_s": self._command_timeout_s,
                    "heartbeat_timeout_s": self._lease_heartbeat_s,
                    "bind_timeout_s": self._lease_bind_s,
                },
                "input_sources": sorted(INPUT_SOURCES),
                "actions": [
                    {
                        "id": name,
                        "api_id": action_id,
                        "name": ACTION_METADATA.get(name, {}).get("label", name),
                        "category": ACTION_METADATA.get(name, {}).get("category", "action"),
                        "description": ACTION_METADATA.get(name, {}).get(
                            "description", "서버 허용 목록에 등록된 Go2 동작입니다."
                        ),
                        "confirmation_required": name in CONFIRM_ACTIONS,
                    }
                    for name, action_id in self._allowed_actions.items()
                ],
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            now = self._now()
            self._lease = None
            self._drive = None
            self._actions.clear()
            self._action_guard_until = 0.0
            self._action_guard_name = ""
            self._emit_stop("manager_closed", now, force=True)
            self._closed = True


__all__ = [
    "ACTION_METADATA",
    "ACTION_GUARD_S",
    "CONFIRM_ACTIONS",
    "INTERNAL_NAVIGATION_SOURCE",
    "INPUT_SOURCES",
    "SAFE_ACTIONS",
    "ClientFrameClock",
    "CommandValidationError",
    "ControlClosed",
    "ControlDisabled",
    "ControlError",
    "ControlManager",
    "ControlNotReady",
    "EmergencyStopLatched",
    "LeaseBindingError",
    "LeaseBusy",
    "LeaseInvalid",
    "SequenceError",
]
