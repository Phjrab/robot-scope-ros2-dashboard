import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
import unittest
from experiments.competition_vm.integration.d0_smoke import run
from experiments.competition_vm.integration.adapter import LifecycleConstraintAdapter,ConstraintAdapter
from experiments.competition_vm.traffic_signals.lifecycle import TrafficLifecycle,ActionEvent
from experiments.competition_vm.traffic_signals.core import StopInput,StopGoFSM

class LifecycleIntegrationTests(unittest.TestCase):
    def make(self):
        f=TrafficLifecycle('vm-run','signal-step','crossing-1','visit-1','signal_01',0,'stop_zone_01','approach',1)
        return f,LifecycleConstraintAdapter(f)
    def test_full_actual_module_trace(self):
        rows=run();self.assertEqual(len(rows),38);self.assertEqual(rows[-1]['fsm_state'],'CLEAR')
    def test_before_deadlock_and_after_approach(self):
        old=StopGoFSM();old.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        i=StopInput(receipt_s=0.,sequence=1)
        c=old.update(i)['motion_constraint'];a=ConstraintAdapter('vm-run','signal-step',0)
        self.assertEqual(c['mode'],'HOLD');a.ingest(c,sequence=1,receipt_s=0.,now=0.)
        self.assertEqual(a.apply(.25,0,1,receipt_s=0.,now=0.,sensor_fresh=True,tf_fresh=True)[2],'SIGNAL_HOLD')
        f,b=self.make();self.assertEqual(b.observe(i,now=0.,pose_age_s=0.)['motion_constraint']['mode'],'RELEASE')
        self.assertEqual(b.apply(.25,0,1,receipt_s=0.,now=0.,sensor_fresh=True,tf_fresh=True,goal_id='approach',goal_generation=1)[2],'FOLLOWING')
    def test_approach_does_not_disable_collision_or_estop(self):
        for gate in ('collision','estop'):
            f,b=self.make();b.observe(StopInput(receipt_s=0.,sequence=1),now=0.,pose_age_s=0.)
            out=b.apply(.25,0,1,receipt_s=0.,now=0.,sensor_fresh=True,tf_fresh=True,
                        goal_id='approach',goal_generation=1,**{gate:True})
            self.assertEqual(out[:2],(0.,0.));self.assertEqual(out[2],gate.upper())
    def test_false_terminal_does_not_create_hold_ack(self):
        f,b=self.make();self.assertFalse(f.accept_event(ActionEvent('APPROACH_TERMINAL','vm-run','signal-step','approach',1,'a',1,0.,status='CANCELED'),now=0.))
        r=b.observe(StopInput(receipt_s=.1,sequence=1),now=.1,pose_age_s=0.)
        self.assertEqual(r['motion_constraint']['mode'],'HOLD');self.assertFalse(f.hold_ack)
    def test_cancel_closes_adapter(self):
        f,b=self.make();r=b.observe(StopInput(receipt_s=0.,sequence=1,cancel=True),now=0.,pose_age_s=0.)
        self.assertTrue(b.adapter.closed);self.assertEqual(r['motion_constraint']['mode'],'HOLD')
    def test_repeated_source_observation_never_restamped_fresh(self):
        f,b=self.make();i=StopInput(receipt_s=0.,sequence=1)
        b.observe(i,now=0.,pose_age_s=0.);r=b.observe(i,now=.1,pose_age_s=0.)
        self.assertEqual(r['motion_constraint']['mode'],'HOLD')
        self.assertEqual(b.apply(.25,0,1,receipt_s=.1,now=.1,sensor_fresh=True,tf_fresh=True,
            goal_id='approach',goal_generation=1)[:2],(0.,0.))
    def test_wrong_goal_command_never_accepted_on_approach(self):
        f,b=self.make();b.observe(StopInput(receipt_s=0.,sequence=1),now=0.,pose_age_s=0.)
        self.assertEqual(b.apply(.25,0,1,receipt_s=0.,now=0.,sensor_fresh=True,tf_fresh=True,
            goal_id='exit',goal_generation=2)[:2],(0.,0.))
    def test_terminal_event_blocks_without_observation_tick(self):
        f,b=self.make();b.observe(StopInput(receipt_s=0.,sequence=0),now=0.,pose_age_s=0.)
        self.assertTrue(f.accept_event(ActionEvent('APPROACH_TERMINAL','vm-run','signal-step','approach',1,'a',1,.1,status='SUCCEEDED'),now=.1))
        self.assertEqual(b.apply(.25,0,1,receipt_s=.1,now=.1,sensor_fresh=True,tf_fresh=True,goal_id='approach',goal_generation=1)[:2],(0.,0.))
    def test_invalid_event_blocks_without_observation_tick(self):
        f,b=self.make();b.observe(StopInput(receipt_s=0.,sequence=0),now=0.,pose_age_s=0.)
        self.assertFalse(f.accept_event(ActionEvent('APPROACH_TERMINAL','wrong','signal-step','approach',1,'a',1,.1,status='SUCCEEDED'),now=.1))
        self.assertEqual(b.apply(.25,0,1,receipt_s=.1,now=.1,sensor_fresh=True,tf_fresh=True,goal_id='approach',goal_generation=1)[:2],(0.,0.))
    def ready(self):
        f,b=self.make()
        b.observe(StopInput(receipt_s=0.,sequence=0),now=0.,pose_age_s=0.)
        self.assertTrue(f.accept_event(ActionEvent('APPROACH_TERMINAL','vm-run','signal-step','approach',1,'a',1,.1,status='SUCCEEDED'),now=.1))
        self.assertTrue(f.accept_event(ActionEvent('HOLD_ACK','vm-run','signal-step','approach',1,'a',2,.2,status='ACKNOWLEDGED',request_id=f.hold_request_id),now=.2))
        for n in range(2,25):
            t=n/10
            b.observe(StopInput(receipt_s=t,sequence=n,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True),now=t,pose_age_s=0.)
        self.assertTrue(f.request_exit('exit',2,now=2.41))
        self.assertTrue(f.accept_event(ActionEvent('EXIT_ACK','vm-run','signal-step','exit',2,'a',3,2.42,status='ACTIVE'),now=2.42))
        return f,b
    def test_retained_release_expires_with_green_or_pose(self):
        for key in ('green','pose'):
            f,b=self.ready()
            r=b.observe(StopInput(receipt_s=2.5,sequence=25,stable_state='GREEN',signal_age_s=.24 if key=='green' else 0.,
                left_inside=True,right_inside=True,visual_zone=True,body_stopped=True),now=2.5,pose_age_s=.24 if key=='pose' else 0.)
            self.assertEqual(r['motion_constraint']['mode'],'RELEASE')
            self.assertEqual(b.apply(.25,0,30,receipt_s=2.505,now=2.505,sensor_fresh=True,tf_fresh=True,goal_id='exit',goal_generation=2)[2],'FOLLOWING')
            self.assertEqual(b.apply(.25,0,31,receipt_s=2.52,now=2.52,sensor_fresh=True,tf_fresh=True,goal_id='exit',goal_generation=2)[2],'SIGNAL_HOLD')
    def test_committed_red_ignores_signal_age_not_pose_age(self):
        f,b=self.ready()
        r=b.observe(StopInput(receipt_s=2.5,sequence=25,stable_state='GREEN',body_stopped=False,departure_observed=True),now=2.5,pose_age_s=0.,observed_goal_id='exit',observed_goal_generation=2)
        self.assertEqual(r['state'],'CROSSING_COMMITTED')
        r=b.observe(StopInput(receipt_s=2.6,sequence=26,stable_state='RED',signal_age_s=100.,body_stopped=False),now=2.6,pose_age_s=.24)
        self.assertEqual(r['motion_constraint']['mode'],'RELEASE')
        self.assertEqual(b.apply(.25,0,30,receipt_s=2.605,now=2.605,sensor_fresh=True,tf_fresh=True,goal_id='exit',goal_generation=2)[2],'FOLLOWING')
        self.assertEqual(b.apply(.25,0,31,receipt_s=2.62,now=2.62,sensor_fresh=True,tf_fresh=True,goal_id='exit',goal_generation=2)[2],'SIGNAL_HOLD')
    def test_invalid_observation_fails_closed_without_exception(self):
        f,b=self.make();self.assertEqual(b.observe(None,now=0.,pose_age_s=0.)['motion_constraint']['mode'],'HOLD')

if __name__=='__main__':unittest.main(verbosity=2)
