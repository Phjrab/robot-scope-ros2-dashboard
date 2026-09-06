#!/usr/bin/env python3
"""Bounded JSON stdin/stdout wrapper for D1 offline development only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_dashboard.relocalization.models import MAX_INPUT_BYTES  # noqa: E402
from robot_dashboard.relocalization.process_adapter import (  # noqa: E402
    OfflineRegistrationProcess,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one offline registration JSON request")
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, action="append", required=True)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        print("registration request is oversized", file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw)
        result = OfflineRegistrationProcess(args.executable, args.allowed_root).run(payload)
    except Exception:
        print("offline registration rejected", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(result, allow_nan=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
