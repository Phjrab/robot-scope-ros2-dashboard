"""VM-only clearance-constrained smoothing + bounded holonomic SE(2) follower."""
from pathlib import Path
import sys,json,math,time
import numpy as np
from scipy.ndimage import maximum_filter,distance_transform_edt
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'left_slalom_20261024'))
import simulate_slalom as base
from core import Occupancy,Scan,plan
from collision import Snapshot,polygon_collision
from functools import lru_cache
DT=.1;RES=.01; base.RES=RES; BODY=base.BODY
CLEARANCE=.03; CHECK_BODY=[[-.435,-.31],[.435,-.31],[.435,.31],[-.435,.31]]
VMAX=.16;AMAX=.20;WMAX=.18;ALPHAMAX=.35;LOOKAHEAD=.05;YAW_MAX=.015

def static_grid():
 mask=np.ones((600,800),bool);poly=base.geo.FLOORS['floor_left_straight']
 for iy in range(49,551):
  for ix in range(141):
   if all(base.geo.contains(poly,((ix+a)*RES,(iy+b)*RES)) for a,b in [(0,0),(1,0),(1,1),(0,1),(.5,.5)]):mask[iy,ix]=False
 return mask

def advance(p,u,dt):return tuple(p[i]+u[i]*dt for i in range(3))
def safe(p,u,horizon,grid):
 travel=(math.hypot(u[0],u[1])+abs(u[2])*.493)*horizon;n=max(2,math.ceil(travel/.003))
 return all(not polygon_collision(advance(p,u,horizon*j/n),CHECK_BODY,grid,RES) for j in range(n+1))
def build_path(pose,grid):
 # Fresh owned snapshot and exact-key memoization, discarded on return.
 snapshot=Snapshot(grid,RES)
 expanded=maximum_filter(grid,size=(87,61),mode='constant',cval=1)
 valid=distance_transform_edt(~expanded)*RES>RES*.71
 raw=plan((expanded,np.zeros_like(expanded)),np.ones_like(expanded),pose[:2],base.GOAL,RES,0.)
 if len(raw)<2:return []
 # Smooth only inside the same full-footprint configuration-space corridor.
 # No use of hidden cone truth, no hand-authored waypoint/path insertion.
 p=np.array(raw,float);p[0]=pose[:2]
 def allowed(q):
  return allowed_cached(tuple(q))
 @lru_cache(maxsize=None)
 def allowed_cached(q):
  iy,ix=int(q[1]/RES),int(q[0]/RES)
  return 0<=iy<grid.shape[0] and 0<=ix<grid.shape[1] and valid[iy,ix] and not snapshot.collides((q[0],q[1],math.pi/2),CHECK_BODY)
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
  while abs(offset)>.001 and snapshot.collides((q[0],q[1],math.pi/2+offset),CHECK_BODY):offset*=.5
  yaw=math.pi/2+offset
  if snapshot.collides((q[0],q[1],yaw),CHECK_BODY):
   yaw=math.pi/2
   if snapshot.collides((q[0],q[1],yaw),CHECK_BODY):return []
  out.append([*q,float(yaw)])
 return out

def target_at(path,pose,distance):
 # Orthogonal projection onto the polyline, then continuous arclength lookahead.
 # Removes nearest-vertex jumps; all collision guards remain unchanged.
 q=np.array(pose[:2]);xy=np.array(path)[:,:2];delta=np.diff(xy,axis=0)
 lengths=np.linalg.norm(delta,axis=1);cum=np.r_[0.,np.cumsum(lengths)]
 den=np.maximum(lengths**2,1e-12)
 frac=np.clip(np.sum((q-xy[:-1])*delta,axis=1)/den,0.,1.)
 projections=xy[:-1]+frac[:,None]*delta
 near=int(np.argmin(np.linalg.norm(projections-q,axis=1)))
 progress=float(cum[near]+frac[near]*lengths[near]);target=min(cum[-1],progress+distance)
 i=min(len(lengths)-1,int(np.searchsorted(cum,target,side='right')-1))
 f=(target-cum[i])/max(lengths[i],1e-12)
 return (np.array(path[i])*(1-f)+np.array(path[i+1])*f).tolist()
def bounded(desired,previous):
 d=np.array(desired[:2])-previous[:2];norm=np.linalg.norm(d)
 if norm>AMAX*DT:d*=AMAX*DT/norm
 xy=np.array(previous[:2])+d
 w=previous[2]+float(np.clip(desired[2]-previous[2],-ALPHAMAX*DT,ALPHAMAX*DT))
 return [*xy,w]
def run(name,cones,static,out,sensor='normal'):
 pose=tuple(base.START);occ=Occupancy(static,RES);truth=base.raster(static,cones);tris=base.sim.mesh(cones)
 frames=[];path=[];cmd=[0.,0.,0.];stop_since=None;outcome='TIMEOUT';contacts=0;distance=0.;points=[];scan_pose=list(pose);scan_t=0.;lastreceipt=-999;begin=time.monotonic();emergency=0;pending=[];rejected_delays=0;lastacquired=-999;planning_times=[]
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
  if step%20==0 or not path:
   planning_start=time.monotonic();candidate=build_path(pose,grid);planning_times.append(time.monotonic()-planning_start)
   if candidate:path=candidate
   # Retain previous path only under fresh occupancy and per-command swept checks.
   # Quantization failure is not proof that a feasible current pose is blocked.
  desired=[0.,0.,0.];state='SAFE_WAIT'
  if fresh and path:
   target=target_at(path,pose,LOOKAHEAD)
   dx,dy=target[0]-pose[0],target[1]-pose[1];d=math.hypot(dx,dy)
   speed=min(VMAX,1.5*d,math.sqrt(2*AMAX*max(0.,math.dist(pose[:2],base.GOAL)-.005)))
   if d>1e-9:desired=[speed*dx/d,speed*dy/d,float(np.clip(1.5*(target[2]-pose[2]),-WMAX,WMAX))]
   state='FOLLOWING'
  elif not fresh:state='SENSOR_STALE_HOLD'
  proposed=bounded(desired,cmd)
  # Safety may override acceleration; normal commands obey bounded slew.
  if not fresh or not safe(pose,proposed,.25,grid):
   # Lower translational speed, while allowing a safe return towards upright yaw.
   found=False
   if fresh and path:
    choices=[]
    # Small bounded dynamic-window recovery keeps the whole expanded body safe;
    # no ground-truth cones are consulted and no cached command is replayed.
    for dx in (-AMAX*DT,0.,AMAX*DT):
     for dy in (-AMAX*DT,0.,AMAX*DT):
      if math.hypot(dx,dy)>AMAX*DT+1e-9:continue
      for dw in (-ALPHAMAX*DT,0.,ALPHAMAX*DT):
       u=[cmd[0]+dx,cmd[1]+dy,cmd[2]+dw]
       if math.hypot(*u[:2])>VMAX or u[1]<-1e-9 or abs(u[2])>WMAX or abs(pose[2]+u[2]*.25-math.pi/2)>YAW_MAX:continue
       if safe(pose,u,.25,grid):
        score=sum((u[i]-desired[i])**2 for i in range(2))+.03*(pose[2]+u[2]*.25-math.pi/2)**2+.005*u[2]**2
        choices.append((score,u))
    if choices:proposed=min(choices,key=lambda x:x[0])[1];found=True
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
  if math.dist(pose[:2],base.GOAL)<.025 and math.hypot(*cmd[:2])<=AMAX*DT+1e-9 and abs(cmd[2])<=ALPHAMAX*DT+1e-9:
   stopped=dict(frames[-1]);t=round(t+DT,6);stopped.update(t=t,pose_t=round(t+DT,6),v=0.,w=0.,vx_world=0.,vy_world=0.,state='GOAL_REACHED',receiver_age_s=t-lastreceipt,source_age_s=t-lastacquired,sensor_fresh=t-lastreceipt<=.25+1e-9 and t-lastacquired<=.25+1e-9);frames.append(stopped)
   outcome='GOAL_REACHED';break
  if stop_since is not None and t-stop_since>=3.:outcome='SAFE_WAIT';break
 frames[-1]['controller_state_before_terminal']=frames[-1]['state'];frames[-1]['state']=outcome;frames[-1]['terminal_outcome']=outcome
 scene=json.loads((base.HERE/'results/slalom_5.json').read_text())['scene'];scene.update(cones=cones,grid_resolution_m=RES,configuration_space_expansion_cells=[87,61],collision_guard_footprint=CHECK_BODY,minimum_clearance_constraint_m=CLEARANCE,configuration_space_note='fixed-reference heading candidate expansion; yaw checked with full padded rectangle; exact clearance audited independently',controller='observed A* + collision-constrained Laplacian smoothing and orientation-gated bounded holonomic SE2 follower',kinematics='HOLONOMIC PLANAR WITH YAW, NOT PHYSICAL GAIT',parameters=dict(vmax=VMAX,amax=AMAX,wmax=WMAX,angular_accel_max=ALPHAMAX,lookahead=LOOKAHEAD,yaw_offset_limit=YAW_MAX),sensor_mode=sensor)
 met=dict(planning_calls=len(planning_times),planning_wall_s=sum(planning_times),planning_p95_s=float(np.percentile(planning_times,95)) if planning_times else 0.,outcome=outcome,contacts=contacts,sim_time_s=t+DT,path_length_m=distance,emergency_slew_overrides=emergency,rejected_delayed_samples=rejected_delays,wall_time_s=time.monotonic()-begin,yaw_min=min(f['pose'][2] for f in frames),yaw_max=max(f['pose'][2] for f in frames))
 out.mkdir(parents=True,exist_ok=True);result=dict(scene=scene,frames=frames,metrics=met);(out/f'{name}.json').write_text(json.dumps(result,separators=(',',':')));(out/f'{name}_scene_mesh.json').write_text(json.dumps(dict(triangles=tris.tolist(),units='metres',frame='arena_design')));print(name,met,flush=True);return result
if __name__=='__main__':
 static=static_grid()
 for n in sys.argv[1:] or ['slalom_5']:
  run(n,base.configs()['slalom_5' if n.startswith('slalom') else n],static,HERE/'results',sensor='dropout' if n.endswith('dropout') else 'delay' if n.endswith('delay') else 'normal')
