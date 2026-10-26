"""D0 receiver-local boundary tests; synthetic values are not native ACKs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from adapter import ConstraintAdapter


def release():
    return dict(owner_id='traffic_vm', run_id='r',step_id='s',generation=1,
                request_id='req',mode='RELEASE',max_vx=None,max_vy=None,max_wz=None,
                validity={'receipt_ttl_s':.25})

class TransportTests(unittest.TestCase):
    def setUp(self): self.a=ConstraintAdapter('r','s',1)
    def ingest(self,n=1,t=10.,**kw):
        return self.a.ingest(release(),sequence=n,receipt_s=t,now=kw.pop('now',t),**kw)
    def move(self,n=1,t=10.,**kw):
        return self.a.apply(.25,0.,n,receipt_s=t,now=t,sensor_fresh=True,tf_fresh=True,**kw)
    def test_receiver_ttl_exact_boundary(self):
        self.assertTrue(self.ingest());self.assertEqual(self.move(t=10.25)[2],'FOLLOWING')
    def test_receiver_ttl_after_boundary(self):
        self.assertTrue(self.ingest());self.assertEqual(self.move(t=10.250001)[2],'SIGNAL_HOLD')
    def test_source_age_exact_boundary(self):
        self.assertTrue(self.ingest(source_age_s=.25));self.assertEqual(self.move()[2],'FOLLOWING')
    def test_source_age_plus_transit_not_separate_loophole(self):
        self.assertFalse(self.ingest(source_age_s=.2,now=10.1))
    def test_source_age_expires_while_receiver_ttl_remains(self):
        self.assertTrue(self.ingest(source_age_s=.2));self.assertEqual(self.move(t=10.06)[2],'SIGNAL_HOLD')
    def test_bad_source_age_revokes_old_release(self):
        for age in (-1,float('nan'),float('inf'),True,.250001):
            self.setUp();self.assertTrue(self.ingest());self.assertFalse(self.ingest(2,source_age_s=age));self.assertEqual(self.move()[:2],(0.,0.))
    def test_producer_duplicate_rejected_despite_new_receiver_sequence(self):
        self.assertTrue(self.ingest(source_sequence=7));self.assertFalse(self.ingest(2,source_sequence=7));self.assertEqual(self.move()[:2],(0.,0.))
    def test_producer_out_of_order_stamp(self):
        self.assertTrue(self.ingest(source_stamp_ns=100));self.assertFalse(self.ingest(2,source_stamp_ns=99))
    def test_source_stamp_never_subtracted_from_receiver_clock(self):
        self.assertTrue(self.ingest(source_stamp_ns=987654321000000000,source_age_s=.01));self.assertEqual(self.move()[2],'FOLLOWING')
    def test_epoch_restart_closes_current_generation(self):
        self.assertTrue(self.ingest(producer_epoch='old'));self.assertFalse(self.ingest(2,producer_epoch='new'))
        self.assertTrue(self.a.closed);self.assertFalse(self.ingest(3,producer_epoch='old'));self.assertEqual(self.move()[:2],(0.,0.))
    def test_explicit_cancel_never_revived(self):
        self.assertTrue(self.ingest());self.a.close();self.assertFalse(self.ingest(2));self.assertEqual(self.move()[:2],(0.,0.))
    def test_goal_identity_barrier(self):
        self.assertTrue(self.a.bind_goal('approach',4));self.assertTrue(self.ingest())
        self.assertEqual(self.move(goal_id='wrong',goal_generation=4)[:2],(0.,0.))
        self.assertEqual(self.move(2,goal_id='approach',goal_generation=4)[2],'FOLLOWING')
        self.assertTrue(self.a.bind_goal('exit',5));self.assertEqual(self.move(3,goal_id='exit',goal_generation=5)[:2],(0.,0.))
        self.assertTrue(self.ingest(2,t=10.1));self.assertEqual(self.move(4,10.1,goal_id='approach',goal_generation=4)[:2],(0.,0.))
        self.assertEqual(self.move(5,10.1,goal_id='exit',goal_generation=5)[2],'FOLLOWING')
    def test_no_old_goal_rebind(self):
        self.a.bind_goal('approach',4);self.a.bind_goal('exit',5)
        self.assertFalse(self.a.bind_goal('approach',4));self.assertFalse(self.a.bind_goal('another',5))
    def test_wrong_session_and_generation_envelope(self):
        for key,value in [('run_id','old'),('step_id','old'),('generation',2)]:
            self.setUp();self.ingest();c=release();c[key]=value
            self.assertFalse(self.a.ingest(c,sequence=2,receipt_s=10.,now=10.));self.assertEqual(self.move()[:2],(0.,0.))
    def test_receiver_future_and_backwards(self):
        self.assertFalse(self.ingest(now=9.9));self.assertTrue(self.ingest());self.assertFalse(self.ingest(2,t=9.9))
    def test_old_held_command_not_reused_after_fresh_release(self):
        self.a.bind_goal('exit',5)
        self.assertEqual(self.move(1,goal_id='exit',goal_generation=5)[:2],(0.,0.))
        self.assertTrue(self.ingest());self.assertEqual(self.move(1,goal_id='exit',goal_generation=5)[:2],(0.,0.))
        self.assertEqual(self.move(2,goal_id='exit',goal_generation=5)[2],'FOLLOWING')

if __name__=='__main__': unittest.main(verbosity=2)
