"""Read actual GLB geometry, not only metadata. Emits reproducible local QA."""
import json,struct,sys,collections,math,unittest
from pathlib import Path
import numpy as np
import geometry as g
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
m=json.loads((ROOT/'arena.json').read_text());r=(ROOT/'arena.glb').read_bytes();magic,v,length=struct.unpack_from('<4sII',r);assert(magic,v,length)==(b'glTF',2,len(r))
o=12;doc=blob=None
while o<len(r):
 n,t=struct.unpack_from('<II',r,o);chunk=r[o+8:o+8+n];o+=8+n
 if t==0x4e4f534a:doc=json.loads(chunk)
 if t==0x004e4942:blob=chunk
ids={x['id']:x for x in m['objects']};seen=set();errors=[]
def matrix(n):
 if 'matrix'in n:return np.array(n['matrix']).reshape(4,4,order='F')
 x,y,z,w=n.get('rotation',[0,0,0,1]);rot=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
 out=np.eye(4);out[:3,:3]=rot@np.diag(n.get('scale',[1]*3));out[:3,3]=n.get('translation',[0]*3);return out
def visit(idx,world):
 n=doc['nodes'][idx];world=world@matrix(n)
 if 'mesh'in n and n['name']in ids:
  name=n['name'];seen.add(name);pts=[]
  for prim in doc['meshes'][n['mesh']]['primitives']:
   a=doc['accessors'][prim['attributes']['POSITION']];bv=doc['bufferViews'][a['bufferView']];assert a['componentType']==5126 and a['type']=='VEC3'
   arr=np.ndarray((a['count'],3),dtype='<f4',buffer=blob,offset=bv.get('byteOffset',0)+a.get('byteOffset',0),strides=(bv.get('byteStride',12),4));pts.extend((world@np.column_stack([arr,np.ones(len(arr))]).T).T[:,:3])
  pts=np.array(pts);lo,hi=ids[name]['bbox_m'];wantlo=[lo[0],lo[2],-hi[1]];wanthi=[hi[0],hi[2],-lo[1]];err=max(abs(pts.min(0)-wantlo).max(),abs(pts.max(0)-wanthi).max());assert err<2e-5,(name,err);errors.append(float(err))
 for c in n.get('children',[]):visit(c,world)
for idx in doc['scenes'][doc.get('scene',0)]['nodes']:visit(idx,np.eye(4))
assert seen==set(ids),(set(ids)-seen)
def ext(name,axis):
 lo,hi=ids[name]['bbox_m'];return hi[axis]-lo[axis]
assert abs(ext('floor_left_straight',1)-5.018)<1e-9
for name in ['floor_in_bay','floor_out_bay']:
 assert abs(ext(name,0)-2.4)<1e-9 and abs(ext(name,1)-1.018)<1e-9
assert abs(ext('floor_parking_bay',1)-1.5)<1e-9
for name in ['wall_marker_P','wall_marker_QR_PLACEHOLDER']:
 assert abs(ext(name,1)-.1)<1e-9 and abs(ext(name,2)-.1)<1e-9

terrain=json.loads((ROOT/'collision/terrain_meshes.json').read_text())
for mesh in terrain['closed_solids']:
 edge=collections.Counter(tuple(sorted((a,b)))for face in mesh['faces']for a,b in zip(face,face[1:]+face[:1]));assert set(edge.values())=={2},mesh['id']
 assert all(math.isfinite(v)for p in mesh['vertices']for v in p)
 assert max(p[2]for p in mesh['vertices'])>min(p[2]for p in mesh['vertices'])
b=json.loads((ROOT/'arena.semantic.json').read_text());assert b['map_transform']is None and not b['navigation_qualified'];assert b['bounds_xy_m']==[[0,0],[8,6]]
scenarios=list(ROOT.glob('scenario_*.json'));assert len(scenarios)>=6
for path in scenarios:
 s=json.loads(path.read_text());assert 0<=len(s['obstacles'])<=10 and not s['gt_schedule_for_detector']
assert g.random_obstacles(10,123)==g.random_obstacles(10,123)
try:g.random_obstacles(11,0);raise AssertionError('limit failed')
except ValueError:pass
zz={z['id']:z for z in b['semantic_zones']};park=zz['zone_parking']
assert g.polygon_inside(park,[[6.6,2.4],[7,2.4],[7,2.9],[6.6,2.9]])
assert not g.polygon_inside(park,[[6.49,2.4],[7,2.4],[7,2.9],[6.49,2.9]])
stop=zz['stop_zone_01'];pt=np.array(stop['polygon']).mean(0).tolist();assert g.feet_inside(stop,pt,pt);assert not g.feet_inside(stop,pt,[0,0])
assert not g.finish_crossed([[7.7,.2],[8.1,.4]],[[7.9,.2],[8.3,.4]])
assert g.finish_crossed([[7.7,.2],[8.1,.4]],[[8.1,.2],[8.5,.4]])
assert not g.finish_crossed([[7.7,3],[8.1,3.4]],[[8.1,3],[8.5,3.4]])
result=dict(status='PASS',validation_type='VM_STATIC_ASSET_AND_QUERY_TEST',checks=dict(glb_actual_vertices=True,source_dimension_checks=True,axis_transform_x_z_minus_y=True,semantic_ids=True,closed_terrain_edges=True,scenario_count=len(scenarios),obstacle_limit=True,fixed_seed=True,full_footprint_parking=True,both_front_feet=True,finite_exit_full_footprint=True),object_count=len(ids),max_glb_bbox_error_m=max(errors),physics_load='NOT_RUN',navigation_qualification='NOT_RUN',physical_measurement='NOT_RUN',unresolved=['crossing measurement baselines','parking gap6.500 vs envelope6.000','wall thickness','map transform','route direction','signal/stop exact siting'])
(ROOT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
