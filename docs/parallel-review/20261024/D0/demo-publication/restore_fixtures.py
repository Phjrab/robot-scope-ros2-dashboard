#!/usr/bin/env python3
"""Verify frozen artifacts and restore exact gzip fixtures, without altering tests."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f'Out-of-repository manifest path: {relative}')
    return path

def restore(check_only=False):
    manifest = json.loads((HERE / 'PUBLICATION_SUBSET.json').read_text())
    count = 0
    for entry in manifest['included']:
        packed = safe_path(entry['path']).read_bytes()
        if digest(packed) != entry['sha256'] or len(packed) != entry['bytes']:
            raise ValueError(f"Published artifact mismatch: {entry['path']}")
        if entry['encoding'] != 'gzip':
            continue
        data = gzip.decompress(packed)
        if digest(data) != entry['source_sha256'] or len(data) != entry['source_bytes']:
            raise ValueError(f"Restored source mismatch: {entry['path']}")
        target = safe_path(entry['restored_path'])
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f'Refusing to replace changed local fixture: {target.relative_to(ROOT)}')
        if not check_only:
            target.write_bytes(data)
        count += 1
    print(f'Verified {len(manifest["included"])} artifacts and {count} lossless fixtures; ' + ('not written' if check_only else 'restored exactly'))
    return count

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    restore(parser.parse_args().check_only)
