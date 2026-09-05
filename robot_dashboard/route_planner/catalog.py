"""Immutable Track G competition catalog and planner configuration."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


CATALOG_SCHEMA_VERSION = 1

_CATALOG: dict[str, Any] = {
    "schema_version": CATALOG_SCHEMA_VERSION,
    "zones": [
        {"id": "ZONE_1", "restaurant_id": "DOMINO", "destination_id": "COEX", "label": "Zone 1"},
        {"id": "ZONE_2", "restaurant_id": "HANSOT", "destination_id": "WHIMOON", "label": "Zone 2"},
        {"id": "ZONE_3", "restaurant_id": "EDIYA", "destination_id": "GANGNAM_POLICE", "label": "Zone 3"},
        {"id": "ZONE_4", "restaurant_id": None, "destination_id": "GTX_SITE", "label": "Zone 4"},
    ],
    "restaurants": {
        "DOMINO": {
            "label": "도미노피자",
            "zone_id": "ZONE_1",
            "menu": {
                "SUPER_SUPREME": "슈퍼슈프림피자",
                "CHEESE_PIZZA": "치즈피자",
            },
        },
        "HANSOT": {
            "label": "한솥도시락",
            "zone_id": "ZONE_2",
            "menu": {
                "SPAM_KIMCHI": "스팸김치도시락",
                "CHICKEN_MAYO": "치킨마요도시락",
            },
        },
        "EDIYA": {
            "label": "이디야커피",
            "zone_id": "ZONE_3",
            "menu": {
                "AMERICANO": "아메리카노",
                "CAFE_LATTE": "카페라떼",
            },
        },
    },
    "destinations": {
        "COEX": {"label": "코엑스", "zone_id": "ZONE_1"},
        "WHIMOON": {"label": "휘문고등학교", "zone_id": "ZONE_2"},
        "GANGNAM_POLICE": {"label": "강남경찰서", "zone_id": "ZONE_3"},
        "GTX_SITE": {"label": "GTX 공사현장", "zone_id": "ZONE_4"},
    },
    "production": {"seconds_per_item": 20, "policy": "ORDER_SEQUENCE_20S"},
    "capacity": 5,
    "minimum_items": 3,
    "minimum_restaurants": 2,
    "crosswalk_violation_feet_outside": 3,
    "underpass_semantic": "UNDERPASS",
    "underpass_aliases": ["UNDERPASS", "OVERPASS"],
    "profiles": {
        "BALANCED": {"time": 1.0, "risk": 4.0, "crosswalk": 2.0, "underpass": 4.0, "turn": 0.5},
        "FASTEST": {"time": 1.0, "risk": 0.5, "crosswalk": 0.5, "underpass": 0.5, "turn": 0.1},
        "SAFEST": {"time": 0.35, "risk": 12.0, "crosswalk": 8.0, "underpass": 12.0, "turn": 1.0},
    },
}


def _revision() -> str:
    encoded = json.dumps(_CATALOG, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def competition_catalog() -> dict[str, Any]:
    """Return a defensive copy of the server-owned fixed catalog."""

    value = copy.deepcopy(_CATALOG)
    value["revision"] = _revision()
    return value


CATALOG_REVISION = _revision()

__all__ = ["CATALOG_REVISION", "CATALOG_SCHEMA_VERSION", "competition_catalog"]
