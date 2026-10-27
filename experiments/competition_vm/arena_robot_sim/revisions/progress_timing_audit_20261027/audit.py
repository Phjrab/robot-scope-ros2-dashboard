"""Offline retained-data arithmetic only. No ROS, network, controller or simulator."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

SOURCE = 'cf7662123bf13c9c38d565c03a978a4b9ae357a2'
ZIP_SHA = '91a7d37428dc838e324de82152ff7f84082a0cd618546376e559dfb73fead404'
HASHES = {
 'params.yaml': 'cab2b2716b42a192033a397d430151202db0818af5f4a1a79e80a3cf167ed872',
 'trace.jsonl': '80f7dd4f27e4f5fa0b8a3d566ebdcba674d3378fe48ca264eaf5164a70f7f0cd',
 'raw_commands.jsonl': '7ab78a024d364b8afa26358e81be449e7958c71de1028cb23db525ae268c3c51',
 'native.log': 'd6800cc427a1d53c7115196bf8b555f282785b22fdee1507770a96a6c746b9cf',
 'fixture.json': '7f6104bf116e83de4be5882fef6ca15a3270bc90df606a3c73e8576b116a2bf5',
}

def stats(values):
    if not values:
        return None
    s = sorted(values)
    return dict(n=len(s), minimum=s[0], median=statistics.median(s),
                p95_nearest_rank=s[math.ceil(.95*len(s))-1], maximum=s[-1],
                mean=sum(s)/len(s))

def increasing(rows, key):
    values = [r[key] for r in rows]
    if not all(math.isfinite(v) for v in values) or any(b <= a for a,b in zip(values,values[1:])):
        raise ValueError('non-increasing clock: '+key)

def integrate(pose, twist, dt):
    # Independent SE(2) exponential expressed by midpoint heading and sinc,
    # not runner's sin/cos endpoint-difference division.
    x,y,theta = pose
    vx,vy,w = twist
    h = w*dt/2
    scale = dt*(math.sin(h)/h if h else 1)
    angle = theta+h
    return [x+scale*(vx*math.cos(angle)-vy*math.sin(angle)),
            y+scale*(vx*math.sin(angle)+vy*math.cos(angle)),theta+2*h]

def distance(rows):
    return sum(math.dist(a['pose'][:2],b['pose'][:2]) for a,b in zip(rows,rows[1:]))

def summarize(trace, commands, native, goal):
    increasing(trace,'sim_t'); increasing(trace,'monotonic')
    increasing(commands,'receipt_monotonic')
    for row in trace:
        if len(row['pose']) != 3 or len(row['actuator']) != 3:
            raise ValueError('invalid dimensions')
        if not all(math.isfinite(x) for x in row['pose']+row['actuator']+row['applied_previous']):
            raise ValueError('nonfinite pose/twist')
    pose_error = previous_error = 0.
    for a,b in zip(trace,trace[1:]):
        dt = b['sim_t']-a['sim_t']
        if abs(dt-.05)>1e-8:
            raise ValueError('unexpected plant step')
        previous_error = max(previous_error,max(abs(x-y) for x,y in zip(a['actuator'],b['applied_previous'])))
        calculated = integrate(a['pose'],b['applied_previous'],dt)
        pose_error = max(pose_error,max(abs(x-y) for x,y in zip(calculated,b['pose'])))
    owners = {}
    for owner in sorted({c['owner'] for c in commands}):
        c = [r for r in commands if r['owner']==owner]
        gaps = [b['receipt_monotonic']-a['receipt_monotonic'] for a,b in zip(c,c[1:])]
        source_gaps = [(b['source_timestamp_ns']-a['source_timestamp_ns'])/1e9 for a,b in zip(c,c[1:])]
        if any(x<=0 for x in source_gaps): raise ValueError('non-increasing source clock')
        dds = [(r['dds_received_timestamp_ns']-r['source_timestamp_ns'])/1e9 for r in c]
        if any(x<0 for x in dds): raise ValueError('negative same-host DDS delta')
        owners[owner] = dict(received=len(c),accepted=sum(r['accepted'] for r in c),
             receipt_gap_s=stats(gaps),source_gap_s=stats(source_gaps),
             gaps_over_75ms=sum(x>.075 for x in gaps),dds_source_to_received_s=stats(dds),
             callback_source_age_s=stats([r['source_age_s'] for r in c]),
             first_sim_t=c[0]['sim_t'],last_sim_t=c[-1]['sim_t'],
             rejected=[dict(index=commands.index(r)+1,sim_t=r['sim_t'],epoch=r['epoch']) for r in c if not r['accepted']])
    controller = [r for r in commands if r['owner']=='controller_server']
    zero = [r for r in controller if r['accepted'] and (r['v'],r['vy'],r['w'])==(0,0,0)][-1]
    start = next(r for r in controller if r['accepted'])
    # Bounds are command-receipt coordinates, NOT internal progress-checker baseline.
    active = [r for r in trace if start['receipt_monotonic']<=r['monotonic']<=zero['receipt_monotonic']]
    last10 = [r for r in active if r['sim_t']>=zero['sim_t']-10]
    periods=[]
    for lo,hi in [(4,10),(10,16),(16,20),(20,26.5)]:
        a=[r for r in trace if lo<=r['sim_t']<hi]
        c=[r for r in controller if lo<=r['sim_t']<hi and r['accepted']]
        periods.append(dict(sim_range_s=[lo,hi],trace_samples=len(a),sampled_distance_m=distance(a),
             raw_translation_mps=stats([math.hypot(r['v'],r['vy']) for r in c]),
             actuator_translation_mps=stats([math.hypot(*r['actuator'][:2]) for r in a]),
             reasons=dict(Counter(r['reason'] for r in a))))
    phases=[]
    for row in trace:
        if not phases or row['reason']!=phases[-1]['reason']:
            phases.append(dict(reason=row['reason'],first_sim_t=row['sim_t'],last_sim_t=row['sim_t'],samples=1))
        else: phases[-1]['last_sim_t']=row['sim_t']; phases[-1]['samples']+=1
    event_names=['Failed to make progress','Running wait','wait completed successfully','Running spin','Collision Ahead - Exiting Spin','Goal failed']
    events=[]
    for line in native.splitlines():
        for name in event_names:
            if name in line:
                m=re.search(r'\[(\d+\.\d+)\]',line)
                events.append(dict(event=name,realtime_text_s=m.group(1) if m else None))
    return dict(schema='d0-offline-progress-timing.v1',evidence_class='INDEPENDENT_RECONSTRUCTION',
      native_execution='NOT_RUN',source_sha=SOURCE,
      records=dict(trace=len(trace),raw_commands=len(commands)),
      clocks=dict(sim_elapsed_s=trace[-1]['sim_t']-trace[0]['sim_t'],
         monotonic_elapsed_s=trace[-1]['monotonic']-trace[0]['monotonic'],
         plant_wall_gap_s=stats([r['wall_gap_s'] for r in trace]),
         explanation='sim advances fixed 0.05 per tick; monotonic measures receipts; source/DDS/log use same-container realtime. Never subtract sim or monotonic from realtime.'),
      owners=owners,phases=phases,events=events,
      control_warnings=native.count('Control loop missed its desired rate of 20.0000Hz'),
      active_control=dict(samples=len(active),reasons=dict(Counter(r['reason'] for r in active)),
        last10_sample_range_s=[last10[0]['sim_t'],last10[-1]['sim_t']],
        last10_sampled_distance_m=distance(last10),
        last10_net_displacement_m=math.dist(last10[0]['pose'][:2],last10[-1]['pose'][:2]),
        last10_max_displacement_from_first_m=max(math.dist(last10[0]['pose'][:2],r['pose'][:2]) for r in last10),
        progress_checker_internal_baseline='INPUT_REQUIRED; this window is not the internal baseline'),
      periods=periods,simulated_actuation=dict(previous_output_max_error=previous_error,pose_integration_max_error=pose_error,
        sampled_path_length_m=distance(trace),remaining_goal_distance_m=math.dist(trace[-1]['pose'][:2],goal[:2]),
        final_actuator=trace[-1]['actuator'],contact_counter_max=max(r['collision_count'] for r in trace),
        boundary_counter_max=max(r['boundary_count'] for r in trace)),
      limitations=['No subscriber record proves absence of lost DDS messages; no isolated controller timing spans.',
        'Source emission gaps and receipt gaps are observed separately, not per-cycle compute latency.',
        'Diagnostic planner JSON/file IO under global map lock may perturb timing; magnitude unmeasured.',
        'No actual robot, wheel slip, gait, Safe mode or physical control inference.',
        'Command decay is observed; critic costs, selected rollout and progress baseline were not captured.'])

def audit(root):
    root=Path(root)
    if (root/'source-sha.txt').read_text().strip()!=SOURCE: raise ValueError('wrong source')
    run=root/'atomic/mppi-d0_feasible1-0/run'
    for name,expected in HASHES.items():
        if hashlib.sha256((run/name).read_bytes()).hexdigest()!=expected: raise ValueError('changed retained file '+name)
    trace=[json.loads(x) for x in (run/'trace.jsonl').read_text().splitlines()]
    commands=[json.loads(x) for x in (run/'raw_commands.jsonl').read_text().splitlines()]
    fixture=json.loads((run/'fixture.json').read_text())
    out=summarize(trace,commands,(run/'native.log').read_text(),fixture['goal'])
    out['input_sha256']=HASHES
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact_directory');p.add_argument('--output',type=Path)
    a=p.parse_args();text=json.dumps(audit(a.artifact_directory),indent=2,allow_nan=False)+'\n'
    if a.output: a.output.write_text(text)
    else: print(text,end='')
