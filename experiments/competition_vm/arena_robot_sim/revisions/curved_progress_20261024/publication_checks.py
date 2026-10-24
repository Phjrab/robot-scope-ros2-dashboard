#!/usr/bin/env python3
"""Publisher-owned portable verification. Frozen sources/tests remain unchanged."""
from pathlib import Path
import argparse, gzip, hashlib, importlib.util, json, os, subprocess, sys, tempfile, time

HERE = Path(__file__).resolve().parent
REVISIONS = HERE.parent
ROOT = HERE.parents[4]
NAMES = ('curved_progress_20261024', 'planning_watchdog_20261024')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Out-of-root manifest path: ' + relative)
    return path


def verify_and_restore(restore=True):
    count = packed_count = 0
    for name in NAMES:
        revision = REVISIONS / name
        manifest = json.loads((revision / 'PUBLICATION_SUBSET.json').read_text())
        for entry in manifest['included_original_files']:
            path = checked_path(revision, entry['publication_path'])
            data = path.read_bytes()
            assert len(data) == entry['publication_bytes'] and digest(data) == entry['publication_sha256'], str(path)
            raw = gzip.decompress(data) if entry['encoding'] == 'gzip-lossless' else data
            assert len(raw) == entry['source_bytes'] and digest(raw) == entry['source_sha256'], str(path)
            if entry['encoding'] == 'gzip-lossless':
                target = checked_path(revision, entry['source_path'])
                if target.exists():
                    assert target.read_bytes() == raw, 'Refusing to replace changed fixture: ' + str(target)
                elif restore:
                    target.write_bytes(raw)
                packed_count += 1
            count += 1
    dependency_manifest = json.loads((HERE / 'PUBLICATION_DEPENDENCIES.json').read_text())
    for entry in dependency_manifest['files']:
        path = checked_path(ROOT, entry['path'])
        if path.exists():
            data = path.read_bytes()
        else:
            packed = checked_path(ROOT, entry['packed_path'])
            assert digest(packed.read_bytes()) == entry['packed_sha256']
            data = gzip.decompress(packed.read_bytes())
            if restore:
                path.write_bytes(data)
        assert len(data) == entry['bytes'] and digest(data) == entry['sha256'], str(path)
    return {'original_artifacts': count, 'exact_gzip_fixtures': packed_count, 'dependency_files': len(dependency_manifest['files']), 'status': 'PASS'}


def run(name, argv, out, cwd):
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    start = time.monotonic()
    proc = subprocess.run(argv, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / (name + '.log')).write_text(proc.stdout)
    result = {'name': name, 'status': 'PASS' if proc.returncode == 0 else 'FAIL', 'returncode': proc.returncode, 'elapsed_s': round(time.monotonic() - start, 3), 'command': argv, 'cwd': str(cwd), 'log': name + '.log'}
    print(name + ': ' + result['status'], flush=True)
    return result


def scan_new_artifacts(out):
    spec = importlib.util.spec_from_file_location('secret_checker', ROOT / 'scripts/check_repository_secrets.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    findings, count = [], 0
    for name in NAMES:
        for path in sorted((REVISIONS / name).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.is_relative_to(out):
                continue
            data = path.read_bytes()
            if path.suffix == '.gz':
                data = gzip.decompress(data)
            try:
                content = data.decode('utf-8')
            except UnicodeDecodeError:
                continue
            count += 1
            for line_no, line in enumerate(content.splitlines(), 1):
                for rule, pattern in mod.SECRET_RULES.items():
                    if pattern.search(line):
                        findings.append({'rule': rule, 'path': str(path.relative_to(ROOT)), 'line': line_no})
    result = {'name': 'new_artifact_secret_scan', 'status': 'FAIL' if findings else 'PASS', 'text_files_including_decompressed_fixtures': count, 'findings': findings, 'limitation': 'Repository pattern-based scanner only; not a comprehensive credential guarantee.'}
    (out / 'new_artifact_secret_scan.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--focused-only', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    integrity = verify_and_restore(not args.check_only)
    print(json.dumps(integrity), flush=True)
    if args.check_only:
        return 0
    out = args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix='followup-publication-'))
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Use an empty output directory; frozen results are never overwritten.')
    print('Output: ' + str(out), flush=True)
    watchdog = REVISIONS / NAMES[1]
    reports = [run('progress_22', [sys.executable, '-B', '-m', 'unittest', 'test_progress', 'test_regression', '-v'], out, HERE),
               run('watchdog_15', [sys.executable, '-B', str(watchdog / 'test_runtime_guard.py')], out, out),
               run('actual_planner_timeout', [sys.executable, '-B', str(watchdog / 'actual_planner_timeout.py')], out, out),
               run('progress_independent_review', [sys.executable, '-B', str(HERE / 'publication_replay_review.py'), 'progress', str(out)], out, out),
               run('watchdog_independent_races', [sys.executable, '-B', str(HERE / 'publication_replay_review.py'), 'watchdog', str(out)], out, out)]
    if not args.focused_only:
        reports.extend([run('repository_python', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], out, ROOT),
                        run('repository_javascript', ['node', '--test', *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'tests').glob('*.mjs'))]], out, ROOT),
                        run('repository_secret_scan', [sys.executable, '-B', 'scripts/check_repository_secrets.py'], out, ROOT),
                        run('diff_check', ['git', 'diff', '--check'], out, ROOT)])
    reports.append(scan_new_artifacts(out))
    integrity_after = verify_and_restore(False)
    summary = {'schema': 'followup-publication-verification.v1', 'scope': 'focused-only' if args.focused_only else 'selected + full repository Python + JavaScript + tracked and new artifact secret scans', 'all_checks_passed': all(x['status'] == 'PASS' for x in reports), 'integrity_before': integrity, 'integrity_after': integrity_after, 'reports': reports, 'not_run': ['new scenario regeneration or repeat simulation', 'profile/memoization benchmark rerun', 'new articulated-mesh or animation validation', 'native ROS, hardware or physical stopping', 'remote CI or publication']}
    (out / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('Output: ' + str(out), flush=True)
    return 0 if summary['all_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
