import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from copy import deepcopy
from adapter import ConstraintAdapter,traffic

def output(state):
    f=traffic.StopGoFSM()
    f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
    for n in range(21):
        result=f.update(traffic.StopInput(receipt_s=n/10,sequence=n,stable_state=state,
                        left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True))
    return result['motion_constraint']

class IntegrationTests(unittest.TestCase):
    def setUp(self):self.a=ConstraintAdapter('vm-run','signal-step',0)
    def ingest(self,c,seq=1,t=2.):return self.a.ingest(c,sequence=seq,receipt_s=t,now=t)
    def move(self,seq=1,t=2.,**kw):
        return self.a.apply(.25,.1,seq,receipt_s=kw.pop('receipt_s',t),now=t,sensor_fresh=True,tf_fresh=True,**kw)
    def test_missing_constraint_holds(self):self.assertEqual(self.move()[:2],(0,0))
    def test_red_clearpath_hold(self):
        self.assertTrue(self.ingest(output('RED')));self.assertEqual(self.move(),(0,0,'SIGNAL_HOLD'))
    def test_unknown_clearpath_hold(self):
        self.assertTrue(self.ingest(output('UNKNOWN')));self.assertEqual(self.move(),(0,0,'SIGNAL_HOLD'))
    def test_release_never_replays_held_command(self):
        self.ingest(output('RED'));self.assertEqual(self.move()[:2],(0,0))
        self.ingest(output('GREEN'),2,2.1)
        self.assertEqual(self.move(t=2.1)[:2],(0,0))
        self.assertEqual(self.move(2,2.1),(.25,.1,'FOLLOWING'))
    def test_release_rejects_pre_release_command_even_new_seq(self):
        self.ingest(output('GREEN'),1,2.1)
        self.assertEqual(self.move(9,2.1,receipt_s=2.)[:2],(0,0))
    def test_expired_release(self):
        self.ingest(output('GREEN'));self.assertEqual(self.move(t=2.3)[:2],(0,0))
    def test_previous_generation_cancel_rejected(self):
        self.ingest(output('GREEN'))
        late=output('RED');late['generation']=-1;late['reason']='CANCELLED'
        self.assertFalse(self.ingest(late,2,2.1));self.assertEqual(self.move(1,2.1)[:2],(0,0))
    def test_wrong_session_release_rejected(self):
        for key,value in [('run_id','old'),('step_id','old'),('generation',1),('owner_id','unknown')]:
            c=output('GREEN');c[key]=value;self.assertFalse(self.ingest(c))
            self.assertEqual(self.move(1)[:2],(0,0))
    def test_invalid_ttl_failclosed(self):
        for ttl in (float('nan'),float('inf'),-1,0,100,True):
            c=output('GREEN');c['validity']['receipt_ttl_s']=ttl
            self.assertFalse(self.ingest(c));self.assertEqual(self.move()[:2],(0,0))
    def test_duplicate_release_invalidates(self):
        c=output('GREEN');self.assertTrue(self.ingest(c));self.assertFalse(self.ingest(c))
        self.assertEqual(self.move()[:2],(0,0))
    def test_multiple_holds_precedence(self):
        self.a=ConstraintAdapter('vm-run','signal-step',0,owners=('traffic_vm','safety_vm'))
        self.ingest(output('GREEN'));self.assertEqual(self.move()[:2],(0,0))
        c=output('RED');c['owner_id']='safety_vm';self.ingest(c)
        self.assertEqual(self.move(2)[:2],(0,0))
        c=output('GREEN');c['owner_id']='safety_vm';self.ingest(c,2)
        self.assertEqual(self.move(3)[2],'FOLLOWING')
    def test_safety_precedes_release(self):
        self.ingest(output('GREEN'));self.assertEqual(self.move(estop=True)[2],'ESTOP')
        self.assertEqual(self.move(2,collision=True)[2],'COLLISION')
    def test_clock_rollback_holds(self):
        self.ingest(output('GREEN'));self.assertEqual(self.move(t=1.9)[:2],(0,0))
    def test_stale_command_not_replayed_later(self):
        self.ingest(output('GREEN'))
        self.assertEqual(self.move(7,receipt_s=1.)[:2],(0,0))
        self.assertEqual(self.move(7)[:2],(0,0))
    def test_no_implicit_caps_or_unknown_modes(self):
        for mode in ('LIMIT_SPEED','go',None):
            c=output('GREEN');c['mode']=mode;self.assertFalse(self.ingest(c))
    def test_zero_caps_required_for_hold(self):
        c=output('RED');c['max_vx']=.1;self.assertFalse(self.ingest(c))

if __name__=='__main__':unittest.main(verbosity=2)
