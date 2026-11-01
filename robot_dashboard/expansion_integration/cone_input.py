"""Bounded legacy display input, adapted from teammate 447d45e9451a6dcc.

Original author: hjj021717-netizen. The original store/feed/router are excluded.
This validator grants no source authority, state, freshness or frame transform.
"""

import json
import math
import re
from typing import Any, Dict, Mapping, NoReturn

SCHEMA = "robot-scope.obstacle-map/v1"

# One cone per detector track.  The arena course is a slalom, not a crowd, so
# a hard ceiling keeps the response bounded without a paging contract.
MAX_CONES = 64
MAX_ABS_COORDINATE_M = 1000.0
MIN_RADIUS_M = 0.01
MAX_RADIUS_M = 2.0
MIN_HEIGHT_M = 0.01
MAX_HEIGHT_M = 3.0
MAX_OBSERVATION_COUNT = 1_000_000
MAX_STAMP_S = 2.0**53
MAX_FPS = 1000.0
MAX_MODEL_PATH_CHARS = 256

# Matches the perception receiver: a last-good projection is never kept LIVE
# through transport loss.
STALE_AFTER_NS = 2_000_000_000

FRAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_/.-]{0,63}\Z")
SHA256_12_PATTERN = re.compile(r"[0-9a-f]{12}\Z")
MODEL_PATH_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:+-]{0,255}\Z")

PAYLOAD_KEYS = frozenset(
    {"schema_version", "stamp", "frame", "model", "health", "cones"}
)
MODEL_KEYS = frozenset({"path", "sha256_12"})
HEALTH_KEYS = frozenset({"stale", "fps"})
CONE_KEYS = frozenset({"id", "x", "y", "n", "radius_m", "height_m"})


class ObstacleValidationError(ValueError):
    """A payload failed the fixed obstacle-map contract."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _integer(value: object, minimum: int, maximum: int, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ObstacleValidationError(code)
    return value


def _number(value: object, minimum: float, maximum: float, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObstacleValidationError(code)
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ObstacleValidationError(code)
    return result


def _boolean(value: object, code: str) -> bool:
    if not isinstance(value, bool):
        raise ObstacleValidationError(code)
    return value


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], code: str
) -> None:
    if frozenset(value) != expected:
        raise ObstacleValidationError(code)


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ObstacleValidationError(code)
    return value


class _Validator:
    def _reject(self, code: str) -> NoReturn:
        raise ObstacleValidationError(code)

    def _validated_model(self, value: object) -> Dict[str, str]:
        model = _mapping(value, "MALFORMED_MODEL")
        if frozenset(model) != MODEL_KEYS:
            self._reject("MALFORMED_MODEL")
        path = model["path"]
        digest = model["sha256_12"]
        if (
            not isinstance(path, str)
            or len(path) > MAX_MODEL_PATH_CHARS
            or not MODEL_PATH_PATTERN.fullmatch(path)
        ):
            self._reject("INVALID_MODEL_PATH")
        if not isinstance(digest, str) or not SHA256_12_PATTERN.fullmatch(digest):
            self._reject("INVALID_MODEL_DIGEST")
        return {"path": str(path), "sha256_12": str(digest)}

    def _validated_health(self, value: object) -> Dict[str, Any]:
        health = _mapping(value, "MALFORMED_HEALTH")
        if frozenset(health) != HEALTH_KEYS:
            self._reject("MALFORMED_HEALTH")
        return {
            "stale": _boolean(health["stale"], "INVALID_HEALTH_STALE"),
            "fps": _number(health["fps"], 0.0, MAX_FPS, "INVALID_HEALTH_FPS"),
        }

    def _validated_cones(self, value: object) -> list[Dict[str, Any]]:
        if not isinstance(value, list) or len(value) > MAX_CONES:
            self._reject("CONE_LIMIT")
        cones: list[Dict[str, Any]] = []
        seen: set[int] = set()
        for raw in value:
            cone = _mapping(raw, "MALFORMED_CONE")
            if frozenset(cone) != CONE_KEYS:
                self._reject("MALFORMED_CONE")
            identifier = _integer(cone["id"], 0, 2**31 - 1, "INVALID_CONE_ID")
            if identifier in seen:
                self._reject("DUPLICATE_CONE_ID")
            seen.add(identifier)
            cones.append(
                {
                    "id": identifier,
                    "x": _number(
                        cone["x"],
                        -MAX_ABS_COORDINATE_M,
                        MAX_ABS_COORDINATE_M,
                        "COORDINATE_OUT_OF_RANGE",
                    ),
                    "y": _number(
                        cone["y"],
                        -MAX_ABS_COORDINATE_M,
                        MAX_ABS_COORDINATE_M,
                        "COORDINATE_OUT_OF_RANGE",
                    ),
                    "n": _integer(
                        cone["n"], 0, MAX_OBSERVATION_COUNT, "INVALID_OBSERVATION_COUNT"
                    ),
                    "radius_m": _number(
                        cone["radius_m"],
                        MIN_RADIUS_M,
                        MAX_RADIUS_M,
                        "RADIUS_OUT_OF_RANGE",
                    ),
                    "height_m": _number(
                        cone["height_m"],
                        MIN_HEIGHT_M,
                        MAX_HEIGHT_M,
                        "HEIGHT_OUT_OF_RANGE",
                    ),
                }
            )
        return cones

    def _validated(self, payload: object) -> Dict[str, Any]:
        value = _mapping(payload, "MALFORMED_PAYLOAD")
        if frozenset(value) != PAYLOAD_KEYS:
            self._reject("MALFORMED_PAYLOAD")
        if value["schema_version"] != SCHEMA:
            self._reject("UNKNOWN_SCHEMA")
        stamp = _number(value["stamp"], 0.0, MAX_STAMP_S, "INVALID_STAMP")
        frame = value["frame"]
        if not isinstance(frame, str) or not FRAME_PATTERN.fullmatch(frame):
            self._reject("INVALID_FRAME")
        return {
            "schema_version": SCHEMA,
            "stamp": stamp,
            "frame": str(frame),
            "model": self._validated_model(value["model"]),
            "health": self._validated_health(value["health"]),
            "cones": self._validated_cones(value["cones"]),
        }


def validate_legacy_cones(payload):
    try:
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ObstacleValidationError("INVALID_JSON_VALUE") from exc
    if len(encoded) > 64 * 1024:
        raise ObstacleValidationError("PAYLOAD_LIMIT")
    return _Validator()._validated(payload)
