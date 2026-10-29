"""Export and verify exact Git objects without changing any checkout or fetching."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

PINS = {
    'main': '5154761bba6fa4f171881e61f986901e2b415ed9',
    'C1': '50600c7bce6f5fae743cd836ca1d8ee68d91b05a',
    'C2': '7625c87ede2489143c44862d883e10fc1791df28',
    'C3': '5bf58097f4a67806f5515b931a3b8013d65bf01e',
    'C4': '7ac0d55b07abd20902d6d756c6b225733613fea7',
    'D1': '203c144f6b4a90966839c34b603ae12ee676cb12',
    'D2': '7313f0a31c00ae87ae216b84ca41a23804e91917',
    'D3': '356d0a036eb62d546e159e12a0691d7f5ea278f6',
}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def prepare(repo, target):
    """Whole immutable exports allow existing owner generators/tests to run unchanged."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    for role, sha in PINS.items():
        if role == 'main':
            continue
        git(repo, 'cat-file', '-e', sha + '^{commit}')
        dest = target / role
        dest.mkdir()
        with tempfile.TemporaryFile() as stream:
            subprocess.run(['git', '-C', str(repo), 'archive', sha], stdout=stream, check=True)
            stream.seek(0)
            with tarfile.open(fileobj=stream) as archive:
                archive.extractall(dest, filter='data')
        for p in dest.rglob('*'):
            if not p.is_symlink():
                p.chmod(p.stat().st_mode & ~0o222)
        dest.chmod(0o555)
    (target / 'pins.json').write_text(json.dumps(PINS, indent=2) + '\n')
    return target


def verify(repo, root):
    """Verify every executable/importable source before execution, not a trusted marker."""
    root = Path(root).resolve()
    if json.loads((root / 'pins.json').read_text()) != PINS:
        raise ValueError('DEPENDENCY_PINS_DIFFER')
    evidence = {}
    for role, sha in PINS.items():
        if role == 'main':
            continue
        entries = git(repo, 'ls-tree', '-r', sha).decode().splitlines()
        hashes = {}
        for entry in entries:
            metadata, name = entry.split('\t', 1)
            mode, kind, blob = metadata.split()
            if not name.endswith(('.py', '.js', '.mjs', '.html', '.json', '.css')):
                continue
            p = root / role / name
            if kind != 'blob' or mode == '120000' or p.is_symlink() or p.stat().st_mode & 0o222:
                raise ValueError('WRITABLE_OR_NONREGULAR_DEPENDENCY:' + name)
            data = p.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual != blob:
                raise ValueError('DEPENDENCY_BLOB_DIFFERS:' + role + '/' + name)
            hashes[name] = hashlib.sha256(data).hexdigest()
        evidence[role] = {'sha': sha, 'verified_files': len(hashes),
                          'source_manifest_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}
    return evidence


def activate(root):
    import robot_dashboard
    import tests
    root = Path(root).resolve()
    # Existing package is only the C7 entrypoint; peer packages are loaded from exact exports.
    for role in ('C1', 'D1', 'D2', 'D3', 'C4', 'C2', 'C3'):
        robot_dashboard.__path__.append(str(root / role / 'robot_dashboard'))
        tests.__path__.append(str(root / role / 'tests'))
    import experiments
    experiments.__path__ = list(experiments.__path__) + [str(root / r / 'experiments') for r in PINS if r != 'main']
    import experiments.expansion_20261029
    experiments.expansion_20261029.__path__ = [str(root / r / 'experiments/expansion_20261029') for r in PINS if r != 'main']


def load_file(name, path):
    if not re.fullmatch(r'[A-Za-z0-9_.]+', name):
        raise ValueError('invalid module name')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
