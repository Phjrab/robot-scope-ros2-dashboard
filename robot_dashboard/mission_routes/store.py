"""Bounded private atomic MR store, independent of legacy mission data."""
from __future__ import annotations

import copy
import json
import os
import stat
from pathlib import Path

from ..application.mission_coordinator import MissionStateStore, MissionUnavailable


class PlanStore(MissionStateStore):
    def __init__(self, root: Path):
        super().__init__(root)
        self.path = self.root / "mission-plans-v1.json"

    def load(self):
        if self.path.is_symlink():
            raise MissionUnavailable("mission plan store cannot be a symlink")
        if not self.path.exists():
            return {"schema": "mission-plans.v1", "definitions": {}, "runs": {}, "requests": {}}
        if self.path.is_symlink():
            raise MissionUnavailable("mission plan store cannot be a symlink")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 512 * 1024:
            raise MissionUnavailable("mission plan store is not a bounded private file")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise MissionUnavailable("mission plan store is corrupt; original preserved") from exc
        if not isinstance(value, dict) or set(value) != {"schema", "definitions", "runs", "requests"} or value["schema"] != "mission-plans.v1" or any(not isinstance(value[k], dict) for k in ("definitions", "runs", "requests")):
            raise MissionUnavailable("mission plan store schema is invalid")
        if len(value["definitions"]) > 64 or len(value["runs"]) > 32 or len(value["requests"]) > 256:
            raise MissionUnavailable("mission plan store exceeds retention bounds")
        return copy.deepcopy(value)
