"""Independent black-box regressions for D0 reviewed boundary defects."""
import unittest
from dataclasses import replace
from experiments.competition_vm.traffic_signals.core import StopInput, TemporalFilter
from experiments.competition_vm.traffic_signals.lifecycle import TrafficLifecycle, ActionEvent
from experiments.competition_vm.integration.adapter import LifecycleConstraintAdapter

class IndependentReview(unittest.TestCase):
 def fresh(self):
  f=TrafficLifecycle('vm-run','signal-step','crossing-1','visit-1','signal_01',0,'stop_zone_01','approach',1)
  return f,LifecycleConstraintAdapter(f)
 def ev(self,kind,seq,t,**kw):
  return ActionEvent(kind,'vm-run','signal-step',kw.pop('goal_id','approach'),kw.pop('goal_generation',1),'actions',seq,t,**kw)
 def obs(self,t,n,**kw):
  return replace(StopInput(t,n,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True),**kw)
 def warm(self):
  f,a=self.fresh()
  assert f.accept_event(self.ev('APPROACH_TERMINAL',1,0,status='SUCCEEDED'),now=0)
  assert f.accept_event(self.ev('HOLD_ACK',2,.1,status='ACKNOWLEDGED',request_id=f.hold_request_id),now=.1)
  for n in range(21):a.observe(self.obs(.2+n*.1,n),now=.2+n*.1,pose_age_s=0)
  return f,a
 def ready(self):
  f,a=self.warm()
  assert f.request_exit('exit',2,2.21)
  assert f.accept_event(self.ev('EXIT_ACK',3,2.22,goal_id='exit',goal_generation=2,status='ACTIVE'),now=2.22)
  a.observe(self.obs(2.3,21),now=2.3,pose_age_s=0)
  return f,a
 def test_invalid_structure_cannot_revive_approach(self):
  f,a=self.fresh();a.observe(self.obs(0,0,path_clear='bad'),now=0,pose_age_s=0)
  self.assertEqual(a.observe(self.obs(.1,1),now=.1,pose_age_s=0)['motion_constraint']['mode'],'HOLD')
 def test_malformed_epoch_fails_closed(self):
  for epoch in ([],None,'',True):
   f,a=self.fresh()
   self.assertEqual(a.observe(self.obs(0,0,epoch=epoch),now=0,pose_age_s=0)['motion_constraint']['mode'],'HOLD')
 def test_composite_age_blocks_approach(self):
  f,a=self.fresh()
  self.assertEqual(a.observe(self.obs(0,0,observation_age_s=.2),now=.2,pose_age_s=0)['motion_constraint']['mode'],'HOLD')
 def test_stale_reset_cannot_replay_green(self):
  f=TemporalFilter(stability_s=.1)
  def u(n,t,age=0):return f.update('GREEN',identity=('e','sig'),sequence=n,source_stamp_ns=n+1,receipt_s=t,source_age_s=age)
  self.assertEqual(u(10,0),'UNKNOWN');self.assertEqual(u(11,.1),'GREEN');self.assertEqual(u(12,.2,1),'UNKNOWN')
  self.assertEqual(u(10,.3),'UNKNOWN');self.assertEqual(u(11,.4),'UNKNOWN')
 def test_event_transition_stops_without_next_sensor(self):
  f,a=self.fresh();a.observe(self.obs(0,0),now=0,pose_age_s=0)
  self.assertTrue(f.accept_event(self.ev('APPROACH_TERMINAL',1,.01,status='SUCCEEDED'),now=.01))
  out=a.apply(.2,0,1,receipt_s=.02,now=.02,sensor_fresh=True,tf_fresh=True,goal_id='approach',goal_generation=1)
  self.assertEqual(out[:2],(0,0))
 def test_expired_green_blocks_cached_release(self):
  f,a=self.ready();a.observe(self.obs(2.4,22,signal_age_s=.24),now=2.4,pose_age_s=0)
  out=a.apply(.2,0,1,receipt_s=2.42,now=2.42,sensor_fresh=True,tf_fresh=True,goal_id='exit',goal_generation=2)
  self.assertEqual(out[:2],(0,0))
 def test_expired_pose_blocks_cached_release(self):
  f,a=self.ready();a.observe(self.obs(2.4,22),now=2.4,pose_age_s=.24)
  out=a.apply(.2,0,1,receipt_s=2.42,now=2.42,sensor_fresh=True,tf_fresh=True,goal_id='exit',goal_generation=2)
  self.assertEqual(out[:2],(0,0))
 def test_motion_before_ack_does_not_commit(self):
  f,a=self.ready();r=a.observe(self.obs(2.4,22,observation_age_s=.2,body_stopped=False,departure_observed=True),now=2.4,pose_age_s=0,observed_goal_id='exit',observed_goal_generation=2)
  self.assertNotEqual(r['state'],'CROSSING_COMMITTED');self.assertEqual(r['motion_constraint']['mode'],'HOLD')
 def test_source_delay_not_credited_to_dwell(self):
  f,a=self.fresh();f.accept_event(self.ev('APPROACH_TERMINAL',1,0,status='SUCCEEDED'),now=0)
  f.accept_event(self.ev('HOLD_ACK',2,.1,status='ACKNOWLEDGED',request_id=f.hold_request_id),now=.1)
  for n in range(21):r=a.observe(self.obs(.2+n*.1,n,observation_age_s=n*.01),now=.2+n*.1,pose_age_s=0)
  self.assertFalse(r['exit_goal_required']);self.assertLess(r['observed_stop_lower_bound_s'],2)
 def test_release_without_movement_not_commit(self):
  f,a=self.ready();self.assertEqual(f.core.state,'DEPART_PENDING')
 def test_red_after_bound_movement_not_signal_stop(self):
  f,a=self.ready();r=a.observe(self.obs(2.4,22,body_stopped=False,departure_observed=True),now=2.4,pose_age_s=0,observed_goal_id='exit',observed_goal_generation=2)
  self.assertEqual(r['state'],'CROSSING_COMMITTED')
  r=a.observe(self.obs(2.5,23,stable_state='RED',body_stopped=False),now=2.5,pose_age_s=0)
  self.assertEqual(r['motion_constraint']['mode'],'RELEASE')
  out=a.apply(.2,0,1,receipt_s=2.5,now=2.5,sensor_fresh=True,tf_fresh=True,collision=True,goal_id='exit',goal_generation=2)
  self.assertEqual(out[:2],(0,0))
if __name__=='__main__':unittest.main(verbosity=2)
