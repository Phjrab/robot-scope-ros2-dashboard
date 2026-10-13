#!/usr/bin/env python3
"""Inventory and preserve explicitly selected durable data in a new directory.

This offline utility never contacts a robot or manages services. Private
manifests contain relative filenames, byte counts and SHA-256 only. It does not
copy environments, credentials, live control state or whole runtime trees.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "robot-scope.onboard-data/v1"
KINDS = ("maps", "datasets", "settings", "routes", "models", "calibration", "events", "mission-history")
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 100_000
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
BLOCKED_PARTS = frozenset({".git", ".ssh", ".venv", "build", "install", "log", "logs",
                           "control", "leases", "commands", "jobs", "competition"})


class MigrationError(ValueError):
    """A data bundle is unsafe or no longer matches its inventory."""


def _path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or value != path.as_posix()
            or any(part in {".", ".."} or part.startswith(".") for part in path.parts)
            or any(part.casefold() in BLOCKED_PARTS for part in path.parts)):
        raise MigrationError("selected paths must be safe relative durable-data paths")
    return path


def _allowed(kind: str, path: PurePosixPath) -> bool:
    name = path.name.casefold()
    if name.endswith((".env", ".key", ".pem", ".bag", ".db3")):
        return False
    if kind == "maps":
        return name.endswith((".pcd", ".pgm", ".yaml", ".yml", ".map-family.json", ".annotations.json"))
    if kind == "settings":
        return name in {"source-selection.json", "presets.json"}
    if kind == "routes":
        return (name == "route-planner.json" or name.endswith(".current")
                or re.fullmatch(r"[0-9a-f]{24}\.[0-9a-f]{64}\.json", name) is not None)
    if kind == "calibration":
        return name in {"xt16-correction.csv", "xt16-calibration.manifest"}
    if kind == "events":
        return re.fullmatch(r"operator-events\.jsonl(?:\.[0-9]+)?", name) is not None
    if kind == "mission-history":
        return name == "missions.json"
    if kind == "datasets":
        # Existing server-produced exports are preserved as opaque files. This
        # utility never extracts ZIP members or treats them as runtime inputs.
        if len(path.parts) == 2 and path.parts[0] == "exports":
            return re.fullmatch(r"[0-9a-f]{32}\.(json|zip)", name) is not None
        return name in {"manifest.json", "metadata.json", "sha256sums.json"} or name.endswith((".jpg", ".jpeg"))
    if kind == "models":
        return name in {"registry.json", "labels.yaml", "metadata.json", "evaluation.json", "sha256.txt", "engine-validation.json"} or name.endswith((".onnx", ".engine", ".plan", ".manifest.json"))
    return False


def _real_path(path: Path, *, directory: bool) -> Path:
    if not path.is_absolute() or path == Path("/"):
        raise MigrationError("paths must be absolute and cannot be filesystem root")
    if path.resolve(strict=True) != path:
        raise MigrationError("paths cannot contain symlinks or traversal")
    details = path.lstat()
    if directory != stat.S_ISDIR(details.st_mode):
        raise MigrationError("path has an unexpected file type")
    if not directory and (not stat.S_ISREG(details.st_mode) or details.st_nlink != 1):
        raise MigrationError("data must use regular files without hardlinks")
    return path


def _digest(path: Path) -> tuple[int, str]:
    _real_path(path, directory=False)
    before = path.stat()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    count = 0
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_ino, opened.st_dev) != (before.st_ino, before.st_dev):
            raise MigrationError("data changed while opening")
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns) or count != before.st_size:
        raise MigrationError("data changed while hashing")
    return count, digest.hexdigest()


def inventory(root: Path, kind: str, selections: list[str]) -> dict[str, Any]:
    _real_path(root, directory=True)
    if kind not in KINDS or not selections:
        raise MigrationError("one durable-data kind and explicit selections are required")
    chosen: set[str] = set()
    for value in selections:
        relative = _path(value)
        selected = root.joinpath(*relative.parts)
        if selected.is_symlink():
            raise MigrationError("selected data cannot be a symlink")
        candidates = selected.rglob("*") if selected.is_dir() else (selected,)
        for candidate in candidates:
            if candidate.is_symlink():
                raise MigrationError("selected data cannot contain symlinks")
            if candidate.is_dir():
                continue
            item = _path(candidate.relative_to(root).as_posix())
            if not _allowed(kind, item):
                raise MigrationError("selection contains unsupported or transient data")
            chosen.add(item.as_posix())
            if len(chosen) > MAX_FILES:
                raise MigrationError("data inventory exceeds the file limit")
    if not chosen:
        raise MigrationError("selection has no durable files")
    files = []
    for name in sorted(chosen):
        size, digest = _digest(root / name)
        files.append({"path": name, "bytes": size, "sha256": digest})
    return {"schema": SCHEMA, "kind": kind, "files": files}


def validate_manifest(value: Any) -> dict[str, Any]:
    if (not isinstance(value, dict) or set(value) != {"schema", "kind", "files"}
            or value["schema"] != SCHEMA or not isinstance(value["kind"], str) or value["kind"] not in KINDS
            or not isinstance(value["files"], list) or not 1 <= len(value["files"]) <= MAX_FILES):
        raise MigrationError("data manifest is invalid")
    names = set()
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise MigrationError("manifest entry is invalid")
        if not isinstance(item["path"], str):
            raise MigrationError("manifest path is invalid")
        relative = _path(item["path"])
        if (not _allowed(value["kind"], relative) or item["path"] in names
                or type(item["bytes"]) is not int or item["bytes"] < 0
                or not isinstance(item["sha256"], str) or not HASH_PATTERN.fullmatch(item["sha256"])):
            raise MigrationError("manifest entry violates its durable-data contract")
        names.add(item["path"])
    return value


def read_manifest(path: Path) -> dict[str, Any]:
    _real_path(path, directory=False)
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise MigrationError("data manifest exceeds the size limit")
    return validate_manifest(json.loads(path.read_text(encoding="utf-8")))


def verify(root: Path, document: dict[str, Any], *, exact: bool = False) -> dict[str, int]:
    _real_path(root, directory=True)
    validate_manifest(document)
    total = 0
    for item in document["files"]:
        size, digest = _digest(root / item["path"])
        if (size, digest) != (item["bytes"], item["sha256"]):
            raise MigrationError("data does not match the inventory")
        total += size
    if exact:
        actual = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise MigrationError("copied bundle contains a symlink")
            if not path.is_dir():
                actual.add(path.relative_to(root).as_posix())
        if actual != {item["path"] for item in document["files"]}:
            raise MigrationError("copied bundle has unlisted data")
    return {"files": len(document["files"]), "bytes": total}


def copy_bundle(source: Path, destination: Path, document: dict[str, Any]) -> dict[str, int]:
    verify(source, document)
    if not destination.is_absolute() or destination == Path("/"):
        raise MigrationError("destination must be an absolute new directory")
    _real_path(destination.parent, directory=True)
    if os.path.lexists(destination):
        raise MigrationError("destination already exists; nothing was overwritten")
    destination.mkdir(mode=0o700)
    # A failed partial copy is preserved for diagnosis. It must never be
    # selected as the runtime directory before a successful exact verification.
    for item in document["files"]:
        target = destination / item["path"]
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _real_path(target.parent, directory=True)
        source_path = source / item["path"]
        _real_path(source_path, directory=False)
        reader = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(reader, "rb") as incoming:
            writer = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(writer, "wb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    outgoing.write(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
    return verify(destination, document, exact=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    make = subparsers.add_parser("inventory")
    make.add_argument("--root", type=Path, required=True)
    make.add_argument("--kind", choices=KINDS, required=True)
    make.add_argument("--include", action="append", required=True)
    make.add_argument("--manifest", type=Path, required=True)
    for action in ("verify", "copy"):
        child = subparsers.add_parser(action)
        child.add_argument("--root", type=Path, required=True)
        child.add_argument("--manifest", type=Path, required=True)
        if action == "copy":
            child.add_argument("--destination", type=Path, required=True)
        else:
            child.add_argument("--exact", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "inventory":
            document = inventory(args.root, args.kind, args.include)
            _real_path(args.manifest.parent, directory=True)
            if os.path.lexists(args.manifest):
                raise MigrationError("manifest already exists; nothing was overwritten")
            encoded = json.dumps(document, sort_keys=True, indent=2).encode("utf-8") + b"\n"
            if len(encoded) > MAX_MANIFEST_BYTES:
                raise MigrationError("data manifest exceeds the size limit")
            descriptor = os.open(args.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(encoded)
            result = {"files": len(document["files"]), "bytes": sum(item["bytes"] for item in document["files"])}
        elif args.action == "copy":
            result = copy_bundle(args.root, args.destination, read_manifest(args.manifest))
        else:
            result = verify(args.root, read_manifest(args.manifest), exact=args.exact)
        print(json.dumps({"status": "PASS", **result}, sort_keys=True))
        return 0
    except (MigrationError, OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, MigrationError) else type(exc).__name__
        print(json.dumps({"status": "FAIL", "reason": reason}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
