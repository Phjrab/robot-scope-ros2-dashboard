"""Explicit synthetic action-event fixtures; no ACK is inferred from a command."""
import unittest
from dataclasses import replace
from experiments.competition_vm.traffic_signals.core import StopInput, StopGoFSM, TemporalFilter
from experiments.competition_vm.traffic_signals.lifecycle import TrafficLifecycle, ActionEvent

class LifecycleD0Tests(unittest.TestCase):
    def setUp(self):
        self.f=TrafficLifecycle('vm-run','signal-step','crossing-1','visit-1','signal_01',0,'stop_zone_01','approach',1)
        self.seq=0;self.event_seq=0
    def obs(self,t,**kw):
        self.seq+=1
        i=StopInput(t,self.seq,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True)
        return self.f.observe(replace(i,**kw),now=t,pose_age_s=0.)
    def event(self,kind,t,**kw):
        self.event_seq+=1
        e=ActionEvent(kind,'vm-run','signal-step','approach',1,'actions-1',self.event_seq,t)
        return replace(e,**kw)
    def terminal(self,t=0.,**kw):
        return self.f.accept_event(self.event('APPROACH_TERMINAL',t,status='SUCCEEDED',**kw),now=t)
    def hold(self,t=.1,**kw):
        return self.f.accept_event(self.event('HOLD_ACK',t,status='ACKNOWLEDGED',request_id=self.f.hold_request_id,**kw),now=t)
    def warm(self):
        self.assertTrue(self.terminal());self.assertTrue(self.hold())
        for n in range(21):r=self.obs(.2+n*.1)
        return r
    def ready(self):
        r=self.warm();self.assertTrue(r['exit_goal_required'])
        self.assertTrue(self.f.request_exit('exit-1',2,2.21))
        self.assertTrue(self.f.accept_event(self.event('EXIT_ACK',2.22,goal_id='exit-1',goal_generation=2,status='ACTIVE'),now=2.22))
        return self.obs(2.3)
    def depart(self):
        self.ready();self.seq+=1
        return self.f.observe(StopInput(2.4,self.seq,stable_state='GREEN',body_stopped=False,departure_observed=True),now=2.4,pose_age_s=0.,observed_goal_id='exit-1',observed_goal_generation=2)
    def test_actual_old_approach_self_hold_reproduced(self):
        old=StopGoFSM();old.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
        self.assertEqual(old.update(StopInput(0.,0))['motion_constraint']['mode'],'HOLD')
        self.assertEqual(self.obs(0.,body_stopped=False)['motion_constraint']['mode'],'RELEASE')
    def test_approach_safety_still_holds(self):
        for field in ('safety_stop','path_clear','localization_ready'):
            self.setUp();kw={field:field=='safety_stop'}
            self.assertEqual(self.obs(0.,**kw)['motion_constraint']['mode'],'HOLD')
    def test_terminal_then_hold_ack_not_inferred(self):
        self.assertTrue(self.terminal())
        self.assertEqual(self.obs(.1)['reason'],'WAIT_MATCHING_HOLD_ACK')
        for n in range(2,30):self.assertFalse(self.obs(n/10)['depart_intent'])
    def test_canceled_without_ack_no_transition(self):
        self.assertFalse(self.f.accept_event(self.event('APPROACH_TERMINAL',0.,status='CANCELED'),now=0.))
        self.assertEqual(self.f.phase,'APPROACH_CANCEL_PENDING')
    def test_canceled_ack_transition(self):
        self.assertTrue(self.f.accept_event(self.event('APPROACH_TERMINAL',0.,status='CANCELED',cancel_ack=True),now=0.))
        self.assertEqual(self.f.phase,'HOLD_ACK_PENDING')
    def test_wrong_approach_goal(self):self.assertFalse(self.terminal(goal_id='old'))
    def test_wrong_approach_generation(self):self.assertFalse(self.terminal(goal_generation=0))
    def test_wrong_run(self):self.assertFalse(self.terminal(run_id='other'))
    def test_wrong_step(self):self.assertFalse(self.terminal(step_id='other'))
    def test_hold_ack_wrong_request(self):
        self.terminal();e=self.event('HOLD_ACK',.1,status='ACKNOWLEDGED',request_id='wrong')
        self.assertFalse(self.f.accept_event(e,now=.1));self.assertFalse(self.f.hold_ack)
    def test_hold_ack_before_request(self):
        self.terminal();self.assertFalse(self.hold(0.))
    def test_hold_ack_delay_expired(self):
        self.terminal();e=self.event('HOLD_ACK',.1,status='ACKNOWLEDGED',request_id=self.f.hold_request_id)
        self.assertFalse(self.f.accept_event(e,now=.350001))
    def test_hold_ack_exact_ttl_boundary(self):
        self.terminal();e=self.event('HOLD_ACK',.1,status='ACKNOWLEDGED',request_id=self.f.hold_request_id)
        self.assertTrue(self.f.accept_event(e,now=.35))
    def test_duplicate_event_rejected(self):
        e=self.event('APPROACH_TERMINAL',0.,status='SUCCEEDED')
        self.assertTrue(self.f.accept_event(e,now=0.));self.assertFalse(self.f.accept_event(e,now=.1))
    def test_action_epoch_restart_requires_new_session(self):
        self.terminal();e=self.event('HOLD_ACK',.1,epoch='restarted',status='ACKNOWLEDGED',request_id=self.f.hold_request_id)
        self.assertFalse(self.f.accept_event(e,now=.1));self.assertTrue(self.f.closed)
    def test_two_seconds_before_after(self):
        self.terminal();self.hold()
        for n in range(20):self.assertFalse(self.obs(.2+n*.1)['exit_goal_required'])
        self.assertTrue(self.obs(2.2)['exit_goal_required'])
    def test_hold_ack_is_not_physical_stop(self):
        self.terminal();self.hold()
        for n in range(30):self.assertFalse(self.obs(.2+n*.1,body_stopped=False)['exit_goal_required'])
    def test_feet_both_required(self):
        self.terminal();self.hold()
        for n in range(30):self.assertFalse(self.obs(.2+n*.1,left_inside=False)['exit_goal_required'])
    def test_receiver_ttl_not_extended_to_gap(self):
        self.warm();self.seq+=1;i=StopInput(2.3,self.seq)
        r=self.f.observe(i,now=2.550001,pose_age_s=0.)
        self.assertEqual(r['reason'],'RECEIPT_OR_POSE_EXPIRED')
    def test_continuity_gap_distinct_from_ttl(self):
        self.terminal();self.hold()
        self.obs(.2)
        # Fresh each time, .4s observation interval allowed by .5s gap despite .25s TTL.
        for t in (.6,1.,1.4,1.8):self.assertFalse(self.obs(t)['exit_goal_required'])
        self.assertTrue(self.obs(2.2)['exit_goal_required'])
    def test_gap_over_half_second_resets(self):
        self.warm();self.assertFalse(self.obs(2.700001)['exit_goal_required'])
    def test_gap_at_half_second_retains(self):
        self.warm();self.assertTrue(self.obs(2.7)['exit_goal_required'])
    def test_source_age_still_quarter_second(self):
        self.warm();self.assertFalse(self.obs(2.3,observation_age_s=.250001)['exit_goal_required'])
    def test_pose_age_required(self):
        self.seq+=1;r=self.f.observe(StopInput(0.,self.seq),now=0.)
        self.assertEqual(r['motion_constraint']['mode'],'HOLD')
    def test_no_exit_ack_no_release(self):self.assertEqual(self.warm()['motion_constraint']['mode'],'HOLD')
    def test_new_exit_generation_required(self):
        self.warm();self.assertFalse(self.f.request_exit('exit',1,2.21))
    def test_old_goal_id_rejected(self):
        self.warm();self.assertFalse(self.f.request_exit('approach',2,2.21))
    def test_release_not_departure_latch(self):
        self.assertEqual(self.ready()['motion_constraint']['mode'],'RELEASE')
        self.assertEqual(self.f.core.state,'DEPART_PENDING')
    def test_exit_ack_wrong_goal(self):
        self.warm();self.f.request_exit('exit-1',2,2.21)
        self.assertFalse(self.f.accept_event(self.event('EXIT_ACK',2.22,goal_id='other',goal_generation=2,status='ACTIVE'),now=2.22))
    def test_departure_requires_goal_binding(self):
        self.ready();r=self.obs(2.4,body_stopped=False,departure_observed=True)
        self.assertEqual(r['reason'],'UNBOUND_DEPARTURE_EVIDENCE')
        self.assertNotEqual(self.f.core.state,'CROSSING_COMMITTED')
    def test_observed_departure_latches_then_red_permitted(self):
        self.assertEqual(self.depart()['state'],'CROSSING_COMMITTED')
        self.assertEqual(self.obs(2.5,stable_state='RED',body_stopped=False)['motion_constraint']['mode'],'RELEASE')
    def test_committed_collision_still_holds(self):
        self.depart();self.assertEqual(self.obs(2.5,path_clear=False)['motion_constraint']['mode'],'HOLD')
    def test_before_departure_red_revokes_exit(self):
        self.ready();self.assertEqual(self.obs(2.4,stable_state='RED')['motion_constraint']['mode'],'HOLD')
        self.assertIsNone(self.f.exit_goal)
    def test_before_departure_unknown_revokes_exit(self):
        self.ready();self.assertEqual(self.obs(2.4,stable_state='UNKNOWN')['motion_constraint']['mode'],'HOLD')
    def test_before_departure_stale_green_revokes_exit(self):
        self.ready();self.assertEqual(self.obs(2.4,signal_age_s=.250001)['motion_constraint']['mode'],'HOLD')
    def test_before_departure_wrong_signal_revokes_exit(self):
        self.ready();self.assertEqual(self.obs(2.4,signal_id='other')['motion_constraint']['mode'],'HOLD')
    def test_duplicate_observation_resets(self):
        self.warm();self.seq-=1;self.assertFalse(self.obs(2.3)['exit_goal_required'])
    def test_retired_sensor_epoch_rejected(self):
        self.obs(0.,epoch='old');self.obs(.1,epoch='new')
        self.assertEqual(self.obs(.2,epoch='old')['reason'],'SESSION_CLOSED')
    def test_receiver_restart_no_implicit_resume(self):
        self.warm();self.setUp();self.assertFalse(self.obs(0.)['exit_goal_required'])
    def test_clock_rollback_closes_session(self):
        self.obs(1.);self.assertEqual(self.obs(.9)['reason'],'SESSION_CLOSED')
    def test_input_cancel_is_terminal(self):
        self.obs(0.,cancel=True);self.assertEqual(self.obs(.1)['reason'],'SESSION_CLOSED')
    def test_simulated_feet_do_not_validate_hardware(self):
        self.f.core.simulation=False;self.assertFalse(self.warm()['exit_goal_required'])

class ReviewD0Tests(LifecycleD0Tests):
    # Inherit helpers only; suppress inherited test discovery below.
    def test_event_composite_source_age(self):
        e=self.event('APPROACH_TERMINAL',0.,source_age_s=.2,status='SUCCEEDED')
        self.assertFalse(self.f.accept_event(e,now=.1))
    def test_observation_composite_source_age(self):
        i=StopInput(0.,0,observation_age_s=.2)
        r=self.f.observe(i,now=.1,pose_age_s=0.)
        self.assertEqual(r['motion_constraint']['mode'],'HOLD')
    def test_pose_composite_source_age(self):
        r=self.f.observe(StopInput(0.,0),now=.1,pose_age_s=.2)
        self.assertEqual(r['reason'],'RECEIPT_OR_POSE_EXPIRED')
    def test_signal_composite_source_age(self):
        self.warm();self.seq+=1
        i=StopInput(2.3,self.seq,signal_age_s=.2,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True)
        r=self.f.observe(i,now=2.4,pose_age_s=0.)
        self.assertFalse(r['exit_goal_required'])
    def test_fault_revokes_cached_exit_eligibility(self):
        self.warm()
        self.assertFalse(self.f.accept_event(self.event('HOLD_ACK',2.21,status='ACKNOWLEDGED',request_id='wrong'),now=2.21))
        self.assertFalse(self.f.request_exit('exit-1',2,2.22))
    def test_invalid_type_cannot_revive_approach(self):
        self.assertEqual(self.obs(0.,left_inside='false')['motion_constraint']['mode'],'HOLD')
        self.assertEqual(self.obs(.1)['reason'],'SESSION_CLOSED')
    def test_cancel_pending_cannot_resume_approach(self):
        self.f.accept_event(self.event('APPROACH_TERMINAL',0.,status='CANCELED'),now=0.)
        self.assertEqual(self.obs(.1)['motion_constraint']['mode'],'HOLD')
        self.assertEqual(self.obs(.2)['motion_constraint']['mode'],'HOLD')
        self.assertTrue(self.f.accept_event(self.event('APPROACH_TERMINAL',.3,status='CANCELED',cancel_ack=True),now=.3))
        self.assertEqual(self.f.phase,'HOLD_ACK_PENDING')
    def test_exit_request_effective_signal_expiry(self):
        self.warm();self.obs(2.3,signal_age_s=.2)
        self.assertFalse(self.f.request_exit('exit-1',2,2.4))
    def test_exit_request_effective_pose_expiry(self):
        self.warm();self.seq+=1
        i=StopInput(2.3,self.seq,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True)
        self.f.observe(i,now=2.3,pose_age_s=.2)
        self.assertFalse(self.f.request_exit('exit-1',2,2.4))
    def test_crossing_clear_requires_exit_goal_binding(self):
        self.depart()
        r=self.obs(2.5,fully_crossed=True,body_stopped=False)
        self.assertEqual(r['motion_constraint']['mode'],'HOLD')
        self.assertNotEqual(self.f.core.state,'CLEAR')
    def test_crossing_clear_bound_goal(self):
        self.depart();self.seq+=1
        i=StopInput(2.5,self.seq,fully_crossed=True,body_stopped=False)
        r=self.f.observe(i,now=2.5,pose_age_s=0.,observed_goal_id='exit-1',observed_goal_generation=2)
        self.assertEqual(r['state'],'CLEAR')
    def test_observation_restart_requires_new_session(self):
        self.warm()
        self.assertEqual(self.obs(2.3,epoch='restart')['reason'],'OBSERVATION_RESTART_REQUIRES_NEW_SESSION')
        self.assertEqual(self.obs(2.4)['reason'],'SESSION_CLOSED')
    def test_variable_source_age_cannot_credit_two_seconds(self):
        self.terminal();self.hold()
        for n in range(21):
            r=self.obs(.2+n*.1,observation_age_s=n*.01)
        self.assertFalse(r['exit_goal_required'])
        self.assertAlmostEqual(r['observed_stop_lower_bound_s'],1.8)
        for n in range(1,4):r=self.obs(2.2+n*.1,observation_age_s=.2)
        self.assertTrue(r['exit_goal_required'])
    def test_supported_source_time_regression_resets_dwell(self):
        self.terminal();self.hold();self.obs(.2);self.obs(.3)
        r=self.obs(.4,observation_age_s=.2)
        self.assertEqual(r['reason'],'SOURCE_STOP_SEQUENCE_OR_GAP_INVALID')
        self.assertEqual(r['observed_stop_lower_bound_s'],0.)
    def test_receiver_residence_never_counts_as_observed_stop(self):
        self.terminal();self.hold()
        for n in range(20):self.obs(.2+n*.1)
        self.seq+=1
        i=StopInput(2.15,self.seq,stable_state='GREEN',left_inside=True,right_inside=True,visual_zone=True,body_stopped=True)
        r=self.f.observe(i,now=2.3,pose_age_s=0.)
        self.assertFalse(r['exit_goal_required'])
        self.assertAlmostEqual(r['observed_stop_lower_bound_s'],1.95)
    def test_delayed_hold_ack_acquired_before_request_rejected(self):
        self.terminal(.1)
        e=self.event('HOLD_ACK',.2,status='ACKNOWLEDGED',request_id=self.f.hold_request_id,source_age_s=.15)
        self.assertFalse(self.f.accept_event(e,now=.2))
    def test_delayed_exit_ack_acquired_before_request_rejected(self):
        self.warm();self.f.request_exit('exit-1',2,2.21)
        e=self.event('EXIT_ACK',2.3,goal_id='exit-1',goal_generation=2,status='ACTIVE',source_age_s=.2)
        self.assertFalse(self.f.accept_event(e,now=2.3))
    def test_pre_ack_movement_cannot_latch(self):
        self.ready();self.seq+=1
        i=StopInput(2.4,self.seq,stable_state='GREEN',body_stopped=False,departure_observed=True,observation_age_s=.2)
        r=self.f.observe(i,now=2.4,pose_age_s=0.,observed_goal_id='exit-1',observed_goal_generation=2)
        self.assertEqual(r['reason'],'UNBOUND_DEPARTURE_EVIDENCE')
        self.assertNotEqual(r['state'],'CROSSING_COMMITTED')
    def test_stop_observation_acquired_before_hold_ack_rejected(self):
        self.terminal();self.hold()
        r=self.obs(.2,observation_age_s=.15)
        self.assertEqual(r['reason'],'STOP_OBSERVATION_PRECEDES_HOLD_ACK')
    def test_replaced_legacy_bool_cannot_hide_invalid_type(self):
        self.assertEqual(self.obs(0.,departure_observed='false')['reason'],'INVALID_INPUT_TYPES')
        self.assertEqual(self.obs(.1)['reason'],'SESSION_CLOSED')
    def test_malformed_epoch_cannot_crash_or_release(self):
        for epoch in ([],None,'',True):
            self.setUp()
            self.assertEqual(self.obs(0.,epoch=epoch)['reason'],'INVALID_INPUT_IDENTITY')
            self.assertEqual(self.obs(.1)['reason'],'SESSION_CLOSED')
    def test_malformed_session_identity_and_sequence(self):
        for kw in ({'run_id':[]},{'step_id':''},{'generation':False},{'generation':-1},{'sequence':False},{'sequence':-1}):
            self.setUp();self.assertEqual(self.obs(0.,**kw)['motion_constraint']['mode'],'HOLD')
    def test_failed_approach_is_terminal(self):
        self.f.accept_event(self.event('APPROACH_TERMINAL',0.,status='FAILED'),now=0.)
        self.assertEqual(self.obs(.1)['reason'],'SESSION_CLOSED')

class FilterD0Tests(unittest.TestCase):
    def test_stale_age_cannot_reset_replay_highwater(self):
        f=TemporalFilter(stability_s=.1)
        def u(seq,t,age=0.,identity=('e','sig')):
            return f.update('GREEN',identity=identity,sequence=seq,source_stamp_ns=str(seq),receipt_s=t,source_age_s=age)
        self.assertEqual(u(10,0.),'UNKNOWN');self.assertEqual(u(11,.1),'GREEN')
        self.assertEqual(u(12,.2,1.),'UNKNOWN')
        self.assertEqual(u(10,.3),'UNKNOWN');self.assertEqual(u(11,.4),'UNKNOWN')
    def test_track_switch_cannot_replay_same_epoch(self):
        f=TemporalFilter(stability_s=.1)
        f.update('GREEN',identity=('e','one'),sequence=10,source_stamp_ns='10',receipt_s=0.,source_age_s=0.)
        f.update('GREEN',identity=('e','two'),sequence=1,source_stamp_ns='1',receipt_s=.1,source_age_s=0.)
        self.assertEqual(f.seq,10)
    def test_nan_then_retired_epoch_stays_retired(self):
        f=TemporalFilter()
        for epoch,seq,t,age in [('old',0,0.,0.),('new',0,.1,0.),('new',1,.2,float('nan'))]:
            f.update('GREEN',identity=(epoch,'s'),sequence=seq,source_stamp_ns=str(seq),receipt_s=t,source_age_s=age)
        self.assertEqual(f.update('GREEN',identity=('old','s'),sequence=100,source_stamp_ns='100',receipt_s=.3,source_age_s=0.),'UNKNOWN')
        self.assertIn('old',f.retired_epochs)
    def test_reset_clears_evidence_not_replay_ledger(self):
        f=TemporalFilter()
        f.update('GREEN',identity=('e','s'),sequence=10,source_stamp_ns='10',receipt_s=0.,source_age_s=0.)
        f.reset()
        self.assertEqual(f.update('GREEN',identity=('e','s'),sequence=1,source_stamp_ns='1',receipt_s=.1,source_age_s=0.),'UNKNOWN')

# Only run each inherited base case once; helpers remain inherited.
for _name in LifecycleD0Tests.__dict__:
    if _name.startswith('test_') and _name not in ReviewD0Tests.__dict__:
        setattr(ReviewD0Tests,_name,None)

if __name__=='__main__':unittest.main()
