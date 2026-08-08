"""Read-only catalog and preview loader for maps saved on the robot host.

Only files discovered below profile-configured roots receive an opaque ID.  API
callers never supply a path, which keeps traversal and accidental arbitrary-file
reads out of the HTTP surface.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np


class SavedMapError(Exception):
    """Base class for expected saved-map failures."""


class SavedMapNotFound(SavedMapError):
    """Raised when an opaque map ID is not in the current catalog."""


class SavedMapFormatError(SavedMapError):
    """Raised when a configured file is not a supported map snapshot."""


@dataclass(frozen=True)
class SavedMapRecord:
    map_id: str
    name: str
    kind: str
    format: str
    path: Path
    root: Path
    modified_ns: int
    size_bytes: int
    details: Dict[str, Any]
    auxiliary_path: Optional[Path] = None

    def public(self) -> Dict[str, Any]:
        modified = datetime.fromtimestamp(
            self.modified_ns / 1_000_000_000,
            tz=timezone.utc,
        ).isoformat()
        result: Dict[str, Any] = {
            "id": self.map_id,
            "name": self.name,
            "kind": self.kind,
            "format": self.format,
            "file_name": self.path.name,
            "modified_at": modified,
            "size_bytes": self.size_bytes,
            "data_url": f"/api/v1/saved-maps/{self.map_id}/data",
        }
        result.update(self.details)
        return result


class SavedMapCatalog:
    """Discover and normalize saved maps under an explicit root allowlist."""

    def __init__(
        self,
        roots: Iterable[Path],
        *,
        max_files: int = 100,
        max_depth: int = 3,
        max_file_bytes: int = 256 * 1024 * 1024,
        preview_points: int = 10_000,
        cloud_radius_limit_m: float = 500.0,
        max_grid_cells: int = 16_000_000,
    ) -> None:
        resolved_roots = []
        for value in roots:
            try:
                root = value.expanduser().resolve(strict=True)
            except OSError:
                continue
            if root.is_dir() and root not in resolved_roots:
                resolved_roots.append(root)
        self.roots = tuple(resolved_roots)
        self.max_files = max(1, min(int(max_files), 2_000))
        self.max_depth = max(0, min(int(max_depth), 10))
        self.max_file_bytes = max(1024, min(int(max_file_bytes), 2 * 1024**3))
        self.preview_points = max(100, min(int(preview_points), 50_000))
        self.cloud_radius_limit_m = max(5.0, min(float(cloud_radius_limit_m), 10_000.0))
        self.max_grid_cells = max(1_000, min(int(max_grid_cells), 64_000_000))

    @classmethod
    def from_profile(
        cls,
        profile: Dict[str, Any],
        *,
        base_dir: Optional[Path] = None,
    ) -> "SavedMapCatalog":
        settings = profile.get("saved_maps", {}) if isinstance(profile, dict) else {}
        if not isinstance(settings, dict) or settings.get("enabled", True) is False:
            return cls(())
        base = (base_dir or Path.cwd()).expanduser().resolve()
        roots = []
        raw_directories = settings.get("directories", [])
        if isinstance(raw_directories, list):
            for raw in raw_directories:
                if not isinstance(raw, str) or not raw.strip():
                    continue
                expanded = Path(os.path.expandvars(raw)).expanduser()
                roots.append(expanded if expanded.is_absolute() else base / expanded)
        return cls(
            roots,
            max_files=settings.get("max_files", 100),
            max_depth=settings.get("max_depth", 3),
            max_file_bytes=settings.get("max_file_bytes", 256 * 1024 * 1024),
            preview_points=settings.get("preview_points", 10_000),
            cloud_radius_limit_m=settings.get(
                "cloud_radius_limit_m",
                profile.get("cloud_radius_limit_m", 500.0),
            ),
            max_grid_cells=settings.get("max_grid_cells", 16_000_000),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.roots)

    def list_snapshot(self) -> Dict[str, Any]:
        records = self._scan()
        return {
            "enabled": self.enabled,
            "count": len(records),
            "maps": [record.public() for record in records],
        }

    def metadata(self, map_id: str) -> Dict[str, Any]:
        return self._find(map_id).public()

    def data(self, map_id: str) -> Dict[str, Any]:
        record = self._find(map_id)
        try:
            self._validate_record(record)
            if record.format == "pcd-binary":
                return self._pcd_snapshot(record)
            if record.format == "robot-scope-json":
                return self._json_snapshot(record)
            if record.format == "map-server-pgm":
                return self._occupancy_snapshot(record)
            raise SavedMapFormatError(f"unsupported saved map format: {record.format}")
        except SavedMapError:
            raise
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
            raise SavedMapFormatError("saved map data could not be read") from exc

    def _find(self, map_id: str) -> SavedMapRecord:
        if not isinstance(map_id, str) or len(map_id) != 24:
            raise SavedMapNotFound("saved map not found")
        record = next((item for item in self._scan() if item.map_id == map_id), None)
        if record is None:
            raise SavedMapNotFound("saved map not found")
        return record

    def _scan(self) -> list[SavedMapRecord]:
        records: list[SavedMapRecord] = []
        for root in self.roots:
            for path in self._iter_candidates(root):
                try:
                    record = self._record_for(root, path)
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    UnicodeError,
                    SavedMapFormatError,
                    json.JSONDecodeError,
                ):
                    continue
                if record is not None:
                    records.append(record)
        records.sort(key=lambda record: (-record.modified_ns, record.name.lower(), record.map_id))
        return records[: self.max_files]

    def _iter_candidates(self, root: Path) -> Iterable[Path]:
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.relative_to(root).parts)
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".") and depth < self.max_depth
            ]
            if depth > self.max_depth:
                continue
            for name in files:
                path = current_path / name
                if name.startswith(".") or path.is_symlink():
                    continue
                if path.suffix.lower() in {".pcd", ".json", ".yaml", ".yml"}:
                    yield path

    def _record_for(self, root: Path, path: Path) -> Optional[SavedMapRecord]:
        resolved = self._contained_file(root, path)
        stat = resolved.stat()
        if stat.st_size <= 0 or stat.st_size > self.max_file_bytes:
            return None
        suffix = resolved.suffix.lower()
        details: Dict[str, Any]
        auxiliary: Optional[Path] = None
        if suffix == ".pcd":
            header = self._read_pcd_header(resolved)
            if header["data"] != "binary":
                return None
            kind, fmt = "pointcloud3d", "pcd-binary"
            details = {
                "point_count": header["points"],
                "fields": header["fields"],
                "frame_id": "camera_init",
            }
        elif suffix == ".json":
            payload = self._read_json(resolved)
            points = payload.get("points")
            if not isinstance(points, list) or len(points) < 3 or len(points) % 3:
                return None
            kind, fmt = "pointcloud3d", "robot-scope-json"
            details = {
                "point_count": len(points) // 3,
                "frame_id": str(payload.get("frame_id", "")),
            }
            if isinstance(payload.get("bounds"), dict):
                details["bounds"] = payload["bounds"]
        else:
            metadata = self._read_map_yaml(resolved)
            auxiliary = self._contained_file(root, resolved.parent / metadata["image"])
            if auxiliary.suffix.lower() != ".pgm":
                return None
            image_stat = auxiliary.stat()
            if image_stat.st_size <= 0 or image_stat.st_size > self.max_file_bytes:
                return None
            width, height, _ = self._read_pgm(auxiliary, pixels=False)
            kind, fmt = "occupancy2d", "map-server-pgm"
            details = {
                "width": width,
                "height": height,
                "resolution": metadata["resolution"],
                "origin": metadata["origin"],
                "frame_id": "map",
                "image_file_name": auxiliary.name,
            }
            stat_size = stat.st_size + image_stat.st_size
            stat_mtime = max(stat.st_mtime_ns, image_stat.st_mtime_ns)
            return SavedMapRecord(
                self._opaque_id(kind, resolved),
                resolved.stem,
                kind,
                fmt,
                resolved,
                root,
                stat_mtime,
                stat_size,
                details,
                auxiliary,
            )
        return SavedMapRecord(
            self._opaque_id(kind, resolved),
            resolved.stem,
            kind,
            fmt,
            resolved,
            root,
            stat.st_mtime_ns,
            stat.st_size,
            details,
            auxiliary,
        )

    @staticmethod
    def _opaque_id(kind: str, path: Path) -> str:
        digest = hashlib.sha256(f"{kind}\0{path}".encode("utf-8")).hexdigest()
        return digest[:24]

    @staticmethod
    def _contained_file(root: Path, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SavedMapFormatError("map file escapes its configured root") from exc
        if not resolved.is_file():
            raise SavedMapFormatError("map path is not a regular file")
        return resolved

    def _validate_record(self, record: SavedMapRecord) -> None:
        current = self._contained_file(record.root, record.path).stat()
        if current.st_size <= 0 or current.st_size > self.max_file_bytes:
            raise SavedMapFormatError("saved map is empty or exceeds the configured limit")
        if record.auxiliary_path is not None:
            auxiliary = self._contained_file(record.root, record.auxiliary_path).stat()
            if auxiliary.st_size <= 0 or auxiliary.st_size > self.max_file_bytes:
                raise SavedMapFormatError("saved map image exceeds the configured limit")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if path.stat().st_size > self.max_file_bytes:
            raise SavedMapFormatError("saved map exceeds the configured limit")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SavedMapFormatError("saved map JSON must be an object")
        return payload

    @staticmethod
    def _read_pcd_header(path: Path) -> Dict[str, Any]:
        metadata: Dict[str, list[str]] = {}
        consumed = 0
        with path.open("rb") as stream:
            while consumed < 64 * 1024:
                line = stream.readline()
                consumed += len(line)
                if not line:
                    break
                decoded = line.decode("ascii", errors="strict").strip()
                if not decoded or decoded.startswith("#"):
                    continue
                key, *values = decoded.split()
                metadata[key.upper()] = values
                if key.upper() == "DATA":
                    break
        if "DATA" not in metadata:
            raise SavedMapFormatError("PCD header ended before DATA")
        fields = metadata.get("FIELDS", [])
        sizes = [int(value) for value in metadata.get("SIZE", [])]
        kinds = metadata.get("TYPE", [])
        counts = [int(value) for value in metadata.get("COUNT", ["1"] * len(fields))]
        if not fields or not (len(fields) == len(sizes) == len(kinds) == len(counts)):
            raise SavedMapFormatError("invalid PCD field metadata")
        if any(name not in fields for name in ("x", "y", "z")):
            raise SavedMapFormatError("PCD requires x, y and z fields")
        points = int(metadata.get("POINTS", metadata.get("WIDTH", ["0"]))[0])
        if points <= 0:
            raise SavedMapFormatError("PCD has no points")
        return {
            "fields": fields,
            "sizes": sizes,
            "types": kinds,
            "counts": counts,
            "points": points,
            "data": metadata["DATA"][0].lower(),
            "data_offset": consumed,
        }

    def _pcd_snapshot(self, record: SavedMapRecord) -> Dict[str, Any]:
        header = self._read_pcd_header(record.path)
        scalar_types = {
            ("F", 4): "<f4", ("F", 8): "<f8",
            ("I", 1): "i1", ("I", 2): "<i2", ("I", 4): "<i4",
            ("U", 1): "u1", ("U", 2): "<u2", ("U", 4): "<u4",
        }
        names, formats, offsets = [], [], []
        offset = 0
        for name, size, kind, count in zip(
            header["fields"], header["sizes"], header["types"], header["counts"]
        ):
            scalar = scalar_types.get((kind, size))
            if scalar is None or count != 1:
                raise SavedMapFormatError(f"unsupported PCD field: {name} {kind}{size}x{count}")
            names.append(name)
            formats.append(scalar)
            offsets.append(offset)
            offset += size
        expected = header["data_offset"] + header["points"] * offset
        if expected > record.path.stat().st_size:
            raise SavedMapFormatError("PCD payload is truncated")
        dtype = np.dtype({"names": names, "formats": formats, "offsets": offsets, "itemsize": offset})
        records = np.memmap(
            record.path,
            mode="r",
            dtype=dtype,
            offset=header["data_offset"],
            shape=(header["points"],),
        )
        sample_count = min(header["points"], max(self.preview_points * 4, self.preview_points))
        indexes = np.linspace(0, header["points"] - 1, sample_count, dtype=np.int64)
        points = np.column_stack((records["x"][indexes], records["y"][indexes], records["z"][indexes]))
        return self._cloud_payload(record, points, header["points"], "camera_init")

    def _json_snapshot(self, record: SavedMapRecord) -> Dict[str, Any]:
        source = self._read_json(record.path)
        raw = np.asarray(source["points"], dtype=np.float64).reshape((-1, 3))
        frame_id = str(source.get("frame_id", ""))
        source_count = int(source.get("source_points", len(raw)))
        payload = self._cloud_payload(record, raw, source_count, frame_id)
        payload["topic"] = str(source.get("topic", "/saved/map"))
        return payload

    def _cloud_payload(
        self,
        record: SavedMapRecord,
        points: np.ndarray,
        source_count: int,
        frame_id: str,
    ) -> Dict[str, Any]:
        finite = points[np.isfinite(points).all(axis=1)]
        if not len(finite):
            raise SavedMapFormatError("saved point cloud has no finite points")
        center = np.median(finite, axis=0)
        distances = np.linalg.norm(finite - center, axis=1)
        finite = finite[distances <= self.cloud_radius_limit_m]
        if not len(finite):
            raise SavedMapFormatError("saved point cloud is outside the configured radius")
        if len(finite) > self.preview_points:
            indexes = np.linspace(0, len(finite) - 1, self.preview_points, dtype=np.int64)
            finite = finite[indexes]
        finite = np.round(finite.astype(np.float64, copy=False), 4)
        return {
            "seq": max(1, record.modified_ns),
            "map_id": record.map_id,
            "name": record.name,
            "kind": "pointcloud3d",
            "topic": "/saved/map",
            "frame_id": frame_id,
            "source_points": int(source_count),
            "sent_points": int(len(finite)),
            "units": "m",
            "bounds": {
                "min": [float(value) for value in np.min(finite, axis=0)],
                "max": [float(value) for value in np.max(finite, axis=0)],
            },
            "offline_snapshot": True,
            "points": [round(float(value), 4) for value in finite.reshape(-1)],
        }

    @staticmethod
    def _read_map_yaml(path: Path) -> Dict[str, Any]:
        values: Dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
        if not values.get("image"):
            raise SavedMapFormatError("map YAML has no image")
        try:
            origin = ast.literal_eval(values.get("origin", "[0, 0, 0]"))
            origin = [float(value) for value in origin]
            resolution = float(values["resolution"])
            occupied = float(values.get("occupied_thresh", "0.65"))
            free = float(values.get("free_thresh", "0.196"))
            negate = int(values.get("negate", "0"))
        except (KeyError, ValueError, SyntaxError, TypeError) as exc:
            raise SavedMapFormatError("invalid map YAML metadata") from exc
        if len(origin) != 3 or resolution <= 0 or not (0 <= free < occupied <= 1):
            raise SavedMapFormatError("invalid map YAML ranges")
        image = values["image"].strip().strip("'\"")
        if not image or "\x00" in image:
            raise SavedMapFormatError("invalid map YAML image")
        return {
            "image": image,
            "resolution": resolution,
            "origin": origin,
            "occupied_thresh": occupied,
            "free_thresh": free,
            "negate": negate,
        }

    def _read_pgm(self, path: Path, *, pixels: bool) -> tuple[int, int, Optional[np.ndarray]]:
        content = path.read_bytes()
        if len(content) > self.max_file_bytes:
            raise SavedMapFormatError("PGM exceeds the configured limit")
        position = 0

        def token() -> bytes:
            nonlocal position
            while position < len(content):
                if content[position] == 35:
                    end = content.find(b"\n", position)
                    position = len(content) if end < 0 else end + 1
                elif chr(content[position]).isspace():
                    position += 1
                else:
                    break
            start = position
            while position < len(content) and not chr(content[position]).isspace():
                position += 1
            if start == position:
                raise SavedMapFormatError("truncated PGM header")
            return content[start:position]

        magic = token()
        try:
            width, height, maximum = int(token()), int(token()), int(token())
        except ValueError as exc:
            raise SavedMapFormatError("invalid PGM header") from exc
        cells = width * height
        if width <= 0 or height <= 0 or cells > self.max_grid_cells or maximum <= 0:
            raise SavedMapFormatError("invalid PGM dimensions")
        if not pixels:
            return width, height, None
        if magic == b"P5":
            if position >= len(content) or not chr(content[position]).isspace():
                raise SavedMapFormatError("invalid binary PGM separator")
            position += 2 if content[position:position + 2] == b"\r\n" else 1
            item_size = 1 if maximum < 256 else 2
            expected = cells * item_size
            if len(content) - position < expected:
                raise SavedMapFormatError("truncated PGM pixels")
            dtype = np.dtype("u1" if item_size == 1 else ">u2")
            values = np.frombuffer(content, dtype=dtype, count=cells, offset=position)
        elif magic == b"P2":
            values = np.asarray([int(token()) for _ in range(cells)], dtype=np.uint32)
        else:
            raise SavedMapFormatError("only P2 and P5 PGM maps are supported")
        normalized = np.clip(values.astype(np.float64) / maximum, 0.0, 1.0)
        return width, height, normalized.reshape((height, width))

    def _occupancy_snapshot(self, record: SavedMapRecord) -> Dict[str, Any]:
        if record.auxiliary_path is None:
            raise SavedMapFormatError("2D map has no image")
        metadata = self._read_map_yaml(record.path)
        width, height, pixels = self._read_pgm(record.auxiliary_path, pixels=True)
        assert pixels is not None
        occupancy_probability = pixels if metadata["negate"] else 1.0 - pixels
        grid = np.full((height, width), -1, dtype=np.int16)
        grid[occupancy_probability > metadata["occupied_thresh"]] = 100
        grid[occupancy_probability < metadata["free_thresh"]] = 0
        # map_server converts top-left image rows into bottom-left ROS map rows.
        grid = np.flipud(grid)
        encoded = bytes((int(value) & 0xFF for value in grid.reshape(-1)))
        return {
            "seq": max(1, record.modified_ns),
            "map_id": record.map_id,
            "name": record.name,
            "kind": "occupancy2d",
            "width": width,
            "height": height,
            "resolution": metadata["resolution"],
            "origin": metadata["origin"],
            "frame_id": "map",
            "topic": "/saved/map",
            "data_b64": base64.b64encode(encoded).decode("ascii"),
            "data_encoding": "int8-base64",
            "cell_order": "row-major; cell(0,0) at origin",
            "offline_snapshot": True,
        }
