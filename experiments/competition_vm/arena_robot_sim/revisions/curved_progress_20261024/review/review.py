"""Read-only independent geometry and motion checks; writes only reviewer results."""
from pathlib import Path
import json, math, hashlib
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=Path('/workspace/scratch/b09eacf6919d/robot-scope-left-slalom-20261024/experiments/competition_vm/arena_robot_sim/revisions')
NEW=ROOT/'curved_progress_20261024/results/candidate02'
OLD=ROOT/'curved_slalom_20261024/results/final_regressions'

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

def review(path):
    d=json.loads(path.read_text());fs=d['frames'];start=np.array(d['scene']['start']);poses=np.array([f['pose'] for f in fs]);prev=np.vstack([start,poses[:-1]])
    sample=(prev[:,None,:]+(poses-prev)[:,None,:]*np.linspace(0,1,11)[None,:,None]).reshape(-1,3)
    body=np.array(d['scene']['footprint']);rot=np.stack([np.stack([np.cos(sample[:,2]),-np.sin(sample[:,2])],-1),np.stack([np.sin(sample[:,2]),np.cos(sample[:,2])],-1)],-2)
    robot=np.einsum('nij,kj->nki',rot,body)+sample[:,None,:2]
    floor=np.array(d['scene']['allowed_floor_polygons']['floor_left_straight'])
    crossfloor,minimum=polygon_separation(robot,floor);violations=np.any(~inside(robot,floor),axis=1)|crossfloor
    for c in d['scene']['cones']:
        x,y=c['xy'];h=c['base_side_m']/2;poly=np.array([[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]])
        crossing,dist=polygon_separation(robot,poly)
        box_inside_robot=np.zeros(len(robot),bool)
        # Rectangular body: invert transform for cone center, supplement edge crossings.
        delta=np.array([x,y])-sample[:,:2]
        local=np.einsum('nji,nj->ni',rot,delta)
        box_inside_robot=(abs(local[:,0])<=.405)&(abs(local[:,1])<=.28)
        overlapping=crossing|np.any(inside(robot,poly),axis=1)|box_inside_robot
        violations|=overlapping;minimum=np.minimum(minimum,np.where(overlapping,0,dist))
    # Any point on a rigid body moves <= translation + radius*angular-change.
    # Nearest audit sample is at most half of each 1/10 interpolation step away.
    displacement=np.linalg.norm(poses[:,:2]-prev[:,:2],axis=1)+np.linalg.norm(body,axis=1).max()*abs(poses[:,2]-prev[:,2])
    lower_per_interval=minimum.reshape(-1,11).min(axis=1)-displacement/20
    velocities=np.array([[f['vx_world'],f['vy_world'],f['w']] for f in fs]);dv=np.diff(np.vstack([np.zeros(3),velocities]),axis=0)
    stale=[f for f in fs if not f['sensor_fresh']]
    kin_error=np.max(abs(poses-prev-velocities*.1))
    linear_jerk=np.diff(velocities[:,:2],n=2,axis=0)/.1**2
    angular_jerk=np.diff(velocities[:,2],n=2)/.1**2
    speed=np.linalg.norm(velocities[:,:2],axis=1);sj=np.diff(speed,n=2)/.1**2
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'outcome':d['metrics']['outcome'],'min_clearance_sampled_m':float(minimum.min()),'min_clearance_continuous_lower_bound_m':float(lower_per_interval.min()),'sampled_polygon_violations':int(violations.sum()),'poses_checked':len(sample),'kinematic_identity_max_abs_error':float(kin_error),'max_linear_accel_m_s2':float(np.linalg.norm(dv[:,:2],axis=1).max()/.1),'max_yaw_accel_rad_s2':float(abs(dv[:,2]).max()/.1),'linear_vector_rms_jerk':float(np.sqrt(np.mean(np.sum(linear_jerk**2,axis=1)))),'scalar_speed_rms_jerk':float(np.sqrt(np.mean(sj**2))),'yaw_rms_jerk':float(np.sqrt(np.mean(angular_jerk**2))),'velocity_total_variation':float(np.linalg.norm(np.diff(velocities[:,:2],axis=0),axis=1).sum()),'terminal_speed':float(speed[-1]),'terminal_yaw_rate':float(velocities[-1,2]),'goal_error_m':float(np.linalg.norm(poses[-1,:2]-d['scene']['goal'])),'first_stale_t':stale[0]['t'] if stale else None,'stale_frames':len(stale),'stale_moving_frames':sum(any(abs(f[k])>1e-12 for k in ['vx_world','vy_world','w']) for f in stale)}

out={}
for name in ['open_normal','tight_normal','open_dropout','open_delay','blocked_5']:
    out[name]=review(NEW/f'{name}.json')
out['previous_open']=review(OLD/'open_normal.json')
(HERE/'independent_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
