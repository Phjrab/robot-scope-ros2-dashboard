"""Verify exported glTF top-face triangles, not just bounding boxes."""
import json,struct,math
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
import geometry as g
ROOT=Path(__file__).resolve().parent
raw=(ROOT/'arena.glb').read_bytes();offset=12;doc=None;blob=None
while offset<len(raw):
 n,t=struct.unpack_from('<II',raw,offset);chunk=raw[offset+8:offset+8+n];offset+=8+n
 if t==0x4e4f534a:doc=json.loads(chunk)
 if t==0x004e4942:blob=chunk
DT={5121:'<u1',5123:'<u2',5125:'<u4',5126:'<f4'}
def acc(i):
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];cols={'SCALAR':1,'VEC3':3}[a['type']];dt=np.dtype(DT[a['componentType']]);stride=v.get('byteStride',cols*dt.itemsize)
 return np.ndarray((a['count'],cols),dtype=dt,buffer=blob,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(stride,dt.itemsize))
def matrix(n):
 if 'matrix'in n:return np.array(n['matrix']).reshape(4,4,order='F')
 x,y,z,w=n.get('rotation',[0,0,0,1]);r=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
 a=np.eye(4);a[:3,:3]=r@np.diag(n.get('scale',[1]*3));a[:3,3]=n.get('translation',[0]*3);return a
errors={}
def visit(i,parent):
 n=doc['nodes'][i];world=parent@matrix(n);name=n.get('name','')
 if name in g.FLOORS:
  tris=[]
  for prim in doc['meshes'][n['mesh']]['primitives']:
   assert prim.get('mode',4)==4
   pos=acc(prim['attributes']['POSITION']);pos=(world@np.column_stack([pos,np.ones(len(pos))]).T).T[:,:3]
   inds=acc(prim['indices']).reshape(-1,3)
   for ix in inds:
    t=pos[ix]
    if max(abs(t[:,1]))<1e-7:
     p=Polygon([(v[0],-v[2])for v in t])
     if p.area>1e-14:tris.append(p)
  actual=unary_union(tris);expected=Polygon(g.FLOORS[name]);err=actual.symmetric_difference(expected).area
  assert err<3e-6,(name,err)
  errors[name]=err
 for c in n.get('children',[]):visit(c,world)
for i in doc['scenes'][doc.get('scene',0)]['nodes']:visit(i,np.eye(4))
assert set(errors)==set(g.FLOORS)
r=dict(status='PASS',floor_count=len(errors),top_face_symmetric_difference_area_m2=errors,tolerance_m2=3e-6,scope='Actual GLB top triangle union versus semantic source polygons, with glTF axis transform applied')
(ROOT/'glb_floor_validation.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
