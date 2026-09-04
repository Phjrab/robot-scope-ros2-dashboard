#!/usr/bin/env python3
"""Replay one allowlisted Route Planner scenario and print its JSON result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from robot_dashboard.route_planner.replay import (  # noqa: E402
    SIDE_EFFECT_COUNTERS,
    ScenarioReplayError,
    replay_scenario_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic software-only Route Planner scenario replay"
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="JSON fixture below tests/fixtures/route_planner/scenarios",
    )
    arguments = parser.parse_args()
    try:
        result = replay_scenario_file(arguments.scenario)
    except ScenarioReplayError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "side_effect_count": 0,
                    "side_effect_counters": dict(SIDE_EFFECT_COUNTERS),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
    )
    return 0 if result["expected_vs_actual"]["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
