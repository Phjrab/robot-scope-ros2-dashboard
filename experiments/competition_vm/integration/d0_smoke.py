"""D0 honest synthetic event replay, no ROS or action client.

Actions/ACKs are separate injected events with explicit provenance. The script
never synthesizes an ACK in response to sending a goal or emitting HOLD.
"""
from pathlib import Path
import sys, json
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from experiments.competition_vm.traffic_signals.lifecycle import TrafficLifecycle, ActionEvent
from experiments.competition_vm.traffic_signals.core import StopInput, StopGoFSM
from experiments.competition_vm.integration.adapter import LifecycleConstraintAdapter, ConstraintAdapter


def run():
    lifecycle=TrafficLifecycle('vm-run','signal-step','crossing-1','visit-1','signal_01',0,'stop_zone_01','approach',1)
    bridge=LifecycleConstraintAdapter(lifecycle)
    rows=[];event_seq=0
    def event(kind,t,**kw):
        nonlocal event_seq
        event_seq+=1
        return lifecycle.accept_event(ActionEvent(kind=kind,run_id='vm-run',step_id='signal-step',
            goal_id=kw.pop('goal_id','approach'),goal_generation=kw.pop('goal_generation',1),
            epoch='action-1',sequence=event_seq,receipt_s=t,**kw),now=t)
    for n in range(38):
        t=round(n/10,6)
        # Explicit scenario events, not return-value-derived fake ACKs.
        if n==3: assert event('APPROACH_TERMINAL',t,status='SUCCEEDED')
        if n==4: assert event('HOLD_ACK',t,status='ACKNOWLEDGED',request_id=lifecycle.hold_request_id)
        if n==26: assert lifecycle.request_exit('exit',2,now=t)
        if n==27: assert event('EXIT_ACK',t,status='ACTIVE',goal_id='exit',goal_generation=2)
        committed=n>=29
        signal='RED' if n<24 or n>=30 else 'GREEN'
        o=StopInput(receipt_s=t,sequence=n,stable_state=signal,
            left_inside=n>=4,right_inside=n>=4,visual_zone=n>=4,body_stopped=4<=n<29,
            departure_observed=n==29,fully_crossed=n==37)
        r=bridge.observe(o,now=t,pose_age_s=0.,observed_goal_id='exit' if committed else None,
                         observed_goal_generation=2 if committed else None)
        goal,gen=bridge.adapter.goal_identity
        command=n if n!=28 else 27 # repeated command cannot resume across release.
        v,w,why=bridge.apply(.25,0.,command,receipt_s=t,now=t,sensor_fresh=True,tf_fresh=True,
                            goal_id=goal,goal_generation=gen)
        rows.append(dict(evidence_type='SYNTHETIC_IN_PROCESS',time_s=t,signal=signal,
             lifecycle_state=r['lifecycle_state'],fsm_state=r['state'],reason=r['reason'],
             constraint=r['motion_constraint']['mode'],goal_id=goal,goal_generation=gen,
             command_sequence=command,simulated_v=v,arbiter_reason=why))
    assert all(r['simulated_v']>0 for r in rows[:3]), 'approach must not self-HOLD'
    assert all(r['simulated_v']==0 for r in rows[3:27]), 'terminal/ACK/dwell/exit gate'
    assert rows[27]['simulated_v']>0 and rows[27]['fsm_state']=='DEPART_PENDING'
    assert rows[28]['simulated_v']==0 and rows[28]['fsm_state']=='DEPART_PENDING'
    assert rows[29]['fsm_state']=='CROSSING_COMMITTED'
    assert rows[30]['signal']=='RED' and rows[30]['simulated_v']>0
    assert rows[-1]['fsm_state']=='CLEAR'
    return rows

if __name__=='__main__':
    for row in run(): print(json.dumps(row,sort_keys=True))
