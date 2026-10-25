"""Bounded offline audit tests; private native archive is optional and explicit."""
import base64, importlib.util, json, os, tempfile, unittest, zlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit',HERE/'analyze_failure.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class AuditTests(unittest.TestCase):
    def test_wrong_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.zip';p.write_bytes(b'not native evidence')
            with self.assertRaisesRegex(ValueError,'SHA256'):a.load_archive(p)
    def test_cost_encoding(self):
        self.assertEqual([a.classify(x) for x in [-1,0,98,99,100]],['unknown','free','inflation_cost','inscribed','lethal'])
    def test_costmap_signed_bytes(self):
        r={'width':3,'height':1,'data_zlib_base64':base64.b64encode(zlib.compress(bytes([255,99,100]))).decode()}
        self.assertEqual(a.decode_costmap(r).tolist(),[[-1,99,100]])
        r['width']=4
        with self.assertRaises(ValueError):a.decode_costmap(r)
    def test_straight_and_curved_integration(self):
        np.testing.assert_allclose(a.propagate([0,0,0],1,0,np.array([0,1])),[[0,0,0],[1,0,0]])
        np.testing.assert_allclose(a.propagate([0,0,0],1,1,np.array([np.pi/2])),[[1,1,np.pi/2]])
    def test_geometry_contact_and_clear(self):
        t={'boundary_polygon':[[-5,-5],[5,-5],[5,5],[-5,5]],'forbidden_polygons':[],'obstacles':[{'polygon':[[1,-1],[2,-1],[2,1],[1,1]]}]}
        fp=[[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]]
        np.testing.assert_allclose(a.geometry_clearances([[0,0,0],[.5,0,0],[1,0,0]],fp,t),[.5,0,0])
    def test_saved_evidence_qualifiers(self):
        j=json.loads((HERE/'results/judgment.json').read_text())
        self.assertFalse(j['native_input']['path_yaw_recorded'])
        self.assertEqual(j['previous_command_counterfactual']['status'],'NOT_THE_REJECTED_CANDIDATE')
        self.assertEqual(j['hypotheses']['exact_rejected_sweep_cause'],'NOT_RUN_MISSING_SIGNALS')
        self.assertGreater(j['first_event']['spin_delay_after_first_s'],1)
        self.assertGreater(j['path_tangent_diagnostic']['central_chord_sensitivity']['raw_clearance_m'],0)
    @unittest.skipUnless(os.environ.get('D0_NATIVE_ARTIFACT'),'Set D0_NATIVE_ARTIFACT to the verified private archive')
    def test_actual_native_archive(self):
        j,_=a.analyze(os.environ['D0_NATIVE_ARTIFACT'])
        saved=json.loads((HERE/'results/judgment.json').read_text())
        self.assertEqual(j,saved)
        self.assertEqual(j['first_event']['native_log_line'],144)
        self.assertAlmostEqual(j['current_recorded_geometry']['minimum_clearance_m']['raw_body'],.18623516060791578)
if __name__=='__main__':unittest.main()
