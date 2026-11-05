"""Loopback-only browser fixture using the actual HTTPS review session owner."""
import argparse
from pathlib import Path
import subprocess
import tempfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import uvicorn

from robot_dashboard.expansion_integration.bootstrap import configure_expansion
from robot_dashboard.expansion_integration.catalogue import compose_maps
from robot_dashboard.expansion_integration.host import STATIC
from robot_dashboard.expansion_integration.review_access import ReviewAccess
from robot_dashboard.expansion_integration.review_owner import ReviewInputs
from tests.integration_i0.fixture import saved_sources


def compose(root, port, off=False):
    app = FastAPI()
    app.mount('/static', StaticFiles(directory=STATIC), name='static')
    env, inputs = {}, None
    if not off:
        access = ReviewAccess(root / 'review.sqlite3')
        access.initialize()
        saved, metadata = saved_sources(root)
        env = {f'ROBOT_SCOPE_EXPANSION_{name}': '1'
               for name in ('MULTIMAP', 'SCENE', 'REPLAY', 'USABILITY')}
        env.update(ROBOT_SCOPE_EXPANSION_REVIEW_DB=str(access.database),
                   ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN=f'https://127.0.0.1:{port}')
        inputs = ReviewInputs(maps_factory=lambda: compose_maps(saved, metadata.get, root / 'bundles'))

        @app.post('/__i0_test__/grant')
        async def grant(request: Request):
            if request.headers.get('x-i0-synthetic-fixture') != 'local-test-only':
                raise HTTPException(403)
            value = await request.json()
            grant_id, code = access.issue(value['role'], value.get('ttl', 180))
            return {'grant_id': grant_id, 'code': code}

    index = configure_expansion(app, env, review_inputs=inputs)

    @app.get('/')
    async def dashboard():
        return index(headers={'Cache-Control': 'no-store'})

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--off', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='i0-review-browser-') as directory:
        root = Path(directory).resolve()
        tls = {}
        if not args.off:
            cert, key = root / 'cert.pem', root / 'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1',
                            '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
            tls = {'ssl_certfile': str(cert), 'ssl_keyfile': str(key)}
        uvicorn.run(compose(root, args.port, args.off), host='127.0.0.1', port=args.port,
                    proxy_headers=False, log_level='warning', **tls)
