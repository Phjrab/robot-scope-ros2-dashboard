#!/usr/bin/env python3
"""Check a saved field-trial snapshot offline. Never sends a request or goal."""
import argparse
import json
from pathlib import Path

from field_trial_evidence import check_navigation_trial, initial_pose_payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path, help='JSON with navigation, control and plan')
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.snapshot.read_text(encoding='utf-8'))
        result = check_navigation_trial(data['navigation'], data['control'], data['plan'])
        plan = data['plan']
        result['standard_initial_pose_payload'] = initial_pose_payload(
            plan['map_id'], plan['map_revision'], plan['start'])
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({'snapshot_checks_passed': False, 'motion_authorized': False,
                          'error_type': type(exc).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
