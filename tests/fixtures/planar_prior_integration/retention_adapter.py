"""Synthetic input → production worker metadata. Never constructs resolution proof.

Execution envelope is explicitly synthetic: no external solver subprocess runs.
The coordinator's expected pin is bound to the actual pinned REVIEWED_HASHES.
"""
import copy
import hashlib
import json
from robot_dashboard.relocalization.global_observation_worker import _retained_candidate_metadata
from robot_dashboard.relocalization.v031_observation_compat import REVIEWED_HASHES
SOURCE_PIN = {'files': dict(REVIEWED_HASHES)}
SOURCE_PIN_SHA256 = hashlib.sha256(json.dumps(SOURCE_PIN, sort_keys=True).encode()).hexdigest()

def attach_real_retention_evidence(result, context, *, variant):
    result = copy.deepcopy(result)
    if variant == 'legacy':
        if context.get('retained_candidates_requested'):raise RuntimeError('LEGACY_RETENTION_UNEXPECTED')
        return result
    if context.get('retained_candidates_requested') is not True:
        raise RuntimeError('REAL_COORDINATOR_RETENTION_REQUEST_REQUIRED')
    for index, candidate in enumerate(result['candidates']):
        candidate['attempt'] = index
        candidate.setdefault('duplicate_of',None)
    for index in range(len(result['candidates']), 6):
        result['candidates'].append({'attempt': index, 'map_from_scan': None, 'gate_reasons': ['FAILED_RANSAC'], 'duplicate_of':None})
    if variant == 'truncated':
        result['candidates'].pop()
    metadata = _retained_candidate_metadata(result)
    if metadata is not None:
        result['candidate_retention'] = metadata
    if variant == 'missing-metadata': result.pop('candidate_retention', None)
    if variant == 'tampered-metadata': result['candidate_retention']['sha256'] = '0' * 64
    result['execution'] = {'source_pin_sha256': SOURCE_PIN_SHA256, 'worker_reaped': True,
                           'fixture_execution': 'SYNTHETIC_RUNNER_NO_SOLVER_SUBPROCESS'}
    return result
