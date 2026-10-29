#!/usr/bin/env python3
"""Validate an explicitly selected, separately built Nav2 1.1.20 overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(prefix, *, project=None, base_library=None):
    project = project or Path(__file__).resolve().parents[1]
    base_library = base_library or Path('/opt/ros/humble/lib/libnav2_rotation_shim_controller.so')
    if not prefix.is_absolute() or prefix.is_symlink():
        raise ValueError('overlay must be an explicit absolute directory')
    receipt = json.loads((prefix / 'robot-scope-heading-receipt.json').read_text())
    if receipt.get('schema') != 'robot-scope.nav2-heading-overlay.v1' or receipt.get('nav2_version') != '1.1.20':
        raise ValueError('unsupported overlay receipt')
    patch_dir = project / 'ros2/nav2_goal_heading_fix'
    for name in ('same-time-goal.patch', 'final-rotation-collision.patch', 'common_time.hpp'):
        if digest(patch_dir / name) != receipt['patch_files'][name]:
            raise ValueError('overlay does not match selected release source')
    if receipt['base_library_sha256'] != digest(base_library):
        raise ValueError('installed Nav2 base library changed; rebuild and retest')
    for name in ('lib/libnav2_rotation_shim_controller.so',
                 'share/nav2_rotation_shim_controller/nav2_rotation_shim_controller.xml',
                 'share/nav2_rotation_shim_controller/package.xml'):
        if digest(prefix / name) != receipt['installed_files'][name]:
            raise ValueError('overlay artifact hash mismatch')
    packages = prefix / 'share/ament_index/resource_index/packages'
    if sorted(p.name for p in packages.iterdir()) != ['nav2_rotation_shim_controller']:
        raise ValueError('heading overlay must contain only the pinned Shim package')
    if receipt.get('native_tests_passed') is not True:
        raise ValueError('native candidate tests were not completed')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, required=True)
    args = parser.parse_args()
    receipt = validate(args.overlay)
    version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}',
                                      'ros-humble-nav2-rotation-shim-controller'], text=True)
    if not version.startswith('1.1.20-'):
        raise SystemExit('installed Nav2 package version differs from 1.1.20')
    print(json.dumps({'nav2_version': receipt['nav2_version'],
                      'library_sha256': receipt['installed_files']['lib/libnav2_rotation_shim_controller.so']}))
