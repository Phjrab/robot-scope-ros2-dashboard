"""Offline JSON CLI. Input files are trusted local files, never HTTP paths."""

import argparse
import json
from pathlib import Path
from . import Tracker, process_lidar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 8 * 1024 * 1024:
        parser.error("input exceeds 8 MiB")
    data = json.loads(args.input.read_text())
    observation = process_lidar(
        data["points"],
        data["meta"],
        ground=data.get("ground"),
        self_boxes=data.get("self_boxes", ()),
    )
    output = Tracker().step(observation, clearing_rays=data.get("clearing_rays", ()))
    args.output.write_text(
        json.dumps(output, sort_keys=True, allow_nan=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
