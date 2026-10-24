"""D0: existing planar controller regression, not a new planner or full-course sim.
No hardware interfaces. Immutable old experiments are only read.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, sys, time
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
import simulate as old
from core import Occupancy, Scan, plan, propagate, swept_safe, polygon_collision, polygon, sat_overlap
SEED=20261024
START=[5.99,1.65,math.pi/2]
GOAL=[5.99,4.35]
DT=.1
SCAN_PERIOD=.2
SOURCE_AGE_MAX=.25
RECEIVER_TTL=.25
BODY=old.FOOTPRINT
RADIUS=max(math.hypot(*p) for p in BODY)
WALLS=json.loads((Path(old.geometry.__file__).parent/'collision/virtual_fences.json').read_text())['walls']


def cone(i,x,y):
 return dict(id=f'cone_{i:02}',xy=[x,y],radius_m=.12,height_m=.32,base_side_m=.26,base_height_m=.04)


def scenarios():
 rows=[(x,y) for y in (2.4,3.2) for x in (5.60,5.86,6.12,6.38,7.0)]
 defs=[('empty_0',[]),('offset_1',[(5.70,3.)]),('center_1',[(5.99,3.)]),('historical_575_1',[(5.75,3.)]),
       ('boundary_1',[(5.62,3.)]),('alternating_2',[(5.70,2.7),(6.30,3.6)]),
       ('occluded_2',[(5.99,2.65),(5.99,3.25)]),
       ('blocked_5',rows[:4]+[(5.99,3.6)]),('dense_10',rows)]
 for name,coords in defs:
  yield dict(name=name,seed=SEED,cones=[cone(i+1,*p) for i,p in enumerate(coords)],sensor='normal',baked_ids=[])
 yield dict(name='delayed_offset_1',seed=SEED,cones=[cone(1,5.70,3.)],sensor='delayed',baked_ids=[])
 yield dict(name='dropout_offset_1',seed=SEED,cones=[cone(1,5.70,3.)],sensor='dropout',baked_ids=[])
 yield dict(name='mapped_center_1',seed=SEED,cones=[cone(1,5.99,3.)],sensor='normal',baked_ids=['cone_01'])


def triangles(cones):
 """Real existing fence/cone meshes plus all existing terrain first-hit occluders."""
 tris=list(old.mesh(cones))
 path=Path(old.geometry.__file__).parent/'collision/terrain_meshes.json'
 for solid in json.loads(path.read_text())['closed_solids']:
  vv=solid['vertices']
  for face in solid['faces']:
   for i in range(1,len(face)-1):tris.append([vv[face[0]],vv[face[i]],vv[face[i+1]]])
 return np.array(tris,float)


def raster_cones(grid,cones):
 out=grid.copy()
 for c in cones:
  x,y=c['xy'];h=c['base_side_m']/2
  for iy in range(max(0,int((y-h)/old.RES)),min(out.shape[0],int((y+h)/old.RES)+1)):
   for ix in range(max(0,int((x-h)/old.RES)),min(out.shape[1],int((x+h)/old.RES)+1)):out[iy,ix]=True
 return out


def allowed_grid(static,strict):
 out=static.copy()
 if strict:
  # The stage is NAVIGATE, not PARK. Forbid every cell intersecting parking.
  park=old.geometry.FLOORS['floor_parking_bay'];x0=min(p[0] for p in park);x1=max(p[0] for p in park);y0=min(p[1] for p in park);y1=max(p[1] for p in park)
  for iy in range(out.shape[0]):
   for ix in range(out.shape[1]):
    if ix*old.RES<=x1 and (ix+1)*old.RES>=x0 and iy*old.RES<=y1 and (iy+1)*old.RES>=y0:out[iy,ix]=True
 return out


def edge_distance(a,b,c,d):
 def ptseg(p,a,b):
  vx,vy=b[0]-a[0],b[1]-a[1]
  u=min(1.,max(0.,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/max(vx*vx+vy*vy,1e-30)))
  return math.hypot(p[0]-a[0]-u*vx,p[1]-a[1]-u*vy)
 # Segment crossing must return zero; old helper missed intersecting edges.
 def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 if cross(a,b,c)*cross(a,b,d)<=0 and cross(c,d,a)*cross(c,d,b)<=0 and max(min(a[0],b[0]),min(c[0],d[0]))<=min(max(a[0],b[0]),max(c[0],d[0])) and max(min(a[1],b[1]),min(c[1],d[1]))<=min(max(a[1],b[1]),max(c[1],d[1])):return 0.
 return min(ptseg(a,c,d),ptseg(b,c,d),ptseg(c,a,b),ptseg(d,a,b))


def geometry_checks(pose,cones,strict):
 """Exact convex cone/parking intersection and fence segment checks.
 Floor/terrain containment is additionally conservatively checked against the raster.
 """
 p=polygon(pose,BODY);edges=list(zip(p,np.roll(p,-1,axis=0)))
 walls=WALLS
 clearance=math.inf;contacts=[]
 for w in walls:
  dist=min(edge_distance(a,b,w['a'],w['b']) for a,b in edges)
  clearance=min(clearance,dist)
  if dist<=1e-10:contacts.append(w['id'])
 for c in cones:
  x,y=c['xy'];h=c['base_side_m']/2;b=np.array([[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]])
  overlap=sat_overlap(p,b)
  dist=0. if overlap else min(edge_distance(a,z,c0,c1) for a,z in edges for c0,c1 in zip(b,np.roll(b,-1,axis=0)))
  clearance=min(clearance,dist)
  if overlap:contacts.append(c['id'])
 parking=bool(sat_overlap(p,np.array(old.geometry.FLOORS['floor_parking_bay'])))
 return dict(physical_contacts=contacts,parking_overlap=parking,forbidden_parking=parking and strict,polygon_edge_clearance_m=clearance)


def run(case,static,strict):
 begin=time.monotonic();cones=case['cones'];policy='strict_no_parking' if strict else 'legacy_parking_allowed'
 allowed=allowed_grid(static,strict)
 known=raster_cones(allowed,[c for c in cones if c['id'] in case['baked_ids']])
 truth=raster_cones(allowed,cones);edt=distance_transform_edt(~truth)*old.RES
 occ=Occupancy(known,old.RES);tris=triangles(cones);pose=tuple(START);path=[];frames=[]
 last_scan=-math.inf;last_source=-math.inf;scan_pose=list(pose);points=[];scan_t=None;last_progress=0.;distance=0.;minproxy=99.;minexact=99.
 swept_contacts=0;forbidden_count=0;physical_contacts=0;rejected_scans=0;accepted_scans=0;parking_samples=0;interpolated=0
 outcome='TIMEOUT';reason='TIME_BUDGET';states={};attempts=0;pending=[]
 for step in range(400):
  t=round(step*DT,9)
  if step%2==0:
   scan_pose=list(pose);scan_t=t;ranges,points=old.raycast(tris,pose)
   missing=case['sensor']=='dropout' and 1.<=t<=4.
   if missing:rejected_scans+=1
   else:
    latency=.4 if case['sensor']=='delayed' and t>=1. else 0.
    pending.append(dict(due=round(t+latency,9),acquired=t,sequence=step,ranges=ranges,pose=tuple(pose)))
  # Real delayed sample queue: receiver time is not acquisition/source time.
  due=[sample for sample in pending if sample['due']<=t+1e-9]
  pending=[sample for sample in pending if sample['due']>t+1e-9]
  for sample in due:
   source_age=t-sample['acquired']
   if source_age>SOURCE_AGE_MAX:rejected_scans+=1
   elif occ.update(Scan('d0',sample['sequence'],str(round(sample['acquired']*1e9)+1),'VM_SIM','vm_laser',old.ANGLES,sample['ranges'],8.,t),sample['pose'],t):
    last_scan=t;last_source=sample['acquired'];accepted_scans+=1
   else:rejected_scans+=1
  fresh=(0<=t-last_scan<=RECEIVER_TTL and 0<=t-last_source<=SOURCE_AGE_MAX)
  obs,unknown=occ.masks(t,ttl=2.);collision=obs|unknown
  if step%5==0:
   path=plan((obs,unknown),~allowed,pose[:2],GOAL,old.RES,RADIUS);attempts+=1
  v=w=0.;state='SAFE_WAIT'
  if not fresh:state='SENSOR_STALE_HOLD'
  elif path:
   nearest=min(range(len(path)),key=lambda i:math.dist(pose[:2],path[i]));target=path[min(nearest+2,len(path)-1)]
   error=(math.atan2(target[1]-pose[1],target[0]-pose[0])-pose[2]+math.pi)%(2*math.pi)-math.pi
   w=max(-.6,min(.6,error*2));v=.18*max(0,1-abs(error)/.7);state='FOLLOWING'
   if not swept_safe(pose,v,w,.5,BODY,collision,old.RES):v=w=0.;state='COLLISION_HOLD'
  old_pose=pose
  # Dense audit between control ticks. This is evaluator truth, NOT planner input.
  samples=[propagate(old_pose,v,w,DT*j/5) for j in range(6)]
  for p in samples:
   interpolated+=1
   grid_contact=polygon_collision(p,BODY,truth,old.RES)
   check=geometry_checks(p,cones,strict)
   swept_contacts+=int(grid_contact);physical_contacts+=int(bool(check['physical_contacts']));forbidden_count+=int(check['forbidden_parking']);parking_samples+=int(check['parking_overlap'])
   minexact=min(minexact,check['polygon_edge_clearance_m'])
  pose=samples[-1];delta=math.dist(old_pose[:2],pose[:2]);distance+=delta
  if abs(v)>1e-9 or abs(w)>1e-9:last_progress=t
  proxy=float(edt[int(pose[1]/old.RES),int(pose[0]/old.RES)]-RADIUS);minproxy=min(minproxy,proxy)
  states[state]=states.get(state,0)+1
  frames.append(dict(t=t,pose_t=round(t+DT,9),pose=list(pose),v=v,w=w,state=state,path=path if step%5==0 else None,points=points if step%2==0 else [],scan_pose=scan_pose,scan_t=scan_t,sensor_fresh=fresh))
  if swept_contacts or physical_contacts or forbidden_count:outcome='CONTACT';reason='GEOMETRY_VIOLATION';break
  if math.dist(pose[:2],GOAL)<.12:outcome='GOAL_REACHED';reason='PLANAR_GOAL_TOLERANCE';break
  if t-last_progress>=6.-1e-9:
   outcome='SAFE_WAIT';reason='SENSOR_STALE' if not fresh else 'NO_SAFE_PATH' if not path else 'TRACKING_SWEEP_BLOCKED';break
 frames[-1]['controller_state_before_terminal']=frames[-1]['state'];frames[-1]['state']=outcome;frames[-1]['terminal_outcome']=outcome
 metrics=dict(outcome=outcome,reason=reason,sim_time_s=t+DT,path_length_m=distance,interpolated_pose_samples=interpolated,swept_grid_contact_samples=swept_contacts,exact_cone_fence_contact_samples=physical_contacts,forbidden_parking_samples=forbidden_count,legacy_parking_overlap_samples=parking_samples,min_grid_circumscribed_clearance_proxy_m=minproxy,min_sampled_polygon_edge_clearance_m=minexact,accepted_scans=accepted_scans,rejected_scans=rejected_scans,states=states,planner_attempts=attempts)
 # A safe wait is an acceptable safety result, not goal success.
 metrics['safety_pass']=not(swept_contacts or physical_contacts or forbidden_count) and outcome in ('GOAL_REACHED','SAFE_WAIT')
 scene=dict(name=case['name'],seed=case['seed'],policy=policy,start=START,goal=GOAL,footprint=BODY,cones=cones,obstacle_count=len(cones),known_static_cone_ids=case['baked_ids'],sensor_mode=case['sensor'],pose_source='SIM_GT',evidence='SYNTHETIC/PLANAR',source_age_max_s=SOURCE_AGE_MAX,receiver_ttl_s=RECEIVER_TTL,control_dt_s=DT,swept_audit_substeps=5,planner='existing vm_astar_rotate_follow with circumscribed radius unchanged',floor_polygons=old.geometry.FLOORS,terrain_policy='BLOCKED_NOT_TRAVERSED',no_full_course_claim=True)
 result=dict(scene=scene,frames=frames,metrics=metrics)
 canonical=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
 return result,hashlib.sha256(canonical).hexdigest(),time.monotonic()-begin


def historical_audit():
 result={}
 static=old.static_grid();strict=allowed_grid(static,True)
 for name in ('empty','cone_detour','blocked'):
  path=ROOT/'results'/f'{name}.json';doc=json.loads(path.read_text());bad=0;maxintrusion=0.
  for f in doc['frames']:
   p=polygon(f['pose'],BODY)
   check=geometry_checks(f['pose'],doc['scene']['cones'],True)
   bad+=int(check['forbidden_parking'])
   if check['parking_overlap']:maxintrusion=max(maxintrusion,max(p[:,0])-6.5)
  result[name]=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),stored_outcome=doc['metrics']['outcome'],strict_parking_violation_frame_samples=bad,max_footprint_x_intrusion_m=maxintrusion,legacy_record_preserved=True)
 return result


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--only',default='');ap.add_argument('--policies',default='strict,legacy');args=ap.parse_args()
 out=HERE/'results';out.mkdir(exist_ok=True);static=old.static_grid();summary=[]
 chosen=[c for c in scenarios() if not args.only or c['name'] in args.only.split(',')]
 for case in chosen:
  for strict in ([True,False] if args.policies=='strict,legacy' else [args.policies=='strict']):
   results=[];hashes=[];times=[]
   for repeat in (1,2):
    result,digest,wall=run(case,static,strict);results.append(result);hashes.append(digest);times.append(wall)
    name=f"{case['name']}__{result['scene']['policy']}__repeat{repeat}.json"
    (out/name).write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(name,result['metrics']['outcome'],round(wall,2),flush=True)
   row=dict(case=case['name'],policy=results[0]['scene']['policy'],count=len(case['cones']),metrics=results[0]['metrics'],repeat_sha256=hashes,reproducible=hashes[0]==hashes[1],wall_seconds=times)
   summary.append(row)
   (out/'summary_partial.json').write_text(json.dumps(summary,indent=2)+'\n')
 (out/'summary.json').write_text(json.dumps(dict(base_commit='7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a',seed=SEED,evidence='SYNTHETIC/PLANAR',cases=summary,historical_audit=historical_audit()),indent=2)+'\n')

if __name__=='__main__':main()
