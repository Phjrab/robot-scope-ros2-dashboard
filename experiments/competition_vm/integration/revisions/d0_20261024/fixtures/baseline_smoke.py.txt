"""Runnable synthetic in-process contract trace, never a robot command."""
import json
from adapter import ConstraintAdapter, traffic

a=ConstraintAdapter('vm-run','signal-step',0)
f=traffic.StopGoFSM(); f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
rows=[]
for n in range(24):
    now=n/10
    state='RED' if n<10 else 'UNKNOWN' if n<21 else 'GREEN'
    result=f.update(traffic.StopInput(receipt_s=now,sequence=n,stable_state=state,
                      left_inside=True,right_inside=True,visual_zone=True,body_stopped=True,approach_ack=True))
    constraint=result['motion_constraint']
    a.ingest(constraint,sequence=n,receipt_s=now,now=now)
    command_seq=n if n!=22 else 21 # Deliberate cached command replay after release.
    v,w,reason=a.apply(.25,0.,command_seq,receipt_s=now,now=now,sensor_fresh=True,tf_fresh=True)
    rows.append(dict(evidence_type='SYNTHETIC_IN_PROCESS',time_s=now,signal=state,
                     fsm_state=result['state'],constraint=constraint['mode'],command_sequence=command_seq,
                     simulated_v=v,simulated_w=w,arbiter_reason=reason))
assert all(r['simulated_v']==0 for r in rows if r['signal'] in ('RED','UNKNOWN'))
assert rows[22]['simulated_v']==0
assert rows[21]['simulated_v']>0 and rows[23]['simulated_v']>0
for row in rows: print(json.dumps(row))
