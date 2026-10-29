"""Opt-in reuse of C3's unmodified local browser load check; finite fixture host."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from .dependencies import PINS, verify


def run_browser(repo, deps, playwright, node, output):
    verify(repo, deps)
    deps = Path(deps).resolve()
    with tempfile.TemporaryDirectory(prefix='c7-c3-browser-') as tmp:
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        host = ThreadingHTTPServer(('127.0.0.1',0), partial(QuietHandler,directory=str(deps/'C3')))
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        env = dict(os.environ, C3_PLAYWRIGHT=str(Path(playwright).resolve()), C3_EVIDENCE=tmp,
            C3_FIXTURE_URL=f'http://127.0.0.1:{host.server_port}/experiments/expansion_20261029/c3_scene_ui/fixture.html')
        try:
            run = subprocess.run([node,str(deps/'C3/tests/expansion_c3/browser.mjs')],env=env,
                                 capture_output=True,text=True,timeout=150)
            path = Path(tmp)/'browser-results.json'
            report = json.loads(path.read_text()) if path.exists() else {'failure':run.stderr}
        finally:
            host.shutdown()
            host.server_close()
            thread.join(timeout=2)
        report['request_count'] = len(report.pop('requests',[]))
        report.update(c3_sha=PINS['C3'], source='tests/expansion_c3/browser.mjs unchanged',
                      exit_code=run.returncode, local_only=True,
                      evidence_kind='ACTUAL_BROWSER_UI_FIXTURE_NOT_NUMERICAL_COMPOSITION',
                      stderr=run.stderr[-2000:])
        Path(output).parent.mkdir(parents=True,exist_ok=True)
        Path(output).write_text(json.dumps(report,indent=2)+'\n')
    verify(repo,deps)
    return run.returncode
