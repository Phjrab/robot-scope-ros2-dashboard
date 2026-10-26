import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from audit import (HERE, RAW, RC, H, corners, segment_box, grid_cell, perimeter_cells,
                   inflation_cost, emitted_cost, gate, occupancy, audit)
from coverage import evaluate


class GeometryAndCoverageTests(unittest.TestCase):
    def setUp(self):
        self.result=json.loads((HERE/'results'/'audit.json').read_text())

    def test_first_failure_margin_not_raw_contact(self):
        p=self.result['samples'][1]
        self.assertAlmostEqual(min(c[1] for c in corners(p['pose'], RAW))-.491,.03321578095532007,places=12)
        self.assertAlmostEqual(min(c[1] for c in corners(p['pose']))-.491,-.0006746805171706782,places=12)

    def test_previous_pose_is_inside_continuous_floor(self):
        self.assertGreater(self.result['samples'][0]['padded_floor_clearance_m'],0)

    def test_counter_semantics_and_stop(self):
        self.assertEqual(self.result['boundary_positive_sample_count'],64)
        self.assertEqual(self.result['distinct_crossing_events'],1)
        self.assertEqual(self.result['post_first_failure_nonzero_actuator_count'],0)

    def test_snapshot_receipt_order_and_source_age(self):
        for s in self.result['samples']:
            for m in s['maps']:
                if m['relation']=='last_received_before':
                    self.assertLessEqual(m['receipt_monotonic'],s['receipt_monotonic'])
                else:
                    self.assertGreater(m['receipt_monotonic'],s['receipt_monotonic'])
                self.assertAlmostEqual(m['source_age_sim_s'],s['sim_t']-m['source_sim_s'])

    def test_local_center_free_but_padded_edge_lethal(self):
        for s in self.result['samples']:
            m=next(m for m in s['maps'] if m['kind']=='local_costmap' and m['relation']=='last_received_before')
            self.assertEqual(m['center_occupancy'],0)
            self.assertGreater(len(m['padded_lethal_edge_cells']),0)
            for hit in m['padded_lethal_edge_cells']:
                self.assertTrue(any(segment_box(s['padded_corners'][i],s['padded_corners'][(i+1)%4],hit['box']) for i in hit['edges']))

    def test_valid_corridor_not_circumcircle(self):
        p=[.5,2,math.pi/2]
        self.assertTrue(all(.16<x<.84 for x,y in corners(p)))
        self.assertGreater(RC,.34)
        self.assertFalse(any(c[0] in (7,42) for c,e in perimeter_cells(corners(p),[0,0],H)))

    def test_corridor_raw_cost_field_and_full_check_acceptance(self):
        # Known synthetic source cells; NOT inversion of a published OccupancyGrid.
        for left,right in [(7,42),(5,44)]:
            pose=[.51,2.01,math.pi/2]
            center=grid_cell(pose[:2],[0,0],H)
            field=lambda x: emitted_cost(min(abs(x-left),abs(x-right))*H,.58)
            center_cost=field(center[0])
            perimeter_max=max(field(cell[0]) for cell,edges in perimeter_cells(corners(pose),[0,0],H))
            self.assertTrue(all(gate(center_cost).values()))
            self.assertLess(center_cost,253)
            self.assertEqual(perimeter_max,253)
            # Official 1.1.20 polygon modes: Smac returns footprint>=254;
            # MPPI with consider_footprint accepts 253, rejects 254.
            self.assertFalse(perimeter_max>=254)
            self.assertFalse(perimeter_max==254)

    def test_smac_snapped_counterexample_is_separate(self):
        c=evaluate()['smac_snapped_corner_counterexample']
        self.assertEqual(c['single_lethal_cell'],[72,66])
        d=H*math.dist(c['center_cell'],c['single_lethal_cell'])
        self.assertFalse(any(gate(emitted_cost(d,.58)).values()))

    def test_closed_segment_corner_contact(self):
        self.assertTrue(segment_box([0,0],[1,1],[[1,1],[2,2]]))
        self.assertFalse(segment_box([0,0],[.99,.99],[[1,1],[2,2]]))
        self.assertTrue(segment_box([1,0],[1,3],[[1,1],[2,2]]))

    def test_cost_and_support_not_same_function(self):
        self.assertEqual(inflation_cost(RC),82)
        self.assertEqual(emitted_cost(RC,.4),0)
        self.assertEqual(emitted_cost(RC,.54),82)

    def test_radius_expansion_is_not_discrete_gate_proof(self):
        c=evaluate()['counterexample']
        self.assertEqual(c['center_cell'],[50,50])
        self.assertEqual(c['single_lethal_cell'],[72,66])
        self.assertGreater(c['center_source_distance_m'],RC)
        self.assertGreater(c['center_raw_cost_by_inflation_radius']['0.58'],0)
        self.assertLess(c['center_raw_cost_by_inflation_radius']['0.58'],82)
        self.assertFalse(any(c['expanded_058_source_gate'].values()))

    def test_mppi_zero_skip_not_disabled_by_zero_threshold(self):
        self.assertTrue(gate(0,0)['smac_full_check_eligible'])
        self.assertFalse(gate(0,0)['mppi_full_check_eligible'])
        self.assertTrue(gate(1,0)['mppi_full_check_eligible'])

    def test_occupancy_special_and_lossy(self):
        self.assertEqual([occupancy(x) for x in [0,253,254,255]],[0,99,100,-1])
        self.assertEqual(occupancy(82),occupancy(83))
        self.assertNotEqual(round(254*99/100),253)

    def test_gate_threshold_equality(self):
        self.assertTrue(all(gate(82,82).values()))
        self.assertFalse(any(gate(81,82).values()))

    def test_sweep_quantization_bound(self):
        s=evaluate()
        self.assertLessEqual(s['finite_sweep']['max_vertex_distance_m'],s['vertex_bound_m'])
        self.assertGreater(s['finite_sweep']['expanded_058_radius_below_threshold'],0)

    @unittest.skipUnless(os.environ.get('D0_B_RUN_DIR'),'Private retained artifact optional; not fabricated')
    def test_private_artifact_reproduction(self):
        r=audit(Path(os.environ['D0_B_RUN_DIR']))
        self.assertEqual(json.loads(json.dumps(r)),self.result)

    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            # A nonexistent required input must fail before analysis, never substitute fixtures.
            with self.assertRaises(FileNotFoundError):
                audit(Path(d))

if __name__=='__main__':
    unittest.main()
