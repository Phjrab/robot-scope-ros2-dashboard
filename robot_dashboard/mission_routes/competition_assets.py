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


def vm_evidence():
    """Published test evidence is diagnostic; never register a native executor."""
    result = {}
    for module, file, checksum in [('traffic_signals','core.py','SHA256SUMS'), ('avoidance','core.py','SHA256SUMS.txt'), ('integration','adapter.py','SHA256SUMS.txt')]:
        try:
            _, sha = checked_file(VM / module, file, checksum)
            result[module] = {'stage':'VM_VERIFIED', 'scope':'SYNTHETIC_ONLY', 'source_sha256':sha, 'native_connected':False}
        except (OSError, ValueError):
            result[module] = {'stage':None, 'scope':'UNAVAILABLE_OR_CHANGED', 'native_connected':False}
    return result
