"""Independent fresh-trace review. Never imports candidate collision code.
Adapted from frozen curved_progress review; closed segment contact is distance <= EPS.
The continuous bound applies to the simulator's linear SE(2) interpolation only.
"""
from pathlib import Path
import json, math, hashlib, datetime
import numpy as np
HERE=Path(__file__).resolve().parent
NEW=HERE.parent/'results/candidate02'
GENERIC=HERE.parent/'results/generic_candidate02'
OLD=HERE.parent.parent/'curved_progress_20261024/results/candidate02'
EPS=1e-10
NAMES=['open_normal','tight_normal','open_dropout','open_delay','blocked_5']
def cross(a,b):return a[...,0]*b[...,1]-a[...,1]*b[...,0]
def inside(p,poly):
    out=np.zeros(p.shape[:-1],bool)
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        if a[1]==b[1]:continue
        out^=((a[1]>p[...,1])!=(b[1]>p[...,1])) & (p[...,0]<(b[0]-a[0])*(p[...,1]-a[1])/(b[1]-a[1])+a[0])
    return out

def dist_point_edges(p,a,b):
    # p: N,P,2; a,b: N,E,2
    d=b-a; v=p[:,:,None,:]-a[:,None,:,:]
    frac=np.clip(np.sum(v*d[:,None,:,:],axis=-1)/np.sum(d*d,axis=-1)[:,None,:],0,1)
    return np.linalg.norm(v-frac[...,None]*d[:,None,:,:],axis=-1).min(axis=(1,2))

def polygon_separation(robot,poly):
    n=len(robot);a=robot;b=np.roll(a,-1,axis=1)
    c=np.broadcast_to(poly,(n,*poly.shape));d=np.roll(c,-1,axis=1)
    v=b-a;w=d-c;delta=c[:,None,:,:]-a[:,:,None,:]
    den=cross(v[:,:,None,:],w[:,None,:,:]);safe=np.where(abs(den)<1e-15,np.nan,den)
    t=cross(delta,w[:,None,:,:])/safe;u=cross(delta,v[:,:,None,:])/safe
    crossing=np.any((t>=0)&(t<=1)&(u>=0)&(u<=1),axis=(1,2))
    distance=np.minimum(dist_point_edges(a,c,d),dist_point_edges(c,a,b))
    return crossing,distance

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def equal_frames(a,b,keys):
    mismatch=[i for i,(x,y) in enumerate(zip(a,b)) if any(x.get(k)!=y.get(k) for k in keys)]
    return {'equal':len(a)==len(b) and not mismatch,'different_common_frames':len(mismatch),'first_different_frame':mismatch[0] if mismatch else None,'new_frames':len(a),'frozen_frames':len(b)}

def audit(name):
    path=NEW/f'{name}.json'; old=OLD/f'{name}.json'
    d=json.loads(path.read_text());frozen=json.loads(old.read_text());fs=d['frames'];scene=d['scene']; oldscene=frozen['scene']
    poses=np.asarray([f['pose'] for f in fs]);prev=np.vstack([scene['start'],poses[:-1]])
    body=np.asarray(scene['footprint']);samples=(prev[:,None,:]+(poses-prev)[:,None,:]*np.linspace(0,1,11)[None,:,None]).reshape(-1,3)
    rot=np.stack([np.stack([np.cos(samples[:,2]),-np.sin(samples[:,2])],-1),np.stack([np.sin(samples[:,2]),np.cos(samples[:,2])],-1)],-2)
    robot=np.einsum('nij,kj->nki',rot,body)+samples[:,None,:2]
    floor=np.asarray(scene['allowed_floor_polygons']['floor_left_straight'])
    crossings,wall_dist=polygon_separation(robot,floor)
    wall_bad=crossings|np.any(~inside(robot,floor),axis=1)|(wall_dist<=EPS)
    minimum=np.where(wall_bad,0.,wall_dist);cone_bad=np.zeros(len(samples),bool)
    for cone in scene['cones']:
        x,y=cone['xy'];h=cone['base_side_m']/2
        poly=np.array([[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]])
        crossing,dist=polygon_separation(robot,poly)
        # Complete containment check: cone center inside body, body vertex inside cone,
        # and edge crossing/contact. Distances handle parallel/collinear edge contact.
        local=np.einsum('nji,nj->ni',rot,np.array([x,y])-samples[:,:2])
        overlap=crossing|(dist<=EPS)|np.any(inside(robot,poly),axis=1)|((abs(local[:,0])<=.405+EPS)&(abs(local[:,1])<=.28+EPS))
        cone_bad|=overlap;minimum=np.minimum(minimum,np.where(overlap,0.,dist))
    motion=np.linalg.norm(poses[:,:2]-prev[:,:2],axis=1)+np.linalg.norm(body,axis=1).max()*abs(poses[:,2]-prev[:,2])
    bound=minimum.reshape(-1,11).min(axis=1)-motion/20
    dt=np.array([f['pose_t']-f['t'] for f in fs]);u=np.array([[f[k] for k in ('vx_world','vy_world','w')] for f in fs]);du=np.diff(np.vstack([np.zeros(3),u]),axis=0)
    lin_acc=np.linalg.norm(du[:,:2],axis=1)/dt;ang_acc=abs(du[:,2])/dt
    states=[f.get('controller_state_before_terminal',f['state']) for f in fs]
    emergency=np.array([s in ('SENSOR_STALE_HOLD','COLLISION_HOLD') and np.max(abs(v))<=EPS for s,v in zip(states,u)])
    normal=~emergency
    stale=np.array([not f['sensor_fresh'] for f in fs]);age_ok=np.array([f['sensor_fresh']==(f['source_age_s']<=.25+1e-9 and f['receiver_age_s']<=.25+1e-9) and f['source_age_s']>=-EPS and f['receiver_age_s']>=-EPS for f in fs])
    checks={
      'full_body_081_by_056_unchanged': scene['footprint']==[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]]==oldscene['footprint'],
      'margin_003_unchanged':scene['minimum_clearance_constraint_m']==oldscene['minimum_clearance_constraint_m']==.03,
      'padded_body_unchanged':scene['collision_guard_footprint']==oldscene['collision_guard_footprint']==[[-.435,-.31],[.435,-.31],[.435,.31],[-.435,.31]],
      'cones_unchanged':scene['cones']==oldscene['cones'],
      'floor_unchanged':scene['allowed_floor_polygons']==oldscene['allowed_floor_polygons'],
      'zero_sampled_polygon_contacts':not np.any(wall_bad|cone_bad),
      'continuous_margin_at_least_003':bool(bound.min()>=.03-EPS),
      'kinematic_identity':bool(np.max(abs(poses-prev-u*dt[:,None]))<1e-10),
      'both_ages_gate_freshness':bool(age_ok.all()),
      'stale_always_zero':bool(np.all(abs(u[stale])<=EPS)),
      'terminal_zero':bool(np.all(abs(u[-1])<=EPS)),
      'expected_outcome':d['metrics']['outcome'] in (('GOAL_REACHED',) if name=='open_normal' else ('GOAL_REACHED','SAFE_WAIT') if name=='tight_normal' else ('SAFE_WAIT',)),
      'terminal_state_matches_outcome':fs[-1]['state']==d['metrics']['outcome'],
      'normal_linear_slew':bool(np.all(lin_acc[normal]<=scene['parameters']['amax']+EPS)),
      'normal_angular_slew':bool(np.all(ang_acc[normal]<=scene['parameters']['angular_accel_max']+EPS)),
      'speed_limit':bool(np.max(np.linalg.norm(u[:,:2],axis=1))<=scene['parameters']['vmax']+EPS),
      'yaw_rate_limit':bool(np.max(abs(u[:,2]))<=scene['parameters']['wmax']+EPS),
      'reported_zero_contacts':d['metrics']['contacts']==0,
      'emergency_override_count_consistent':int(np.sum(emergency & np.any(abs(np.vstack([np.zeros(3),u[:-1]]))>1e-8,axis=1)))==d['metrics']['emergency_slew_overrides'],
      'delay_rejected_when_applicable':name!='open_delay' or d['metrics']['rejected_delayed_samples']>0,
      'fault_cases_become_stale':name not in ('open_delay','open_dropout') or bool(stale.any()),
    }
    return {'sha256':digest(path),'frozen_sha256':digest(old),'pass':all(checks.values()),'checks':checks,'outcome':d['metrics']['outcome'],'geometry':{'poses_checked':len(samples),'wall_contacts':int(wall_bad.sum()),'cone_contacts':int(cone_bad.sum()),'sampled_clearance_m':float(minimum.min()),'continuous_clearance_lower_bound_m':float(bound.min())},'motion':{'frames':len(fs),'normal_max_linear_accel':float(lin_acc[normal].max()) if normal.any() else 0.,'normal_max_angular_accel':float(ang_acc[normal].max()) if normal.any() else 0.,'emergency_max_linear_accel':float(lin_acc[emergency].max()) if emergency.any() else 0.,'emergency_max_angular_accel':float(ang_acc[emergency].max()) if emergency.any() else 0.,'emergency_slew_exceeding_frames':int(np.sum(emergency&((lin_acc>.2+EPS)|(ang_acc>.35+EPS)))),'reported_emergency_overrides':d['metrics']['emergency_slew_overrides'],'stale_frames':int(stale.sum()),'first_stale_t':next((f['t'] for f in fs if not f['sensor_fresh']),None),'rejected_delayed_samples':d['metrics']['rejected_delayed_samples'],'goal_error_m':float(np.linalg.norm(poses[-1,:2]-scene['goal']))},'comparison':{'actual_poses_commands_states':equal_frames(fs,frozen['frames'],['t','pose_t','pose','v','w','vx_world','vy_world','state','controller_state_before_terminal','terminal_outcome']),'sensing':equal_frames(fs,frozen['frames'],['sensor_fresh','receiver_age_s','source_age_s']),'paths_separate':equal_frames(fs,frozen['frames'],['path','path_yaws']),'path_xy_only':equal_frames(fs,frozen['frames'],['path']),'path_yaw_only':equal_frames(fs,frozen['frames'],['path_yaws']),'scene_equal':scene==oldscene,'scene_changed_keys':[k for k in scene if scene.get(k)!=oldscene.get(k)],'deterministic_metrics_equal':{k:v for k,v in d['metrics'].items() if k not in ('wall_time_s','planning_wall_s','planning_p95_s')}=={k:v for k,v in frozen['metrics'].items() if k not in ('wall_time_s','planning_wall_s','planning_p95_s')}}}

if __name__=='__main__':
    results={name:audit(name) for name in NAMES}
    for name,r in results.items():
        gp=GENERIC/f'{name}.json';fresh=json.loads((NEW/f'{name}.json').read_text());generic=json.loads(gp.read_text());a=fresh['frames'];b=generic['frames']
        r['generic_sha256']=digest(gp)
        r['comparison_vs_generic']={
            'actual_poses_commands_states':equal_frames(a,b,['t','pose_t','pose','v','w','vx_world','vy_world','state','controller_state_before_terminal','terminal_outcome']),
            'paths_separate':equal_frames(a,b,['path','path_yaws']),
            'sensing':equal_frames(a,b,['sensor_fresh','receiver_age_s','source_age_s']),
            'scene_equal':fresh['scene']==generic['scene'],
            'deterministic_metrics_equal':{k:v for k,v in fresh['metrics'].items() if k not in ('wall_time_s','planning_wall_s','planning_p95_s')}=={k:v for k,v in generic['metrics'].items() if k not in ('wall_time_s','planning_wall_s','planning_p95_s')},
        }
        r['checks']['generic_execution_equivalence']=all(v['equal'] if isinstance(v,dict) else v for v in r['comparison_vs_generic'].values())
        r['pass']=all(r['checks'].values())
    out={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fresh_input_directory':str(NEW.relative_to(HERE.parent)),'source_sha256':{n:digest(HERE.parent/n) for n in ['collision.py','fast_snapshot.py','simulate_curved.py','run_candidate.py']},'all_pass':all(r['pass'] for r in results.values()),'scenarios':results,'limitations':['Only newly executed closed_cell_collision_20261025 traces are audited; frozen traces are comparison references, not fresh tests.','Full body planar rectangle and exact cone base/floor polygons; not articulated-mesh, dynamics, real-robot or physical gait validation.','Continuous bound uses commanded linear position/yaw integration and 11 samples per interval.','Closed-cell corrections may change planned paths. Actual poses, commands and states are compared separately without assuming equivalence.','Wall-clock/planning timing metrics excluded from deterministic comparison; concurrent scenario/test workload is not a performance benchmark.','No real-time capability is inferred from this replay or its wall times.','A tight-normal SAFE_WAIT is a safe unresolved case, not proof that the course is infeasible.']}
    (HERE/'independent_scenarios_results.json').write_text(json.dumps(out,indent=2)+'\n')
    lines=['# Independent fresh scenario review','',f"Overall: {'PASS' if out['all_pass'] else 'FAIL'}",'']
    for n,r in results.items():
        g=r['geometry'];c=r['comparison'];lines.append(f"- {n}: {'PASS' if r['pass'] else 'FAIL'}, {r['outcome']}; continuous clearance lower bound {g['continuous_clearance_lower_bound_m']:.9f} m; actual poses/commands/states equal to frozen: {c['actual_poses_commands_states']['equal']}; paths equal: {c['paths_separate']['equal']}.")
        lines.append(f"  Versus fresh generic implementation: actual poses/commands/states equal: {r['comparison_vs_generic']['actual_poses_commands_states']['equal']}; planned paths equal: {r['comparison_vs_generic']['paths_separate']['equal']}; source SHA-256 values are recorded in the JSON report.")
        if not c['paths_separate']['equal']:lines.append(f"  Path differences begin at frame {c['paths_separate']['first_different_frame']} and affect {c['paths_separate']['different_common_frames']} common frames; XY equal: {c['path_xy_only']['equal']}, path yaw equal: {c['path_yaw_only']['equal']}. A closed-cell guard can legitimately change planning candidates without changing the executed trajectory.")
        if not r['pass']:lines.append('  Failed checks: '+', '.join(k for k,v in r['checks'].items() if not v))
    lines+=['','Open normal must reach the goal; tight normal may safely wait (as the frozen baseline did) or reach the goal. Dropout, delay and blocked cases must terminate in SAFE_WAIT. Normal slew is tested separately from immediate emergency zero stops. Source and receiver age both gate freshness. Body, margin, cone and floor values are checked against the frozen source and explicit dimensions.','','## Scope and comparison notes']+['- '+s for s in out['limitations']]
    (HERE/'SCENARIO_REVIEW.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(out,indent=2))
    raise SystemExit(0 if out['all_pass'] else 1)
