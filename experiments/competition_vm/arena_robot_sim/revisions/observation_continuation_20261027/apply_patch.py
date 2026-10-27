"""Apply only to an explicit C3 checkout; fail on drift, no server/native execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def apply(checkout):
    here = Path(__file__).resolve().parent
    pin = json.loads((here / 'source_pin.json').read_text())
    checkout = Path(checkout).resolve()
    target = checkout / pin['path']
    helper = target.with_name('native_observation.py')
    if hashlib.sha256(target.read_bytes()).hexdigest() != pin['base_sha256']:
        raise ValueError('source hash differs; inspect upstream changes, do not force apply')
    if helper.exists():
        raise ValueError('helper exists; preserve and review before modifying')
    patch = here / 'native_runner.patch'
    subprocess.run(['git', 'apply', '--unidiff-zero', '--check', str(patch)], cwd=checkout, check=True)
    subprocess.run(['git', 'apply', '--unidiff-zero', str(patch)], cwd=checkout, check=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != pin['patched_sha256']:
        raise RuntimeError('patched hash mismatch; inspect checkout, no automatic rollback')
    helper.write_bytes((here / 'observation.py').read_bytes())
    return target


if __name__ == '__main__':
    print(apply(sys.argv[1]))
