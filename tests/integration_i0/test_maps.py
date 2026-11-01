import copy
import tempfile
import time
import unittest

from fastapi import FastAPI
from tests.expansion_services.http_client import TestClient

from robot_dashboard.expansion_contracts import FusionRequest
from robot_dashboard.expansion_integration.flags import ExpansionFlags
from robot_dashboard.expansion_integration.host import install_expansion
from .fixture import compose


class MapIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="i0-maps-")
        self.composition = compose(self.temp.name)
        self.client = TestClient(self.composition.app, base_url="http://testserver")
        self.client.__enter__()
        self.headers = {"x-i0-synthetic-fixture": "local-test-only", "Origin": "http://testserver"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def request_body(self, sources):
        return FusionRequest(schema_version="0.1", evidence_kind="SYNTHETIC", producer="i0-test",
            sequence=1, source_epoch="i0-generated", request_id="i0-request",
            anchor_source_key=sources[0].key, sources=[s.to_dict() for s in sources],
            source_pins={s.key:s.sha256 for s in sources}, initial_guesses=[],
            correspondences=[], mode="auto", options={}).to_dict()

    def test_defaults_and_auth_origin_no_private_read(self):
        app=FastAPI()
        before=list(app.routes)
        self.assertIsNone(install_expansion(app))
        self.assertEqual(before, app.routes)
        install_expansion(app, ExpansionFlags(multimap=True))
        with TestClient(app, base_url="http://testserver") as client:
            self.assertEqual(client.get('/api/v1/extensions/multimap/sources').status_code,401)
            self.assertIn('BLOCKED_AUTH',client.get('/extensions').text)
        for path in ['/multimap/sources','/scene/assets/'+'1'*24+'/'+'1'*64]:
            self.assertIn(self.client.get('/api/v1/extensions'+path).status_code,(401,404))
        response=self.client.post('/api/v1/extensions/multimap/jobs',json={},headers={**self.headers,'Origin':'http://foreign.invalid'})
        self.assertEqual(response.status_code,403)
        self.assertFalse(self.composition.owner.store.root.exists())

    def test_saved_catalogue_real_solver_full_copy_and_ancestry(self):
        owner=self.composition.owner
        sources=[owner.catalogue.resolve(i).descriptor for i in owner.catalogue.list_ids()][:2]
        before={s.map_id:s.sha256 for s in sources}
        self.assertEqual(len(owner.catalogue.preview(sources[0].map_id)['points']),480)
        body=self.request_body(sources)
        response=self.client.post('/api/v1/extensions/multimap/jobs',json=body,headers=self.headers)
        self.assertEqual(response.status_code,202,response.text)
        job=response.json()['job_id']
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            state=self.client.get(f'/api/v1/extensions/multimap/jobs/{job}',headers=self.headers).json()
            if state['state'] not in ('QUEUED','RUNNING'):break
            time.sleep(.02)
        self.assertEqual(state['state'],'SOLVED_CANDIDATE',state)
        review=self.client.post(f'/api/v1/extensions/multimap/jobs/{job}/review',headers=self.headers,
            json=dict(expected_proposal_revision=state['proposal_revision'],accepted=True,manual_selection=None))
        self.assertEqual(review.status_code,200,review.text)
        revision=review.json()['proposal_revision']
        export=self.client.post(f'/api/v1/extensions/multimap/jobs/{job}/exports',headers=self.headers,
            json=dict(name='i0_copy',expected_proposal_revision=revision))
        self.assertEqual(export.status_code,201,export.text)
        result=export.json()
        self.assertEqual(result['point_count'],800)
        self.assertFalse(result['operational_installed'])
        self.assertEqual(result['legacy_family']['status'],'DEFERRED')
        self.assertEqual(self.composition.saved.list_snapshot()['count'],3)
        self.assertEqual({s.map_id:owner.catalogue.resolve(s.map_id).descriptor.sha256 for s in sources},before)
        merged=owner.catalogue.resolve(result['id']).descriptor
        self.assertIsNone(merged.mapping_session_id)
        body=self.request_body([merged,sources[0]])
        response=self.client.post('/api/v1/extensions/multimap/jobs',json=body,headers=self.headers)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['error']['code'],'ANCESTRY_OVERLAP')
        stale=copy.deepcopy(sources[0].to_dict());stale['revision']='f'*64
        from robot_dashboard.expansion_contracts import MapSourceDescriptor
        body=self.request_body([MapSourceDescriptor.from_dict(stale),sources[1]])
        response=self.client.post('/api/v1/extensions/multimap/jobs',json=body,headers=self.headers)
        self.assertEqual(response.status_code,409,response.text)


if __name__ == '__main__':
    unittest.main()
