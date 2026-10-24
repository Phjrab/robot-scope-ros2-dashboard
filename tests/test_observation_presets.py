"""Persistent anchor values and API isolation; no ROS or hardware involved."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from fastapi import FastAPI

from robot_dashboard.api.routers.observation_presets import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.navigation_presets import PresetConflict, PresetInvalid, PresetUnavailable
from robot_dashboard.observation_presets import ObservationPresetStore
from test_navigation_presets import LocalASGIClient


class ObservationPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'anchors'
        self.map_id = 'a' * 24
        self.meta = dict(kind='pointcloud3d', revision='b' * 64, frame_id='camera_init')
        self.catalog = SimpleNamespace(metadata=lambda _: dict(self.meta))
        self.store = ObservationPresetStore(self.directory, self.catalog)
        self.body = dict(name='출입구 · 서 있음', map_revision=self.meta['revision'], map_frame='camera_init',
                         pose_reference='FASTLIO_IMU', pose=dict(x=.376, y=.439, z=.044, roll=.6, pitch=-.5, yaw=12.4))

    def create(self, **changes):
        return self.store.create(self.map_id, **{**self.body, **changes})

    def client(self):
        app = FastAPI()
        app.state.runtime = ApplicationRuntime(observation_presets=self.store)
        app.include_router(router)
        return LocalASGIClient(app)

    def test_values_survive_server_recreation_without_an_odometry_transform(self):
        saved = self.create()['preset']
        result = ObservationPresetStore(self.directory, self.catalog).snapshot(self.map_id)
        self.assertEqual(result['presets'], [saved])
        self.assertEqual(saved['values']['pose'], self.body['pose'])
        self.assertIn('+00:00', saved['values']['saved_at'])
        self.assertNotIn('T_map_odom', saved['values'])
        self.assertTrue(result['requires_reanchor'])

    def test_changed_revision_and_frame_cannot_be_loaded_or_saved_as_current(self):
        self.create()
        for change in ({'revision': 'c' * 64}, {'frame_id': 'other_map'}):
            original = dict(self.meta)
            self.meta.update(change)
            snapshot = self.store.snapshot(self.map_id)
            self.assertEqual(snapshot['presets'], [])
            self.assertEqual(snapshot['incompatible_count'], 1)
            with self.assertRaises(PresetConflict):
                self.create(name='new')
            self.meta = original

    def test_names_are_scoped_to_map_and_duplicates_preserve_existing_values(self):
        self.create()
        saved = (self.directory / self.map_id / 'presets.json').read_bytes()
        with self.assertRaises(PresetConflict):
            self.create(pose={**self.body['pose'], 'x': 5})
        self.assertEqual((self.directory / self.map_id / 'presets.json').read_bytes(), saved)
        self.store.create('c' * 24, **self.body)
        self.assertEqual(len(self.store.snapshot('c' * 24)['presets']), 1)

    def test_invalid_pose_reference_nan_boolean_and_unknown_fields_do_not_write(self):
        for pose in ({**self.body['pose'], 'x': float('nan')}, {**self.body['pose'], 'x': True},
                     {**self.body['pose'], 'yaw': 361}, {**self.body['pose'], 'T_map_odom': []}):
            with self.subTest(pose=pose), self.assertRaises(PresetInvalid):
                self.create(pose=pose)
        with self.assertRaises(PresetInvalid):
            self.create(pose_reference='VERIFIED_BODY')
        self.assertFalse(self.directory.exists())

    def test_corrupt_catalog_is_preserved(self):
        self.create()
        path = self.directory / self.map_id / 'presets.json'
        path.write_text('invalid')
        with self.assertRaises(PresetUnavailable):
            self.create(name='other')
        self.assertEqual(path.read_text(), 'invalid')

    def test_api_save_read_and_origin_guard_without_other_runtime_components(self):
        client = self.client(); path = '/api/v1/observations/anchor-presets/' + self.map_id
        self.assertEqual(client.post(path, json=self.body, headers={'Origin': 'http://other'}).status_code, 403)
        saved = client.post(path, json=self.body)
        self.assertEqual(saved.status_code, 201, saved.text)
        loaded = client.get(path)
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json()['presets'][0], saved.json()['preset'])
        self.assertTrue(saved.json()['approximate_only'])

    def test_api_rejects_extra_fields_and_non_numeric_values(self):
        client = self.client(); path = '/api/v1/observations/anchor-presets/' + self.map_id
        for body in ({**self.body, 'apply': True}, {**self.body, 'pose': {**self.body['pose'], 'x': True}},
                     {**self.body, 'pose': {**self.body['pose'], 'x': '1'}}):
            self.assertEqual(client.post(path, json=body).status_code, 422)
        self.assertFalse(self.directory.exists())
