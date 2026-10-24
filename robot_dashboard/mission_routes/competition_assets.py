"""Read-only adapter for the published VM bundle. No ROS imports or launch.

Only allowlisted repository assets with matching publication hashes are served.
Asset integrity is not map registration, native availability or qualification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARENA = REPO / 'assets/competition-arena/revisions/rulebook-20261015'
VM = REPO / 'experiments/competition_vm'


def checked_file(root, name, checksums='SHA256SUMS.txt', limit=2_000_000):
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('VM_ASSET_UNAVAILABLE')
    content = path.read_bytes()
    lines = (root / checksums).read_text().splitlines()
    expected = next((line.split()[0] for line in lines if len(line.split()) == 2 and line.split()[1] == name), None)
    if expected is None or hashlib.sha256(content).hexdigest() != expected:
        raise ValueError('VM_ASSET_HASH_MISMATCH')
    return content, expected


def arena_manifest():
    from .competition_contract import arena_view
    try:
        raw, semantic_hash = checked_file(ARENA, 'arena.semantic.json')
        _, glb_hash = checked_file(ARENA, 'arena.glb')
        data = json.loads(raw)
        if data.get('schema_version') != '0.1' or data.get('frame_id') != 'arena_design' or data.get('gltf_transform') != '(x,z,-y)':
            raise ValueError('VM_ARENA_SCHEMA_UNSUPPORTED')
        view = arena_view(data)
        return {**view, 'available': True, 'evidence_type': 'VM_DESIGN_FIXTURE', 'stage': 'VM_VERIFIED',
                'visual_asset': {'url':'/api/v1/mission-competition/arena/asset', 'sha256':glb_hash, 'format':'glb', 'up_axis':'Y'},
                'semantic_sha256':semantic_hash, 'dimensions': data.get('dimensions', []),
                'semantic_zones':data.get('semantic_zones', []), 'course_status':'DRAFT',
                'notice':'VM 설계 모델 · map_transform 미확정 · 실측 pose overlay 금지 / 현장 주행 검증 아님'}
    except (OSError, ValueError, TypeError):
        return {**arena_view(None), 'available':False, 'evidence_type':'unavailable', 'reason':'VM_ARENA_MISSING_OR_HASH_MISMATCH'}


def vm_evidence(revision='D0-20261024'):
    """Verify one reviewed source AND validation/log bundle, never motion readiness.

    Historical publication queries use preserved source snapshots. The original
    publication manifests are immutable; they do not attest to current D0 code.
    The registry is a code-reviewed allowlist, not a caller-provided manifest.
    """
    modules = ('traffic_signals', 'avoidance', 'integration')
    try:
        registry = json.loads(Path(__file__).with_name('competition_evidence_revisions.json').read_text())
        selected = registry[revision]
        verified = {}
        for name, expected in selected['files'].items():
            path = REPO / name
            if (path.is_symlink() or REPO.resolve() not in path.resolve().parents
                    or not path.is_file() or path.stat().st_size > 8_000_000):
                raise ValueError('EVIDENCE_FILE_UNAVAILABLE')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('EVIDENCE_HASH_MISMATCH')
            verified[name] = expected
        if selected['manifest']:
            manifest = json.loads((REPO / selected['manifest']).read_text())
            if (manifest['revision'] != revision or manifest['scope'] != 'SYNTHETIC_ONLY'
                    or manifest['native_connected'] is not False
                    or any(verified.get(name) != sha for name, sha in manifest['sha256'].items())):
                raise ValueError('EVIDENCE_MANIFEST_MISMATCH')
        return {module: {'stage': 'VM_VERIFIED', 'scope': 'SYNTHETIC_ONLY',
                         'revision': revision, 'native_connected': False,
                         'historical': revision == 'publication-7f2a707',
                         'verified_sha256': {name: sha for name, sha in verified.items()
                                             if '/'+module+'/' in name}}
                for module in modules}
    except (OSError, ValueError, TypeError, KeyError):
        return {module: {'stage': None, 'scope': 'UNAVAILABLE_OR_CHANGED',
                         'revision': revision, 'native_connected': False} for module in modules}
