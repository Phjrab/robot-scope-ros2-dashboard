"""Offline contract, transform, sensor and reproducibility checks. No ROS needed."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_fixtures as exporter


class SharedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenes = exporter.scenes()
        cls.files = exporter.build_bundle()

    def test_minimum_cases_and_separate_open(self):
        self.assertEqual(set(self.scenes), {'empty','feasible1','feasible2','original_tight5','blocked','sensor_dropout','open_diagnostic'})
        self.assertTrue(self.scenes['open_diagnostic']['diagnostic_only'])
        self.assertFalse(self.scenes['original_tight5']['diagnostic_only'])

    def test_deterministic_semantic_hashes(self):
        again = exporter.build_bundle()
        self.assertEqual({k:exporter.digest(v) for k,v in self.files.items()},
                         {k:exporter.digest(v) for k,v in again.items()})

    def test_export_roundtrip_and_check(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = exporter.export(output)
            self.assertEqual(manifest, exporter.export(output, check=True))
            for name, expected in manifest['files'].items():
                self.assertEqual(exporter.digest(json.loads((output/name).read_text())), expected)
            path = output/'empty.truth.json'
            value = json.loads(path.read_text()); value['start'][0] += .001
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'differs'):
                exporter.export(output, check=True)

    def test_coordinate_roundtrip_and_real_registration_unknown(self):
        for pose in [[0.,0.,0.], [8.,6.,math.pi], [-.4,2.1,-2.]]:
            self.assertEqual(exporter.sim_to_design(exporter.design_to_sim(pose)), pose)
            self.assertEqual(exporter.gltf_to_design(exporter.design_to_gltf(pose)), pose)
        geometry = self.files['geometry.json']
        self.assertIsNone(geometry['map_transform'])
        self.assertEqual(geometry['real_map_registration'], 'INPUT_REQUIRED')
        self.assertEqual(exporter.design_to_gltf([2.,3.,.4]), [2.,.4,-3.])

    def test_original_and_approved_revisions_not_conflated(self):
        geometry = self.files['geometry.json']
        self.assertNotEqual(geometry['original']['source_sha256'], geometry['corridor_parallel']['source_sha256'])
        self.assertEqual(geometry['original']['revision'], 'rulebook-20261015-v1')
        self.assertEqual(geometry['corridor_parallel']['revision'], 'corridor-parallel-20261024-v1')
        self.assertEqual(geometry['original']['floors']['floor_left_straight'],
                         geometry['corridor_parallel']['floors']['floor_left_straight'])
        self.assertNotEqual(geometry['original']['outer_boundary'], geometry['corridor_parallel']['outer_boundary'])

    def test_original_full_geometry_and_strict_forbidden_retained(self):
        original = exporter.load_geometry(exporter.GEOMETRY_PATH)
        geometry = self.files['geometry.json']['original']
        self.assertEqual(geometry['outer_boundary'], original.OUTER)
        self.assertEqual(geometry['holes'], original.HOLES)
        self.assertEqual(geometry['semantic_zones'], original.zones())
        for scene in self.scenes.values():
            self.assertFalse(scene['parking_allowed'])
            self.assertIn(original.FLOORS['floor_parking_bay'], scene['forbidden_polygons'])
            self.assertIn(original.FLOORS['floor_center_base'], scene['forbidden_polygons'])
            for zone in original.zones():
                if zone['type'] in ('RAMP','STAIRS'):
                    self.assertIn(zone['polygon'], scene['forbidden_polygons'])

    def test_body_and_visual_envelope_distinct(self):
        geometry = self.files['geometry.json']
        self.assertEqual(geometry['collision_body']['polygon'], [[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]])
        bounds = geometry['visual_envelope']['standing_fk_bounds']
        self.assertLess(bounds['max_xyz'][0]-bounds['min_xyz'][0], .81)
        self.assertEqual(geometry['clearance_policy']['margin_m'], .03)

    def test_cone_sizes_and_original_positions_unchanged(self):
        originals = exporter.base.configs()
        for name, key in [('original_tight5','slalom_5'), ('blocked','blocked_5')]:
            for actual, source in zip(self.scenes[name]['cones'], originals[key]):
                self.assertEqual({k:v for k,v in actual.items() if k!='appears_s'}, source)
        for scene in self.scenes.values():
            for cone in scene['cones']:
                self.assertEqual((cone['radius_m'],cone['height_m'],cone['base_side_m'],cone['base_height_m']), (.12,.32,.26,.04))
                self.assertEqual(cone['appears_s'], 0.)

    def test_truth_observations_separate_and_linked(self):
        for name in self.scenes:
            truth = self.files[name+'.truth.json']
            stream = self.files[name+'.observations.json']
            self.assertNotIn('ranges_m', truth)
            self.assertNotIn('cones', stream)
            self.assertEqual(truth['scene_sha256'], exporter.digest(self.scenes[name]))
            self.assertEqual(stream['truth_sha256'], exporter.digest(truth))
            self.assertEqual(truth['geometry_sha256'], exporter.digest(self.files['geometry.json']))

    def test_sensor_origin_fov_range_and_stamps(self):
        sensor = exporter.sensor_config('empty')
        self.assertEqual(sensor['origin_xy_body_m'], [0.,0.])
        self.assertEqual(sensor['origin_z_ground_m'], [.025,.10,.20,.35])
        self.assertEqual(sensor['horizontal_fov_rad'], 2*math.pi)
        for probe in self.files['empty.observations.json']['probes']:
            observation = probe['observation']
            self.assertEqual(len(observation['ranges_m']), 360)
            self.assertTrue(all(.02 < r <= 8. for r in observation['ranges_m']))
            self.assertEqual(observation['source_stamp_s'], probe['probe_stamp_s'])
            self.assertEqual(observation['receipt_stamp_s'], observation['source_stamp_s'])
            self.assertEqual(observation['seed'], exporter.SEED)

    def test_first_hit_occlusion_and_square_base(self):
        scene = copy.deepcopy(self.scenes['empty'])
        scene['cones'] = [dict(exporter.base.cone(1,.5,2.), appears_s=0.), dict(exporter.base.cone(2,.5,3.), appears_s=0.)]
        both = exporter.observe(scene, exporter.START, 0.)
        scene['cones'] = scene['cones'][:1]
        near = exporter.observe(scene, exporter.START, 0.)
        scene['cones'] = [dict(exporter.base.cone(2,.5,3.), appears_s=0.)]
        far = exporter.observe(scene, exporter.START, 0.)
        # Zero sensor angle points straight along +y because body yaw is pi/2.
        self.assertAlmostEqual(both['ranges_m'][180], .92, places=9)
        self.assertEqual(both['ranges_m'][180], near['ranges_m'][180])
        self.assertGreater(far['ranges_m'][180], near['ranges_m'][180]+.9)

    def test_spawn_schedule_not_baked_into_prior(self):
        scene = copy.deepcopy(self.scenes['empty'])
        scene['cones'] = [dict(exporter.base.cone(1,.5,2.), appears_s=1.)]
        before = exporter.observe(scene, exporter.START, .9)
        after = exporter.observe(scene, exporter.START, 1.)
        self.assertGreater(before['ranges_m'][180], after['ranges_m'][180])
        self.assertAlmostEqual(after['ranges_m'][180], .92, places=9)

    def test_dropout_absent_observation_not_restamped_clear_scan(self):
        scene = self.scenes['sensor_dropout']
        self.assertIsNotNone(exporter.observe(scene, exporter.START, 3.999))
        self.assertIsNone(exporter.observe(scene, exporter.START, 4.))
        self.assertIsNone(exporter.observe(scene, exporter.START, 100.))
        probes = self.files['sensor_dropout.observations.json']['probes']
        self.assertEqual(probes[-1]['delivery'], 'DROPPED')
        self.assertIsNone(probes[-1]['observation'])
        self.assertNotEqual(probes[0]['requested_pose_sim'], probes[1]['requested_pose_sim'])

    def test_sensor_does_not_leak_global_module_mutation(self):
        geometry = exporter.base.sim.geometry
        exporter.observe(self.scenes['empty'], exporter.START, 0.)
        self.assertIs(exporter.base.sim.geometry, geometry)

    def test_open_changes_obstacle_spacing_not_floor(self):
        tight, opened = self.scenes['original_tight5'], self.scenes['open_diagnostic']
        self.assertEqual(tight['boundary_polygon'], opened['boundary_polygon'])
        self.assertNotEqual([c['xy'] for c in tight['cones']], [c['xy'] for c in opened['cones']])


if __name__ == '__main__':
    unittest.main(verbosity=2)
