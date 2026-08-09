"""Authenticated same-host protocol for the Robot Scope control bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from typing import Any, Mapping


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 8_192
MIN_SHARED_KEY_BYTES = 32


class ControlProtocolError(ValueError):
    """Raised when a bridge message is malformed, stale, or unauthenticated."""


def shared_key(value: str | bytes) -> bytes:
    key = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    if len(key) < MIN_SHARED_KEY_BYTES:
        raise ControlProtocolError(
            f"bridge key must contain at least {MIN_SHARED_KEY_BYTES} bytes"
        )
    return key


def _reject_constant(value: str) -> None:
    raise ControlProtocolError(f"non-finite JSON value is not allowed: {value}")


def _canonical(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ControlProtocolError("bridge payload is not valid JSON") from exc


def encode_signed(
    payload: Mapping[str, Any],
    key: str | bytes,
    *,
    now: float | None = None,
) -> str:
    body = dict(payload)
    body.pop("mac", None)
    body["version"] = PROTOCOL_VERSION
    body["issued_at_ms"] = int((time.time() if now is None else now) * 1_000)
    body["mac"] = hmac.new(shared_key(key), _canonical(body), hashlib.sha256).hexdigest()
    encoded = json.dumps(body, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ControlProtocolError("bridge message is too large")
    return encoded


def decode_signed(
    encoded: str,
    key: str | bytes,
    *,
    now: float | None = None,
    max_age_s: float = 3.0,
) -> dict[str, Any]:
    if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ControlProtocolError("bridge message is missing or too large")
    try:
        body = json.loads(encoded, parse_constant=_reject_constant)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ControlProtocolError("bridge message is not valid JSON") from exc
    if not isinstance(body, dict):
        raise ControlProtocolError("bridge message must be a JSON object")

    supplied_mac = body.pop("mac", None)
    if not isinstance(supplied_mac, str) or len(supplied_mac) != 64:
        raise ControlProtocolError("bridge message has no valid signature")
    expected_mac = hmac.new(
        shared_key(key), _canonical(body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_mac, expected_mac):
        raise ControlProtocolError("bridge message signature does not match")
    if body.get("version") != PROTOCOL_VERSION:
        raise ControlProtocolError("unsupported bridge protocol version")

    issued_at_ms = body.get("issued_at_ms")
    if isinstance(issued_at_ms, bool) or not isinstance(issued_at_ms, int):
        raise ControlProtocolError("bridge message timestamp is invalid")
    current = time.time() if now is None else now
    age_s = abs(current - issued_at_ms / 1_000.0)
    if not math.isfinite(age_s) or age_s > max(0.1, float(max_age_s)):
        raise ControlProtocolError("bridge message is stale")
    return body
