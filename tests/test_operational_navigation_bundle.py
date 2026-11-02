"""Robot-free map-bundle integration against the real saved-map catalogue.

PCD, occupancy, and calibration records here are synthetic software fixtures.
The tests do not qualify a robot's map alignment or body calibration.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.application.operational_navigation import OperationalNavigation
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.operational import load_bundle
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapError
from test_operational_3d_localization import fixture_bundle, write_pcd


class Jobs:
    controller_odom_topic = '/robot_scope/nav/controller_odom'
    navigation_profile = 'go2-xt16-wireless-competition-fastlio'

    def __init__(self):
        self.state = 'idle'

    def snapshot(self):
        return {'pipeline': {'state': self.state}}


class OperationalNavigationBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.maps = self.root / 'maps'
        self.maps.mkdir()
        self.runtime_root = self.root / 'runtime'
        self.runtime_root.mkdir()
        self.pcd = self.maps / 'fixture.pcd'
        self.points = np.random.default_rng(514).uniform([-3, -2, -.5], [4, 3, 2.], (384, 3))
        self.points[:12] = [.2, .2, .2]
        self.sha = write_pcd(self.pcd, self.points)
        self.image = self.maps / 'floor.pgm'
        self.image.write_bytes(b'P5\n2 2\n255\n' + bytes([255, 0, 128, 255]))
        self.yaml = self.maps / 'floor.yaml'
        self.yaml.write_text('image: floor.pgm\nresolution: 0.05\norigin: [0.7, -0.3, 0.2]\n'
                             'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
        self.catalog = SavedMapCatalog([self.maps], managed_roots=[self.maps], preview_points=100)
        maps = self.catalog.list_snapshot()['maps']
        self.localization = next(item for item in maps if item['kind'] == 'pointcloud3d')
        self.navigation = next(item for item in maps if item['kind'] == 'occupancy2d')
        self.source = self.catalog.pcd_edit_source(self.localization['id'])
        self.jobs = Jobs()
        self.manager = OperationalNavigation(self.catalog, self.runtime_root, self.jobs)
        self.calibration = self.make_calibration()
        self.write_calibration()
        self.selection = self.make_selection()

    def make_calibration(self):
        value = fixture_bundle(self.sha)['calibration']
        value.update(localization_frame=self.source['frame_id'],
            localization_root={key: self.source[key] for key in ('map_id', 'revision', 'sha256', 'frame_id', 'units')},
            navigation_map_id=self.navigation['id'], navigation_map_revision=self.navigation['revision'],
            controller_odom_topic=self.jobs.controller_odom_topic, navigation_profile=self.jobs.navigation_profile,
            tf_publishers={'/tf': [], '/tf_static': []}, policy=fixture_bundle(self.sha)['policy'])
        return value

    def write_calibration(self):
        (self.runtime_root / 'operational-calibration.json').write_text(json.dumps(self.calibration))

    def make_selection(self):
        return {'map_id': self.source['map_id'], 'map_revision': self.source['revision'],
            'navigation_map_id': self.navigation['id'], 'navigation_map_revision': self.navigation['revision'],
            'seed_pose': {'x': .3, 'y': -.4, 'z': .7, 'roll': .05, 'pitch': -.08, 'yaw': .2}}

    def job_directory(self, name='job'):
        directory = self.root / name
        directory.mkdir()
        return directory

    def test_real_catalogue_selection_snapshots_full_source_and_sidecar_loads_same_hash(self):
        before_pcd, before_image = self.pcd.read_bytes(), self.image.read_bytes()
        state = self.manager.select(self.selection)
        directory = self.job_directory()
        self.catalog.snapshot_navigation_map(self.navigation['id'], self.navigation['revision'], directory)
        self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory)
        snapshot_pcd = directory / 'localization-reference.pcd'
        self.assertEqual(snapshot_pcd.read_bytes(), before_pcd)
        self.assertEqual(hashlib.sha256(snapshot_pcd.read_bytes()).hexdigest(), state['selected']['localization_3d']['sha256'])
        self.assertEqual(self.pcd.read_bytes(), before_pcd)
        self.assertEqual(self.image.read_bytes(), before_image)
        engine = load_bundle(directory / 'nav2_params.yaml')
        self.addCleanup(engine.close)
        self.assertEqual(engine.full_count, 384)
        self.assertEqual(engine.bundle['generation'], state['selected']['generation'])
        self.assertIsNone(engine.seed, 'loading a staged map must not auto-arm a seed')
        self.assertIsNone(engine.correction)
        np.testing.assert_allclose(engine.reference, self.points, atol=2e-7)

    def test_alignment_and_body_transform_produce_correct_planar_initial_confirmation(self):
        nav_from_map = from_translation_rpy([2., -.5, .3], [.03, -.04, .5])
        imu_from_base = from_translation_rpy([.25, -.1, -.2], [.02, .01, -.15])
        self.calibration['T_nav_map_from_localization_map'] = nav_from_map.tolist()
        self.calibration['T_imu_base'] = imu_from_base.tolist()
        self.write_calibration()
        state = self.manager.select(self.selection)
        seed = from_translation_rpy([.3, -.4, .7], [.05, -.08, .2])
        expected = nav_from_map @ seed @ imu_from_base
        confirmed = state['initial_pose_confirmation']
        self.assertEqual(confirmed['map_id'], self.navigation['id'])
        self.assertEqual(confirmed['map_revision'], self.navigation['revision'])
        self.assertAlmostEqual(confirmed['pose']['x'], expected[0, 3])
        self.assertAlmostEqual(confirmed['pose']['y'], expected[1, 3])
        self.assertAlmostEqual(confirmed['pose']['yaw'], np.arctan2(expected[1, 0], expected[0, 0]))

    def test_map_bundle_keeps_actual_occupancy_origin_resolution_and_hashes(self):
        selected = self.manager.select(self.selection)['selected']
        pin = selected['navigation_2d']
        self.assertEqual(pin['map_id'], self.navigation['id'])
        self.assertEqual(pin['revision'], self.navigation['revision'])
        self.assertEqual(pin['origin'], [0.7, -0.3, 0.2])
        self.assertEqual(pin['resolution'], .05)
        self.assertEqual(pin['yaml_sha256'], hashlib.sha256(self.yaml.read_bytes()).hexdigest())
        self.assertEqual(pin['image_sha256'], hashlib.sha256(self.image.read_bytes()).hexdigest())

    def test_consumer_snapshot_allows_rewritten_image_name_and_pins_consumed_geometry(self):
        self.manager.select(self.selection)
        directory = self.job_directory()
        snapshot = self.catalog.snapshot_navigation_map(self.navigation['id'], self.navigation['revision'], directory)
        self.assertIn('image: map.pgm', snapshot.yaml_path.read_text())
        self.assertIn('image: floor.pgm', self.yaml.read_text())
        self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory, snapshot)
        document = json.loads((directory / 'operational-3d.json').read_text())
        pin = document['navigation_2d']
        self.assertEqual(pin['consumer_yaml_sha256'], hashlib.sha256(snapshot.yaml_path.read_bytes()).hexdigest())
        self.assertNotEqual(pin['consumer_yaml_sha256'], pin['yaml_sha256'])
        self.assertEqual(pin['resolution'], snapshot.resolution)
        self.assertEqual(pin['origin'], list(snapshot.origin))

    def test_changed_consumer_snapshot_rejected_even_while_source_map_remains_identical(self):
        self.manager.select(self.selection)
        original_yaml, original_image = self.yaml.read_bytes(), self.image.read_bytes()
        for variant in ('yaml_origin', 'pgm_payload', 'different_revision', 'image_reference',
                        'origin_metadata', 'resolution_metadata'):
            with self.subTest(variant=variant):
                directory = self.job_directory(variant)
                snapshot = self.catalog.snapshot_navigation_map(self.navigation['id'], self.navigation['revision'], directory)
                if variant == 'yaml_origin':
                    snapshot.yaml_path.write_text(snapshot.yaml_path.read_text().replace('[0.7, -0.3, 0.2]', '[0.8, -0.3, 0.2]'))
                elif variant == 'pgm_payload':
                    changed = bytearray(snapshot.image_path.read_bytes())
                    changed[-1] = 0
                    snapshot.image_path.write_bytes(changed)
                elif variant == 'different_revision':
                    snapshot = replace(snapshot, revision='f' * 64)
                elif variant == 'image_reference':
                    (directory / 'rogue.pgm').write_bytes(b'P5\n2 2\n255\n' + bytes([0, 0, 0, 0]))
                    snapshot.yaml_path.write_text(snapshot.yaml_path.read_text().replace('image: map.pgm', 'image: rogue.pgm'))
                elif variant == 'origin_metadata':
                    snapshot = replace(snapshot, origin=(.8, -.3, .2))
                else:
                    snapshot = replace(snapshot, resolution=.1)
                with self.assertRaisesRegex(ValueError, 'NAVIGATION_JOB_SNAPSHOT_MISMATCH'):
                    self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory, snapshot)
                self.assertFalse((directory / 'operational-3d.json').exists())
                self.assertEqual(self.yaml.read_bytes(), original_yaml)
                self.assertEqual(self.image.read_bytes(), original_image)

    def test_edit_copy_is_a_separate_revision_and_worker_uses_that_exact_copy(self):
        source = self.source
        edited = self.catalog.save_pcd_edited_copy(source['map_id'], {
            'schema': 'robot-scope.pcd-edit-request.v1', 'name': 'software-localization-copy',
            'purpose': 'localization', 'source': source,
            'annotation': {'schema': 'robot-dashboard.map-editor3d', 'schema_version': 1,
                'version_id': 'synthetic-software-edit',
                'source': {key: source[key] for key in ('map_id', 'revision', 'frame_id')},
                'runtime_installed': False,
                'regions': [{'kind': 'localization', 'selection': 'inside',
                    'polygon': [[0, 0], [1, 0], [1, 1], [0, 1]], 'z_min': -1., 'z_max': 1.}]}})
        self.assertNotEqual(edited['id'], source['map_id'])
        self.assertLess(edited['point_count'], 384)
        selection = {**self.selection, 'map_id': edited['id'], 'map_revision': edited['revision']}
        selected = self.manager.select(selection)['selected']
        directory = self.job_directory()
        self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory)
        engine = load_bundle(directory / 'nav2_params.yaml')
        self.addCleanup(engine.close)
        self.assertEqual(engine.bundle['localization_3d']['map_id'], edited['id'])
        self.assertEqual(engine.bundle['localization_3d']['sha256'], edited['sha256'])
        self.assertEqual(engine.full_count, edited['point_count'])
        self.assertEqual(selected['localization_3d']['lineage'], edited['origin'])
        self.assertEqual(hashlib.sha256(self.pcd.read_bytes()).hexdigest(), self.sha)
        self.assertEqual(self.image.read_bytes(), b'P5\n2 2\n255\n' + bytes([255, 0, 128, 255]))

    def test_rejected_selection_preserves_previous_bundle_and_cannot_switch_while_running(self):
        first = self.manager.select(self.selection)['selected']
        invalid = copy.deepcopy(self.selection)
        invalid['map_revision'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'LOCALIZATION_MAP_REVISION_CHANGED'):
            self.manager.select(invalid)
        self.assertEqual(self.manager.status()['selected']['generation'], first['generation'])
        self.jobs.state = 'running'
        with self.assertRaisesRegex(ValueError, 'STOP_NAVIGATION_BEFORE_SOURCE_SELECTION'):
            self.manager.select({})
        self.assertEqual(self.manager.status()['selected']['generation'], first['generation'])

    def test_unrelated_pcd_with_same_frame_cannot_reuse_the_calibrated_map_alignment(self):
        first = self.manager.select(self.selection)['selected']
        other = self.maps / 'different-mapping-session.pcd'
        write_pcd(other, self.points + [20., -10., 0.])
        record = next(item for item in self.catalog.list_snapshot()['maps'] if item['name'] == other.stem)
        source = self.catalog.pcd_edit_source(record['id'])
        self.assertEqual(source['frame_id'], self.source['frame_id'])
        selection = {**self.selection, 'map_id': source['map_id'], 'map_revision': source['revision']}
        with self.assertRaisesRegex(ValueError, 'CALIBRATION_LOCALIZATION_ROOT_MISMATCH'):
            self.manager.select(selection)
        self.assertEqual(self.manager.status()['selected']['generation'], first['generation'])

    def test_root_identity_hash_revision_and_missing_pin_are_each_rejected(self):
        for key in ('map_id', 'revision', 'sha256', None):
            with self.subTest(key=key):
                self.calibration = self.make_calibration()
                if key is None:
                    self.calibration.pop('localization_root')
                else:
                    self.calibration['localization_root'][key] = 'f' * (24 if key == 'map_id' else 64)
                self.write_calibration()
                with self.assertRaisesRegex(ValueError, 'CALIBRATION_LOCALIZATION_ROOT_MISMATCH'):
                    self.manager.select(self.selection)
        self.assertIsNone(self.manager.status()['selected'])

    def test_restart_returns_legacy_mode_and_does_not_restore_seed_or_selection(self):
        self.manager.select(self.selection)
        restarted = OperationalNavigation(self.catalog, self.runtime_root, self.jobs)
        self.assertEqual(restarted.status()['activation'], 'LEGACY_2D')
        self.assertIsNone(restarted.status()['selected'])
        directory = self.job_directory()
        restarted.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory)
        self.assertFalse((directory / 'operational-3d.json').exists())
        self.assertIsNone(load_bundle(directory / 'nav2_params.yaml'))

    def test_missing_or_different_effective_device_calibration_is_rejected(self):
        path = self.runtime_root / 'operational-calibration.json'
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED'):
            self.manager.select(self.selection)
        for key in ('localization_frame', 'controller_odom_topic', 'navigation_profile', 'navigation_map_revision'):
            calibration = self.make_calibration()
            calibration[key] = 'different-effective-device-value'
            path.write_text(json.dumps(calibration))
            with self.assertRaisesRegex(ValueError, 'CALIBRATION_PROFILE_OR_MAP_MISMATCH'):
                self.manager.select(self.selection)
        self.assertIsNone(self.manager.status()['selected'])

    def test_modified_source_or_nav_geometry_cannot_be_snapshotted_with_old_revision(self):
        self.manager.select(self.selection)
        original = self.pcd.read_bytes()
        modified = bytearray(original)
        modified[-1] ^= 1
        self.pcd.write_bytes(modified)
        directory = self.job_directory()
        with self.assertRaises((ValueError, SavedMapError)):
            self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory)
        self.assertFalse((directory / 'operational-3d.json').exists())
        self.pcd.write_bytes(original)
        # Re-select with the refreshed catalogue identity, then mutate occupancy.
        self.source = self.catalog.pcd_edit_source(self.localization['id'])
        self.selection = self.make_selection()
        self.calibration = self.make_calibration()
        self.write_calibration()
        self.manager.select(self.selection)
        self.image.write_bytes(b'P5\n2 2\n255\n' + bytes([0, 0, 128, 255]))
        directory = self.job_directory('second-job')
        with self.assertRaises((ValueError, SavedMapError)):
            self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory)
        self.assertFalse((directory / 'operational-3d.json').exists())

    def pair_fixture(self):
        from robot_dashboard.map_lineage import build_family_document, serialize_family_document
        family = build_family_document(family_id='a' * 24, mapping_session_id='b' * 24,
            pcd_map_id=self.source['map_id'], pcd_revision=self.source['revision'],
            source_frame_id=self.source['frame_id'], occupancy_map_id=self.navigation['id'],
            occupancy_revision=self.navigation['revision'], occupancy_frame_id='map',
            resolution=.05, width=2, height=2, origin=[.7, -.3, .2],
            parameters={'resolution': .05, 'z_min': -.2, 'z_max': .8,
                        'noise_radius': .1, 'min_neighbors': 10, 'background': 'unknown'})
        (self.maps / 'floor.map-family.json').write_bytes(serialize_family_document(family))
        (self.maps / 'floor.map-family.json').chmod(0o600)
        return {key: value for key, value in self.selection.items() if key != 'seed_pose'}

    def test_pair_rebinds_only_map_transform_using_explicit_lineage_without_changing_calibration(self):
        pair = self.pair_fixture()
        self.calibration['navigation_map_id'] = 'e' * 24
        self.calibration['navigation_map_revision'] = 'e' * 64
        self.calibration['localization_root']['map_id'] = 'f' * 24
        self.calibration['T_nav_map_from_localization_map'] = from_translation_rpy([3, 2, 1], [.1, .2, .3]).tolist()
        self.write_calibration()
        before = (self.runtime_root / 'operational-calibration.json').read_bytes()
        result = self.manager.select_pair(pair)
        self.assertTrue(result['pair']['valid'])
        self.assertFalse(result['pair']['can_start'])
        self.assertIsNone(result['selected']['seed_T_map_imu'])
        self.assertIsNone(result['initial_pose_confirmation'])
        self.assertEqual(result['selected']['calibration']['T_imu_base'], self.calibration['T_imu_base'])
        self.assertEqual(result['selected']['policy'], self.calibration['policy'])
        np.testing.assert_allclose(result['selected']['calibration']['T_nav_map_from_localization_map'], np.eye(4))
        self.assertEqual((self.runtime_root / 'operational-calibration.json').read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'INITIAL_HEIGHT_TILT_REQUIRED'):
            self.manager.preflight(self.navigation['id'], self.navigation['revision'])

    def test_pair_rejects_wrong_source_and_preserves_previous_selection(self):
        pair = self.pair_fixture()
        original = self.manager.select_pair(pair)['selected']
        other = self.maps / 'unrelated.pcd'
        write_pcd(other, self.points + 10)
        item = next(m for m in self.catalog.list_snapshot()['maps'] if m['name'] == 'unrelated')
        with self.assertRaisesRegex(ValueError, 'MAP_PAIR_LINEAGE_MISMATCH'):
            self.manager.select_pair({**pair, 'map_id': item['id'], 'map_revision': item['revision']})
        self.assertEqual(self.manager.status()['selected'], original)
        self.jobs.state = 'running'
        with self.assertRaisesRegex(ValueError, 'STOP_NAVIGATION'):
            self.manager.select_pair(pair)

    def test_pair_geometry_explicit_and_one_execution_only_with_reconfirm_and_legacy_restore(self):
        state = self.manager.select_pair(self.pair_fixture())
        generation = state['selected']['generation']
        for bad in ({'generation': generation, 'z': .4, 'roll': 0.},
                    {'generation': generation, 'z': float('nan'), 'roll': 0., 'pitch': 0.},
                    {'generation': 'e' * 32, 'z': .4, 'roll': 0., 'pitch': 0.}):
            with self.assertRaises(ValueError):
                self.manager.seed_geometry(bad)
        body = {'generation': generation, 'z': .4, 'roll': .02, 'pitch': -.04}
        self.assertTrue(self.manager.seed_geometry(body)['pair']['can_start'])
        self.manager.preflight(self.navigation['id'], self.navigation['revision'])
        directory = self.job_directory()
        self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], directory)
        doc = json.loads((directory / 'operational-3d.json').read_text())
        self.assertIsNone(doc['seed_T_map_imu'])
        self.assertEqual(doc['seed_geometry']['source'], 'operator')
        self.assertEqual(self.manager.expected_source(directory.name, self.navigation['id'], self.navigation['revision'])['bundle_generation'], generation)
        self.assertIsNone(self.manager.expected_source('different-job', self.navigation['id'], self.navigation['revision']))
        with self.assertRaisesRegex(ValueError, 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED'):
            self.manager.preflight(self.navigation['id'], self.navigation['revision'])
        self.assertTrue(self.manager.seed_geometry(body)['pair']['can_start'])
        self.assertEqual(self.manager.select({})['activation'], 'LEGACY_2D')
        self.assertIsNone(self.manager.status()['pair'])

    def test_pair_rename_invalidates_old_proof_and_rebind_preserves_annotations(self):
        pair = self.pair_fixture()
        self.manager.select_pair(pair)
        annotations = self.catalog.annotations(self.navigation['id'])
        renamed = self.catalog.rename(self.navigation['id'], 'renamed_floor')
        state = self.manager.status()
        self.assertFalse(state['pair']['valid'])
        self.assertEqual(state['pair']['restart_from_step'], 1)
        with self.assertRaises(SavedMapError):
            self.manager.preflight(self.navigation['id'], self.navigation['revision'])
        state = self.manager.select_pair({**pair, 'navigation_map_id': renamed['id'], 'navigation_map_revision': renamed['revision']})
        self.assertTrue(state['pair']['valid'])
        self.assertIsNone(state['pair']['seed_geometry'])
        self.assertEqual(self.catalog.annotations(renamed['id'])['points'], annotations['points'])

    def test_pair_changed_calibration_blocks_until_revalidated_without_silent_update(self):
        pair = self.pair_fixture()
        first = self.manager.select_pair(pair)
        self.calibration['evidence'] = 'software fixture changed readback'
        self.write_calibration()
        state = self.manager.status()
        self.assertFalse(state['pair']['valid'])
        self.assertEqual(state['pair']['checks'][0]['code'], 'CALIBRATION_CHANGED_REAPPLY_PAIR')
        self.assertEqual(first['selected'], state['selected'])

    def test_pair_operations_admit_catalog_once_and_external_status_revalidates(self):
        pair = self.pair_fixture()
        with patch.object(self.catalog, '_scan', wraps=self.catalog._scan) as scan:
            self.assertIsNone(self.manager.status()['selected'])
            self.manager.preflight(self.navigation['id'], self.navigation['revision'])
            self.assertEqual(scan.call_count, 0)
            state = self.manager.select_pair(pair)
            self.assertEqual(scan.call_count, 1)
            self.assertTrue(self.manager.status()['pair']['valid'])
            self.assertEqual(scan.call_count, 1, 'status verifies selected files without discovery')
            self.assertEqual(len(self.manager._selected_records), 2)
            for operation in (
                lambda: self.manager.seed_geometry({'generation': state['selected']['generation'],
                    'z': .4, 'roll': .02, 'pitch': -.04}),
                lambda: self.manager.preflight(self.navigation['id'], self.navigation['revision']),
                lambda: self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], self.job_directory()),
            ):
                before = scan.call_count
                operation()
                self.assertEqual(scan.call_count, before + 1)
            self.pcd.write_bytes(self.pcd.read_bytes() + b'changed reference')
            before = scan.call_count
            state = self.manager.status()
            self.assertFalse(state['pair']['valid'])
            self.assertIn('LOCALIZATION_MAP_REVISION_CHANGED', state['pair']['checks'][0]['code'])
            self.assertEqual(scan.call_count, before)

    def test_status_retained_references_do_not_cache_sha_and_invalid_references_report_checks(self):
        self.manager.select_pair(self.pair_fixture())
        before = self.pcd.stat()
        data = bytearray(self.pcd.read_bytes())
        data[-1] ^= 1
        self.pcd.write_bytes(data)
        os.utime(self.pcd, ns=(before.st_atime_ns, before.st_mtime_ns))
        with patch.object(self.catalog, '_scan', side_effect=AssertionError('status must not scan')):
            state = self.manager.status()
        self.assertFalse(state['pair']['valid'])
        self.assertEqual(state['pair']['checks'][0]['code'], 'LOCALIZATION_MAP_REVISION_CHANGED')
        self.manager._selected_records = (replace(self.manager._selected_records[0], root=self.root),)
        state = self.manager.status()
        self.assertFalse(state['pair']['valid'])
        self.assertIn('outside configured roots', state['pair']['checks'][0]['code'])
        self.manager.select({})
        self.assertIsNone(self.manager._selected_records)

    def test_preflight_and_snapshot_still_require_full_catalog_admission(self):
        state = self.manager.select_pair(self.pair_fixture())
        self.manager.seed_geometry({'generation': state['selected']['generation'],
                                   'z': .4, 'roll': .02, 'pitch': -.04})
        self.catalog.max_files = 1
        self.assertTrue(self.manager.status()['pair']['valid'])
        with self.assertRaises(SavedMapError):
            self.manager.preflight(self.navigation['id'], self.navigation['revision'])
        with self.assertRaises(SavedMapError):
            self.manager.snapshot_for_job(self.navigation['id'], self.navigation['revision'], self.job_directory())



if __name__ == '__main__':
    unittest.main()
