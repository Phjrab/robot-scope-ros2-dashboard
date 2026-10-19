"""Fixed private subprocess entry point. Never imports dashboard ROS modules."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main(folder: Path) -> None:
    started = time.monotonic()
    envelope = json.loads((folder / "input.json").read_text())
    source = Path(envelope["source_root"])
    pin = envelope["source_pin"]["files"]
    actual = {str(p.relative_to(source)) for p in (source / "auto_localization").rglob("*.py")}
    if actual != set(pin):
        raise ValueError("source coverage changed")
    verified_source = folder / "verified-source"
    for name, expected in pin.items():
        path = source / name
        raw = path.read_bytes()
        if path.resolve() != path or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("source changed before worker import")
        target = verified_source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    # The package name and callable are fixed. Only server configuration supplies its root.
    # Copy verified source only: an existing unverified .pyc cannot override it.
    sys.path.insert(0, str(verified_source))
    from auto_localization.isolated import run_se3_isolated
    import numpy as np

    context = envelope["context"]
    for name in ("scan", "map"):
        raw = (folder / (name + ".f64")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != context[name]["sha256"]:
            raise ValueError("input hash changed")
        array = np.frombuffer(raw, dtype="<f8").reshape(-1, 3)
        if len(array) != context[name]["point_count"] or not np.isfinite(array).all():
            raise ValueError("unsupported input population")
        np.save(folder / (name + ".npy"), array, allow_pickle=False)
    manifest = {"map_file": "map.npy", "map_frame": context["map_frame"],
                "sensor_frame": context["source_frame"], "frames": [{
                    "points_file": "scan.npy", "frame_id": context["source_frame"],
                    "session_id": context["observer_epoch"], "source_stamp_ns": context["source_stamp_ns"]}]}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, allow_nan=False))
    remaining = envelope["remaining_s"] - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("worker startup exceeded deadline")
    values = run_se3_isolated(str(path), timeout_s=remaining, max_results=1)
    if len(values) != 1:
        raise ValueError("expected one complete observation")
    encoded = json.dumps(values[0], allow_nan=False, separators=(",", ":")).encode()
    if not 0 < len(encoded) <= 65_536:
        raise ValueError("result exceeds limit; diagnostics were not truncated")
    fd = os.open(folder / "result.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
