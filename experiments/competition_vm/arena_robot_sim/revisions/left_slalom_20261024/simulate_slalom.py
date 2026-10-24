"""Offline left slalom: existing observed-grid A*, fixed-yaw holonomic kinematic plant.
NOT Nav2, gait dynamics, calibrated LiDAR, or real robot control.
"""
from pathlib import Path
import importlib.util,sys,json,math,time,hashlib
import numpy as np
from scipy.ndimage import maximum_filter
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1];REPO=BASE.parents[2]
sys.path.insert(0,str(BASE));import simulate as sim
sys.path.insert(0,str(BASE.parent/'avoidance'))
from core import Occupancy,Scan,plan,polygon_collision,polygon,sat_overlap
spec=importlib.util.spec_from_file_location('corrected_geometry',REPO/'assets/competition-arena/revisions/corridor-parallel-20261024/geometry.py');geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
sim.geometry=geo
RES=.02; DT=.1; SEED=20261024
BODY=[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]]
START=[.5,.95,math.pi/2];GOAL=[.5,5.05]
# A* circle is candidate-center margin only, NOT the full robot collision shape.
CANDIDATE_RADIUS=.225

def cone(i,x,y):return dict(id=f'cone_{i:02}',xy=[x,y],radius_m=.12,height_m=.32,base_side_m=.26,base_height_m=.04)
def configs():
 return {'empty':[], 'slalom_3':[cone(i+1,x,y) for i,(x,y) in enumerate([(.18,1.8),(.82,3.0),(.18,4.2)])],
 'slalom_5':[cone(i+1,x,y) for i,(x,y) in enumerate([(.18,1.55),(.18,1.83),(.82,3.0),(.82,3.28),(.18,4.45)])],
 'blocked_5':[cone(i+1,x,y) for i,(x,y) in enumerate([(.15,2.5),(.50,2.5),(.85,2.5),(.18,3.5),(.82,4.5)])]}
def static_grid():
 mask=np.ones((300,400),bool);poly=geo.FLOORS['floor_left_straight']
 for iy in range(24,276):
  for ix in range(0,71):
   if all(geo.contains(poly,((ix+a)*RES,(iy+b)*RES)) for a,b in [(0,0),(1,0),(1,1),(0,1),(.5,.5)]):mask[iy,ix]=False
 return mask

def raster(mask,cones):
 out=mask.copy()
 for c in cones:
  x,y=c['xy'];h=c['base_side_m']/2
  for iy in range(int((y-h)/RES),int((y+h)/RES)+1):
   for ix in range(int((x-h)/RES),int((x+h)/RES)+1):out[iy,ix]=True
 return out

def interpolate(p,vx,vy,dt):return (p[0]+vx*dt,p[1]+vy*dt,p[2])
def safe(p,vx,vy,dt,mask):
 n=max(2,int(math.hypot(vx,vy)*dt/.004)+1)
 return all(not polygon_collision(interpolate(p,vx,vy,dt*i/n),BODY,mask,RES) for i in range(n+1))
def run(name,cones,static,out):
 begin=time.monotonic();pose=tuple(START);occ=Occupancy(static,RES);truth=raster(static,cones);tris=sim.mesh(cones)
 frames=[];path=[];distance=0.;stop_since=None;outcome='TIMEOUT';contacts=0;points=[];scan_pose=list(pose);scan_t=0.;last=None
 for step in range(1000):
  t=round(step*DT,6)
  if step%2==0:
   scan_pose=list(pose);scan_t=t;rr,points=sim.raycast(tris,pose)
   assert occ.update(Scan('left-slalom',step,str(step+1),'VM_SIM','vm_laser',sim.ANGLES,rr,8.,t),pose,t)
  obs,unknown=occ.masks(t,ttl=2.);collision=obs|unknown
  if step%5==0:
   # Fixed yaw permits conservative axis-aligned Minkowski expansion. Existing A* unchanged.
   expanded=maximum_filter(collision,size=(43,31),mode='constant',cval=1)
   path=plan((expanded,np.zeros_like(expanded)),np.ones_like(expanded),pose[:2],GOAL,RES,0.)
  vx=vy=0.;state='SAFE_WAIT'
  if path:
   nearest=min(range(len(path)),key=lambda i:math.dist(pose[:2],path[i]));target=path[min(nearest+2,len(path)-1)]
   dx,dy=target[0]-pose[0],target[1]-pose[1];d=math.hypot(dx,dy)
   if d>1e-10:vx,vy=.16*dx/d,.16*dy/d
   state='FOLLOWING'
   if not safe(pose,vx,vy,.3,collision):vx=vy=0.;state='COLLISION_HOLD'
  previous=pose
  # Independent ground-truth guard is evaluation only, never informs planner.
  for j in range(6):contacts+=int(polygon_collision(interpolate(previous,vx,vy,DT*j/5),BODY,truth,RES))
  pose=interpolate(previous,vx,vy,DT);distance+=math.dist(previous[:2],pose[:2])
  if math.hypot(vx,vy)<1e-9:stop_since=t if stop_since is None else stop_since
  else:stop_since=None
  f=dict(t=t,pose_t=round(t+DT,6),pose=list(pose),v=vy,w=0.,vx_world=vx,vy_world=vy,state=state,path=path,points=points,scan_pose=scan_pose,scan_t=scan_t)
  frames.append(f)
  if contacts:outcome='CONTACT';break
  if math.dist(pose[:2],GOAL)<.06:outcome='GOAL_REACHED';break
  if stop_since is not None and t-stop_since>=3.:outcome='SAFE_WAIT';break
 frames[-1]['controller_state_before_terminal']=frames[-1]['state'];frames[-1]['state']=outcome;frames[-1]['terminal_outcome']=outcome
 scene=dict(start=START,goal=GOAL,cones=cones,footprint=BODY,arena_revision=geo.REV,pose_source='SIM_GT_NOT_SLAM',seed=SEED,controller='observed-grid A* candidate path + fixed-yaw holonomic point follower, full rectangle swept guard',kinematics='HOLONOMIC PLANAR, no dynamics or gait validation',course_scope='LEFT SLALOM ONLY; no terrain/parking/full-lap qualification',allowed_floor_polygons={'floor_left_straight':geo.FLOORS['floor_left_straight']},sensor='ideal four-height first-hit virtual LiDAR',sensor_heights_m=sim.HEIGHTS,candidate_radius_m=0.,configuration_space_expansion_cells=[43,31],configuration_space_note='fixed-yaw rectangular envelope Minkowski expansion plus A* cell margin; not circumscribed body radius',full_collision_footprint_source='animated-joint worker proposed conservative .405 longitudinal/.28 transverse; final FK audit required',routing_permissions='PROVISIONAL_VM_ONLY')
 metrics=dict(outcome=outcome,contacts=contacts,sim_time_s=round(t+DT,6),path_length_m=distance,wall_time_s=time.monotonic()-begin,seed=SEED,count=len(cones),x_min=min(f['pose'][0] for f in frames),x_max=max(f['pose'][0] for f in frames))
 result=dict(scene=scene,frames=frames,metrics=metrics)
 out.mkdir(parents=True,exist_ok=True);(out/f'{name}.json').write_text(json.dumps(result,separators=(',',':')))
 (out/f'{name}_scene_mesh.json').write_text(json.dumps(dict(triangles=tris.tolist(),units='metres',frame='arena_design')))
 print(name,metrics,flush=True);return result
if __name__=='__main__':
 out=HERE/'results';static=static_grid()
 for n in sys.argv[1:] or configs():run(n,configs()[n],static,out)
