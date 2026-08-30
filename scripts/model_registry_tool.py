#!/usr/bin/env python3
"""Explicit local operator tool for WP05 model lifecycle transitions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from robot_dashboard.model_registry import ModelRegistry, ModelRegistryError
from robot_dashboard.competition import (
    CompetitionError,
    CompetitionStateManager,
    CompetitionUnavailable,
)


DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "model-registry"
DEFAULT_COMPETITION_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "competition"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage, validate, activate, or roll back a local Robot Scope model",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("archive", type=Path)
    validate = commands.add_parser("validate-engine")
    validate.add_argument("model_id")
    validate.add_argument("engine", type=Path)
    validate.add_argument("evidence", type=Path)
    validate.add_argument("build_log", type=Path)
    activate = commands.add_parser("activate")
    activate.add_argument("model_id")
    activate.add_argument("--confirm", required=True)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("task", choices=("lane", "object", "depth_summary"))
    rollback.add_argument("--confirm-active-model", required=True)
    commands.add_parser("list")
    commands.add_parser("active")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(os.environ.get("ROBOT_SCOPE_MODEL_REGISTRY_DIR") or DEFAULT_ROOT)
    try:
        registry = ModelRegistry(root)
        if args.command in {"activate", "rollback"}:
            competition_root = Path(
                os.environ.get("ROBOT_SCOPE_COMPETITION_STATE_DIR")
                or (
                    Path(os.environ["ROBOT_SCOPE_RUNTIME_DIR"]) / "competition"
                    if os.environ.get("ROBOT_SCOPE_RUNTIME_DIR")
                    else DEFAULT_COMPETITION_ROOT
                )
            )
            if not (competition_root / "state.json").is_file():
                raise CompetitionUnavailable(
                    "competition state must exist before model activation"
                )
            CompetitionStateManager(competition_root).require_unlocked(
                "model activation" if args.command == "activate" else "model rollback"
            )
        if args.command == "stage":
            result = registry.stage_archive(args.archive)
        elif args.command == "validate-engine":
            result = registry.validate_engine(
                args.model_id,
                args.engine,
                args.evidence,
                args.build_log,
            )
        elif args.command == "activate":
            result = registry.activate(args.model_id, args.confirm)
        elif args.command == "rollback":
            result = registry.rollback(args.task, args.confirm_active_model)
        elif args.command == "active":
            result = registry.active_snapshot()
        else:
            result = registry.list_models()
    except (ModelRegistryError, CompetitionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps({"ok": True, "result": result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
