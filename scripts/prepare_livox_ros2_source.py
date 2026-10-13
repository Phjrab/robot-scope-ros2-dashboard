#!/usr/bin/env python3
"""Prepare a separate Livox ROS2 package without modifying the pinned clone.

The pinned upstream build.sh replaces package.xml and deletes build/install
trees. This prepares its ROS2 XML/launch selection in a separate source copy;
the bootstrap then invokes bounded colcon directly without upstream deletions.
An existing copy must match exactly and is never reset or overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path
from typing import Sequence


def inventory(root: Path) -> dict[str, tuple[str, str]]:
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise ValueError("Livox source copy must not contain symlinks")
        if path.is_dir():
            result[relative.as_posix()] = ("directory", "")
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[relative.as_posix()] = ("file", digest.hexdigest())
        else:
            raise ValueError("Livox source copy contains a non-regular entry")
    return result


def prepare(source: Path, destination: Path) -> Path:
    if not source.is_absolute() or not destination.is_absolute() or source == Path("/") or destination == Path("/"):
        raise ValueError("Livox source and destination must be absolute non-root paths")
    if not source.is_dir() or source.is_symlink() or destination.is_symlink():
        raise ValueError("Livox source and destination must be real directories")
    source = source.resolve()
    for parent in destination.parents:
        if parent.is_symlink():
            raise ValueError("Livox staging path must not contain symlinks")
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Livox source and staging trees must be separate")
    expected = inventory(source)
    if "package_ROS2.xml" not in expected or not (source / "launch_ROS2").is_dir():
        raise ValueError("pinned Livox ROS2 package or launch source is missing")
    if "launch" in expected:
        raise ValueError("pinned Livox clone has an unexpected existing launch selection")
    expected["package.xml"] = expected["package_ROS2.xml"]
    expected["launch"] = ("directory", "")
    for relative, value in inventory(source / "launch_ROS2").items():
        expected["launch/" + relative] = value
    if destination.exists():
        if not destination.is_dir() or inventory(destination) != expected:
            raise ValueError("existing Livox ROS2 staging differs; preserving it without reset")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
    shutil.copy2(source / "package_ROS2.xml", destination / "package.xml")
    shutil.copytree(source / "launch_ROS2", destination / "launch")
    if inventory(destination) != expected:
        raise ValueError("new Livox ROS2 staging checksum verification failed")
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        destination = prepare(args.source, args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Livox source preparation failed: {exc}\n")
    print(f"Verified separate Livox ROS2 source: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
