#!/usr/bin/env python3
"""Build or verify one immutable Robot Scope competition release package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_dashboard.release_package import (  # noqa: E402
    OfflineReleaseBuilder,
    ReleasePackageError,
    load_release_manifest,
    verify_offline_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify an immutable, offline Robot Scope release",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-manifest")
    validate.add_argument("manifest", type=Path)
    build = commands.add_parser("build")
    build.add_argument("manifest", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("package", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-manifest":
            manifest = load_release_manifest(args.manifest)
            result = {
                "ok": True,
                "release_id": manifest["release_id"],
                "git_commit": manifest["git_commit"],
            }
        elif args.command == "build":
            output = OfflineReleaseBuilder(ROOT).build(args.manifest)
            result = {"ok": True, "package": str(output), **verify_offline_package(output)}
        else:
            result = verify_offline_package(args.package)
    except ReleasePackageError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
