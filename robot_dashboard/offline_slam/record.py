"""Read-only ROS bag conversion and explicitly launched FAST-LIO recorder.

No publisher, service client, TF broadcaster, driver start or robot command.
Exact source stamps pair registered parent-frame points with odometry. These
are processed FAST-LIO keyframes, not raw LiDAR/IMU archives.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
import json
import os
from pathlib import Path
import uuid

import numpy as np
from scipy.spatial.transform import Rotation

from .core import (
    MAX_BYTES,
    MAX_FRAMES,
    MAX_POINTS,
    SCHEMA,
    encoded,
    inverse,
    project,
    validate_session,
    vector,
)


class Recorder:
    def __init__(
        self,
        calibration_id,
        *,
        distance=0.3,
        angle=0.15,
        parent="camera_init",
        local="body",
        journal=None,
        sensor_origin_body=(0.0, 0.0, 0.0),
    ):
        if not calibration_id or not 0.05 <= distance <= 5 or not 0.02 <= angle <= 1:
            raise ValueError("INVALID_RECORDING_SETTINGS")
        self.data = dict(
            schema=SCHEMA,
            session_id=uuid.uuid4().hex,
            provenance="recorded_fastlio",
            parent_frame=parent,
            local_frame=local,
            calibration_id=calibration_id,
            sensor_origin_body=list(sensor_origin_body),
            processing="FASTLIO_REGISTERED_XYZ_TO_BODY_EXACT_STAMP_VOXEL_0.08M",
            keyframes=[],
            statistics={"paired": 0, "unmatched_evicted": 0, "invalid": 0},
        )
        self.distance, self.angle = distance, angle
        self.poses, self.clouds = OrderedDict(), OrderedDict()
        self.latest = -1
        self.journal = Path(journal) if journal else None
        if self.journal:
            with self.journal.open("xb") as handle:
                handle.write(
                    encoded({k: v for k, v in self.data.items() if k != "keyframes"})
                    + b"\n"
                )
                handle.flush()
                os.fsync(handle.fileno())

    def add(self, kind, stamp, value, frame, child=None):
        if frame != self.data["parent_frame"] or (
            kind == "pose" and child != self.data["local_frame"]
        ):
            raise ValueError("RECORDING_FRAME_MISMATCH")
        if kind not in {"pose", "cloud"}:
            raise ValueError("RECORDING_KIND")
        cache = self.poses if kind == "pose" else self.clouds
        if stamp < self.latest - 2_000_000_000:
            raise ValueError("SOURCE_TIME_RESET_NEW_SESSION_REQUIRED")
        if stamp <= self.latest:
            return
        cache[stamp] = value
        if len(cache) > 32:
            cache.popitem(last=False)
            self.data["statistics"]["unmatched_evicted"] += 1
        if stamp not in self.poses or stamp not in self.clouds:
            return
        t, cloud = self.poses.pop(stamp), self.clouds.pop(stamp)
        self.latest = stamp
        self.data["statistics"]["paired"] += 1
        frames = self.data["keyframes"]
        if frames:
            delta = vector(inverse(np.array(frames[-1]["T_parent_body"])) @ t)
            if (
                np.linalg.norm(delta[:3]) < self.distance
                and np.linalg.norm(delta[3:]) < self.angle
            ):
                return
        if len(frames) >= MAX_FRAMES:
            raise ValueError("RECORDING_KEYFRAME_LIMIT")
        local = project(cloud, inverse(t))
        local = local[np.isfinite(local).all(1) & (np.linalg.norm(local, axis=1) < 100)]
        if len(local) < 30:
            self.data["statistics"]["invalid"] += 1
            return
        _, index = np.unique(
            np.floor(local / 0.08).astype(np.int64), axis=0, return_index=True
        )
        local = local[np.sort(index)]
        if len(local) < 30:
            self.data["statistics"]["invalid"] += 1
            return
        if len(local) > MAX_POINTS:
            local = local[np.linspace(0, len(local) - 1, MAX_POINTS, dtype=int)]
        frames.append(
            dict(stamp_ns=int(stamp), T_parent_body=t.tolist(), points=local.tolist())
        )
        if self.journal:
            with self.journal.open("ab") as handle:
                handle.write(encoded(frames[-1]) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())

    def write(self, destination):
        validate_session(self.data)
        raw = encoded(self.data)
        if len(raw) > MAX_BYTES:
            raise ValueError("RECORDING_SIZE_LIMIT")
        # Exclusive create: no overwrite of an earlier recording.
        with Path(destination).open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())


def recover(journal, destination):
    if Path(journal).stat().st_size > MAX_BYTES:
        raise ValueError("RECORDING_SIZE_LIMIT")
    lines = Path(journal).read_bytes().splitlines(keepends=True)
    data = json.loads(lines[0])
    data["keyframes"] = []
    for index, line in enumerate(lines[1:]):
        if not line.endswith(b"\n") and index == len(lines) - 2:
            break  # An interrupted final write is not a keyframe.
        data["keyframes"].append(json.loads(line))
    data["recovered_from_journal"] = True
    validate_session(data)
    with Path(destination).open("xb") as handle:
        handle.write(encoded(data))


def consume(recorder, kind, message):
    stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
    if kind == "pose":
        p, q = message.pose.pose.position, message.pose.pose.orientation
        quat = np.array([q.x, q.y, q.z, q.w])
        if not np.isfinite(quat).all() or not np.isclose(
            np.linalg.norm(quat), 1, atol=0.01
        ):
            raise ValueError("INVALID_ODOMETRY_QUATERNION")
        t = np.eye(4)
        t[:3, :3] = Rotation.from_quat(quat).as_matrix()
        t[:3, 3] = [p.x, p.y, p.z]
        if not np.isfinite(t).all():
            raise ValueError("INVALID_ODOMETRY")
        recorder.add(kind, stamp, t, message.header.frame_id, message.child_frame_id)
    else:
        from sensor_msgs_py.point_cloud2 import read_points

        if message.width * message.height > 300000:
            raise ValueError("CLOUD_POINT_LIMIT")
        rows = read_points(message, field_names=("x", "y", "z"), skip_nans=True)
        points = np.array([[float(p[0]), float(p[1]), float(p[2])] for p in rows])
        if points.size:
            recorder.add(kind, stamp, points, message.header.frame_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--sensor-origin-body",
        type=float,
        nargs=3,
        help="Calibrated LiDAR origin XYZ in FAST-LIO body coordinates (metres)",
    )
    parser.add_argument(
        "--calibration-id",
        help="Hash or immutable ID of the installed calibration",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--bag", help="Existing ROS2 bag directory; never replayed into ROS"
    )
    source.add_argument(
        "--recover", help="Recover completed keyframes from a .partial.jsonl journal"
    )
    source.add_argument(
        "--live",
        action="store_true",
        help="Explicitly subscribe; does not start FAST-LIO",
    )
    parser.add_argument("--storage-id", default="sqlite3", choices=("sqlite3", "mcap"))
    parser.add_argument("--cloud-topic", default="/cloud_registered")
    parser.add_argument("--pose-topic", default="/Odometry")
    args = parser.parse_args()
    if Path(args.output).exists():
        parser.error("output already exists")
    if args.recover:
        recover(args.recover, args.output)
        return
    if not args.calibration_id:
        parser.error("--calibration-id is required for recording or bag conversion")
    if (
        args.sensor_origin_body is None
        or not np.isfinite(args.sensor_origin_body).all()
        or max(map(abs, args.sensor_origin_body)) > 5
    ):
        parser.error("--sensor-origin-body requires calibrated XYZ in metres")
    recorder = Recorder(
        args.calibration_id,
        journal=args.output + ".partial.jsonl",
        sensor_origin_body=args.sensor_origin_body,
    )
    topics = {args.cloud_topic: "cloud", args.pose_topic: "pose"}
    if len(topics) != 2:
        parser.error("cloud and pose topics must differ")
    if args.bag:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import PointCloud2

        reader = rosbag2_py.SequentialReader()
        reader.open(
            rosbag2_py.StorageOptions(uri=args.bag, storage_id=args.storage_id),
            rosbag2_py.ConverterOptions("", ""),
        )
        expected = {
            args.cloud_topic: "sensor_msgs/msg/PointCloud2",
            args.pose_topic: "nav_msgs/msg/Odometry",
        }
        actual = {t.name: t.type for t in reader.get_all_topics_and_types()}
        if any(actual.get(k) != v for k, v in expected.items()):
            raise ValueError("BAG_TOPIC_CONTRACT")
        while reader.has_next():
            topic, raw, _ = reader.read_next()
            if topic in topics:
                consume(
                    recorder,
                    topics[topic],
                    deserialize_message(
                        raw, Odometry if topics[topic] == "pose" else PointCloud2
                    ),
                )
    else:
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import PointCloud2

        rclpy.init()
        node = rclpy.create_node("robot_scope_offline_keyframe_recorder")
        for topic, kind in topics.items():
            node.create_subscription(
                Odometry if kind == "pose" else PointCloud2,
                topic,
                lambda msg, kind=kind: consume(recorder, kind, msg),
                qos_profile_sensor_data,
            )
        try:
            while rclpy.ok():
                for topic in topics:
                    if node.count_publishers(topic) > 1:
                        raise ValueError("MULTIPLE_INPUT_PUBLISHERS")
                rclpy.spin_once(node, timeout_sec=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            node.destroy_node()
            rclpy.shutdown()
    recorder.write(args.output)
    print(
        json.dumps(
            {
                "keyframes": len(recorder.data["keyframes"]),
                **recorder.data["statistics"],
            }
        )
    )


if __name__ == "__main__":
    main()
