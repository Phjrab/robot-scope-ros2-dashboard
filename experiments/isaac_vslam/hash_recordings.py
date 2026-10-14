#!/usr/bin/env python3
"""Read closed SQLite bags from the lab archive and write a fresh SHA256 inventory."""
import argparse
import hashlib
import json
from pathlib import Path

from labctl import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    if a.output.parent.resolve() != ROOT / 'evidence':
        raise ValueError('Output must be in the dedicated evidence directory')
    rows = []
    archive = ROOT / 'recordings'
    for path in sorted(archive.rglob('*.db3')):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError('Unexpected symlink')
        digest = hashlib.sha256()
        before = path.stat()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('Bag changed during hashing; stop the owned recorder first')
        rows.append({'path': str(path.relative_to(ROOT)), 'bytes': after.st_size,
                     'sha256': digest.hexdigest()})
    with a.output.open('x') as output:
        json.dump(rows, output, indent=2)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
