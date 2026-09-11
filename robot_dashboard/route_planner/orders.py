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


ORDER_SCHEMA_VERSION = 2
ORDER_ID_RE = re.compile(r"^[0-9a-f]{32}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_LINES = 5
MAX_ORDERS = MAX_LINES
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


def _batch_difficulty(order_count: int) -> str:
    if order_count <= 2:
        return "LOW"
    if order_count <= 4:
        return "MEDIUM"
    return "HIGH"


def _canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **({"orders": value["orders"]} if "orders" in value else {}),
        "schema_version": ORDER_SCHEMA_VERSION,
        "id": value["id"],
        "label": value["label"],
        "destination_id": value["destination_id"],
        "destination_ids": value["destination_ids"],
        "lines": value["lines"],
        "order_count": value["order_count"],
        "order_mode": value["order_mode"],
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
    if "orders" in payload:
        return _normalize_sheets(payload, order_id=order_id, identifier_factory=identifier_factory)
    allowed = {"label", "destination_id", "lines", "order_started_at", "locked"}
    if set(payload) - allowed:
        raise OrderValidationError("order contains unsupported or derived fields")
    identifier = order_id or (identifier_factory or (lambda: secrets.token_hex(16)))()
    if not isinstance(identifier, str) or not ORDER_ID_RE.fullmatch(identifier):
        raise OrderValidationError("order id is invalid")
    catalog = competition_catalog()
    destinations = catalog["destinations"]
    restaurants = catalog["restaurants"]
    lines = payload.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES:
        raise OrderValidationError("order batch must contain 1 to 5 order sheets")
    legacy_destination_id = payload.get("destination_id")
    line_destination_presence = [
        isinstance(line, Mapping) and "destination_id" in line for line in lines
    ]
    if any(line_destination_presence):
        if not all(line_destination_presence) or legacy_destination_id is not None:
            raise OrderValidationError("use either one legacy destination or one destination per order sheet")
        order_mode = "MULTI_DESTINATION"
    else:
        if legacy_destination_id not in destinations:
            raise OrderValidationError("destination is not registered")
        order_mode = "LEGACY_SINGLE_DESTINATION"
    normalized_lines: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    cumulative_quantity = 0
    for line in lines:
        expected_fields = {"sequence", "restaurant_id", "menu_id", "quantity"}
        if order_mode == "MULTI_DESTINATION":
            expected_fields.add("destination_id")
        if not isinstance(line, Mapping) or set(line) != expected_fields:
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
        destination_id = (
            line.get("destination_id")
            if order_mode == "MULTI_DESTINATION"
            else legacy_destination_id
        )
        if destination_id not in destinations:
            raise OrderValidationError("destination is not registered")
        destination_zone = destinations[destination_id]["zone_id"]
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
                "destination_id": destination_id,
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
    if order_mode == "LEGACY_SINGLE_DESTINATION":
        if restaurant_count < int(catalog["minimum_restaurants"]):
            raise OrderValidationError("order must include at least two restaurants")
        if not int(catalog["minimum_items"]) <= cumulative_quantity <= int(catalog["capacity"]):
            raise OrderValidationError("total quantity must be between 3 and 5")
        difficulty = _difficulty(restaurant_count, cumulative_quantity)
        if difficulty == "CUSTOM" and not allow_custom:
            raise OrderValidationError("order does not match a competition difficulty shape")
    else:
        if cumulative_quantity > int(catalog["capacity"]):
            raise OrderValidationError("total quantity must be between 1 and 5")
        difficulty = _batch_difficulty(len(normalized_lines))
    destination_ids = list(
        dict.fromkeys(str(item["destination_id"]) for item in normalized_lines)
    )
    locked = payload.get("locked", False)
    if not isinstance(locked, bool):
        raise OrderValidationError("locked must be boolean")
    value: dict[str, Any] = {
        "schema_version": ORDER_SCHEMA_VERSION,
        "id": identifier,
        "label": _label(payload.get("label", "Competition order")),
        "destination_id": destination_ids[0] if len(destination_ids) == 1 else None,
        "destination_ids": destination_ids,
        "lines": normalized_lines,
        "order_count": len(normalized_lines),
        "order_mode": order_mode,
        "total_quantity": cumulative_quantity,
        "restaurant_count": restaurant_count,
        "difficulty": difficulty,
        "order_started_at": _timestamp(payload.get("order_started_at")),
        "locked": locked,
        "catalog_revision": CATALOG_REVISION,
    }
    value["revision"] = order_revision(value)
    return value


def _normalize_sheets(payload, *, order_id=None, identifier_factory=None):
    """Bounded grouped input, with legacy-normalized lines for route consumers."""
    if set(payload) - {"label", "orders", "order_started_at", "locked"}:
        raise OrderValidationError("grouped orders cannot mix legacy or derived fields")
    sheets = payload["orders"]
    if not isinstance(sheets, list) or not 1 <= len(sheets) <= MAX_ORDERS:
        raise OrderValidationError("batch must contain 1 to 5 order sheets")
    grouped, flattened = [], []
    seed = None
    for number, sheet in enumerate(sheets, 1):
        if not isinstance(sheet, Mapping) or set(sheet) != {"destination_id", "lines"}:
            raise OrderValidationError("order sheet schema is invalid")
        items = sheet["lines"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_LINES:
            raise OrderValidationError("each order sheet must contain 1 to 5 menu lines")
        normalized = []
        for index, item in enumerate(items, 1):
            if not isinstance(item, Mapping) or set(item) != {"sequence", "restaurant_id", "menu_id", "quantity"}:
                raise OrderValidationError("menu line schema is invalid")
            if isinstance(item["sequence"], bool) or not isinstance(item["sequence"], int) or item["sequence"] != index:
                raise OrderValidationError("menu sequences must be continuous integers")
            validated = normalize_order({
                "label": payload.get("label", "Competition orders"),
                "locked": payload.get("locked", False),
                "order_started_at": payload.get("order_started_at"),
                "lines": [{**item, "sequence": 1, "destination_id": sheet["destination_id"]}],
            }, order_id=seed["id"] if seed else order_id, identifier_factory=identifier_factory)
            seed = validated
            normalized.append(dict(item))
            flattened.append({**validated["lines"][0], "sequence": len(flattened) + 1,
                              "order_sequence": number, "menu_sequence": index})
        grouped.append({"destination_id": sheet["destination_id"], "lines": normalized})
    total = 0
    for line in flattened:
        total += line["quantity"]
        line["ready_at_s"] = total * int(competition_catalog()["production"]["seconds_per_item"])
    destinations = list(dict.fromkeys(line["destination_id"] for line in flattened))
    seed.update(orders=grouped, lines=flattened, order_mode="GROUPED_SHEETS",
                order_count=len(grouped), total_quantity=total,
                destination_ids=destinations,
                destination_id=destinations[0] if len(destinations) == 1 else None,
                restaurant_count=len({line["restaurant_id"] for line in flattened}),
                difficulty=_batch_difficulty(len(grouped)))
    seed["revision"] = order_revision(seed)
    return seed


__all__ = [
    "MAX_LINES",
    "MAX_ORDERS",
    "ORDER_ID_RE",
    "ORDER_SCHEMA_VERSION",
    "OrderValidationError",
    "normalize_order",
    "order_revision",
]
