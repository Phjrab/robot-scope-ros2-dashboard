#!/usr/bin/env python3
"""Publish only observed camera ancestor transforms from a hashed bag inspection.

No transform values or frames are synthesized. Only the isolated /vslam_lab TF
topic is used. The original bag /tf and whole /tf_static must not be replayed.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import time


def selected_transforms(evidence, contract):
    source_sha = contract['source']['sha256']
    if contract['source']['kind'] != 'bag' or not any(row.get('sha256') == source_sha for row in evidence.get('files', [])):
        raise ValueError('Inspection bag SHA-256 does not match the input contract')
    topic = evidence['topics']['/tf_static']
    # The official sample has exactly one static TF message. Never mistake a
    # first-message snapshot for a complete multi-message static TF history.
    if topic.get('type') != 'tf2_msgs/msg/TFMessage' or topic.get('count') != 1:
        raise ValueError('This selected publisher requires a complete single-message /tf_static inspection')
    transforms = topic['first']['transforms']
    by_child = {}
    for transform in transforms:
        child = transform['child_frame_id']
        if child in by_child:
            raise ValueError('Ambiguous repeated child in static transform evidence')
        by_child[child] = transform
    base = contract['base_frame']
    selected = {}
    for target in (contract['left']['image_frame'], contract['right']['image_frame']):
        cursor, visited = target, set()
        while cursor != base:
            if cursor in visited or cursor not in by_child:
                raise ValueError('Missing or cyclic observed static transform chain')
            visited.add(cursor)
            transform = by_child[cursor]
            parent = transform['header']['frame_id']
            if parent in ('base_link', 'map', 'odom') or cursor in ('base_link', 'map', 'odom'):
                raise ValueError('Selected camera chain must not include operational/body/world frames')
            t = transform['transform']['translation']
            q = transform['transform']['rotation']
            values = [t[k] for k in ('x', 'y', 'z')] + [q[k] for k in ('x', 'y', 'z', 'w')]
            if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in values):
                raise ValueError('Nonfinite static transform')
            if abs(sum(q[k] ** 2 for k in ('x', 'y', 'z', 'w')) - 1) > 1e-5:
                raise ValueError('Recorded rotation must be unit length; never silently normalize evidence')
            selected[cursor] = copy.deepcopy(transform)
            cursor = parent
    return list(selected.values())


def load_selected(evidence_path, contract_path):
    raw = evidence_path.read_bytes()
    contract = json.loads(contract_path.read_text())
    if hashlib.sha256(raw).hexdigest() != contract.get('static_tf_evidence_sha256'):
        raise ValueError('Static TF inspection file hash differs from the observed contract')
    return selected_transforms(json.loads(raw), contract)


def publish_when_clock_ready(broadcaster, messages, ros_time_ns, wall_now, next_publish):
    """Keep original evidence intact across the bag's first ROS clock jump.

    A TF listener can clear its buffer when /clock starts after construction.
    Re-send the same static observations on a bounded wall-clock cadence; ROS
    time controls readiness only, so a paused bag never blocks cleanup.
    """
    if ros_time_ns <= 0 or wall_now < next_publish:
        return next_publish, False
    broadcaster.sendTransform(messages)
    return wall_now + .5, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=180)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 900:
        parser.error('duration must be finite and 1..900 seconds')
    guard = runpy.run_path(str(Path(__file__).resolve().parent / 'config' / 'launch_contract.py'))
    guard['isolated_environment'](os.environ)
    transforms = load_selected(args.evidence, args.contract)
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from geometry_msgs.msg import TransformStamped
    from tf2_ros import StaticTransformBroadcaster
    rclpy.init(args=['--ros-args', '-r', '/tf_static:=/vslam_lab/tf_static', '-p', 'use_sim_time:=true'])
    node = rclpy.create_node('observed_static_tf', namespace='/vslam_lab')
    broadcaster = StaticTransformBroadcaster(node)
    messages = []
    for value in transforms:
        msg = TransformStamped()
        msg.header.frame_id = value['header']['frame_id']
        msg.header.stamp.sec = value['header']['stamp']['sec']
        msg.header.stamp.nanosec = value['header']['stamp']['nanosec']
        msg.child_frame_id = value['child_frame_id']
        for name in ('x', 'y', 'z'):
            setattr(msg.transform.translation, name, float(value['transform']['translation'][name]))
        for name in ('x', 'y', 'z', 'w'):
            setattr(msg.transform.rotation, name, float(value['transform']['rotation'][name]))
        messages.append(msg)
    print(json.dumps({'status': 'WAITING_FOR_POSITIVE_ROS_CLOCK', 'count': len(messages),
                      'topic': '/vslam_lab/tf_static', 'pairs': [[m.header.frame_id, m.child_frame_id] for m in messages]}), flush=True)
    try:
        deadline = time.monotonic() + args.duration
        next_publish, publish_count = 0.0, 0
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
            next_publish, published = publish_when_clock_ready(
                broadcaster, messages, node.get_clock().now().nanoseconds,
                time.monotonic(), next_publish)
            if published:
                publish_count += 1
                if publish_count == 1:
                    print(json.dumps({'status': 'PUBLISHED_RECORDED_CAMERA_TF_ONLY',
                                      'count': len(messages), 'republish_wall_interval_s': .5}), flush=True)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
