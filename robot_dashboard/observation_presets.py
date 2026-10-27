"""Server-persisted approximate map anchors; never stores odometry transforms."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import re

from .navigation_presets import NavigationPresetStore, PresetConflict, PresetInvalid


POSE_FIELDS = ("x", "y", "z", "roll", "pitch", "yaw")
REFERENCES = {"FASTLIO_IMU", "UNVERIFIED_BODY"}


def anchor_values(value):
    if not isinstance(value, dict) or set(value) != {
        "map_id", "map_revision", "map_frame", "pose_reference", "pose", "saved_at", "units"
    }:
        raise PresetInvalid("초기값 프리셋 형식이 올바르지 않습니다.")
    if (not re.fullmatch(r"[a-f0-9]{24}", str(value["map_id"]))
            or not re.fullmatch(r"[a-f0-9]{64}", str(value["map_revision"]))
            or not isinstance(value["map_frame"], str) or not 1 <= len(value["map_frame"]) <= 160
            or value["pose_reference"] not in REFERENCES or value["units"] != "metres_degrees"):
        raise PresetInvalid("지도 또는 위치 기준이 올바르지 않습니다.")
    pose = value["pose"]
    if not isinstance(pose, dict) or set(pose) != set(POSE_FIELDS):
        raise PresetInvalid("위치·방향 6개 값을 모두 입력해 주세요.")
    for field in POSE_FIELDS:
        number = pose[field]
        limit = 1000 if field in {"x", "y", "z"} else 360
        if type(number) not in (int, float) or not math.isfinite(number) or abs(number) > limit:
            raise PresetInvalid("위치는 ±1000m, 각도는 ±360° 이내의 유한한 숫자여야 합니다.")
    try:
        if datetime.fromisoformat(value["saved_at"]).utcoffset() is None:
            raise ValueError("timezone missing")
    except (TypeError, ValueError) as exc:
        raise PresetInvalid("저장 시각이 올바르지 않습니다.") from exc
    return {**value, "pose": {key: float(pose[key]) for key in POSE_FIELDS}}


class ObservationPresetStore:
    values_validator = staticmethod(anchor_values)

    def __init__(self, directory: Path, catalog):
        self.directory, self.catalog = Path(directory), catalog

    def _context(self, map_id):
        if not isinstance(map_id, str) or not re.fullmatch(r"[a-f0-9]{24}", map_id):
            raise PresetInvalid("잘못된 지도 ID입니다.")
        meta = self.catalog.metadata(map_id)
        if meta.get("kind") != "pointcloud3d" or not meta.get("frame_id"):
            raise PresetInvalid("저장된 3D 지도를 선택해 주세요.")
        return {"map_id": map_id, "map_revision": meta["revision"], "map_frame": meta["frame_id"]}

    def _store(self, map_id):
        # IDs have already been checked; caller-supplied paths are never accepted.
        if self.directory.is_symlink():
            raise PresetInvalid("프리셋 저장 디렉터리를 확인해 주세요.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = self.directory / map_id
        if directory.is_symlink():
            raise PresetInvalid("프리셋 저장 디렉터리를 확인해 주세요.")
        directory.mkdir(exist_ok=True, mode=0o700)
        return NavigationPresetStore(directory, self.values_validator)

    def snapshot(self, map_id):
        context = self._context(map_id)
        presets = self._store(map_id).snapshot()["presets"]
        compatible = [entry for entry in presets if all(entry["values"].get(k) == v for k, v in context.items())]
        return {"map": context, "presets": compatible, "incompatible_count": len(presets) - len(compatible),
                "approximate_only": True, "requires_reanchor": True}

    def create(self, map_id, name, map_revision, map_frame, pose_reference, pose):
        context = self._context(map_id)
        if (context["map_revision"], context["map_frame"]) != (map_revision, map_frame):
            raise PresetConflict("지도가 변경됐습니다. 현재 지도를 다시 선택해 주세요.")
        values = anchor_values({**context, "pose_reference": pose_reference, "pose": pose,
                                "units": "metres_degrees", "saved_at": datetime.now(timezone.utc).isoformat()})
        result = self._store(map_id).create(name, values)
        return {"preset": result["preset"], "approximate_only": True, "requires_reanchor": True}
