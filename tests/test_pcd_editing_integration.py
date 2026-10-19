"""Optional common wiring contract; synthetic local fixtures only."""
import asyncio
import hashlib
import json
import struct
import tempfile
import threading
import zipfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException

from robot_dashboard.api.routers.pcd_editing import create_router as create_pcd_editing_router
from robot_dashboard.pcd_editing.store import MAX_DOCUMENT_BYTES, PcdEditConflict, PcdEditError
from robot_dashboard.saved_maps import (
    SavedMapCatalog, SavedMapConflict, SavedMapNotFound,
)
from robot_dashboard.competition import CompetitionConflict


def write_pcd(path):
    points = [(0., 0., 0., 11.), (1., 1., 0., 12.), (8., 8., 0., 13.)]
    header = ("VERSION .7\nFIELDS x y z intensity\nSIZE 4 4 4 4\nTYPE F F F F\n"
              "COUNT 1 1 1 1\nWIDTH 3\nHEIGHT 1\nPOINTS 3\nDATA binary\n").encode()
    path.write_bytes(header + b''.join(struct.pack('<ffff', *row) for row in points))


def payload(source):
    identity = {key: source[key] for key in ('map_id', 'revision', 'frame_id')}
    return {
        'schema': 'robot-scope.pcd-edit-request.v1', 'name': 'synthetic-edited',
        'purpose': 'visibility', 'source': source,
        'annotation': {
            'schema': 'robot-dashboard.map-editor3d', 'schema_version': 1,
            'version_id': 'synthetic-annotation', 'source': identity,
            'runtime_installed': False,
            'regions': [{'kind': 'visibility', 'selection': 'inside',
                         'polygon': [[-.5, -.5], [1.5, -.5], [1.5, 1.5], [-.5, 1.5]],
                         'z_min': -1., 'z_max': 1.}],
        },
    }


class CatalogueIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'synthetic.pcd'
        write_pcd(self.source)
        self.catalogue = SavedMapCatalog([self.root], managed_roots=[self.root])
        self.original = self.catalogue.list_snapshot()['maps'][0]

    def test_full_source_roundtrip_preserves_hash_and_semantic_identity(self):
        before = self.source.read_bytes()
        self.assertFalse((self.root / 'pcd-edits').exists())
        descriptor = self.catalogue.pcd_edit_source(self.original['id'])
        self.assertFalse((self.root / 'pcd-edits').exists(), 'descriptor GET must be read-only')
        self.assertEqual(set(descriptor), {'map_id', 'revision', 'frame_id', 'units', 'sha256', 'asset_role'})
        self.assertEqual(descriptor['sha256'], hashlib.sha256(before).hexdigest())
        result = self.catalogue.save_pcd_edited_copy(self.original['id'], payload(descriptor))
        self.assertEqual(self.source.read_bytes(), before)
        self.assertNotEqual(result['id'], self.original['id'])
        self.assertEqual(result['point_count'], 1)
        self.assertFalse(result['runtime_installed'])
        fresh = SavedMapCatalog([self.root], managed_roots=[self.root])
        registered = fresh.metadata(result['id'])
        for key in ('id', 'name', 'revision', 'frame_id', 'units', 'sha256', 'origin', 'edit_history'):
            self.assertEqual(registered[key], result[key])
        self.assertFalse(registered['manageable'])
        bundle, bundle_meta = fresh.download_bundle(result['id'])
        with bundle, zipfile.ZipFile(bundle) as archive:
            downloaded = json.loads(archive.read('manifest.json'))
            self.assertEqual(downloaded['map']['revision'], result['revision'])
            self.assertEqual(hashlib.sha256(archive.read('map.pcd')).hexdigest(), result['sha256'])
            self.assertEqual(bundle_meta['revision'], result['revision'])
        self.assertEqual(fresh.pcd_edit_source(result['id'])['revision'], result['revision'])
        child = fresh.save_pcd_edited_copy(result['id'], payload(fresh.pcd_edit_source(result['id'])))
        self.assertEqual(child['origin'], result['origin'])
        self.assertEqual(len(child['edit_history']), 2)

    def test_tampered_or_incomplete_publication_is_not_listed_under_a_fallback_id(self):
        descriptor = self.catalogue.pcd_edit_source(self.original['id'])
        result = self.catalogue.save_pcd_edited_copy(self.original['id'], payload(descriptor))
        folder = self.root / 'pcd-edits' / result['id']
        (folder / 'map.pcd').write_bytes((folder / 'map.pcd').read_bytes() + b'tampered')
        self.assertEqual(self.catalogue.list_snapshot()['count'], 1)
        (folder / 'manifest.json').unlink()
        self.assertEqual(self.catalogue.list_snapshot()['count'], 1)

    def test_source_id_and_revision_conflicts_fail_without_changing_catalogue(self):
        descriptor = self.catalogue.pcd_edit_source(self.original['id'])
        request = payload(descriptor)
        with self.assertRaises(SavedMapConflict):
            self.catalogue.save_pcd_edited_copy('f' * 24, request)
        request['source']['revision'] = 'f' * 64
        with self.assertRaises(PcdEditConflict):
            self.catalogue.save_pcd_edited_copy(self.original['id'], request)
        self.assertEqual(self.catalogue.list_snapshot()['count'], 1)
        self.assertFalse((self.root / 'pcd-edits').exists())

    def test_preview_retains_manifest_frame_instead_of_legacy_default(self):
        descriptor = self.catalogue.pcd_edit_source(self.original['id'])
        # A trusted resolver can supply an explicit frame for registered output.
        original_resolver = self.catalogue._pcd_edit_source_asset
        from dataclasses import replace
        with patch.object(self.catalogue, '_pcd_edit_source_asset',
                          side_effect=lambda map_id: replace(original_resolver(map_id), frame_id='survey_origin')):
            descriptor = self.catalogue.pcd_edit_source(self.original['id'])
            result = self.catalogue.save_pcd_edited_copy(self.original['id'], payload(descriptor))
        preview = self.catalogue.data(result['id'])
        self.assertEqual(preview['frame_id'], 'survey_origin')


class HttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Bind the real router to a minimal app. No dashboard lifespan, robot
        # agent, ROS connection, or configured host is started.
        self.app = FastAPI()
        self.main_thread = threading.get_ident()
        self.thread_ids = []
        self.calls = []
        self.failure = None
        self.locked = False
        def describe(map_id):
            self.thread_ids.append(threading.get_ident())
            if self.failure:
                raise self.failure
            return {'map_id': map_id, 'asset_role': 'full_source'}
        def save(map_id, body):
            self.thread_ids.append(threading.get_ident())
            self.calls.append((map_id, body))
            if self.failure:
                raise self.failure
            return {'id': 'a' * 24, 'runtime_installed': False}
        def unlocked(action):
            if self.locked:
                raise CompetitionConflict('locked')
        runtime = SimpleNamespace(competition=SimpleNamespace(require_unlocked=unlocked))
        def map_error(exc):
            return HTTPException(404 if isinstance(exc, SavedMapNotFound) else 409, 'map error')
        self.app.include_router(create_pcd_editing_router(
            lambda: SimpleNamespace(pcd_edit_source=describe, save_pcd_edited_copy=save),
            map_error, runtime,
        ))
        # No socket/server or cross-thread anyio portal is needed for ASGI.
        self.client = self

    def request(self, method, url, **kwargs):
        async def send():
            supplied = kwargs.get('headers', {})
            headers = {key.lower(): value for key, value in supplied.items()}
            headers.setdefault('host', 'testserver')
            if 'json' in kwargs:
                body = json.dumps(kwargs['json']).encode()
                headers.setdefault('content-type', 'application/json')
            else:
                body = kwargs.get('content', b'')
                if isinstance(body, str):
                    body = body.encode()
            if isinstance(body, bytes):
                headers.setdefault('content-length', str(len(body)))
                sent = False

                async def receive():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {'type': 'http.request', 'body': body, 'more_body': False}
                    return {'type': 'http.disconnect'}
            else:
                chunks = body.__aiter__()

                async def receive():
                    try:
                        return {'type': 'http.request', 'body': await anext(chunks), 'more_body': True}
                    except StopAsyncIteration:
                        return {'type': 'http.request', 'body': b'', 'more_body': False}

            status_code = None
            response_body = bytearray()

            async def respond(message):
                nonlocal status_code
                if message['type'] == 'http.response.start':
                    status_code = message['status']
                elif message['type'] == 'http.response.body':
                    response_body.extend(message.get('body', b''))

            scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                     'scheme': 'http', 'method': method, 'path': url, 'raw_path': url.encode(),
                     'query_string': b'', 'root_path': '', 'server': ('testserver', 80),
                     'client': ('testclient', 1),
                     'headers': [(key.encode(), value.encode()) for key, value in headers.items()]}
            await self.app(scope, receive, respond)
            return SimpleNamespace(status_code=status_code,
                                   json=lambda: json.loads(response_body))
        loop = asyncio.new_event_loop()
        # Some restricted Linux sandboxes suppress the self-pipe wakeup used by
        # call_soon_threadsafe. A pending timer also bounds the selector wait.
        def tick():
            loop.call_later(.01, tick)
        loop.call_soon(tick)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def test_routes_offload_catalogue_io_and_return_creation_status(self):
        self.assertEqual(self.client.get('/api/v1/saved-maps/test/pcd-edit-source').status_code, 200)
        response = self.client.post('/api/v1/saved-maps/test/pcd-edited-copy', json={}, headers={'Origin': 'http://testserver'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['map']['runtime_installed'], False)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(value != self.main_thread for value in self.thread_ids))

    def test_post_requires_same_origin_and_unlocked_state_before_io(self):
        for headers in ({}, {'Origin': 'https://other.invalid'}):
            self.assertEqual(self.client.post('/api/v1/saved-maps/test/pcd-edited-copy', json={}, headers=headers).status_code, 403)
        self.locked = True
        response = self.client.post('/api/v1/saved-maps/test/pcd-edited-copy', json={}, headers={'Origin': 'http://testserver'})
        self.assertEqual(response.status_code, 423)
        self.assertFalse(self.calls)

    def test_post_guards_before_body_read_and_enforces_raw_2mib_limit(self):
        consumed = []

        async def too_large_stream():
            consumed.append(True)
            yield b'{' + b' ' * MAX_DOCUMENT_BYTES

        url = '/api/v1/saved-maps/test/pcd-edited-copy'
        response = self.client.post(url, content=too_large_stream(), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(consumed)
        self.locked = True
        response = self.client.post(url, content=too_large_stream(), headers={
            'Origin': 'http://testserver', 'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 423)
        self.assertFalse(consumed)
        self.locked = False
        response = self.client.post(url, content=too_large_stream(), headers={
            'Origin': 'http://testserver', 'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        self.assertTrue(consumed)
        response = self.client.post(url, content='{}', headers={
            'Origin': 'http://testserver', 'Content-Type': 'application/json',
            'Content-Length': '9' * 5000})
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self.calls)

    def test_post_rejects_ambiguous_json_and_wrong_content_type(self):
        url = '/api/v1/saved-maps/test/pcd-edited-copy'
        origin = {'Origin': 'http://testserver'}
        self.assertEqual(self.client.post(url, content='{}', headers=origin).status_code, 415)
        response = self.client.post(url, content='{"source":{},"source":{}}', headers={
            **origin, 'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.calls)

    def test_conflict_bad_payload_and_notfound_status_mapping(self):
        for failure, expected in [(PcdEditConflict('stale'), 409), (PcdEditError('invalid'), 422), (SavedMapNotFound('missing'), 404)]:
            self.failure = failure
            with self.subTest(expected=expected):
                self.assertEqual(self.client.get('/api/v1/saved-maps/test/pcd-edit-source').status_code, expected)
                self.assertEqual(self.client.post('/api/v1/saved-maps/test/pcd-edited-copy', json={}, headers={'Origin': 'http://testserver'}).status_code, expected)


if __name__ == '__main__':
    unittest.main()
