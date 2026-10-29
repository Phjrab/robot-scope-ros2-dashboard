"""Explicit verified owner module loading. No automatic fetch, install or fallback."""

import hashlib
import json
from pathlib import Path

PINS = {
    "C1": "50600c7bce6f5fae743cd836ca1d8ee68d91b05a",
    "C3": "5bf58097f4a67806f5515b931a3b8013d65bf01e",
}


def verify(directory, role):
    root = Path(directory).resolve(strict=True)
    receipt = json.loads((root / "receipt.json").read_text())
    for name, info in receipt.items():
        if info["role"] != role:
            continue
        path = root / name
        if (
            not path.resolve().is_relative_to(root)
            or path.is_symlink()
            or path.stat().st_mode & 0o222
        ):
            raise ValueError("DEPENDENCY_NOT_READONLY")
        if (
            info["sha"] != PINS[role]
            or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]
        ):
            raise ValueError("DEPENDENCY_HASH_MISMATCH")
    if not any(i["role"] == role for i in receipt.values()):
        raise ValueError("DEPENDENCY_INPUT_REQUIRED")
    return root


def c1_validator(directory):
    root = verify(directory, "C1")
    import robot_dashboard

    path = str(root / "robot_dashboard")
    if path not in robot_dashboard.__path__:
        robot_dashboard.__path__.append(path)
    from robot_dashboard.expansion_contracts import ScenePacket
    import robot_dashboard.expansion_contracts as module

    if not Path(module.__file__).resolve().is_relative_to(root):
        raise ValueError("WRONG_C1_IMPORT_ORIGIN")
    return lambda wire: ScenePacket.from_dict(wire)
