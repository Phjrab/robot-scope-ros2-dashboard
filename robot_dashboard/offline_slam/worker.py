"""One disposable CPU worker; no ROS import or operational application."""

import sys
from pathlib import Path

from .core import Settings, optimize, preview
from .maps import rebuild
from .store import Store, read_json


def run(path):
    try:
        data = read_json(path / "session.json")
        result = optimize(data, Settings(**read_json(path / "settings.json")))
        if result["state"] == "SUCCEEDED":
            for name, payload in rebuild(data, result).items():
                (path / name).write_bytes(payload)
            Store._replace(path / "preview.json", preview(data, result))
        Store._replace(path / "result.json", result)
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, ValueError) and str(exc).replace("_", "").isalnum()
            else "OFFLINE_WORKER_FAILED"
        )
        Store._replace(path / "result.json", dict(state="FAILED", error=error[:100]))


if __name__ == "__main__":
    run(Path(sys.argv[1]))
