import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('progress_audit',HERE/'audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class Arithmetic(unittest.TestCase):
    def test_straight_rotated(self):
        self.assertAlmostEqual(a.integrate([0,0,math.pi/2],[1,0,0],.05)[1],.05)
    def test_lateral(self):
        self.assertEqual(a.integrate([0,0,0],[0,1,0],.05),[0,.05,0])
    def test_rotation(self):
        x,y,t=a.integrate([0,0,0],[1,0,1],math.pi/2)
        self.assertAlmostEqual(x,1);self.assertAlmostEqual(y,1);self.assertAlmostEqual(t,math.pi/2)
    def test_even_median(self):self.assertEqual(a.stats([1,3])['median'],2)
    def test_empty_stats_unknown(self): self.assertIsNone(a.stats([]))
    def test_negative_clock_rejected(self):
        with self.assertRaises(ValueError):a.increasing([{'t':2},{'t':1}],'t')
    def test_duplicate_clock_rejected(self):
        with self.assertRaises(ValueError):a.increasing([{'t':1},{'t':1}],'t')
    def test_zero_window_distance(self):self.assertEqual(a.distance([{'pose':[1,2,0]}]),0)

class Retained(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ.get('D0_R8_ARTIFACT','/tmp/c3-r7'))
        if not cls.root.exists():raise unittest.SkipTest('retained private artifact not materialized')
        run=cls.root/'atomic/mppi-d0_feasible1-0/run'
        cls.t=[json.loads(x)for x in(run/'trace.jsonl').read_text().splitlines()]
        cls.c=[json.loads(x)for x in(run/'raw_commands.jsonl').read_text().splitlines()]
        cls.log=(run/'native.log').read_text();cls.goal=json.loads((run/'fixture.json').read_text())['goal']
    def test_reproduce(self):
        actual=a.audit(self.root)
        self.assertEqual(actual,json.loads((HERE/'result.json').read_text()))
        self.assertEqual(actual['active_control']['reasons'],{'RELEASE':456})
        self.assertLess(actual['simulated_actuation']['pose_integration_max_error'],1e-10)
        self.assertEqual(actual['simulated_actuation']['previous_output_max_error'],0)
    def test_receipt_clock_mutation(self):
        c=copy.deepcopy(self.c);c[2]['receipt_monotonic']=c[1]['receipt_monotonic']-1
        with self.assertRaises(ValueError):a.summarize(self.t,c,self.log,self.goal)
    def test_sim_step_mutation(self):
        t=copy.deepcopy(self.t);t[2]['sim_t']+=.01
        with self.assertRaises(ValueError):a.summarize(t,self.c,self.log,self.goal)
    def test_applied_command_mutation_detected(self):
        t=copy.deepcopy(self.t);t[200]['applied_previous'][0]+=.1
        result=a.summarize(t,self.c,self.log,self.goal)
        self.assertGreater(result['simulated_actuation']['previous_output_max_error'],.09)
        self.assertGreater(result['simulated_actuation']['pose_integration_max_error'],.004)
    def test_wrong_source_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            Path(d,'source-sha.txt').write_text('wrong')
            with self.assertRaisesRegex(ValueError,'source'):a.audit(d)

if __name__=='__main__':unittest.main()
