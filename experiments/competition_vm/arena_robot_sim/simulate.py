"""Actual-arena, closed-loop planar kinematic simulation. Not SLAM or gait physics."""
import sys,json,math,time
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT.parent/'avoidance'))
from core import Occupancy,Scan,plan,propagate,swept_safe,polygon_collision,polygon
sys.path.insert(0,str(REPO/'assets/competition-arena/revisions/rulebook-20261015'))
import geometry
RES=.04
# Conservative symmetric bounding rectangle of actual standing FK mesh.
FOOTPRINT=[[-.358,-.162],[.358,-.162],[.358,.162],[-.358,.162]]
ANGLES=np.linspace(-math.pi,math.pi,360,endpoint=False)
HEIGHTS=[.025,.10,.20,.35]

def quad(a,b,c,d):return [[a,b,c],[a,c,d]]
def cone_mesh(c):
 x,y=c['xy'];s=c['base_side_m']/2;h=c['base_height_m'];r=c['radius_m'];top=c['height_m'];out=[]
 corners=[[x-s,y-s],[x+s,y-s],[x+s,y+s],[x-s,y+s]]
 for a,b in zip(corners,corners[1:]+corners[:1]):out+=quad([*a,0],[*b,0],[*b,h],[*a,h])
 out+=quad([*corners[0],h],[*corners[1],h],[*corners[2],h],[*corners[3],h])
 for i in range(32):
  a=2*math.pi*i/32;b=2*math.pi*(i+1)/32
  out.append([[x+r*math.cos(a),y+r*math.sin(a),h],[x+r*math.cos(b),y+r*math.sin(b),h],[x,y,top]])
 return out

def mesh(cones):
 walls=json.load(open(Path(geometry.__file__).parent/'collision/virtual_fences.json'))['walls'];tris=[]
 for w in walls:
  a,b=w['a'],w['b'];tris+=quad([*a,0],[*b,0],[*b,w['height_m']],[*a,w['height_m']])
 for c in cones:tris+=cone_mesh(c)
 return np.array(tris,float)

def raycast(tris,pose):
 """Two-sided Moller-Trumbore intersections against exact rendered cone/base/fences."""
 ray=ANGLES+pose[2];d=np.stack([np.cos(ray),np.sin(ray),np.zeros(len(ray))],axis=1)
 e1=tris[:,1]-tris[:,0];e2=tris[:,2]-tris[:,0]
 p=np.cross(d[:,None,:],e2[None,:,:]);det=np.sum(e1[None,:,:]*p,axis=2)
 inv=np.divide(1.,det,out=np.zeros_like(det),where=abs(det)>1e-10)
 ranges=[];points=[]
 for ring,z in enumerate(HEIGHTS):
  o=np.array([pose[0],pose[1],z]);tv=o-tris[:,0];u=np.sum(tv[None,:,:]*p,axis=2)*inv;q=np.cross(tv,e1)
  v=np.sum(d[:,None,:]*q[None,:,:],axis=2)*inv;t=np.sum(e2*q,axis=1)[None,:]*inv
  valid=(abs(det)>1e-10)&(u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)&(t>.02)&(t<8)
  rr=np.min(np.where(valid,t,8.),axis=1);ranges.append(rr)
  for j in range(0,len(ray),3):
   if rr[j]<8:points.append([float(o[0]+d[j,0]*rr[j]),float(o[1]+d[j,1]*rr[j]),z,ring])
 return np.min(ranges,axis=0),points

def static_grid():
 mask=np.ones((150,200),bool)
 terrain=[z['polygon'] for z in geometry.zones() if z['type'] in ('RAMP','STAIRS')]+[geometry.FLOORS['floor_center_base']]
 # Cell center AND corners must be in floor union; terrain cell touches remain blocked.
 for iy in range(150):
  for ix in range(200):
   samples=[((ix+a)*RES,(iy+b)*RES) for a,b in [(0,0),(1,0),(1,1),(0,1),(.5,.5)]]
   if all(any(geometry.contains(poly,p) for poly in geometry.FLOORS.values()) for p in samples) and not any(geometry.contains(poly,p) for poly in terrain for p in samples):mask[iy,ix]=False
 return mask

def exact_planar_clearance(pose,cones):
    robot=polygon(pose,FOOTPRINT)
    walls=json.loads((Path(geometry.__file__).parent/'collision/virtual_fences.json').read_text())['walls']
    segments=[(w['a'],w['b']) for w in walls]
    for c in cones:
        x,y=c['xy'];h=c['base_side_m']/2
        corners=[[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]]
        segments.extend(zip(corners,corners[1:]+corners[:1]))
    def ptseg(p,a,b):
        p,a,b=map(np.asarray,(p,a,b));v=b-a
        t=np.clip(np.dot(p-a,v)/np.dot(v,v),0,1)
        return float(np.linalg.norm(p-(a+t*v)))
    result=float('inf')
    for a,b in zip(robot,np.roll(robot,-1,axis=0)):
        for c,d in segments:
            result=min(result,ptseg(a,c,d),ptseg(b,c,d),ptseg(c,a,b),ptseg(d,a,b))
    return result

def run(name,static):
 cones=[]
 def cone(i,x,y):return dict(id=f'cone_{i}',xy=[x,y],radius_m=.12,height_m=.32,base_side_m=.26,base_height_m=.04)
 if name=='cone_detour':cones=[cone(1,5.70,3.)]
 if name=='blocked':cones=[cone(i,x,2.4) for i,x in enumerate([5.60,5.86,6.12,6.38])]
 start=[5.99,1.65,math.pi/2];goal=[5.99,4.35];pose=tuple(start);tris=mesh(cones);occ=Occupancy(static,RES);radius=max(math.hypot(*p) for p in FOOTPRINT)
 truth=static.copy()
 for c in cones:
  x,y=c['xy'];s=c['base_side_m']/2
  for iy in range(max(0,int((y-s)/RES)),min(150,int((y+s)/RES)+1)):
   for ix in range(max(0,int((x-s)/RES)),min(200,int((x+s)/RES)+1)):truth[iy,ix]=True
 frames=[];path=[];distance=0.;contacts=0;minclear=99.;begin=time.time();outcome='TIMEOUT';points=[]
 for step in range(900):
  t=step*.1
  if step%2==0:
   scan_pose=list(pose);scan_t=t;ranges,points=raycast(tris,pose);occ.update(Scan('arena',step,str(step+1),'VM_SIM','vm_laser',ANGLES,ranges,8.,t),pose,t)
  obstacles,unknown=occ.masks(t,ttl=2.);collision=obstacles|unknown
  if step%5==0:path=plan((obstacles,unknown),~static,pose[:2],goal,RES,radius)
  v=w=0.;state='SAFE_WAIT'
  if path:
   nearest=min(range(len(path)),key=lambda i:math.dist(pose[:2],path[i]));target=path[min(nearest+2,len(path)-1)]
   error=(math.atan2(target[1]-pose[1],target[0]-pose[0])-pose[2]+math.pi)%(2*math.pi)-math.pi
   w=max(-.6,min(.6,error*2));v=.18*max(0,1-abs(error)/.7);state='FOLLOWING'
   if not swept_safe(pose,v,w,.5,FOOTPRINT,collision,RES):v=w=0.;state='COLLISION_HOLD'
  old=pose;pose=propagate(pose,v,w,.1);distance+=math.dist(old[:2],pose[:2])
  contact=polygon_collision(pose,FOOTPRINT,truth,RES);contacts+=int(contact)
  clearance=distance_transform_edt(~truth)[int(pose[1]/RES),int(pose[0]/RES)]*RES-radius;minclear=min(minclear,float(clearance))
  if step%2==0:frames.append(dict(t=round(t,3),pose_t=round(t+.1,3),pose=list(pose),v=v,w=w,state=state,path=path,points=points,scan_pose=scan_pose,scan_t=scan_t))
  if contact:outcome='CONTACT';break
  if math.dist(pose[:2],goal)<.12:outcome='GOAL_REACHED';break
  if name=='blocked' and t>=6 and not path:outcome='SAFE_WAIT';break
 if not frames or frames[-1]['t']!=round(t,3):frames.append(dict(t=round(t,3),pose_t=round(t+.1,3),pose=list(pose),v=v,w=w,state=state,path=path,points=points,scan_pose=scan_pose,scan_t=scan_t))
 frames[-1]['terminal_outcome']=outcome
 frames[-1]['controller_state_before_terminal']=frames[-1]['state']
 frames[-1]['state']=outcome
 straight_contacts=sum(polygon_collision((start[0],yy,start[2]),FOOTPRINT,truth,RES) for yy in np.linspace(start[1],goal[1],200))
 metrics=dict(straight_reference_contact_samples=straight_contacts,outcome=outcome,contacts=contacts,sim_time_s=t,path_length_m=distance,min_grid_circumscribed_clearance_proxy_m=minclear, min_sampled_planar_envelope_edge_clearance_m=min(exact_planar_clearance(f['pose'],cones) for f in frames), clearance_sample_hz=5,wall_time_s=time.time()-begin,expected='SAFE_WAIT' if name=='blocked' else 'GOAL_REACHED')
 metrics['pass']=metrics['outcome']==metrics['expected'] and contacts==0
 scene=dict(start=start,goal=goal,cones=cones,footprint=FOOTPRINT,arena_revision=geometry.REV,pose_source='SIM_GT_NOT_SLAM',sensor='four-height horizontal virtual LiDAR, exact triangle intersections',sensor_heights_m=HEIGHTS,kinematics='planar differential chassis; no contact dynamics or gait validation',course_scope='right straight and parking extension only; not competition route compliance',allowed_floor_polygons=geometry.FLOORS,terrain_handoff_polygons=[z['polygon'] for z in geometry.zones() if z['type'] in ('RAMP','STAIRS')],routing_permissions='PROVISIONAL_LOCAL_DEMONSTRATION_NOT_COMPETITION_APPROVAL',footprint_source='rendering/standing_bounds.json; symmetric outward rounding to .358/.162 m',lidar_limitations='Ideal noiseless synthetic stacked horizontal planes, not calibrated Unitree LiDAR; ground plane known; SIM_GT pose; full cone/base visual triangles used')
 result=dict(scene=scene,frames=frames,metrics=metrics)
 (ROOT/'results'/f'{name}.json').write_text(json.dumps(result,separators=(',',':')))
 (ROOT/'results'/f'{name}_scene_mesh.json').write_text(json.dumps(dict(triangles=tris.tolist(),units='metres',frame='arena_design')))
 print(name,metrics,flush=True);return metrics
if __name__=='__main__':
 static=static_grid();np.save(ROOT/'results'/'static_grid.npy',static)
 results=[run(n,static) for n in (sys.argv[1:] or ['empty','cone_detour','blocked'])]
 (ROOT/'results'/'metrics.json').write_text(json.dumps(results,indent=2))
