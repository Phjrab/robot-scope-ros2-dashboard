"""Private, bounded team preset catalog. Saving never applies Nav2 parameters."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping


class PresetInvalid(ValueError):
    pass


class PresetConflict(ValueError):
    pass


class PresetUnavailable(RuntimeError):
    pass


def preset_name(value: str) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        raise PresetInvalid("프리셋 이름에 제어 문자를 사용할 수 없습니다.")
    name = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(name) <= 64:
        raise PresetInvalid("프리셋 이름은 1~64자로 입력해 주세요.")
    return name


class NavigationPresetStore:
    MAX_PRESETS = 64
    MAX_BYTES = 256 * 1024

    def __init__(self, runtime_dir: Path, validator: Callable):
        self.directory = runtime_dir
        self.validator = validator

    @contextmanager
    def _locked(self):
        try:
            fd = os.open(self.directory / "presets.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "r+") as lock:
                if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
                    raise OSError("not a regular lock")
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as exc:
            raise PresetUnavailable("프리셋 저장소에 접근할 수 없습니다.") from exc

    def _read(self) -> list[dict[str, Any]]:
        try:
            fd = os.open(self.directory / "presets.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return []
        try:
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("not a regular catalog")
                raw = stream.read(self.MAX_BYTES + 1)
            if len(raw) > self.MAX_BYTES:
                raise ValueError("catalog too large")
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("version") != 1:
                raise ValueError("invalid version")
            presets = document["presets"]
            if not isinstance(presets, list) or len(presets) > self.MAX_PRESETS:
                raise ValueError("invalid catalog")
            ids, names = set(), set()
            result = []
            for entry in presets:
                identifier = entry["id"]
                name = preset_name(entry["label"])
                if not isinstance(identifier, str) or not re.fullmatch(r"user-[0-9a-f]{32}", identifier):
                    raise ValueError("invalid id")
                if identifier in ids or name.casefold() in names:
                    raise ValueError("duplicate preset")
                ids.add(identifier)
                names.add(name.casefold())
                result.append({"id": identifier, "label": name, "description": "팀 공용 사용자 프리셋", "values": self.validator(entry["values"])})
            return result
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise PresetUnavailable("저장된 프리셋을 읽을 수 없습니다. 관리자 확인이 필요합니다.") from exc

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            return {"presets": self._read()}

    def create(self, name: str, values: Mapping[str, Any]) -> dict[str, Any]:
        name = preset_name(name)
        normalized = self.validator(values)
        with self._locked():
            presets = self._read()
            if any(entry["label"].casefold() == name.casefold() for entry in presets):
                raise PresetConflict("같은 이름의 프리셋이 있습니다. 다른 이름을 입력해 주세요.")
            if len(presets) >= self.MAX_PRESETS:
                raise PresetConflict("프리셋 저장 한도(64개)에 도달했습니다.")
            preset = {"id": "user-" + uuid.uuid4().hex, "label": name, "description": "팀 공용 사용자 프리셋", "values": normalized}
            presets.append(preset)
            payload = json.dumps({"version": 1, "presets": presets}, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(payload) > self.MAX_BYTES:
                raise PresetConflict("프리셋 저장 용량 한도에 도달했습니다.")
            fd, staging = tempfile.mkstemp(prefix=".presets-", dir=self.directory)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(staging, self.directory / "presets.json")
            finally:
                if os.path.exists(staging):
                    os.unlink(staging)
            return {"preset": preset, "presets": presets}
