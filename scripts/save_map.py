#!/usr/bin/env python3
"""Capture one fresh ``/Laser_map`` frame as a bounded binary PCD.

ROS imports are confined to :func:`capture_ros_map`; the PointCloud2 parser and
atomic writer are ordinary Python and are covered on non-ROS hosts.  The
prototype copied into ``~/ws/go2_3d`` was captured at SHA-256
a1b1339d83b2e3025c1ed552f6183efe51d00b4cd95258814acc146696df2512.
"""

from __future__ import annotations

import argparse
import math
import os
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


MAP_TOPIC = "/Laser_map"
POINTCLOUD_TYPE = "sensor_msgs/msg/PointCloud2"
FLOAT32 = 7
MAX_POINTS = 2_000_000
MAX_ROWS = 4_096
MAX_POINT_STEP = 4_096
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_OUTPUT_BYTES = 256 * 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024

PCD_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("intensity", "<f4"),
    ]
)


class MapCaptureError(ValueError):
    """The fixed map-capture or output contract was violated."""


@dataclass(frozen=True)
class PcdSnapshot:
    header: bytes
    payload: bytes
    points: int

    @property
    def size(self) -> int:
        return len(self.header) + len(self.payload)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise MapCaptureError(f"{label} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MapCaptureError(f"{label} must be an integer") from exc


def _field_offsets(message: Any, point_step: int) -> tuple[int, int, int, int | None]:
    fields = getattr(message, "fields", None)
    if not isinstance(fields, Sequence):
        raise MapCaptureError("PointCloud2 fields are missing")
    by_name: dict[str, Any] = {}
    for field in fields:
        name = str(getattr(field, "name", ""))
        if not name or name in by_name:
            raise MapCaptureError("PointCloud2 fields are unnamed or duplicated")
        by_name[name] = field
    offsets: list[int] = []
    for name in ("x", "y", "z"):
        field = by_name.get(name)
        if field is None:
            raise MapCaptureError(f"/Laser_map is missing field {name}")
        offset = _integer(getattr(field, "offset", None), f"{name}.offset")
        datatype = _integer(getattr(field, "datatype", None), f"{name}.datatype")
        count = _integer(getattr(field, "count", None), f"{name}.count")
        if datatype != FLOAT32 or count != 1 or offset < 0 or offset + 4 > point_step:
            raise MapCaptureError(f"/Laser_map field {name} must be one in-bounds float32")
        offsets.append(offset)
    intensity_offset: int | None = None
    intensity = by_name.get("intensity")
    if intensity is not None:
        intensity_offset = _integer(
            getattr(intensity, "offset", None),
            "intensity.offset",
        )
        datatype = _integer(getattr(intensity, "datatype", None), "intensity.datatype")
        count = _integer(getattr(intensity, "count", None), "intensity.count")
        if (
            datatype != FLOAT32
            or count != 1
            or intensity_offset < 0
            or intensity_offset + 4 > point_step
        ):
            raise MapCaptureError(
                "/Laser_map intensity must be one in-bounds float32 when present"
            )
    occupied = [(offset, offset + 4) for offset in offsets]
    if intensity_offset is not None:
        occupied.append((intensity_offset, intensity_offset + 4))
    occupied.sort()
    if any(right[0] < left[1] for left, right in zip(occupied, occupied[1:])):
        raise MapCaptureError("/Laser_map fields overlap")
    return offsets[0], offsets[1], offsets[2], intensity_offset


def pointcloud_to_pcd(message: Any) -> PcdSnapshot:
    """Validate and encode one bounded PointCloud2 without trusting padding."""

    header = getattr(message, "header", None)
    if not str(getattr(header, "frame_id", "")):
        raise MapCaptureError("/Laser_map frame_id is empty")
    width = _integer(getattr(message, "width", None), "width")
    height = _integer(getattr(message, "height", None), "height")
    point_step = _integer(getattr(message, "point_step", None), "point_step")
    row_step = _integer(getattr(message, "row_step", None), "row_step")
    points = width * height
    if height > MAX_ROWS:
        raise MapCaptureError(f"/Laser_map height exceeds the {MAX_ROWS}-row limit")
    if width <= 0 or height <= 0 or points <= 0 or points > MAX_POINTS:
        raise MapCaptureError(f"/Laser_map must contain 1..{MAX_POINTS} points")
    if point_step < 12 or point_step > MAX_POINT_STEP:
        raise MapCaptureError("/Laser_map point_step is outside the supported range")
    if bool(getattr(message, "is_bigendian", False)):
        raise MapCaptureError("big-endian /Laser_map data is unsupported")
    minimum_row = width * point_step
    if row_step < minimum_row or row_step > MAX_INPUT_BYTES:
        raise MapCaptureError("/Laser_map row_step is outside the supported range")
    total_bytes = row_step * height
    if total_bytes <= 0 or total_bytes > MAX_INPUT_BYTES:
        raise MapCaptureError("/Laser_map payload exceeds the supported range")
    try:
        data = memoryview(getattr(message, "data", None)).cast("B")
    except (TypeError, ValueError) as exc:
        raise MapCaptureError("/Laser_map data is missing") from exc
    if data.nbytes != total_bytes:
        raise MapCaptureError("/Laser_map payload length does not match its layout")
    x_offset, y_offset, z_offset, intensity_offset = _field_offsets(message, point_step)
    names = ["x", "y", "z"]
    offsets = [x_offset, y_offset, z_offset]
    formats = ["<f4", "<f4", "<f4"]
    if intensity_offset is not None:
        names.append("intensity")
        offsets.append(intensity_offset)
        formats.append("<f4")
    source_dtype = np.dtype(
        {
            "names": names,
            "formats": formats,
            "offsets": offsets,
            "itemsize": point_step,
        }
    )

    output = np.empty(points, dtype=PCD_DTYPE)
    finite_points = 0
    for row in range(height):
        try:
            records = np.frombuffer(
                data,
                dtype=source_dtype,
                count=width,
                offset=row * row_step,
            )
        except (TypeError, ValueError, BufferError) as exc:
            raise MapCaptureError(
                "/Laser_map payload cannot be decoded safely"
            ) from exc
        finite = (
            np.isfinite(records["x"])
            & np.isfinite(records["y"])
            & np.isfinite(records["z"])
        )
        records = records[finite]
        if not len(records):
            continue
        target = output[finite_points : finite_points + len(records)]
        target.fill(0)
        for name in ("x", "y", "z"):
            target[name] = records[name]
        if intensity_offset is not None:
            intensity = records["intensity"].astype(np.float32, copy=False)
            target["intensity"] = np.where(np.isfinite(intensity), intensity, 0.0)
        finite_points += len(target)
    if finite_points <= 0:
        raise MapCaptureError("/Laser_map contains no finite XYZ points")
    pcd_header = (
        "# .PCD v0.7\n"
        "VERSION 0.7\n"
        "FIELDS x y z intensity\n"
        "SIZE 4 4 4 4\n"
        "TYPE F F F F\n"
        "COUNT 1 1 1 1\n"
        f"WIDTH {finite_points}\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {finite_points}\n"
        "DATA binary\n"
    ).encode("ascii")
    payload = output[:finite_points].tobytes()
    if len(pcd_header) > MAX_HEADER_BYTES or len(payload) != finite_points * 16:
        raise MapCaptureError("encoded PCD size does not match its point count")
    snapshot = PcdSnapshot(pcd_header, payload, finite_points)
    if snapshot.size > MAX_OUTPUT_BYTES:
        raise MapCaptureError("encoded PCD exceeds the supported file limit")
    return snapshot


def validate_output_path(value: Path) -> Path:
    path = value.expanduser()
    if path.suffix.lower() != ".pcd" or path.name in {".pcd", ".."}:
        raise MapCaptureError("output must be a named .pcd file")
    if not path.is_absolute():
        path = Path.cwd() / path
    parent = path.parent
    try:
        parent_stat = parent.lstat()
    except OSError as exc:
        raise MapCaptureError("output directory does not exist") from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise MapCaptureError("output directory must be a real directory")
    if path.exists() or path.is_symlink():
        raise MapCaptureError("output file already exists")
    return path


def write_pcd_exclusive(path: Path, snapshot: PcdSnapshot) -> None:
    path = validate_output_path(path)
    descriptor = -1
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(snapshot.header)
            stream.write(snapshot.payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory_fd = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise MapCaptureError(f"PCD output could not be published: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture one fresh /Laser_map as binary PCD.")
    parser.add_argument("output", type=Path)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def _validate_timeout(value: float) -> float:
    if not math.isfinite(value) or value < 1.0 or value > 30.0:
        raise MapCaptureError("timeout must be between 1 and 30 seconds")
    return float(value)


def capture_ros_map(output: Path, timeout: float) -> int:
    output = validate_output_path(output)
    timeout = _validate_timeout(timeout)
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
        from sensor_msgs.msg import PointCloud2
    except ImportError as exc:
        print(f"[Robot Scope] map saver cannot import ROS: {exc}", file=sys.stderr)
        return 2

    qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    snapshot: list[PcdSnapshot] = []
    fatal: list[str] = []

    class MapSaver(Node):
        def __init__(self) -> None:
            super().__init__("robot_scope_map_saver")
            self._map_subscription = self.create_subscription(
                PointCloud2,
                MAP_TOPIC,
                self._on_map,
                qos,
            )

        def _on_map(self, message: Any) -> None:
            if snapshot or fatal:
                return
            publishers = self.get_publishers_info_by_topic(MAP_TOPIC)
            if len(publishers) != 1:
                fatal.append("expected exactly one /Laser_map publisher")
                return
            publisher = publishers[0]
            if str(getattr(publisher, "topic_type", "")) != POINTCLOUD_TYPE:
                fatal.append("/Laser_map publisher type is incompatible")
                return
            publisher_qos = getattr(publisher, "qos_profile", None)
            if (
                getattr(publisher_qos, "reliability", None) != ReliabilityPolicy.RELIABLE
                or getattr(publisher_qos, "durability", None) != DurabilityPolicy.VOLATILE
            ):
                fatal.append("/Laser_map publisher QoS is incompatible")
                return
            try:
                snapshot.append(pointcloud_to_pcd(message))
            except MapCaptureError as exc:
                fatal.append(str(exc))

    # The map topic is fixed; do not allow process-level ROS remaps to retarget
    # this one-shot reader to another graph source.
    rclpy.init(args=[])
    node: Any | None = None
    try:
        node = MapSaver()
        deadline = time.monotonic() + timeout
        while not snapshot and not fatal and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
        if fatal:
            print(f"[Robot Scope] /Laser_map rejected: {fatal[0]}", file=sys.stderr)
            return 3
        if not snapshot:
            print(
                f"[Robot Scope] fresh /Laser_map timed out after {timeout:.1f}s",
                file=sys.stderr,
            )
            return 4
        write_pcd_exclusive(output, snapshot[0])
        print(f"[Robot Scope] PCD saved: {output} ({snapshot[0].points} points)")
        return 0
    except MapCaptureError as exc:
        print(f"[Robot Scope] map save failed: {exc}", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        return 130
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main(argv: Iterable[str] | None = None) -> int:
    options = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        return capture_ros_map(options.output, options.timeout)
    except MapCaptureError as exc:
        print(f"[Robot Scope] map save rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
