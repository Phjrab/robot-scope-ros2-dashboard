#!/usr/bin/env python3
"""Validate private measurement references and compare camera/body poses offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from robot_dashboard.pose_precision import (  # noqa: E402
    EVIDENCE_ROLES,
    MAX_BYTES,
    OUTPUT_SCHEMA,
    PosePrecisionError,
    evaluate,
    require,
)


def _read(path: Path) -> bytes:
    require(path.is_file(), "regular input/evidence file required")
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "input/evidence size bound exceeded")
    return raw


def _json(raw: bytes):
    def constant(_):
        raise PosePrecisionError("nonfinite JSON constant rejected")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key rejected")
            result[key] = value
        return result

    return json.loads(raw, parse_constant=constant, object_pairs_hook=unique)


def evaluate_file(path: Path) -> dict:
    raw = _read(path)
    manifest = _json(raw)
    result = evaluate(manifest)
    # References must remain beneath the private input directory. No downloads.
    directory = path.resolve().parent
    for role in EVIDENCE_ROLES:
        item = manifest["evidence"][role]
        relative = Path(item["path"])
        require(not relative.is_absolute(), "evidence paths must be relative")
        reference = (directory / relative).resolve(strict=True)
        require(
            reference.is_relative_to(directory) and reference.is_file(),
            "evidence escapes private input directory",
        )
        reference_bytes = _read(reference)
        require(
            hashlib.sha256(reference_bytes).hexdigest() == item["sha256"],
            "evidence hash mismatch: " + role,
        )
        if role in {"estimate", "truth"}:
            require(
                _json(reference_bytes) == manifest[role],
                "pose series does not match artifact: " + role,
            )
    result["evidence_bytes_verified"] = True
    result["pose_series_artifact_semantic_match"] = True
    result["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    result["cli_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["module_sha256"] = hashlib.sha256(
        (ROOT / "robot_dashboard/pose_precision.py").read_bytes()
    ).hexdigest()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate_file(args.manifest)
        code = 0
    except (
        ValueError,
        OSError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
    ) as error:
        result = {
            "schema": OUTPUT_SCHEMA,
            "status": "BLOCKED",
            "reason": str(error),
            "position_error_m": None,
            "rotation_error_rad": None,
            "accuracy_acceptance": False,
            "body_extrinsic_qualified_by_tool": False,
            "operational_application": "NOT_RUN",
        }
        code = 2
    # Exclusive create also rejects existing outputs and symlinks; never overwrite evidence.
    try:
        descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as error:
        parser.error(str(error))
    with os.fdopen(descriptor, "w") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
