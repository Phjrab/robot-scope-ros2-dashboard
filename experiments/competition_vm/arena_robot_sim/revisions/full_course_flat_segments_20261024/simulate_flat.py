"""Independent flat-segment closed loop: existing A* + smoothed bounded holonomic follower.
Known static floor map, not LiDAR/SLAM; no terrain or actual sitting simulation.
"""
from pathlib import Path
import sys,json,math,hashlib
import numpy as np
from scipy.ndimage import maximum_filter
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[4]
sys.path.insert(0,str(REPO/'experiments/competition_vm/avoidance'))
from core import plan,polygon,polygon_collision
REV=REPO/'assets/competition-arena/revisions/corridor-parallel-20261024'
SEM=json.loads((REV/'arena.semantic.json').read_text())
BODY=[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]]
RES=.02;DT=.1;VMAX=.16;AMAX=.2;LOOK=.10
RECTS={z['id']:[min(p[0] for p in z['polygon']),min(p[1] for p in z['polygon']),max(p[0] for p in z['polygon']),max(p[1] for p in z['polygon'])] for z in SEM['semantic_zones'] if z['id'] in ['floor_in_bay','floor_out_bay','floor_right_straight','floor_parking_bay']}
def area(p):return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(p,p[1:]+p[:1])))/2 if len(p)>2 else 0.
def clip(p,rect):
 p=[list(q) for q in p]
 for axis,limit,greater in [(0,rect[0],True),(0,rect[2],False),(1,rect[1],True),(1,rect[3],False)]:
  out=[]
  for a,b in zip(p,p[1:]+p[:1]):
   ia=a[axis]>=limit if greater else a[axis]<=limit;ib=b[axis]>=limit if greater else b[axis]<=limit
   if ia:out.append(a)
   if ia!=ib:
    t=(limit-a[axis])/(b[axis]-a[axis]);out.append([a[i]+t*(b[i]-a[i]) for i in range(2)])
  p=out
  if not p:break
 return p
def containment(pose,rects):
 p=polygon(pose,BODY).tolist();return max(0.,area(p)-sum(area(clip(p,r)) for r in rects.values()))
def grid(rects):
 g=np.ones((301,461),bool)
 for iy in range(g.shape[0]):
  for ix in range(g.shape[1]):
   if all(any(r[0]-1e-10<=(ix+a)*RES<=r[2]+1e-10 and r[1]-1e-10<=(iy+b)*RES<=r[3]+1e-10 for r in rects.values()) for a,b in [(0,0),(1,0),(1,1),(0,1),(.5,.5)]):g[iy,ix]=False
 return g
def create_path(pose,goal,g):
 hx=max(abs(q[0]-pose[0]) for q in polygon(pose,BODY));hy=max(abs(q[1]-pose[1]) for q in polygon(pose,BODY))
 exp=maximum_filter(g,size=(2*math.ceil(hy/RES)+3,2*math.ceil(hx/RES)+3),mode='constant',cval=1)
 path=plan((exp,np.zeros_like(g)),np.ones_like(g),pose[:2],goal,RES,0.)
 if len(path)<2:return []
 p=np.array(path,float);p[0]=pose[:2]
 def free(q):
  ix,iy=int(q[0]/RES),int(q[1]/RES)
  return 0<=iy<g.shape[0] and 0<=ix<g.shape[1] and not exp[iy,ix]
 for _ in range(35):
  old=p.copy()
  for i in range(1,len(p)-1):
   q=old[i]+.3*(old[i-1]+old[i+1]-2*old[i])
   if free(q) and all(free(old[i]+t*(q-old[i])) for t in (.25,.5,.75)):p[i]=q
 return p.tolist()
def safe(pose,u,g,rects,horizon):
 n=max(2,math.ceil(math.hypot(*u)*horizon/.003))
 for j in range(n+1):
  p=(pose[0]+u[0]*horizon*j/n,pose[1]+u[1]*horizon*j/n,pose[2])
  if polygon_collision(p,BODY,g,RES) or containment(p,rects)>1e-9:return False
 return True
def run(name,start,goal,apron=False,hold=0):
 rects=dict(RECTS)
 if apron:rects['PROPOSED_OUT_APRON']=[8.,0.,9.2,1.018]
 g=grid(rects);pose=tuple(start);path=create_path(pose,goal,g);cmd=np.array([0.,0.]);frames=[];outcome='TIMEOUT';length=0.;contact=0;samples=0;wait=None;maxacc=0;maxuncovered=0;hold_start=None;arrived=False
 for k in range(1800):
  t=k*DT;desired=np.array([0.,0.]);state='SAFE_WAIT'
  remaining=math.dist(pose[:2],goal)
  if remaining<.055 or arrived:
   arrived=True
   state='DECELERATING_AT_GOAL'
  elif path:
   nearest=min(range(len(path)),key=lambda i:math.dist(path[i],pose[:2]));n=nearest;d=0.
   while n+1<len(path) and d<LOOK:d+=math.dist(path[n],path[n+1]);n+=1
   delta=np.array(path[n])-pose[:2];dist=np.linalg.norm(delta)
   if dist:desired=delta/dist*min(VMAX,1.2*dist)
   state='FOLLOWING'
  change=desired-cmd;norm=np.linalg.norm(change)
  if norm>AMAX*DT:change*=AMAX*DT/norm
  proposed=cmd+change
  # Count kinematic hold only after bounded deceleration has reached zero.
  if arrived and np.linalg.norm(proposed)<1e-8:
   if hold_start is None:hold_start=t
   state='ZERO_COMMAND_HOLD' if hold else 'GOAL_REACHED'
  if not safe(pose,proposed,g,rects,.3):proposed[:]=0;state='COLLISION_HOLD'
  maxacc=max(maxacc,float(np.linalg.norm(proposed-cmd)/DT));old=pose;cmd=proposed
  n=max(2,math.ceil(np.linalg.norm(cmd)*DT/.001))
  for j in range(n+1):
   p=(pose[0]+cmd[0]*DT*j/n,pose[1]+cmd[1]*DT*j/n,pose[2]);un=containment(p,rects);maxuncovered=max(maxuncovered,un);contact+=int(polygon_collision(p,BODY,g,RES) or un>1e-9);samples+=1
  pose=(pose[0]+cmd[0]*DT,pose[1]+cmd[1]*DT,pose[2]);length+=math.dist(old[:2],pose[:2])
  frames.append({'t':round(t,6),'pose_t':round(t+DT,6),'pose':pose,'vx_world':float(cmd[0]),'vy_world':float(cmd[1]),'w':0.,'v':float(cmd[0]*math.cos(pose[2])+cmd[1]*math.sin(pose[2])),'state':state,'path':path})
  if contact:outcome='CONTACT';break
  if hold_start is not None and t-hold_start>=hold-1e-9:outcome='POSITION_AND_HOLD_COMPLETE' if hold else 'GOAL_REACHED';break
  if np.linalg.norm(cmd)<1e-9 and hold_start is None:
   wait=t if wait is None else wait
   if t-wait>=3:outcome='SAFE_WAIT';break
  else:wait=None
 frames[-1]['state']=outcome;frames[-1]['terminal_outcome']=outcome
 parked=all(6.5<=x<=8 and 2.25<=y<=3.75 for x,y in polygon(pose,BODY)) if name=='parking' else None
 rear=float(min(p[0] for p in polygon(pose,BODY))) if name=='out' else None
 result={'scene':{'start':start,'goal':goal,'footprint':BODY,'cones':[],'arena_revision':SEM['revision'],'rectangles':rects,'allowed_floor_polygons':{n:[[r[0],r[1]],[r[2],r[1]],[r[2],r[3]],[r[0],r[3]]] for n,r in rects.items()},'controller':'existing VM A* + clearance constrained Laplacian smoothing + bounded holonomic follower','pose_source':'SIM_GT','sensing':'known static map, NO sensor validation','parameters':{'vmax_m_s':VMAX,'amax_m_s2':AMAX,'dt_s':DT,'lookahead_m':LOOK,'yaw':'fixed per segment'},'terrain':'not executed','parking_sit':'not simulated','opening':'PROPOSED, x=8 and y=0..1.018; scene-only outside apron' if apron else None},'frames':frames,'metrics':{'outcome':outcome,'sim_time_s':round(t+DT,6),'path_length_m':length,'swept_checks':samples,'violations':contact,'max_uncovered_area_m2':maxuncovered,'parking_full_body_contained':parked,'kinematic_zero_command_hold_s':round(t-hold_start,6) if hold_start is not None else None,'physical_stopping_evidence':False,'exit_body_rear_x':rear,'whole_body_beyond_proposed_exit_plane':rear>8 if rear else None,'full_course_success':False,'max_velocity_slew_m_s2':maxacc}}
 out=HERE/'output';out.mkdir(exist_ok=True);(out/f'{name}.json').write_text(json.dumps(result,separators=(',',':')));print(name,result['metrics'],flush=True);return result
if __name__=='__main__':
 run('in',[7.4,5.49,math.pi],[6.1,5.49])
 parking=run('parking',[5.99,2.,math.pi/2],[7.25,3.],hold=5.)
 run('out',parking['frames'][-1]['pose'],[8.6,.509],apron=True)

if __name__=='__main__':
 run('out_closed',parking['frames'][-1]['pose'],[8.6,.509],apron=False)
