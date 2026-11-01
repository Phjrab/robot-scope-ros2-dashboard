"""Explicit real-owner regression, isolated from repository test module imports."""
import asyncio
import os
from pathlib import Path
import unittest
from robot_dashboard.expansion_diagnostics.dependencies import activate, verify
from robot_dashboard.expansion_diagnostics.measure import Measurements
from robot_dashboard.expansion_diagnostics.observations import capacity_case, exact_sample_boundary, fences, exact_compactor_boundary, exact_wire_boundary
from robot_dashboard.expansion_diagnostics.workloads import queue_probe, canonical_composition


class ActualOwners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deps=Path(os.environ['C7_DEPENDENCY_ROOT']).resolve()
        cls.manifest=verify(Path.cwd(),cls.deps)
        activate(cls.deps)

    def test_geometry_specific_sixteen_and_byte_boundary(self):
        m=Measurements()
        sparse,_,_,_=capacity_case(self.deps,m,'sparse',16)
        cone,_,_,_=capacity_case(self.deps,m,'cone',16)
        self.assertEqual(sparse['compactor']['status'],'ACCEPTED')
        self.assertEqual(cone['compactor']['status'],'REJECTED')
        self.assertTrue(cone['geometry_preserved'])
        self.assertEqual(cone['retained_core_objects'],16)
        self.assertEqual(cone['full_wire']['status'],'ACCEPTED')
        self.assertEqual(cone['full_service_probe']['status'],'REJECTED')
        _,_,small,_=capacity_case(self.deps,m,'cone',1)
        self.assertEqual([v['ingest']['status'] for v in exact_sample_boundary(small)],['ACCEPTED','ACCEPTED','REJECTED'])
        self.assertEqual([v['wire']['status'] for v in exact_wire_boundary(small)],['ACCEPTED','ACCEPTED','REJECTED'])
        self.assertEqual([v['result']['status'] for v in exact_compactor_boundary(small)],['ACCEPTED','ACCEPTED','REJECTED'])
        fault=fences(small)
        self.assertEqual(fault['expired_status'],'expired')
        self.assertIsNone(fault['expired_value'])
        self.assertTrue(fault['map_cleared'] and fault['map_rejected'])
        self.assertEqual(fault['clock_status'],'unavailable')
        self.assertIsNone(fault['clock_age_ms'])
        self.assertEqual(fault['history_max'],16)
        self.assertEqual(fault['sink_false_probe']['dropped'],1)
        self.assertIsNone(fault['sink_false_probe']['returned'])

    def test_actual_bounded_worker(self):
        row=asyncio.run(queue_probe(self.deps))
        self.assertEqual(row['input'],60)
        self.assertEqual(row['processed'],2)
        self.assertEqual(row['replaced_pending'],58)
        self.assertEqual(row['pending_max'],1)
        self.assertEqual(row['displayed_sequence'],60)
        self.assertIsNone(row['latest_after_close'])

    def test_current_canonical_connection_has_no_fake_collision_geometry(self):
        result=canonical_composition(self.deps,Measurements(),'node')
        self.assertEqual(result['status'],'PASS',result)
        self.assertFalse(result['c3']['collisionAvailable'])
        self.assertEqual(result['c3']['obstacleCount'],1)

    @classmethod
    def tearDownClass(cls):
        if verify(Path.cwd(),cls.deps)!=cls.manifest:
            raise AssertionError('owner sources changed')


if __name__=='__main__':
    unittest.main(verbosity=2)
