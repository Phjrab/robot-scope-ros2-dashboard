import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from dataclasses import replace
import numpy as np
import cv2
from core import *
from detector import *

def lamp(color):
    a=np.zeros((64,64,3),np.uint8)+15
    cv2.circle(a,(32,32),12,color,-1)
    return a

class ColorTests(unittest.TestCase):
    def test_red(self):self.assertEqual(classify_roi(lamp((0,0,230)))['raw_state'],'RED')
    def test_green(self):self.assertEqual(classify_roi(lamp((0,230,0)))['raw_state'],'GREEN')
    def test_white_unknown(self):self.assertEqual(classify_roi(np.full((32,32,3),255,np.uint8))['raw_state'],'UNKNOWN')
    def test_off_unknown(self):self.assertEqual(classify_roi(lamp((0,0,0)))['raw_state'],'UNKNOWN')
    def test_dual_ambiguous(self):
        a=lamp((0,230,0));cv2.circle(a,(12,12),6,(0,0,230),-1)
        self.assertEqual(classify_roi(a)['raw_state'],'AMBIGUOUS')
    def test_low_chroma(self):self.assertIn('LOW_CHROMA',classify_roi(lamp((230,230,230)))['quality_flags'])
    def test_tiny(self):self.assertIn('TOO_SMALL',classify_roi(lamp((0,230,0)),(1,1,3,3))['quality_flags'])
    def test_truncated(self):self.assertEqual(classify_roi(lamp((0,230,0)),(-1,0,64,64))['raw_state'],'UNKNOWN')
    def test_encoding(self):self.assertEqual(classify_roi(lamp((0,230,0)),encoding='mono8')['raw_state'],'UNKNOWN')
    def test_rgb_order(self):self.assertEqual(classify_roi(lamp((230,0,0)),encoding='rgb8')['raw_state'],'RED')
    def test_settling(self):self.assertEqual(classify_roi(lamp((0,230,0)),exposure_settling=True)['raw_state'],'UNKNOWN')
    def test_reflection_unassociated(self):self.assertEqual(classify_roi(lamp((0,230,0)),association_verified=False)['raw_state'],'UNKNOWN')
    def test_variants(self):
        for v in ('raw','luminance','combined'):self.assertEqual(classify_roi(lamp((0,230,0)),variant=v)['raw_state'],'GREEN')
    def test_inverse_letterbox(self):self.assertEqual(inverse_letterbox((0,160,640,480),(1280,640),(640,640)),(0,0,1280,640))
    def test_odd_letterbox(self):
        img=np.ones((333,517,3),np.uint8);out=letterbox(img)
        r=min(640/517,640/333);rh=round(333*r);top=(640-rh)//2
        self.assertEqual(inverse_letterbox((0,top,640,top+rh),(517,333),(640,640)),(0,0,517,333))
        self.assertEqual(out.shape,(640,640,3))
    def test_bad_box(self):
        with self.assertRaises(ValueError):inverse_letterbox((1,1,0,0),(640,480),(640,640))

class TemporalTests(unittest.TestCase):
    def setUp(self):self.f=TemporalFilter()
    def update(self,t,state='GREEN',seq=None,identity=('epoch','track','cross','visit'),age=0.,flags=()):
        return self.f.update(state,identity=identity,sequence=round(t*10) if seq is None else seq,
            source_stamp_ns=str(round(t*1e9)),receipt_s=t,source_age_s=age,flags=flags)
    def warm(self):
        for x in range(5):s=self.update(x/10)
        return s
    def test_stable_after_time(self):self.assertEqual(self.warm(),'GREEN')
    def test_duplicate_rejects(self):self.warm();self.assertEqual(self.update(.4),'UNKNOWN')
    def test_epoch_reset(self):self.warm();self.assertEqual(self.update(.5,identity=('new','track','cross','visit')),'UNKNOWN')
    def test_roi_track_reset(self):self.warm();self.assertEqual(self.update(.5,identity=('epoch','new','cross','visit')),'UNKNOWN')
    def test_clock_rewind(self):self.warm();self.assertEqual(self.update(.2,seq=9),'UNKNOWN')
    def test_gap(self):self.warm();self.assertEqual(self.update(1.),'UNKNOWN')
    def test_stale_age(self):self.warm();self.assertEqual(self.update(.5,age=1.),'UNKNOWN')
    def test_expiry_poll(self):self.warm();self.assertEqual(self.f.current(1.),'UNKNOWN')
    def test_invalid_clears_history(self):self.warm();self.assertEqual(self.update(.5,flags=['CLIPPED']),'UNKNOWN');self.assertEqual(self.update(.6),'UNKNOWN')
    def test_red_no_green_interpolation(self):self.warm();self.assertEqual(self.update(.5,'RED'),'UNKNOWN')

class FSMTests(unittest.TestCase):
    def setUp(self):
        self.f=StopGoFSM();self.f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
    def sample(self,t,**kw):
        base=StopInput(receipt_s=t,sequence=round(t*10),stable_state='GREEN',left_inside=True,right_inside=True,
            visual_zone=True,body_stopped=True,approach_ack=True)
        return replace(base,**kw)
    def warm(self,state='GREEN'):
        for n in range(21):r=self.f.update(self.sample(n/10,stable_state=state))
        return r
    def test_green_no_skip(self):
        for n in range(20):self.assertFalse(self.f.update(self.sample(n/10))['depart_intent'])
        self.assertTrue(self.f.update(self.sample(2.))['depart_intent'])
    def test_red_then_green(self):self.assertEqual(self.warm('RED')['state'],'WAIT_GREEN');self.assertTrue(self.f.update(self.sample(2.1))['depart_intent'])
    def test_pending_revoked_red(self):self.warm();self.assertFalse(self.f.update(self.sample(2.1,stable_state='RED'))['depart_intent'])
    def test_red_departure_same_frame_not_committed(self):self.warm();self.assertNotEqual(self.f.update(self.sample(2.1,stable_state='RED',departure_observed=True))['state'],'CROSSING_COMMITTED')
    def test_committed_ignores_red(self):
        self.warm();self.f.update(self.sample(2.1,departure_observed=True,body_stopped=False))
        self.assertEqual(self.f.update(self.sample(2.2,stable_state='RED',body_stopped=False))['motion_constraint']['mode'],'RELEASE')
    def test_committed_obstacle_holds(self):
        self.warm();self.f.update(self.sample(2.1,departure_observed=True,body_stopped=False))
        self.assertEqual(self.f.update(self.sample(2.2,path_clear=False))['motion_constraint']['mode'],'HOLD')
    def test_one_foot_out_resets(self):self.warm();self.f.update(self.sample(2.1,left_inside=False));self.assertFalse(self.f.update(self.sample(2.2))['depart_intent'])
    def test_body_motion_resets(self):self.warm();self.f.update(self.sample(2.1,body_stopped=False));self.assertFalse(self.f.update(self.sample(2.2))['depart_intent'])
    def test_camera_stale(self):self.warm();self.assertFalse(self.f.update(self.sample(2.1,signal_age_s=1.))['depart_intent'])
    def test_duplicate_resets(self):self.warm();self.assertFalse(self.f.update(self.sample(2.))['depart_intent'])
    def test_epoch_resets(self):self.warm();self.assertFalse(self.f.update(self.sample(2.1,epoch='new'))['depart_intent'])
    def test_gap_resets(self):self.warm();self.assertFalse(self.f.update(self.sample(3.))['depart_intent'])
    def test_wrong_signal(self):self.warm();self.assertEqual(self.f.update(self.sample(2.1,signal_id='opposite'))['reason'],'IDENTITY_MISMATCH')
    def test_no_approach_ack(self):self.assertEqual(self.f.update(self.sample(0.,approach_ack=False))['state'],'APPROACH')
    def test_proxy_rejected(self):
        for n in range(25):self.assertFalse(self.f.update(self.sample(n/10,feet_kind='PROXY'))['depart_intent'])
    def test_sim_gt_not_hardware(self):
        self.f.simulation=False
        for n in range(25):self.assertFalse(self.f.update(self.sample(n/10))['depart_intent'])
    def test_cancel_late_results(self):self.warm();self.f.update(self.sample(2.1,cancel=True));self.assertEqual(self.f.update(self.sample(2.2))['state'],'CANCELLED')
    def test_restart_requires_begin(self):self.f=StopGoFSM();self.assertFalse(self.f.update(self.sample(0.))['depart_intent'])
    def test_revisit_requires_new_dwell(self):self.warm();self.f.begin('vm-run','signal-step','crossing-1','visit-2','signal_01');self.assertFalse(self.f.update(self.sample(2.1,visit_id='visit-2'))['depart_intent'])
    def test_nan_rejected(self):self.warm();self.assertFalse(self.f.update(self.sample(2.1,observation_age_s=float('nan')))['depart_intent'])
    def test_minimum_cannot_reduce(self):
        with self.assertRaises(ValueError):StopGoFSM(minimum_stop_s=1.)

class DetectorTests(unittest.TestCase):
    def test_missing_weight(self):
        with self.assertRaises(FileNotFoundError):LocalUltralytics('/nonexistent.pt',expected_sha256='x')
    def test_refuse_pickle_before_import(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model.pt';p.write_bytes(b'untrusted')
            with self.assertRaisesRegex(ValueError,'untrusted pickle'):LocalUltralytics(p,expected_sha256=hashlib.sha256(b'untrusted').hexdigest())
    def test_wrong_direction_not_largest(self):
        a=Association();good=Detection((0,0,10,10),.8,0,'a');bad=Detection((30,0,100,80),.99,0,'b')
        self.assertEqual(a.select([bad,good],(0,0,10,10),'cross')[0],good)
    def test_ambiguous_no_selection(self):
        a=Association();d=Detection((0,0,10,10),.8,0,'a')
        self.assertIsNone(a.select([d,d],(0,0,10,10),'cross')[0])


class AdditionalAdversarial(unittest.TestCase):
    def test_bool_string_rejected(self):
        f=StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        self.assertEqual(f.update(StopInput(0.,0,left_inside='false'))['reason'],'INVALID_INPUT_TYPES')
    def test_visual_rectangle_candidate_not_qualified(self):
        from stop_zone import rectangle_candidates
        a=np.zeros((100,100,3),np.uint8);cv2.rectangle(a,(10,10),(90,90),(255,255,255),3)
        self.assertTrue(rectangle_candidates(a))
        self.assertEqual(rectangle_candidates(a)[0]['status'],'UNASSOCIATED_CANDIDATE')
    def test_feet_membership(self):
        from stop_zone import feet_membership
        p=[(0,0),(1,0),(1,1),(0,1)]
        self.assertTrue(feet_membership(p,[(0,.5),(.5,.5)],evidence_kind='SIM_GT')['both_inside'])
        self.assertFalse(feet_membership(p,[(2,.5),(.5,.5)],evidence_kind='VISUAL')['both_inside'])
    def test_unknown_feet(self):
        from stop_zone import feet_membership
        self.assertFalse(feet_membership([(0,0),(1,0),(1,1)], [None,(.5,.5)],evidence_kind='PROXY')['both_inside'])
    def test_inf_ttl_rejected(self):
        with self.assertRaises(ValueError):StopGoFSM(ttl_s=float('inf'))
    def test_long_hold_does_not_skip_no_green(self):
        f=StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        for n in range(250):
            v=StopInput(n/10,n,stable_state='RED',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True)
            self.assertFalse(f.update(v)['depart_intent'])

class ArenaBindingTest(unittest.TestCase):
    def test_wrong_zone_rejected(self):
        f=StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        self.assertEqual(f.update(StopInput(0.,0,zone_id='stop_zone_02'))['reason'],'IDENTITY_MISMATCH')
    def test_arena_ids_resolve(self):
        import json
        root=Path(__file__).resolve().parents[1]
        arena=root.parents[2]/'assets/competition-arena/revisions/rulebook-20261015/arena.semantic.json'
        if not arena.exists():self.skipTest('separate arena bundle not present')
        zones={z['id']:z for z in json.loads(arena.read_text())['semantic_zones']}
        for b in json.loads((root/'config/arena_bindings.json').read_text())['bindings']:
            self.assertEqual(zones[b['signal_id']]['type'],'TRAFFIC_SIGNAL')
            self.assertEqual(zones[b['zone_id']]['type'],'STOP_ZONE')

class ReviewRegressions(unittest.TestCase):
    def test_wrong_identity_interrupts_dwell(self):
        f=StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        for n in range(20):f.update(StopInput(n/10,n,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True))
        r=f.update(StopInput(1.95,21,run_id='other',signal_id='opposite'))
        self.assertEqual(r['motion_constraint']['run_id'],'vm-run')
        r=f.update(StopInput(2.,22,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True))
        self.assertFalse(r['depart_intent'])
    def test_new_epoch_sequence_reset_recover(self):
        f=StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        for n in range(21):f.update(StopInput(n/10,n+100,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True))
        for n in range(21):r=f.update(StopInput(2.1+n/10,n,epoch='new',stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True))
        self.assertTrue(r['depart_intent'])
        self.assertEqual(f.update(StopInput(4.2,500,epoch='epoch-1'))['reason'],'RETIRED_EPOCH')
    def test_filter_retired_epoch(self):
        f=TemporalFilter()
        f.update('GREEN',identity=('old','track'),sequence=0,source_stamp_ns='0',receipt_s=0.,source_age_s=0.)
        f.update('GREEN',identity=('new','track'),sequence=0,source_stamp_ns='0',receipt_s=.1,source_age_s=0.)
        self.assertEqual(f.update('GREEN',identity=('old','track'),sequence=99,source_stamp_ns='100',receipt_s=.2,source_age_s=0.),'UNKNOWN')
    def test_short_replay(self):
        from replay import run,fixture
        import tempfile
        with tempfile.TemporaryDirectory() as d:self.assertEqual(run(fixture()[:1],Path(d),True)['frames'],1)
    def test_empty_replay(self):
        from replay import run
        with self.assertRaisesRegex(ValueError,'empty'):run([],Path('/tmp/unused-empty-traffic'),False)

class LifecycleRegression(unittest.TestCase):
    def test_duplicate_begin_does_not_reset(self):
        f=StopGoFSM();key=('vm-run','signal-step','crossing-1','visit-1','signal_01')
        self.assertTrue(f.begin(*key));f.state='HOLD_2S';f.start=1.
        self.assertFalse(f.begin(*key));self.assertEqual(f.start,1.)
    def test_terminal_begin_requires_new_identity(self):
        for state in ('CANCELLED','CLEAR'):
            f=StopGoFSM();key=('vm-run','signal-step','crossing-1','visit-1','signal_01')
            f.begin(*key);f.state=state
            self.assertFalse(f.begin(*key));self.assertEqual(f.state,state)
            self.assertTrue(f.begin(*key,generation=1))
    def test_contradictory_departure_holds(self):
        f=StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01');f.state='DEPART_PENDING'
        r=f.update(StopInput(1.,1,stable_state='GREEN',departure_observed=True,body_stopped=True))
        self.assertEqual(r['reason'],'CONTRADICTORY_DEPARTURE_EVIDENCE');self.assertFalse(r['depart_intent'])

if __name__=='__main__':unittest.main()
