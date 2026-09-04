"""Strict OrderSheet normalization and the ORDER_SEQUENCE_20S policy."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime
from typing import Any, Callable, Mapping

from .catalog import CATALOG_REVISION, competition_catalog


ORDER_SCHEMA_VERSION = 1
ORDER_ID_RE = re.compile(r"^[0-9a-f]{32}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_LINES = 5
MAX_LABEL_CHARS = 64


class OrderValidationError(ValueError):
    """A bounded public OrderSheet validation failure."""


def _label(value: object) -> str:
    if not isinstance(value, str):
        raise OrderValidationError("order label must be text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > MAX_LABEL_CHARS:
        raise OrderValidationError("order label must contain 1 to 64 characters")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise OrderValidationError("order label contains unsupported characters")
    return normalized


def _timestamp(value: object) -> str | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str) or len(value) > 32:
        raise OrderValidationError("order_started_at is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrderValidationError("order_started_at is invalid") from exc
    if parsed.tzinfo is None:
        raise OrderValidationError("order_started_at must include a timezone")
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _difficulty(restaurants: int, items: int) -> str:
    if (restaurants, items) == (2, 3):
        return "LOW"
    if (restaurants, items) == (2, 4):
        return "MEDIUM"
    if (restaurants, items) == (3, 5):
        return "HIGH"
    return "CUSTOM"


def _canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ORDER_SCHEMA_VERSION,
        "id": value["id"],
        "label": value["label"],
        "destination_id": value["destination_id"],
        "lines": value["lines"],
        "total_quantity": value["total_quantity"],
        "difficulty": value["difficulty"],
        "order_started_at": value["order_started_at"],
        "locked": value["locked"],
        "catalog_revision": CATALOG_REVISION,
    }


def order_revision(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_order(
    payload: Mapping[str, Any],
    *,
    order_id: str | None = None,
    identifier_factory: Callable[[], str] | None = None,
    allow_custom: bool = False,
) -> dict[str, Any]:
    """Normalize one competition order; derived fields cannot be supplied."""

    if not isinstance(payload, Mapping):
        raise OrderValidationError("order must be an object")
    allowed = {"label", "destination_id", "lines", "order_started_at", "locked"}
    if set(payload) - allowed:
        raise OrderValidationError("order contains unsupported or derived fields")
    identifier = order_id or (identifier_factory or (lambda: secrets.token_hex(16)))()
    if not isinstance(identifier, str) or not ORDER_ID_RE.fullmatch(identifier):
        raise OrderValidationError("order id is invalid")
    catalog = competition_catalog()
    destinations = catalog["destinations"]
    restaurants = catalog["restaurants"]
    destination_id = payload.get("destination_id")
    if destination_id not in destinations:
        raise OrderValidationError("destination is not registered")
    lines = payload.get("lines")
    if not isinstance(lines, list) or not 2 <= len(lines) <= MAX_LINES:
        raise OrderValidationError("order must contain 2 to 5 lines")
    destination_zone = destinations[destination_id]["zone_id"]
    normalized_lines: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    cumulative_quantity = 0
    for line in lines:
        if not isinstance(line, Mapping) or set(line) != {"sequence", "restaurant_id", "menu_id", "quantity"}:
            raise OrderValidationError("order line schema is invalid")
        sequence = line.get("sequence")
        quantity = line.get("quantity")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1 or sequence > MAX_LINES:
            raise OrderValidationError("order line sequence is invalid")
        if sequence in seen_sequences:
            raise OrderValidationError("order line sequences must be unique")
        seen_sequences.add(sequence)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0 or quantity > 5:
            raise OrderValidationError("order line quantity must be a positive integer")
        restaurant_id = line.get("restaurant_id")
        menu_id = line.get("menu_id")
        restaurant = restaurants.get(restaurant_id)
        if restaurant is None:
            raise OrderValidationError("restaurant is not registered")
        if restaurant["zone_id"] == destination_zone:
            raise OrderValidationError("destination-zone restaurant is excluded")
        if menu_id not in restaurant["menu"]:
            raise OrderValidationError("menu does not belong to restaurant")
        normalized_lines.append(
            {
                "sequence": sequence,
                "restaurant_id": restaurant_id,
                "menu_id": menu_id,
                "quantity": quantity,
            }
        )
    normalized_lines.sort(key=lambda item: item["sequence"])
    if [item["sequence"] for item in normalized_lines] != list(range(1, len(normalized_lines) + 1)):
        raise OrderValidationError("order line sequences must be continuous from 1")
    cumulative_quantity = 0
    for item in normalized_lines:
        cumulative_quantity += int(item["quantity"])
        item["ready_at_s"] = cumulative_quantity * int(catalog["production"]["seconds_per_item"])
    restaurant_count = len({item["restaurant_id"] for item in normalized_lines})
    if restaurant_count < int(catalog["minimum_restaurants"]):
        raise OrderValidationError("order must include at least two restaurants")
    if not int(catalog["minimum_items"]) <= cumulative_quantity <= int(catalog["capacity"]):
        raise OrderValidationError("total quantity must be between 3 and 5")
    difficulty = _difficulty(restaurant_count, cumulative_quantity)
    if difficulty == "CUSTOM" and not allow_custom:
        raise OrderValidationError("order does not match a competition difficulty shape")
    locked = payload.get("locked", False)
    if not isinstance(locked, bool):
        raise OrderValidationError("locked must be boolean")
    value: dict[str, Any] = {
        "schema_version": ORDER_SCHEMA_VERSION,
        "id": identifier,
        "label": _label(payload.get("label", "Competition order")),
        "destination_id": destination_id,
        "lines": normalized_lines,
        "total_quantity": cumulative_quantity,
        "restaurant_count": restaurant_count,
        "difficulty": difficulty,
        "order_started_at": _timestamp(payload.get("order_started_at")),
        "locked": locked,
        "catalog_revision": CATALOG_REVISION,
    }
    value["revision"] = order_revision(value)
    return value


__all__ = [
    "MAX_LINES",
    "ORDER_ID_RE",
    "ORDER_SCHEMA_VERSION",
    "OrderValidationError",
    "normalize_order",
    "order_revision",
]
