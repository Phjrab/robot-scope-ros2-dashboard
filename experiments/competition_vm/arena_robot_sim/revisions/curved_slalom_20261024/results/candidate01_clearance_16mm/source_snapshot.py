"""VM-only clearance-constrained smoothing + bounded holonomic SE(2) follower."""
from pathlib import Path
import sys,json,math,time
import numpy as np
from scipy.ndimage import maximum_filter
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'left_slalom_20261024'))
import simulate_slalom as base
from core import Occupancy,Scan,plan,polygon_collision
DT=.1;RES=base.RES;BODY=base.BODY
VMAX=.16;AMAX=.20;WMAX=.18;ALPHAMAX=.35;LOOKAHEAD=.05;YAW_MAX=.04

def advance(p,u,dt):return tuple(p[i]+u[i]*dt for i in range(3))
def safe(p,u,horizon,grid):
 travel=(math.hypot(u[0],u[1])+abs(u[2])*.493)*horizon;n=max(2,math.ceil(travel/.003))
 return all(not polygon_collision(advance(p,u,horizon*j/n),BODY,grid,RES) for j in range(n+1))
def build_path(pose,grid):
 expanded=maximum_filter(grid,size=(43,31),mode='constant',cval=1)
 raw=plan((expanded,np.zeros_like(expanded)),np.ones_like(expanded),pose[:2],base.GOAL,RES,0.)
 if len(raw)<2:return []
 # Smooth only inside the same full-footprint configuration-space corridor.
 # No use of hidden cone truth, no hand-authored waypoint/path insertion.
 p=np.array(raw,float);p[0]=pose[:2]
 def allowed(q):
  iy,ix=int(q[1]/RES),int(q[0]/RES)
  return 0<=iy<grid.shape[0] and 0<=ix<grid.shape[1] and not expanded[iy,ix]
 for _ in range(45):
  old=p.copy()
  for i in range(1,len(p)-1):
   q=old[i]+.35*(old[i-1]+old[i+1]-2*old[i])
   if allowed(q) and all(allowed(old[i]+(q-old[i])*t) for t in (.25,.5,.75)):p[i]=q
 # Clearance-gated desired body orientation follows the path gently, rather
 # than assuming a circle certifies arbitrary rotation of a long rectangle.
 out=[]
 for i,q in enumerate(p):
  lo=max(0,i-3);hi=min(len(p)-1,i+3);d=p[hi]-p[lo]
  offset=np.clip(math.atan2(d[1],d[0])-math.pi/2,-YAW_MAX,YAW_MAX)
  while abs(offset)>.001 and polygon_collision((q[0],q[1],math.pi/2+offset),BODY,grid,RES):offset*=.5
  yaw=math.pi/2+offset
  if polygon_collision((q[0],q[1],yaw),BODY,grid,RES):return []
  out.append([*q,float(yaw)])
 return out

def target_at(path,pose,distance):
 near=min(range(len(path)),key=lambda i:math.dist(pose[:2],path[i][:2]));i=near;travel=0.
 while i+1<len(path) and travel<distance:
  travel+=math.dist(path[i][:2],path[i+1][:2]);i+=1
 return path[i]
def bounded(desired,previous):
 d=np.array(desired[:2])-previous[:2];norm=np.linalg.norm(d)
 if norm>AMAX*DT:d*=AMAX*DT/norm
 xy=np.array(previous[:2])+d
 w=previous[2]+float(np.clip(desired[2]-previous[2],-ALPHAMAX*DT,ALPHAMAX*DT))
 return [*xy,w]
def run(name,cones,static,out,sensor='normal'):
 pose=tuple(base.START);occ=Occupancy(static,RES);truth=base.raster(static,cones);tris=base.sim.mesh(cones)
 frames=[];path=[];cmd=[0.,0.,0.];stop_since=None;outcome='TIMEOUT';contacts=0;distance=0.;points=[];scan_pose=list(pose);scan_t=0.;lastreceipt=-999;begin=time.monotonic();emergency=0;pending=[];rejected_delays=0;lastacquired=-999
 for step in range(1400):
  t=round(step*DT,6)
  if step%2==0:
   scan_pose=list(pose);scan_t=t
   rr,points=base.sim.raycast(tris,pose)
   if not(sensor=='dropout' and t>=4.):
    pending.append(dict(due=t+(.4 if sensor=='delay' and t>=4. else 0.),acquired=t,sequence=step,ranges=rr,pose=pose))
  due=[x for x in pending if x['due']<=t+1e-9];pending=[x for x in pending if x['due']>t+1e-9]
  for sample in due:
   if t-sample['acquired']>.25+1e-9:rejected_delays+=1;continue
   if occ.update(Scan('curved-slalom',sample['sequence'],str(sample['sequence']+1),'VM_SIM','vm_laser',base.sim.ANGLES,sample['ranges'],8.,t),sample['pose'],t):lastreceipt=t;lastacquired=sample['acquired']
  obs,unknown=occ.masks(t,ttl=2.);grid=obs|unknown;fresh=t-lastreceipt<=.25+1e-9 and t-lastacquired<=.25+1e-9
  if step%10==0 or not path:
   candidate=build_path(pose,grid)
   if candidate:path=candidate
   # Retain previous path only under fresh occupancy and per-command swept checks.
   # Quantization failure is not proof that a feasible current pose is blocked.
  desired=[0.,0.,0.];state='SAFE_WAIT'
  if fresh and path:
   target=target_at(path,pose,LOOKAHEAD)
   dx,dy=target[0]-pose[0],target[1]-pose[1];d=math.hypot(dx,dy)
   speed=min(VMAX,1.5*d)
   if d>1e-9:desired=[speed*dx/d,speed*dy/d,float(np.clip(1.5*(target[2]-pose[2]),-WMAX,WMAX))]
   state='FOLLOWING'
  elif not fresh:state='SENSOR_STALE_HOLD'
  proposed=bounded(desired,cmd)
  # Safety may override acceleration; normal commands obey bounded slew.
  if not fresh or not safe(pose,proposed,.25,grid):
   # Lower translational speed, while allowing a safe return towards upright yaw.
   found=False
   if fresh and path:
    for scale in (.75,.5,.25):
     u=[proposed[0]*scale,proposed[1]*scale,proposed[2]*scale]
     if np.linalg.norm(np.array(u[:2])-cmd[:2])<=AMAX*DT+1e-8 and abs(u[2]-cmd[2])<=ALPHAMAX*DT+1e-8 and safe(pose,u,.25,grid):proposed=u;found=True;break
   if not found:
    if any(abs(x)>1e-8 for x in cmd):emergency+=1
    proposed=[0.,0.,0.];state='COLLISION_HOLD' if fresh else 'SENSOR_STALE_HOLD'
  cmd=proposed;previous=pose
  for j in range(11):contacts+=int(polygon_collision(advance(previous,cmd,DT*j/10),BODY,truth,RES))
  pose=advance(previous,cmd,DT);distance+=math.dist(previous[:2],pose[:2])
  moving=math.hypot(*cmd[:2])+abs(cmd[2])>.001
  stop_since=None if moving else t if stop_since is None else stop_since
  frames.append(dict(t=t,pose_t=round(t+DT,6),pose=list(pose),v=cmd[0]*math.cos(pose[2])+cmd[1]*math.sin(pose[2]),w=cmd[2],vx_world=cmd[0],vy_world=cmd[1],state=state,path=[p[:2] for p in path],path_yaws=[p[2] for p in path],points=points,scan_pose=scan_pose,scan_t=scan_t,sensor_fresh=fresh,receiver_age_s=t-lastreceipt,source_age_s=t-lastacquired))
  if contacts:outcome='CONTACT';break
  if math.dist(pose[:2],base.GOAL)<.06:outcome='GOAL_REACHED';break
  if stop_since is not None and t-stop_since>=3.:outcome='SAFE_WAIT';break
 frames[-1]['controller_state_before_terminal']=frames[-1]['state'];frames[-1]['state']=outcome;frames[-1]['terminal_outcome']=outcome
 scene=json.loads((base.HERE/'results/slalom_5.json').read_text())['scene'];scene.update(cones=cones,controller='observed A* + collision-constrained Laplacian smoothing and orientation-gated bounded holonomic SE2 follower',kinematics='HOLONOMIC PLANAR WITH YAW, NOT PHYSICAL GAIT',parameters=dict(vmax=VMAX,amax=AMAX,wmax=WMAX,angular_accel_max=ALPHAMAX,lookahead=LOOKAHEAD,yaw_offset_limit=YAW_MAX),sensor_mode=sensor)
 met=dict(outcome=outcome,contacts=contacts,sim_time_s=t+DT,path_length_m=distance,emergency_slew_overrides=emergency,rejected_delayed_samples=rejected_delays,wall_time_s=time.monotonic()-begin,yaw_min=min(f['pose'][2] for f in frames),yaw_max=max(f['pose'][2] for f in frames))
 out.mkdir(parents=True,exist_ok=True);result=dict(scene=scene,frames=frames,metrics=met);(out/f'{name}.json').write_text(json.dumps(result,separators=(',',':')));(out/f'{name}_scene_mesh.json').write_text(json.dumps(dict(triangles=tris.tolist(),units='metres',frame='arena_design')));print(name,met,flush=True);return result
if __name__=='__main__':
 static=base.static_grid()
 for n in sys.argv[1:] or ['slalom_5']:
  run(n,base.configs()['slalom_5' if n.startswith('slalom') else n],static,HERE/'results',sensor='dropout' if n.endswith('dropout') else 'delay' if n.endswith('delay') else 'normal')
