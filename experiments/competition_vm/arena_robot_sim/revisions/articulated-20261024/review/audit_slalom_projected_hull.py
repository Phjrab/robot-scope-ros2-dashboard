"""Conservative projected articulated-mesh hull audit, not contact dynamics."""
import sys,json,math,time,argparse,hashlib
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from test_independent_review import independent_fk,rigid,ASSET
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE));import gait
SOURCE_ROOT=gait.ROOT
verts={name:np.array(m['vertices_q']).reshape(-1,3)*m['quantization_m']for name,m in ASSET['meshes'].items()}

def inside(P,poly):
 poly=np.asarray(poly);x,y=P[:,0],P[:,1];ans=np.zeros(len(P),bool)
 for a,b in zip(poly,np.roll(poly,-1,axis=0)):
  dy=b[1]-a[1]
  if abs(dy)>1e-15:ans^=((a[1]>y)!=(b[1]>y))&(x<(b[0]-a[0])*(y-a[1])/dy+a[0])
 return ans

def intersect(a,b,c,d):
 def cross(u,v):return u[0]*v[1]-u[1]*v[0]
 ab=b-a;cd=d-c;den=cross(ab,cd)
 if abs(den)<1e-12:return False
 t=cross(c-a,cd)/den;u=cross(c-a,ab)/den
 return -1e-9<=t<=1+1e-9 and -1e-9<=u<=1+1e-9

def dist(p,a,b):
 v=b-a;t=np.clip(np.dot(p-a,v)/np.dot(v,v),0,1);return float(np.linalg.norm(p-(a+t*v)))

def audit(name):
 source=json.loads(((SOURCE_ROOT/'experiments/competition_vm/arena_robot_sim/revisions/left_slalom_20261024/results')/f'{name}.json').read_text());rr=json.loads((HERE/'output'/f'{name}_joints.json').read_text())['records']
 walls=json.loads(((SOURCE_ROOT/'assets/competition-arena/revisions/corridor-parallel-20261024/collision/virtual_fences.json')).read_text())['walls'];segments=[(np.asarray(w['a']),np.asarray(w['b']))for w in walls]
 boxes=[]
 for c in source['scene']['cones']:
  x,y=c['xy'];h=c['base_side_m']/2;box=np.array([[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]]);boxes.append(box);segments.extend(zip(box,np.roll(box,-1,axis=0)))
 bounds=np.max(np.abs(np.array(source['scene']['footprint'])),axis=0);floors=list(source['scene']['allowed_floor_polygons'].values());results=dict(case=name,poses=0,wall_or_cone_intersections=0,floor_edge_sample_violations=0,cone_containment=0,min_planar_hull_to_boundary_clearance_m=999.,min_mesh_ground_m=999.,interpolation_substeps=10,floor_edge_sample_spacing_m=.005,clearance_sample_hz=15,planned_envelope_violations=0,max_local_abs_x_m=0.,max_local_abs_y_m=0.,joint_limit_violations=0)
 for i in range(len(rr)):
  a=rr[i];b=rr[min(i+1,len(rr)-1)]
  for f in range(1 if i==len(rr)-1 else 10):
   u=f/10;pose=(1-u)*np.array(a['pose'])+u*np.array(b['pose']);q={n:(1-u)*a['q'][n]+u*b['q'][n]for n in a['q']};T=independent_fk(q);results['joint_limit_violations']+=sum(not (j['limit']['lower']<=q[j['name']]<=j['limit']['upper'])for j in ASSET['skeleton']['joints']if j['type']=='revolute');root=rigid([*pose[:2],gait.HEIGHT],[0,0,pose[2]]);v=[]
   for link in ASSET['skeleton']['links']:
    o=link['visual_origin'];tr=root@T[link['name']]@rigid(o['xyz'],o['rpy']);v.append(verts[link['mesh']]@tr[:3,:3].T+tr[:3,3])
   v=np.concatenate(v);lv=(v-root[:3,3])@root[:3,:3];mx=float(np.abs(lv[:,0]).max());my=float(np.abs(lv[:,1]).max());results['max_local_abs_x_m']=max(results['max_local_abs_x_m'],mx);results['max_local_abs_y_m']=max(results['max_local_abs_y_m'],my);results['planned_envelope_violations']+=int(mx>bounds[0]+1e-9 or my>bounds[1]+1e-9);results['min_mesh_ground_m']=min(results['min_mesh_ground_m'],float(v[:,2].min()));hull=v[ConvexHull(v[:,:2]).vertices,:2];edges=list(zip(hull,np.roll(hull,-1,axis=0)));sample=np.concatenate([np.linspace(p,z,max(2,int(np.linalg.norm(p-z)/.005)+1))for p,z in edges]);okay=np.zeros(len(sample),bool)
   for floor in floors:okay|=inside(sample,floor)
   results['floor_edge_sample_violations']+=int(not okay.all())
   hit=any(intersect(p,z,c,d)for p,z in edges for c,d in segments);results['wall_or_cone_intersections']+=int(hit)
   results['cone_containment']+=int(any(inside(box,hull).any() or inside(hull,box).any()for box in boxes))
   # nearest distance computed against segment endpoints / hull vertices, plus proper crossings above.
   if results['poses']%10==0:
    md=min(min(dist(p,c,d),dist(z,c,d),dist(c,p,z),dist(d,p,z))for p,z in edges for c,d in segments);results['min_planar_hull_to_boundary_clearance_m']=min(results['min_planar_hull_to_boundary_clearance_m'],md)
   results['poses']+=1
 results['planned_local_half_extents_m']=bounds.tolist();results['source_trace_sha256']=hashlib.sha256((SOURCE_ROOT/'experiments/competition_vm/arena_robot_sim/revisions/left_slalom_20261024/results'/f'{name}.json').read_bytes()).hexdigest();results['joint_record_sha256']=hashlib.sha256((HERE/'output'/f'{name}_joints.json').read_bytes()).hexdigest();return results
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,default=gait.ROOT);args=parser.parse_args();SOURCE_ROOT=args.source_root
 r=[audit(n)for n in ['slalom_5','blocked_5']];(HERE/'review/slalom_projected_hull_audit.json').write_text(json.dumps({'results':r,'limitations':['Sampling/interpolated geometric check, not continuous certified collision proof','Original static-footprint planner metrics remain distinct','Uses corrected-revision fences and strictly left-corridor allowed floor; no parking permission','No contact-force, self-collision, balance, gait controller, real sensor or hardware validation']},indent=2));print(json.dumps(r,indent=2))
