#!/usr/bin/env python3
"""Read-only structural checks of generated metadata and GLB (Python + NumPy)."""
import json, struct, hashlib, math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
meta=json.loads((ROOT/'arena.json').read_text())
raw=(ROOT/'arena.glb').read_bytes();magic,version,length=struct.unpack_from('<4sII',raw,0)
assert magic==b'glTF' and version==2 and length==len(raw)
offset=12;doc=None;binary=None
while offset<len(raw):
 n,t=struct.unpack_from('<II',raw,offset);offset+=8;chunk=raw[offset:offset+n];offset+=n
 if t==0x4e4f534a:doc=json.loads(chunk.decode().rstrip(' \0'))
 if t==0x004e4942:binary=chunk
assert doc and binary
ids={o['id'] for o in meta['objects']};nodes=doc['nodes'];node_ids={n['name'] for n in nodes if 'mesh' in n}
assert ids==node_ids,(ids-node_ids,node_ids-ids)
def matrix(n):
 if 'matrix' in n:return np.array(n['matrix']).reshape(4,4,order='F')
 t=np.array(n.get('translation',[0,0,0]));s=np.array(n.get('scale',[1,1,1]));x,y,z,w=n.get('rotation',[0,0,0,1])
 r=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
 m=np.eye(4);m[:3,:3]=r@np.diag(s);m[:3,3]=t;return m
bounds=[];node_checks=[]
def visit(idx,parent):
 n=nodes[idx];world=parent@matrix(n)
 if 'mesh' in n:
  pts=[]
  for prim in doc['meshes'][n['mesh']]['primitives']:
   a=doc['accessors'][prim['attributes']['POSITION']];v=doc['bufferViews'][a['bufferView']]
   assert a['componentType']==5126 and a['type']=='VEC3'
   start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',12)
   pos=np.ndarray((a['count'],3),dtype='<f4',buffer=binary,offset=start,strides=(stride,4)).astype(float)
   hp=np.column_stack([pos,np.ones(len(pos))]);pts.extend((world@hp.T).T[:,:3])
  pts=np.asarray(pts);lo=pts.min(0);hi=pts.max(0);bounds.extend([lo,hi])
  src=next(o for o in meta['objects'] if o['id']==n['name']);slo=src['bbox_m']['min'];shi=src['bbox_m']['max'];expected_lo=np.array([slo[0],slo[2],-shi[1]]);expected_hi=np.array([shi[0],shi[2],-slo[1]])
  err=max(np.max(np.abs(lo-expected_lo)),np.max(np.abs(hi-expected_hi)))
  assert err<2e-5,(n['name'],err,lo,expected_lo)
  node_checks.append({'id':n['name'],'source_to_gltf_bbox_max_error_m':float(err)})
 for child in n.get('children',[]):visit(child,world)
for idx in doc['scenes'][doc.get('scene',0)]['nodes']:visit(idx,np.eye(4))
b=np.array(bounds);lo=b.min(0);hi=b.max(0)
assert abs(lo[0])<1e-6 and abs(hi[0]-8)<1e-6
assert abs(lo[2]+6.018)<1e-6 and abs(hi[2])<1e-6
wall_materials=set()
for n in nodes:
 if n.get('name','').startswith('wall_'):
  for p in doc['meshes'][n['mesh']]['primitives']:wall_materials.add(p['material'])
assert all(doc['materials'][i].get('doubleSided',False) for i in wall_materials)
right=next(o for o in meta['objects'] if o['id']=='floor_right_straight')
assert abs(right['bbox_m']['max'][0]-right['bbox_m']['min'][0]-1)<1e-6
assert all(o['modeled_surface_thickness_m']==0 for o in meta['objects'] if o['category']=='wall')
for name in ['ramp_sw','ramp_ne']:
 o=next(o for o in meta['objects'] if o['id']==name);assert (o['run_m'],o['rise_m'],o['width_m'])==(1.1,.18,1)
for o in meta['objects']:
 if o['category']=='stair':assert o['tread_depth_m']==.25 and o['riser_height_m']==.06
source_checks=[]
for src in meta['sources']:
 p=Path('/workspace/scratch/b09eacf6919d/course_images')/src['filename']
 if p.exists():
  match=hashlib.sha256(p.read_bytes()).hexdigest()==src['sha256'];assert match
  source_checks.append({'id':src['id'],'unchanged_hash':match,'size_matches_reattachment_metadata':p.stat().st_size==src['expected_size_bytes']})
result={'status':'passed','scope':'Visualization asset consistency only; not source/CAD/survey accuracy, physical collision, localization or Nav2 validation.','checks':{'glb_header_and_length':True,'object_ids_match_json':True,'source_to_gltf_axis_transform':True,'plan_bounds_8_by_6_018_m':True,'right_corridor_clear_width_1_m':True,'wall_materials_double_sided':True,'wall_thickness_unspecified_surface_model':True,'ramp_run_rise_width':True,'stair_dimensions':True,'source_files_unchanged':source_checks},'object_count':len(ids),'gltf_world_bounds_m':{'min':lo.tolist(),'max':hi.tolist()},'maximum_object_bbox_error_m':max(n['source_to_gltf_bbox_max_error_m'] for n in node_checks),'node_checks':node_checks}
(ROOT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='node_checks'},ensure_ascii=False,indent=2))
