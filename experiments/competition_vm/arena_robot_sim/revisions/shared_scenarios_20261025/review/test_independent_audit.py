"""Adversarial controls for the independent review verifier."""
import json
import unittest
import numpy as np
import audit_saved_witnesses as audit


class AuditControls(unittest.TestCase):
    def test_crossing_without_contained_vertices(self):
        horizontal = audit.as_complex([[[-2,-.1],[2,-.1],[2,.1],[-2,.1]]])
        vertical = audit.as_complex([[-.1,-2],[.1,-2],[.1,2],[-.1,2]])
        self.assertEqual(audit.separation(horizontal, vertical)[0], 0.)

    def test_collinear_contact(self):
        square = audit.as_complex([[[0,0],[1,0],[1,1],[0,1]]])
        touching = audit.as_complex([[1,0],[2,0],[2,1],[1,1]])
        self.assertEqual(audit.separation(square, touching)[0], 0.)

    def test_nested_obstacle_containment(self):
        square = audit.as_complex([[0,0],[1,0],[1,1],[0,1]])
        self.assertTrue(audit.inside(audit.as_complex([[.5,.5]]), square)[0])
        self.assertFalse(audit.inside(audit.as_complex([[2,.5]]), square)[0])

    def test_mutated_witness_rejected(self):
        truth = json.loads((audit.ROOT/'fixtures/original_tight5.truth.json').read_text())
        witness = json.loads((audit.ROOT/'witnesses/original_tight5.json').read_text())
        witness['poses'][1] = [.18, 1.55, np.pi/2]
        with self.assertRaises(AssertionError):
            audit.audit(truth, witness)

    def test_distinct_feasible_inputs_and_scene_links(self):
        one = json.loads((audit.ROOT/'fixtures/feasible1.truth.json').read_text())
        two = json.loads((audit.ROOT/'fixtures/feasible2.truth.json').read_text())
        self.assertEqual(len(one['cones']), 1)
        self.assertEqual(len(two['cones']), 2)
        self.assertNotEqual(one['scene_sha256'], two['scene_sha256'])
        results = json.loads((audit.ROOT/'feasibility_results.json').read_text())
        for name, result in results['results'].items():
            truth = json.loads((audit.ROOT/'fixtures'/f'{name}.truth.json').read_text())
            self.assertEqual(truth['scene_sha256'], result['input_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
