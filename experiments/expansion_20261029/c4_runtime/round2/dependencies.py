"""Read-only exact-SHA dependency setup; never fetches, checks out or copies code here."""
import hashlib
import os
from pathlib import Path
import subprocess

PINS = {
    'c1': '54629c793ad4ae0ea88127f00ed1b7f8805fc4e2',
    'd2': 'c0d266e290a2d29c173d3b83520f8c96efea9447',
    'd3': '09b68b692fa4b7ccdea39b1a16e3ff150794e12d',
    'c3': '92658bccc253f31552415f9c9d667bbd28957a06',
}
PREFIXES = {
    'c1': ['robot_dashboard/expansion_contracts', 'robot_dashboard/expansion_services'],
    'd2': ['robot_dashboard/obstacle_fusion_core'],
    'd3': ['robot_dashboard/collision_geometry_core'],
    'c3': ['robot_dashboard/static/features/obstacle_scene'],
}
REPO = Path(__file__).resolve().parents[4]
_loaded = None


def load():
    global _loaded
    if _loaded is not None:
        return _loaded
    root = Path(os.environ['C4_ROUND2_DEP_ROOT']).resolve()
    import robot_dashboard
    paths = {}
    for role, sha in PINS.items():
        export = root / f'{role}-{sha}'
        tree = subprocess.check_output(['git', 'ls-tree', '-r', sha, '--', *PREFIXES[role]], cwd=REPO, text=True)
        if not tree.strip():
            raise RuntimeError('PINNED_TREE_MISSING: ' + role)
        for entry in tree.splitlines():
            info, name = entry.split('\t'); expected = info.split()[2]
            path = export / name
            data = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual != expected or path.stat().st_mode & 0o222:
                raise RuntimeError('DEPENDENCY_HASH_OR_READONLY_MISMATCH: ' + name)
        paths[role] = export
        if role != 'c3':
            robot_dashboard.__path__.append(str(export / 'robot_dashboard'))
    # Both cores import pre-existing common code. Prove that local common sources
    # match their pinned owner copies; no implicit use of a different algorithm.
    for role, prefix in [('d2', 'robot_dashboard/relocalization'), ('c1', 'robot_dashboard/pcd_editing')]:
        changed = subprocess.check_output(['git', 'diff', '--name-only', PINS[role], 'HEAD', '--', prefix], cwd=REPO, text=True)
        if changed.strip():
            raise RuntimeError('COMMON_DEPENDENCY_DIFF: ' + changed)
    _loaded = paths
    return paths
