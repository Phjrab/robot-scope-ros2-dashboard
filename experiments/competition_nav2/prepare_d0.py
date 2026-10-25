"""Materialize only pinned read-only D0 input/sensor dependencies from Git objects."""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def prepare():
    pin = json.loads((ROOT / "repro/d0-source.json").read_text())
    target = ROOT / "d0_input"
    for name, expected in pin["files_sha256"].items():
        data = subprocess.check_output(
            ["git", "show", pin["source_commit"] + ":" + name], cwd=ROOT
        )
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("D0 Git input hash mismatch: " + name)
        path = target / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError("existing D0 input differs; refusing overwrite: " + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(
        json.dumps(
            dict(
                source_commit=pin["source_commit"],
                files=len(pin["files_sha256"]),
                root=str(target),
            )
        )
    )


if __name__ == "__main__":
    prepare()
