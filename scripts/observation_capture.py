#!/usr/bin/env python3
"""Explicit one-request input capture, or completely offline historical replay."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from robot_dashboard.relocalization.observation_capture import (  # noqa: E402
    MAX_CAPTURE_BYTES, decode_capture, replay_capture,
)


def read_json(path, limit=MAX_CAPTURE_BYTES):
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('INPUT_SIZE_LIMIT')
    return json.loads(data)


def output_path(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    if path.resolve().is_relative_to(REPO):
        raise ValueError('OUTPUT_MUST_BE_OUTSIDE_REPOSITORY')
    if not path.parent.is_dir():
        raise ValueError('OUTPUT_PARENT_MISSING')
    return path


def save(path, payload):
    path = output_path(path)
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    if len(data) > MAX_CAPTURE_BYTES:
        raise ValueError('OUTPUT_SIZE_LIMIT')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('CAPTURE_REDIRECT_REFUSED')


def capture(base_url, request_file):
    from robot_dashboard.api.routers.observation_alignment import ObservationRequest

    url = urllib.parse.urlsplit(base_url)
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
            or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('EXPECTED_DASHBOARD_ORIGIN')
    origin = f'{url.scheme}://{url.netloc}'
    body = ObservationRequest.model_validate(read_json(request_file, 16384)).model_dump()
    body['capture_inputs'] = True
    request = urllib.request.Request(origin + '/api/v1/observations/map-alignment',
        data=json.dumps(body).encode(), headers={'Origin': origin, 'Content-Type': 'application/json'}, method='POST')
    # One attempt only. A 409 or timeout requires an operator-reviewed fresh request.
    with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
        data = response.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise ValueError('CAPTURE_SIZE_LIMIT')
    payload = json.loads(data)
    decode_capture(payload)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    record = commands.add_parser('capture', help='One explicit numerical request; no sensor startup or pose application')
    record.add_argument('--base-url', required=True)
    record.add_argument('--request', required=True, help='Existing map/source/seed request JSON; never silently refreshed')
    record.add_argument('--output', required=True, help='New private JSON file outside the repository')
    replay = commands.add_parser('replay', help='Offline only; never contacts the dashboard')
    replay.add_argument('input')
    replay.add_argument('--output', required=True)
    replay.add_argument('--budget-seconds', type=float, default=10)
    args = parser.parse_args(argv)
    destination = output_path(args.output)  # Refuse invalid destination before any network request.
    if args.command == 'capture':
        payload = capture(args.base_url, args.request)
    else:
        payload = replay_capture(read_json(args.input), budget_s=args.budget_seconds)
    save(destination, payload)
    print(json.dumps({'output': str(destination), 'data_kind': payload.get('data_kind', 'HISTORICAL_CAPTURE'),
                      'operational_application': 'NOT_RUN'}))


if __name__ == '__main__':
    main()
