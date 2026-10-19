"""Synthetic full-source PCD catalogue bridge for the browser E2E fixture.

Each invocation creates a fresh SavedMapCatalog. Only the temporary directory
supplied by the test is used; this never opens the robot application or ROS.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

from robot_dashboard.pcd_editing.store import PcdEditConflict, PcdEditError
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapConflict, SavedMapError, SavedMapNotFound


def initialize(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "synthetic_source.pcd"
    if source.exists():
        raise RuntimeError("synthetic source already exists")
    count = 12_000
    header = (
        "VERSION .7\nFIELDS x y z intensity\nSIZE 4 4 4 4\nTYPE F F F F\n"
        f"COUNT 1 1 1 1\nWIDTH {count}\nHEIGHT 1\nPOINTS {count}\nDATA binary\n"
    ).encode("ascii")
    with source.open("xb") as stream:
        stream.write(header)
        for index in range(count):
            x = (index % 120) / 10 - 6
            y = (index // 120) / 10 - 5
            stream.write(struct.pack("<ffff", x, y, 0.0, float(index)))


def main() -> None:
    root = Path(sys.argv[1])
    command = sys.argv[2]
    if command == "init":
        initialize(root)
    catalogue = SavedMapCatalog([root], managed_roots=[root], preview_points=150)
    try:
        if command in ("init", "list"):
            value = catalogue.list_snapshot()
        elif command == "descriptor":
            value = catalogue.pcd_edit_source(sys.argv[3])
        elif command == "data":
            value = catalogue.data(sys.argv[3], max_points=150)
        elif command == "save":
            value = {"map": catalogue.save_pcd_edited_copy(sys.argv[3], json.loads(sys.argv[4]))}
        else:
            raise ValueError("unknown fixture command")
        print(json.dumps({"status": 201 if command == "save" else 200, "data": value}, allow_nan=False))
    except (PcdEditConflict, SavedMapConflict) as exc:
        print(json.dumps({"status": 409, "data": {"detail": str(exc)}}))
    except SavedMapNotFound as exc:
        print(json.dumps({"status": 404, "data": {"detail": str(exc)}}))
    except (PcdEditError, SavedMapError, ValueError) as exc:
        print(json.dumps({"status": 422, "data": {"detail": str(exc)}}))


if __name__ == "__main__":
    main()
