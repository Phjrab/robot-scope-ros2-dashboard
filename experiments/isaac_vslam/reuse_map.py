#!/usr/bin/env python3
"""Bounded map reuse using an explicit camera pose hint; no global localization claim."""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import runpy
import time

from save_map import map_inventory, mapping_evidence


def checked_map(saved_run):
    report = json.loads((saved_run / 'map-save.json').read_text())
    if report.get('status') != 'SAVED_NOT_RELOCALIZATION_TESTED':
        raise ValueError('No verified saved map')
    actual = map_inventory(saved_run / 'map')
    if actual != report.get('files'):
        raise ValueError('Map files changed after save')
    return actual


def checked_hint(path):
    hint = json.loads(path.read_text())
    if not hint.get('evidence'):
        raise ValueError('Explicit hint provenance required')
    p, q = hint['position'], hint['quaternion_xyzw']
    if len(p) != 3 or len(q) != 4 or not all(
            isinstance(v, (float, int)) and math.isfinite(v) for v in p + q):
        raise ValueError('Finite 6DoF hint required')
    if abs(math.hypot(*q) - 1) > .001:
        raise ValueError('Normalized hint quaternion required')
    return hint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-run', type=Path, required=True)
    parser.add_argument('--saved-run', type=Path, required=True)
    parser.add_argument('--pose-hint', type=Path, required=True)
    a = parser.parse_args()
    report = {'status': 'FAILED', 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'global_localization_tested': False, 'motion_accuracy_tested': False}
    node = None
    initialized = False
    with (a.current_run / 'map-reuse.json').open('x') as output:
        try:
            runpy.run_path(str(Path(__file__).parent / 'config/launch_contract.py'))['isolated_environment'](os.environ)
            if a.current_run.resolve() == a.saved_run.resolve():
                raise ValueError('A separate estimator run is required')
            report['files'] = checked_map(a.saved_run)
            report['current_mapping_evidence'] = mapping_evidence(a.current_run)
            report['hint'] = checked_hint(a.pose_hint)
            import rclpy
            from isaac_ros_visual_slam_interfaces.srv import FilePath, LocalizeInMap
            rclpy.init(args=[])
            initialized = True
            node = rclpy.create_node('map_reuse_verifier', namespace='/vslam_lab')
            deadline = time.monotonic() + 20
            def call(typ, name, request):
                client = node.create_client(typ, name)
                try:
                    if not client.wait_for_service(timeout_sec=max(0, deadline-time.monotonic())):
                        raise TimeoutError(name)
                    future = client.call_async(request)
                    rclpy.spin_until_future_complete(node, future, timeout_sec=max(0, deadline-time.monotonic()))
                    if not future.done():
                        future.cancel()
                        raise TimeoutError(name)
                    result = future.result()
                    return bool(result is not None and result.success)
                finally:
                    node.destroy_client(client)
            directory = str((a.saved_run / 'map').resolve())
            request = FilePath.Request()
            request.file_path = directory
            report['load_path_accepted'] = call(FilePath, '/vslam_lab/visual_slam/load_map', request)
            request = LocalizeInMap.Request()
            request.map_folder_path = directory
            p, q = report['hint']['position'], report['hint']['quaternion_xyzw']
            request.pose_hint.position.x, request.pose_hint.position.y, request.pose_hint.position.z = map(float, p)
            (request.pose_hint.orientation.x, request.pose_hint.orientation.y,
             request.pose_hint.orientation.z, request.pose_hint.orientation.w) = map(float, q)
            report['localize_service_success'] = call(LocalizeInMap, '/vslam_lab/visual_slam/localize_in_map', request)
            report['status'] = ('LOCALIZE_SERVICE_SUCCESS_REQUIRES_POSE_REVIEW' if report['localize_service_success']
                                else 'LOCALIZE_FAILED')
        except Exception as exc:
            report['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            report['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            json.dump(report, output, indent=2, allow_nan=False)
            if node is not None:
                node.destroy_node()
            if initialized and rclpy.ok():
                rclpy.shutdown()


if __name__ == '__main__':
    main()
