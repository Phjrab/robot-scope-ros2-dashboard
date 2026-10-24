"""Independent artifact/FK checks, no robot connection or renderer required."""
import unittest,json,sys,math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE));import gait
ASSET=json.loads(gait.ASSET.read_text())

def rigid(xyz,rpy):
 r,p,y=rpy
 Rx=np.array([[1,0,0],[0,math.cos(r),-math.sin(r)],[0,math.sin(r),math.cos(r)]])
 Ry=np.array([[math.cos(p),0,math.sin(p)],[0,1,0],[-math.sin(p),0,math.cos(p)]])
 Rz=np.array([[math.cos(y),-math.sin(y),0],[math.sin(y),math.cos(y),0],[0,0,1]])
 T=np.eye(4);T[:3,:3]=Rz@Ry@Rx;T[:3,3]=xyz;return T

def independent_fk(q):
 ts={'base':np.eye(4)}
 for j in ASSET['skeleton']['joints']:
  o=j['origin'];R=np.eye(4)
  if j['type']=='revolute':R=rigid([0,0,0],np.asarray(j['axis'])*q[j['name']])
  ts[j['child']]=ts[j['parent']]@rigid(o['xyz'],o['rpy'])@R
 return ts

