"""Offline kinematic visualization. Never a robot controller or physics claim."""
import json, math, hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
ASSET=ROOT/'robot_dashboard/static/assets/go2/go2-official-lite.json'
LEGS=('FL','FR','RL','RR'); HEIGHT=.33407456

def rot(axis,q):
 a=np.asarray(axis,float);a/=np.linalg.norm(a);x,y,z=a;c=math.cos(q);s=math.sin(q);C=1-c
 R=np.array([[c+x*x*C,x*y*C-z*s,x*z*C+y*s],[y*x*C+z*s,c+y*y*C,y*z*C-x*s],[z*x*C-y*s,z*y*C+x*s,c+z*z*C]])
 T=np.eye(4);T[:3,:3]=R;return T

def origin(o):
 T=np.eye(4);T[:3,3]=o['xyz'];r,p,y=o['rpy'];T[:3,:3]=(rot((0,0,1),y)@rot((0,1,0),p)@rot((1,0,0),r))[:3,:3];return T

def fk(asset,q):
 T={'base':np.eye(4)}
 for j in asset['skeleton']['joints']:
  T[j['child']]=T[j['parent']]@origin(j['origin'])@(rot(j['axis'],q[j['name']]) if j['type']=='revolute' else np.eye(4))
 return T

def ik(leg,target):
 # URDF origins: hip +/- .1934, +/- .0465; thigh lateral .0955; L=.213.
 front=1 if leg[0]=='F' else -1;side=1 if leg[1]=='L' else -1
 x,y,z=np.asarray(target)-[front*.1934,side*.0465,0]
 r=math.hypot(y,z);d=side*.0955
 if abs(d)>r:raise ValueError('Unreachable hip target')
 phi=math.atan2(z,y);delta=math.acos(d/r)
 cand=[(phi+v+math.pi)%(2*math.pi)-math.pi for v in (delta,-delta)]
 a=min(cand,key=abs); zz=-y*math.sin(a)+z*math.cos(a)
 cc=(x*x+zz*zz-2*.213**2)/(2*.213**2)
 if abs(cc)>1+1e-8:raise ValueError('Unreachable foot target')
 c=-math.acos(max(-1,min(1,cc)));b=math.atan2(-x,-zz)-math.atan2(.213*math.sin(c),.213*(1+math.cos(c)))
 return {leg+'_hip_joint':a,leg+'_thigh_joint':b,leg+'_calf_joint':c}

def sample(trace,t):
 frames=trace['frames'];tt=np.array([f['t'] for f in frames]);p=np.array([f['pose'] for f in frames]);yaw=np.unwrap(p[:,2]);return np.array([np.interp(t,tt,p[:,0]),np.interp(t,tt,p[:,1]),np.interp(t,tt,yaw)])

def world(local,pose):
 R=rot((0,0,1),pose[2])[:3,:3];return R@local+np.array([pose[0],pose[1],HEIGHT])

def local(w,pose):return rot((0,0,1),-pose[2])[:3,:3]@(w-np.array([pose[0],pose[1],HEIGHT]))

def build(trace,asset,fps=15,stride_m=.16):
 if not math.isfinite(fps) or fps<=0 or not math.isfinite(stride_m) or stride_m<=0:raise ValueError('Positive finite fps/stride required')
 raw=np.array([[f['t'],*f['pose']] for f in trace['frames']],float)
 if len(raw)<2 or not np.isfinite(raw).all() or not (np.diff(raw[:,0])>0).all():raise ValueError('Finite strictly increasing timestamped poses required')
 end=trace['frames'][-1]['t'];start=trace['frames'][0]['t'];times=np.linspace(start,end,round((end-start)*fps)+1)
 poses=np.array([sample(trace,t) for t in times]);increments=np.linalg.norm(np.diff(poses[:,:2],axis=0),axis=1)+.15*np.abs(np.diff(poses[:,2]));motion=np.r_[0,np.cumsum(increments)]
 active=motion[-1]>1e-8
 # Normalize each contiguous moving segment to whole cycles. Every stationary
 # interval consequently begins with all four feet in stance (phases 0/.5).
 phases=np.zeros(len(times));segment_ends=np.arange(len(times));basephase=0.;k=0
 while k<len(increments):
  if increments[k]<=1e-8:
   phases[k+1]=basephase;k+=1;continue
  begin=k
  while k<len(increments) and increments[k]>1e-8:k+=1
  end_index=k;distance=motion[end_index]-motion[begin];cycles=max(1,round(distance/stride_m))
  phases[begin:end_index+1]=basephase+(motion[begin:end_index+1]-motion[begin])/distance*cycles
  phases[end_index]=basephase+cycles;segment_ends[begin:end_index+1]=end_index;basephase+=cycles
 nominal={leg:np.array([(.1934 if leg[0]=='F' else -.1934),(.142 if leg[1]=='L' else -.142),.024-HEIGHT]) for leg in LEGS}
 anchors={leg:world(nominal[leg],poses[0]) for leg in LEGS};previous={leg:0 for leg in LEGS};swing_start={};swing_end={};out=[]
 footmesh=asset['meshes']['foot'];fv=np.array(footmesh['vertices_q']).reshape(-1,3)*footmesh['quantization_m']
 for i,(t,p,phase) in enumerate(zip(times,poses,phases)):
  q={};feet={};stance={}
  for leg in LEGS:
   offset=0 if leg in ('FL','RR') else .5
   u=(phase+offset)%1;in_swing=active and .65<u<1 and i<len(times)-1
   if in_swing and not previous[leg]:
    swing_start[leg]=anchors[leg].copy();landing=math.floor(phase+offset)+1-offset
    future_idx=min(int(segment_ends[i]),int(np.searchsorted(phases,landing+.20)))
    swing_end[leg]=world(nominal[leg],poses[future_idx]);swing_end[leg][2]=.024
   if in_swing:
    v=(u-.65)/.35;blend=v*v*(3-2*v);target=(1-blend)*swing_start[leg]+blend*swing_end[leg];lift=.045*math.sin(math.pi*v)**2
   else:
    if previous[leg]:anchors[leg]=swing_end[leg].copy()
    target=anchors[leg].copy();lift=0
   target[2]=.024+lift
   # Solve exact mesh sole height, without changing stance horizontal anchor.
   for k in range(5):
    qleg=ik(leg,local(target,p));T=fk(asset,{**asset['skeleton']['default_joint_positions'],**qleg})[leg+'_foot'];lowest=(fv@T[:3,:3].T+T[:3,3])[:,2].min()+HEIGHT
    target[2]+=lift+.001-lowest
   q.update(ik(leg,local(target,p)));feet[leg]=target.tolist();stance[leg]=not in_swing;previous[leg]=in_swing
  out.append({'t':float(t),'pose':p.tolist(),'q':q,'feet_world':feet,'stance':stance,'phase':float(phase)})
 return out

def validate(records,asset):
 mins=np.full(3,np.inf);maxs=-mins;ground=1e9;maxerr=0;maxslip=0;prev=None
 vertices={name:np.array(m['vertices_q']).reshape(-1,3)*m['quantization_m'] for name,m in asset['meshes'].items()}
 for f in records:
  T=fk(asset,f['q'])
  for j in asset['skeleton']['joints']:
   if j['type']=='revolute':assert j['limit']['lower']<=f['q'][j['name']]<=j['limit']['upper'],j['name']
  for link in asset['skeleton']['links']:
   tr=T[link['name']]@origin(link['visual_origin']);v=vertices[link['mesh']]@tr[:3,:3].T+tr[:3,3];mins=np.minimum(mins,v.min(0));maxs=np.maximum(maxs,v.max(0));ground=min(ground,v[:,2].min()+HEIGHT)
  for leg in LEGS:
   actual=world(T[leg+'_foot'][:3,3],f['pose']);maxerr=max(maxerr,float(np.linalg.norm(actual-f['feet_world'][leg])))
   if prev and f['stance'][leg] and prev['stance'][leg]:maxslip=max(maxslip,float(np.linalg.norm(np.array(f['feet_world'][leg][:2])-prev['feet_world'][leg][:2])))
  prev=f
 return {'frames':len(records),'min_mesh_ground_clearance_m':float(ground),'max_foot_ik_residual_m':maxerr,'max_consecutive_stance_xy_slip_m':maxslip,'articulated_local_bounds_m':[mins.tolist(),maxs.tolist()],'joint_limits_pass':True,'physics':False,'collision_requalification':'NOT_RUN: original static-footprint trace metrics do not certify this articulated envelope'}

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--trace-path');parser.add_argument('--case',default='external');parser.add_argument('--stride-m',type=float,default=.16);args=parser.parse_args()
 out=HERE/'output';out.mkdir(exist_ok=True);asset=json.loads(ASSET.read_text());summary={}
 for case in ([args.case] if args.trace_path else ('cone_detour','blocked')):
  path=Path(args.trace_path) if args.trace_path else HERE.parents[1]/'results'/f'{case}.json';trace=json.loads(path.read_text());records=build(trace,asset,stride_m=args.stride_m);v=validate(records,asset);v['animation_stride_m']=args.stride_m;v['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();v['original_metrics']=trace['metrics'];summary[case]=v
  (out/f'{case}_joints.json').write_text(json.dumps({'source_trace':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name,'records':records,'validation':v},indent=2))
 (out/(args.case+'_VALIDATION.json' if args.trace_path else 'VALIDATION.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
