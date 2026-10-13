#!/usr/bin/env python3
"""Save an observed lab SLAM map before stopping its estimator.

A successful service response and nonempty files prove persistence only;
map coverage, accuracy and relocalization still need separate verification.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import time


def mapping_evidence(run_dir):
    launch = json.loads((run_dir / 'vslam_launch.json').read_text())
    if (launch.get('mode') not in ('slam_vo', 'slam_vio') or
            launch.get('requested_parameters', {}).get('enable_localization_n_mapping') is not True):
        raise ValueError('This run did not launch mapping mode')
    if str(launch.get('ros_domain_id')) != os.environ.get('ROS_DOMAIN_ID'):
        raise ValueError('Launch domain differs from the current lab domain')
    starts, paths = [], []
    with (run_dir / 'metrics.jsonl').open() as source:
        for line in source:
            event = json.loads(line)
            if event.get('event') == 'run_start':
                starts.append(event)
            if (event.get('event') == 'sample' and event.get('stream') == 'slam_path'
                    and event.get('path_poses', 0) > 0):
                paths.append(event['path_poses'])
    if (len(starts) != 1 or starts[0].get('run_id') != run_dir.name or
            str(starts[0].get('ros_domain_id')) != os.environ.get('ROS_DOMAIN_ID')):
        raise ValueError('Metrics do not belong to this run and domain')
    if not paths:
        raise RuntimeError('No nonempty SLAM path observed; refusing to claim a map')
    return {'slam_path_samples': len(paths), 'max_path_poses': max(paths),
            'evidence_type': starts[0].get('evidence_type')}


def map_inventory(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError('Save service did not create a map directory')
    files = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Unexpected symlink in saved map')
        if path.is_file() and path.stat().st_size:
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(block)
            files.append({'path': str(path.relative_to(directory)),
                          'bytes': path.stat().st_size, 'sha256': digest.hexdigest()})
    if not files:
        raise RuntimeError('Save service returned without nonempty map files')
    return files


def save_run_map(run_dir, timeout=45):
    run_dir = Path(run_dir).resolve(strict=True)
    report = {'status': 'FAILED', 'map_directory': str(run_dir / 'map'),
              'service': '/vslam_lab/visual_slam/save_map',
              'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'relocalization_verified': False, 'coverage_verified': False}
    # Exclusive creation preserves the result of any earlier attempt.
    with (run_dir / 'map-save.json').open('x') as output:
        node = None
        initialized = False
        try:
            guard = runpy.run_path(str(Path(__file__).parent / 'config/launch_contract.py'))
            guard['isolated_environment'](os.environ)
            if not 1 <= timeout <= 60:
                raise ValueError('Map save timeout must be 1..60 seconds')
            destination = run_dir / 'map'
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('Map destination already exists; use a new run')
            report['observation'] = mapping_evidence(run_dir)
            import rclpy
            from rcl_interfaces.srv import GetParameters
            from rcl_interfaces.msg import ParameterType
            from isaac_ros_visual_slam_interfaces.srv import FilePath

            rclpy.init(args=[])
            initialized = True
            node = rclpy.create_node('map_save_verifier', namespace='/vslam_lab')
            deadline = time.monotonic() + timeout

            def call(service_type, name, request):
                client = node.create_client(service_type, name)
                try:
                    if not client.wait_for_service(timeout_sec=max(0, deadline - time.monotonic())):
                        raise TimeoutError(f'Service unavailable: {name}')
                    future = client.call_async(request)
                    rclpy.spin_until_future_complete(
                        node, future, timeout_sec=max(0, deadline - time.monotonic()))
                    if not future.done():
                        future.cancel()
                        raise TimeoutError(f'Service did not finish: {name}')
                    return future.result()
                finally:
                    node.destroy_client(client)

            request = GetParameters.Request()
            request.names = ['enable_localization_n_mapping']
            response = call(GetParameters, '/vslam_lab/visual_slam_node/get_parameters', request)
            if (response is None or len(response.values) != 1 or
                    response.values[0].type != ParameterType.PARAMETER_BOOL or
                    not response.values[0].bool_value):
                raise RuntimeError('Running estimator does not have mapping enabled')
            report['runtime_mapping_enabled'] = True
            request = FilePath.Request()
            request.file_path = str(destination)
            response = call(FilePath, report['service'], request)
            report['service_success'] = response is not None and bool(response.success)
            if not report['service_success']:
                raise RuntimeError('Isaac ROS save_map reported failure')
            report['files'] = map_inventory(destination)
            report['status'] = 'SAVED_NOT_RELOCALIZATION_TESTED'
            return report
        except BaseException as exc:
            report['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            report['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            json.dump(report, output, indent=2, allow_nan=False)
            output.write('\n')
            if node is not None:
                node.destroy_node()
            if initialized and rclpy.ok():
                rclpy.shutdown()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=15)
    args = parser.parse_args()
    print(json.dumps(save_run_map(args.run_dir, args.timeout), indent=2))
