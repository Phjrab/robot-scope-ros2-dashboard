"""Export verified Git blobs into a new read-only directory; no checkout mutation."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PINS = json.loads(Path(__file__).with_name("pins.json").read_text())
PATHS = {
    "C1": [
        "robot_dashboard/expansion_contracts/",
        "robot_dashboard/expansion_services/",
    ],
    "C3": [
        "robot_dashboard/static/features/obstacle_scene/",
        "robot_dashboard/static/features/route_planner/spatial_editor.js",
        "docs/parallel-expansion-20261029/C3/evidence/round2-v02/NATIVE_REPLAY.http-body.json",
    ],
    "D3": ["robot_dashboard/collision_geometry_core/"],
    "C4": ["docs/parallel-expansion-20261029/C4/FOLLOWUP.md"],
}


def prepare(destination):
    destination.mkdir(mode=0o700)
    receipt = {}
    for role, prefixes in PATHS.items():
        names = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", PINS[role]], text=True
        ).splitlines()
        for name in names:
            if not any(name.startswith(prefix) for prefix in prefixes):
                continue
            raw = subprocess.check_output(["git", "show", PINS[role] + ":" + name])
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            receipt[name] = dict(
                role=role, sha=PINS[role], sha256=hashlib.sha256(raw).hexdigest()
            )
    (destination / "receipt.json").write_text(json.dumps(receipt, indent=2))
    for p in sorted(destination.rglob("*"), reverse=True):
        p.chmod(0o555 if p.is_dir() else 0o444)
    destination.chmod(0o555)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    print(prepare(parser.parse_args().directory))
