"""Provisioned copied-map inputs fail closed and retain existing auth boundaries."""
import json
import http.client
from pathlib import Path
import tempfile
import unittest
from fastapi import FastAPI
from tests.expansion_services.http_client import TestClient
from tests.integration_i0.fixture import saved_sources
from robot_dashboard.expansion_integration.review_workspace import configured_review_inputs
from robot_dashboard.expansion_integration.bootstrap import configure_expansion
from robot_dashboard.expansion_integration.review_access import ReviewAccess

class ReviewWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve();self.root.chmod(0o700)
        saved,metadata=saved_sources(self.root);(self.root/'sources').chmod(0o700)
        self.manifest=self.root/'workspace.json';self.data={'schema':'robot-scope.review-workspace.v1','catalogue_root':str(self.root/'sources'),'bundle_root':str(self.root/'bundles'),'metadata':metadata};self.write()
        self.env={'ROBOT_SCOPE_EXPANSION_MULTIMAP':'1','ROBOT_SCOPE_EXPANSION_REVIEW_WORKSPACE':str(self.manifest)}
    def write(self):self.manifest.write_text(json.dumps(self.data));self.manifest.chmod(0o600)
    def test_disabled_does_not_read_manifest(self):
        self.assertIsNone(configured_review_inputs({'ROBOT_SCOPE_EXPANSION_REVIEW_WORKSPACE':'/missing'}))
    def test_real_copy_catalogue_and_drift_fencing(self):
        catalogue,manager,store=configured_review_inputs(self.env).maps_factory();self.addCleanup(manager.close)
        rows=catalogue.list();self.assertEqual(len(rows),3);self.assertTrue(all(x['evidence_kind']=='SYNTHETIC' for x in rows));self.assertEqual(store.root,self.root/'bundles')
        source=catalogue.resolve(rows[0]['map_id']).asset.path;source.write_bytes(source.read_bytes()+b'x')
        with self.assertRaises(Exception):catalogue.resolve(rows[0]['map_id'])
    def test_missing_identity_unsafe_root_and_manifest_permissions(self):
        row=next(iter(self.data['metadata'].values()));del row['source_epoch'];self.write()
        with self.assertRaises(ValueError):configured_review_inputs(self.env).maps_factory()
        row['source_epoch']='UNAVAILABLE';self.write()
        with self.assertRaises(ValueError):configured_review_inputs(self.env).maps_factory()
        row['source_epoch']='i0-generated';self.data['catalogue_root']=str(self.root.parent);self.write()
        with self.assertRaises(ValueError):configured_review_inputs(self.env).maps_factory()
        self.data['catalogue_root']=str(self.root/'sources');self.write();self.manifest.chmod(0o644)
        with self.assertRaises(ValueError):configured_review_inputs(self.env).maps_factory()
    def test_copy_retains_original_identity_without_replacing_copy_identity(self):
        row=next(iter(self.data['metadata'].values()))
        original={'map_id':'a'*24,'revision':'b'*64,'sha256':row['sha256']}
        row.update(original_source=original,qualification={'same_place_operator_confirmation':True,'original_sensor_epoch':None})
        self.write()
        catalogue,manager,_=configured_review_inputs(self.env).maps_factory();self.addCleanup(manager.close)
        descriptor=catalogue.resolve(row['map_id']).descriptor
        self.assertEqual(descriptor.map_id,row['map_id'])
        self.assertEqual(descriptor.revision,row['revision'])
        self.assertEqual(descriptor.acquisition['original_source'],original)
        self.assertTrue(descriptor.acquisition['qualification']['same_place_operator_confirmation'])
        row['original_source']['sha256']='c'*64;self.write()
        with self.assertRaises(Exception):configured_review_inputs(self.env).maps_factory()
    def test_http_landing_redirects_only_when_session_owner_is_configured(self):
        db=self.root/'access.sqlite3';ReviewAccess(db).initialize()
        env={**self.env,'ROBOT_SCOPE_EXPANSION_REVIEW_DB':str(db),'ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN':'https://127.0.0.1:18443'}
        app=FastAPI();configure_expansion(app,env,review_inputs=configured_review_inputs(env))
        with TestClient(app,base_url='http://testserver') as client:
            connection=http.client.HTTPConnection('127.0.0.1',client.listener.getsockname()[1])
            self.addCleanup(connection.close)
            connection.request('GET','/extensions',headers={'Host':'testserver'})
            response=connection.getresponse();self.assertEqual(response.status,307);self.assertEqual(response.getheader('Location'),'https://127.0.0.1:18443/extensions');response.read()
            self.assertEqual(client.get('/api/v1/extensions/multimap/sources').status_code,403)
