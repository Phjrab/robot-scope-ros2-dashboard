"""Strict local configuration. Model class names are identities, never colors."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def identity(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value))


@dataclass(frozen=True)
class TrafficConfig:
    document: dict
    sha256: str

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {
            "schema_version", "model", "class_map", "association", "min_confidence"
        } or value["schema_version"] != "traffic-input-config.v0.1":
            raise ValueError("CONFIG_FIELDS_INVALID")
        model = value["model"]
        fields = {"sha256", "provenance", "family", "package_version", "trusted_pickle"}
        if not isinstance(model, dict) or set(model) != fields:
            raise ValueError("MODEL_FIELDS_INVALID")
        if (not isinstance(model["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", model["sha256"])
                or not isinstance(model["provenance"], str)
                or not 1 <= len(model["provenance"].strip()) <= 512
                or model["family"] != "ultralytics"
                or not isinstance(model["package_version"], str)
                or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", model["package_version"])
                or type(model["trusted_pickle"]) is not bool):
            raise ValueError("MODEL_PROVENANCE_OR_VERSION_INVALID")
        mapping = value["class_map"]
        if not isinstance(mapping, dict) or not mapping or len(mapping) > 100:
            raise ValueError("CLASS_MAP_REQUIRED")
        for key, name in mapping.items():
            if (not isinstance(key, str) or not re.fullmatch(r"0|[1-9][0-9]{0,3}", key)
                    or not isinstance(name, str) or not 1 <= len(name.strip()) <= 64):
                raise ValueError("CLASS_MAP_INVALID")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("CLASS_NAMES_AMBIGUOUS")
        a = value["association"]
        if not isinstance(a, dict) or set(a) != {
            "signal_id", "crossing_id", "binding_id", "native_image_size", "expected_roi_native", "verified"
        }:
            raise ValueError("ASSOCIATION_FIELDS_INVALID")
        if not all(identity(a[x]) for x in ("signal_id", "crossing_id", "binding_id")):
            raise ValueError("ASSOCIATION_ID_INVALID")
        if type(a["verified"]) is not bool:
            raise ValueError("ASSOCIATION_VERIFICATION_REQUIRED")
        size, roi = a["native_image_size"], a["expected_roi_native"]
        if (not isinstance(size, list) or len(size) != 2
                or any(type(n) is not int or not 1 <= n <= 8192 for n in size)
                or not isinstance(roi, list) or len(roi) != 4
                or not all(finite(n, 0, 8192) for n in roi)
                or not 0 <= roi[0] < roi[2] <= size[0]
                or not 0 <= roi[1] < roi[3] <= size[1]):
            raise ValueError("ASSOCIATION_GEOMETRY_INVALID")
        if not finite(value["min_confidence"], 0, 1):
            raise ValueError("CONFIDENCE_INVALID")
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return cls(json.loads(canonical), hashlib.sha256(canonical.encode()).hexdigest())

    @classmethod
    def read(cls, path):
        return cls.parse(json.loads(Path(path).read_text(encoding="utf-8")))
