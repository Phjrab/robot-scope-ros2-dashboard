#!/usr/bin/env python3
"""Run unchanged frozen demo assertions, full repository tests, JS and secret scan."""
import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from restore_fixtures import ROOT, HERE, restore

R = Path('experiments/competition_vm/arena_robot_sim/revisions')

def run(name, argv, out, cwd=ROOT, extra_env=None):
    env = os.environ.copy()
    env.update(extra_env or {})
    start = time.monotonic()
    result = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log = out / (name + '.txt')
    log.write_text(result.stdout)
    report = {'name': name, 'status': 'PASS' if result.returncode == 0 else 'FAIL', 'returncode': result.returncode, 'command': argv, 'cwd': str(Path(cwd).relative_to(ROOT)), 'extra_environment': extra_env or {}, 'elapsed_s': round(time.monotonic() - start, 3), 'log': log.name}
    print(f'{name}: {report["status"]}', flush=True)
    return report

def scan_compressed_fixtures(out):
    spec = importlib.util.spec_from_file_location('secret_checker', ROOT / 'scripts/check_repository_secrets.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    findings = []
    manifest = json.loads((HERE / 'PUBLICATION_SUBSET.json').read_text())
    # Extend the repository scan to all included text, including gzip and >2 MiB originals.
    for entry in manifest['included']:
        path = ROOT / entry['path']
        data = path.read_bytes()
        if entry['encoding'] == 'gzip':
            data = gzip.decompress(data)
        try:
            content = data.decode('utf-8')
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(content.splitlines(), 1):
            for rule, pattern in module.SECRET_RULES.items():
                if pattern.search(line):
                    findings.append({'rule': rule, 'path': entry['path'], 'line': line_number})
    (out / 'included_artifact_secret_scan.json').write_text(json.dumps({'status': 'FAIL' if findings else 'PASS', 'artifact_count': len(manifest['included']), 'findings': findings}, indent=2) + '\n')
    return {'name': 'included_artifact_secret_scan', 'status': 'FAIL' if findings else 'PASS', 'finding_count': len(findings)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--focused-only', action='store_true', help='Omit required full repository, JS and tracked-source checks; never a full-pass claim.')
    parser.add_argument('--output-dir', type=Path, default=HERE / 'validation')
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    restore()
    reports = []
    for name, revision, pattern in [('old_gait', 'articulated-20261024', 'test_gait.py'), ('curved_gait', 'articulated-curved-20261024', 'test_gait.py'), ('left_slalom', 'left_slalom_20261024', 'test_slalom.py'), ('curved_controller', 'curved_slalom_20261024', 'test_curved.py'), ('partial_course', 'full_course_flat_segments_20261024', 'test_flat.py')]:
        reports.append(run(name, [sys.executable, '-m', 'unittest', 'discover', '-s', str(R / revision), '-p', pattern, '-v'], out))
    reports.append(run('old_independent_review', [sys.executable, '-m', 'unittest', 'discover', '-s', str(R / 'articulated-20261024/review'), '-v'], out, extra_env={'ARENA_SLALOM_SOURCE_ROOT': str(ROOT)}))
    metrics = ROOT / R / 'articulated-curved-20261024/review/synthetic_curve_metrics.json'
    original_metrics = metrics.read_bytes()
    try:
        for case, mode in [('open_normal', 'variable'), ('open_baseline', 'fixed')]:
            reports.append(run('curved_review_' + case, [sys.executable, '-m', 'unittest', 'discover', '-s', str(R / 'articulated-curved-20261024/review'), '-v'], out, extra_env={'CURVED_TRACE_FILE': str(ROOT / R / 'curved_slalom_20261024/results/final_regressions' / (case + '.json')), 'CURVED_JOINT_FILE': str(ROOT / R / 'articulated-curved-20261024/output' / (case + '_joints.json')), 'EXPECTED_YAW_MODE': mode}))
            (out / ('synthetic_curve_metrics_' + case + '.json')).write_bytes(metrics.read_bytes())
    finally:
        # The unchanged synthetic tests generate this output. Preserve the frozen historical artifact.
        metrics.write_bytes(original_metrics)
    if not args.focused_only:
        reports.append(run('repository_python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], out))
        reports.append(run('repository_javascript', ['node', '--test', *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'tests').glob('*.mjs'))]], out))
        reports.append(run('repository_secret_scan', [sys.executable, 'scripts/check_repository_secrets.py'], out))
    reports.append(scan_compressed_fixtures(out))
    restore(check_only=True)
    summary = {'schema': 'd0-demo-publication-verification.v1', 'scope': 'focused-only' if args.focused_only else 'focused + full repository Python + JavaScript + secret scans', 'all_checks_passed': all(x['status'] == 'PASS' for x in reports), 'reports': reports}
    (out / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if summary['all_checks_passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
