"""Export exact owner blobs to a new read-only directory; never merge peer code."""
import argparse
import io
from pathlib import Path
import subprocess
import tarfile

PINS = {
    'C1': '50600c7bce6f5fae743cd836ca1d8ee68d91b05a',
    'D1': '203c144f6b4a90966839c34b603ae12ee676cb12',
    'D2': '7313f0a31c00ae87ae216b84ca41a23804e91917',
    'D3': '356d0a036eb62d546e159e12a0691d7f5ea278f6',
    'C2': '47a1d031d797c098c38a0147894523d07d30db8f',
}
PATHS = {
    'C1': ('robot_dashboard/expansion_contracts', 'robot_dashboard/expansion_services',
           'experiments/expansion_20261029/c1_service_host/host.py'),
    'D1': ('robot_dashboard/multimap_core', 'experiments/expansion_20261029/d1_multimap/generate.py'),
    'D2': ('robot_dashboard/obstacle_fusion_core',),
    'D3': ('robot_dashboard/collision_geometry_core',),
    'C2': ('experiments/expansion_20261029/c2_map_ui/exact_service_host.py',),
}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    args.directory.mkdir()  # Existing dependency trees are never changed.
    for role, paths in PATHS.items():
        raw=subprocess.check_output(['git','archive',PINS[role],*paths])
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(args.directory,filter='data')
    for path in args.directory.rglob('*'):
        path.chmod(0o555 if path.is_dir() else 0o444)
    args.directory.chmod(0o555)
    print(args.directory)

if __name__=='__main__':main()
