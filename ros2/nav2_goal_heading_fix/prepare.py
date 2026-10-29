#!/usr/bin/env python3
"""Verify pinned upstream input and prepare a separate, inactive overlay source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def prepare(cache, destination, *, tf_only=False):
    here = Path(__file__).resolve().parent
    manifest = json.loads((here / 'upstream.json').read_text())
    for name, evidence in manifest['files'].items():
        if hashlib.sha256((cache / name).read_bytes()).hexdigest() != evidence['sha256']:
            raise ValueError('upstream source hash mismatch: ' + name)
    if destination.exists():
        raise ValueError('destination must not exist')
    destination.mkdir(parents=True)
    shutil.copytree(cache / 'nav2_rotation_shim_controller',
                    destination / 'nav2_rotation_shim_controller')
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(here / 'same-time-goal.patch')],
                   cwd=destination, check=True)
    if not tf_only:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(here / 'final-rotation-collision.patch')], cwd=destination, check=True)
    include = destination / 'nav2_rotation_shim_controller' / 'include'
    shutil.copy2(here / 'common_time.hpp', include / 'common_time.hpp')
    (destination / 'source-receipt.json').write_text(json.dumps({
        'upstream': manifest,
        'patch_sha256': hashlib.sha256((here / 'same-time-goal.patch').read_bytes()).hexdigest(),
        'helper_sha256': hashlib.sha256((here / 'common_time.hpp').read_bytes()).hexdigest(),
        'collision_patch_sha256': None if tf_only else hashlib.sha256(
            (here / 'final-rotation-collision.patch').read_bytes()).hexdigest(),
    }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--tf-only', action='store_true')
    args = parser.parse_args()
    prepare(args.cache.resolve(), args.destination.resolve(), tf_only=args.tf_only)
