"""Regenerate a readable summary exclusively from saved JSON, without rerunning cores."""
import json


def markdown(r):
    lines = ['# C7 offline capacity diagnostics', '',
        'READ_ONLY_DIAGNOSTIC_NOT_DRIVING_AUTHORIZATION. Synthetic inputs; no robot/native execution.', '',
        f"Profile: `{r['profile']}`; generated: {r['generated_utc']}", '', '## Status', '',
        '| Check | Result |', '|---|---|']
    lines += [f'| {k} | {v} |' for k,v in r['checks'].items()]
    lines += ['', '## Exact source pins', '', '| Owner | SHA |', '|---|---|']
    lines += [f'| {k} | `{v}` |' for k,v in r['pins'].items()]
    lines += ['', '## Payload boundaries', '',
        '| Input | Objects | Metadata | Full B | Compact B | + reserve B | C4 projected B | Delivery |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for row in [r['baseline']] + r['cases']:
        size = row['compact']['total'] if row['compact'] else None
        lines.append(f"| {row['family']} | {row['objects']} | {row['metadata_bytes']} | {row['full']['total']} | {size} | {size+row['reserve_bytes'] if size else None} | {row['projected_bytes']} | {row['actual_delivery']['status']} {row['actual_delivery'].get('reason') or ''} |")
    lines += ['', 'Compaction rejection retains all core geometry; NOT_SENT does not claim C1/C3 received it.',
        'Each full/compact partition is additive: geometry values, provenance values, input_sources, health, and remaining JSON bytes.',
        '', '## Timings', '', 'Nearest-rank p50/p95, warm-up excluded. Small n is diagnostic, not a stable capacity estimate.', '',
        '| Exact case / stage | n | p50 ms | p95 ms | max ms |', '|---|---:|---:|---:|---:|']
    for name, s in r['timings'].items():
        lines.append(f"| {name} | {s['n']} | {s['p50_ms']:.3f} | {s['p95_ms']:.3f} | {s['max_ms']:.3f} |")
    for key in ('first_observed_rejections','exact_sample_boundary','exact_compactor_boundary','exact_wire_boundary','aggregate_and_assets','counts','fences','queue','composition','maps','c3_cache','browser','process','clocks','environment','configuration','not_measured'):
        if key in r:
            lines += ['', '## '+key.replace('_',' '), '', '```json', json.dumps(r[key],indent=2), '```']
    return '\n'.join(lines) + '\n'
