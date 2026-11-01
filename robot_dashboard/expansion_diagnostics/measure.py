"""Measurement records have a clock and a precise operation; no cross-clock subtraction."""
from collections import defaultdict
import hashlib
import json
import math
import time


def encoded(value):
    # Diagnostic byte accounting only. Acceptance always invokes the owner's validator.
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def stats(values):
    ordered = sorted(values)
    if not ordered:
        return {'n': 0, 'p50_ms': None, 'p95_ms': None, 'max_ms': None}
    return dict(n=len(values), p50_ms=ordered[math.ceil(.5 * len(ordered)) - 1],
                p95_ms=ordered[math.ceil(.95 * len(ordered)) - 1], max_ms=ordered[-1])


class Measurements:
    def __init__(self):
        self.events = []
        self.warmup = False
        self.case = ''

    def call(self, stage, function, *args, **kwargs):
        start, cpu = time.perf_counter_ns(), time.process_time_ns()
        outcome = 'PASS'
        try:
            return function(*args, **kwargs)
        except Exception:
            outcome = 'RAISED'
            raise
        finally:
            end = time.perf_counter_ns()
            self.events.append(dict(case=self.case, stage=stage, warmup=self.warmup,
                clock='python.perf_counter_ns', start_ns=start, end_ns=end,
                duration_ms=(end-start)/1e6, process_cpu_ms=(time.process_time_ns()-cpu)/1e6,
                outcome=outcome, evidence_kind='ACTUAL_CODE_SYNTHETIC_INPUT'))

    def summary(self):
        groups = defaultdict(list)
        for e in self.events:
            if not e['warmup']:
                groups[e['case'] + '/' + e['stage']].append(e['duration_ms'])
        return {k: stats(v) for k, v in groups.items()}


def duration(start, end):
    if start['clock'] != end['clock'] or end['ns'] < start['ns']:
        return {'status': 'UNKNOWN', 'reason': 'CLOCK_MAPPING_MISSING_OR_REVERSED'}
    return {'status': 'MEASURED', 'duration_ns': end['ns'] - start['ns'], 'clock': start['clock']}


def breakdown(frame):
    """Disjoint additive JSON byte partition, including punctuation in residual."""
    geometry = sum(len(encoded(o['geometry'])) for o in frame['obstacles'])
    provenance = sum(len(encoded(o.get('provenance'))) for o in frame['obstacles'])
    sources = len(encoded(frame['input_sources']))
    metadata = len(encoded(frame['health']))
    total = len(encoded(frame))
    return dict(total=total, geometry_values=geometry, provenance_values=provenance,
                input_sources_value=sources, health_value=metadata,
                other_fields_keys_and_json_punctuation=total-geometry-provenance-sources-metadata)
