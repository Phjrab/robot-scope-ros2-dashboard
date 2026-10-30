"""Input contract tests only; deliberately no native/ROS success claim."""
import struct
import unittest
from experiments.expansion_20261029.d3_collision_sim.c4_input_fixture import (
    CASES, STAGES, audit_case, latency_ns, measurement,
)


class C4InputFixtureTests(unittest.TestCase):
    def test_raw_wall_returns_not_empty_scene_certificate(self):
        f = measurement()
        self.assertIsNone(f['coverage'])
        self.assertEqual(f['protection_mode'], 'ADVISORY_ONLY')
        self.assertEqual(f['message']['width'], 33)
        self.assertEqual(len(f['message']['data']), f['message']['row_step'])
        for i, ray in enumerate(f['rays']):
            point = struct.unpack_from('<fff', f['message']['data'], i*12)
            for actual, expected in zip(point, ray['endpoint']):
                self.assertAlmostEqual(actual, expected, places=6)
            self.assertEqual(ray['raw_reference'], f['raw_reference'])
            self.assertTrue(ray['measurement_valid'])

    def test_rebind_old_identity_not_relabelled(self):
        old = measurement()
        new = measurement(epoch='sensor-2', revision='r2', generation=1)
        self.assertEqual(old['identity']['source_epoch'], 'sensor-1')
        self.assertNotEqual(old['raw_reference'], new['raw_reference'])
        self.assertEqual(old['identity']['map_generation'], 0)
        self.assertEqual(new['identity']['map_generation'], 1)

    def test_latency_requires_clock_and_epoch_and_is_lossless(self):
        start = dict(clock_id='sim', epoch='a', stamp_ns=str(2**53+12345))
        end = dict(start, stamp_ns=str(2**53+12352))
        self.assertEqual(latency_ns(start,end), '7')
        self.assertIsNone(latency_ns(start, dict(end, epoch='b')))
        self.assertIsNone(latency_ns(start, dict(end, clock_id='host')))
        self.assertIsNone(latency_ns(end,start))
        self.assertIsNone(latency_ns({},{}))

    def test_publish_and_mock_never_native_success(self):
        for case in CASES:
            self.assertEqual(audit_case(case, {'execution':'MOCK'})['status'], 'NOT_RUN')
            self.assertEqual(audit_case(case, {'execution':'NATIVE_NAV2_SIM',
                'observation_published':True})['status'], 'FAIL')

    def test_clearing_requires_raw_ray_and_cell_proof(self):
        evidence = {key: True for key in STAGES}
        evidence.update(execution='NATIVE_NAV2_SIM', independent_validation='PASS',
                        contact_count=0, boundary_count=0)
        self.assertEqual(audit_case('obstacle_removed_with_rays',evidence)['reason'],
                         'CLEARING_RAY_AND_CELL_PROOF_REQUIRED')
        evidence.update(raw_ray_reference='raw:1', cleared_cell_indices=[2],
                        marking_cell_indices=[2], ray_cell_intersections=[2])
        self.assertEqual(audit_case('obstacle_removed_with_rays',evidence)['claim'],
                         'EVIDENCE_ENVELOPE_ONLY')
        evidence['contact_count'] = 1
        self.assertEqual(audit_case('obstacle_removed_with_rays',evidence)['status'], 'FAIL')
