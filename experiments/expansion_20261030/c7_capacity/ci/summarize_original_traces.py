"""Extract bounded evidence from original Actions ZIPs without executing their content."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def summarize(path):
    raw = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        traces = [name for name in outer.namelist() if name.endswith('/trace.zip')]
        if len(traces) != 1:
            raise ValueError('Expected exactly one failed-test trace in each original artifact')
        trace_name = traces[0]
        trace_bytes = outer.read(trace_name)
        attachments = {
            name: {'bytes': len(outer.read(name)), 'sha256': sha256(outer.read(name))}
            for name in outer.namelist()
            if name.startswith(trace_name.rsplit('/', 1)[0] + '/')
        }
    with zipfile.ZipFile(io.BytesIO(trace_bytes)) as trace:
        rows = [json.loads(line) for line in trace.read('test.trace').splitlines()]
        browser = [json.loads(line) for line in trace.read('0-trace.trace').splitlines()]
        network = [json.loads(line)['snapshot'] for line in trace.read('0-trace.network').splitlines()]
    context = rows[0]
    base = context['monotonicTime']
    after = {row['callId']: row for row in rows if row['type'] == 'after'}
    errors = [row for row in rows if row['type'] == 'after' and row.get('error')]
    closed = [row for row in errors if 'webSocketRoute.send: Target page' in row['error'].get('message', '')]
    stacks = Counter()
    for row in closed:
        match = re.search(r'(tests/e2e/[^\s)]+)', row['error'].get('stack', ''))
        stacks[match.group(1) if match else 'unknown'] += 1
    actions = []
    for row in rows:
        selector = row.get('params', {}).get('selector', '')
        if row['type'] != 'before' or not (
            'savedGlobalHistory' in selector or 'mount-calibration' in selector
            or 'Navigate to' in row.get('title', '')
            or row.get('title') == 'Expect "toBeVisible"'
        ):
            continue
        end = after.get(row['callId'], {}).get('endTime')
        actions.append({'title': row.get('title'), 'start_ms': round(row['startTime'] - base, 3),
                        'end_ms': None if end is None else round(end - base, 3)})
    requests = []
    for row in network:
        url = row['request']['url']
        if '/observations/global-jobs' in url or '/mount-calibration/estimate' in url:
            requests.append({'method': row['request']['method'], 'path': url.split(':4173')[-1],
                             'status': row['response']['status'],
                             'start_ms': round(row['_monotonicTime'] - base, 3), 'duration_ms': row['time']})
    return {
        'artifact': path.name, 'artifact_bytes': len(raw), 'artifact_sha256': sha256(raw),
        'trace_member': trace_name, 'attachments': attachments,
        'playwright': context['playwrightVersion'], 'test_timeout_ms': context['testTimeout'],
        'test_trace_events': len(rows), 'network_requests': len(network),
        'last_browser_api_event_ms': round(max(row.get(key, 0) for row in browser
                                               for key in ('time', 'startTime', 'endTime')) - base, 3),
        'closed_socket_send_errors': len(closed), 'closed_socket_error_stacks': dict(stacks),
        'actions_relative_to_test_trace_start': actions,
        'relevant_http_requests': requests,
        'pointer_interceptions': [{'time_ms': round(row['time'] - base, 3), 'message': row['message']}
                                 for row in browser if row['type'] == 'log'
                                 and 'intercepts pointer events' in row.get('message', '')],
        'interpretation_limit': 'Trace evidence does not measure host CPU or prove a single sufficient cause for timeout.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([summarize(path) for path in args.artifacts], indent=2, ensure_ascii=False))
