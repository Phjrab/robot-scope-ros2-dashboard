#!/usr/bin/env python3
"""Move closed owned legacy recordings into the shared quota archive; never delete."""
import argparse
import datetime
import json
from pathlib import Path

from bounded_record import ARCHIVE_CAP, tree_bytes
from labctl import ROOT, owned


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    archive = ROOT / 'recordings'
    if archive.is_symlink() or not archive.is_dir():
        raise RuntimeError('Create a real dedicated recording archive first')
    total, plan = tree_bytes(archive), []
    for state_path in sorted((ROOT / 'runs').glob('*/ownership.json')):
        legacy = state_path.parent / 'recordings'
        if not legacy.exists():
            continue
        if legacy.is_symlink() or legacy.resolve() != legacy:
            raise RuntimeError('Unexpected legacy path')
        state = json.loads(state_path.read_text())
        if owned(state)['State']['Running']:
            raise RuntimeError('Stop this owned container before consolidating its data')
        for source in sorted(legacy.iterdir()):
            if source.name == '.record.lock' and source.is_file() and not source.is_symlink():
                total += source.stat().st_size
                continue  # Retain the old empty lock as provenance; it is not a bag.
            if not source.is_dir() or source.is_symlink():
                raise RuntimeError('Unexpected entry in legacy archive')
            destination = archive / (state['run_id'] + '-' + source.name)
            if destination.exists():
                raise FileExistsError(destination)
            size = tree_bytes(source)
            total += size
            plan.append({'source': str(source), 'destination': str(destination), 'bytes': size})
    if total >= ARCHIVE_CAP:
        raise RuntimeError('Retained recordings exceed the cumulative 8 GiB budget')
    report = {'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'plan': plan, 'total_bytes': total, 'applied': False}
    if a.apply:
        # Same filesystem rename preserves the original payload and all failure logs.
        for row in plan:
            Path(row['source']).rename(row['destination'])
        report['applied'] = True
        name = 'recording-consolidation-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json'
        with (ROOT / 'evidence' / name).open('x') as output:
            json.dump(report, output, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
