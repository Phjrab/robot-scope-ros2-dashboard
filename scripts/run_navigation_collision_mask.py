#!/usr/bin/env python3
"""Publish one exact-pinned mask on the explicitly selected ROS environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_dashboard.navigation_collision_profile import load_collision_mask
from robot_dashboard.ros.collision_mask_publisher import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-digest", required=True)
    args = parser.parse_args(argv)
    try:
        artifact = load_collision_mask(args.artifact, expected_digest=args.artifact_digest)
        return run(artifact)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "reason": type(exc).__name__,
                          "runtime_policy_enforced": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
