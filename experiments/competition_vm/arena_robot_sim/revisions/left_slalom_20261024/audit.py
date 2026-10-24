"""Independent continuous-between-sample geometric audit of saved trace."""
import json,math,hashlib
from pathlib import Path
import simulate_slalom as s
import numpy as np
from core import polygon,sat_overlap
HERE=Path(__file__).resolve().parent

def ptseg(p,a,b):
 vx,vy=b[0]-a[0],b[1]-a[1];u=max(0,min(1,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/(vx*vx+vy*vy)))
 return math.hypot(p[0]-a[0]-u*vx,p[1]-a[1]-u*vy)
def edges(poly):return list(zip(poly,poly[1:]+poly[:1]))
def check(pose,cones):
 robot=polygon(pose,s.BODY).tolist();floor=s.geo.FLOORS['floor_left_straight'];bad=not all(s.geo.contains(floor,p) for p in robot)
 clear=min(min(ptseg(p,a,b) for a,b in edges(floor)) for p in robot)
 for c in cones:
  x,y=c['xy'];h=c['base_side_m']/2;box=[[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]]
  overlap=sat_overlap(np.array(robot),np.array(box));bad|=overlap
  d=0 if overlap else min([ptseg(p,a,b) for p in robot for a,b in edges(box)]+[ptseg(p,a,b) for p in box for a,b in edges(robot)])
  clear=min(clear,d)
 return bad,clear

def audit(path):
 data=json.loads(path.read_text());cones=data['scene']['cones'];last=data['scene']['start'];minimum=99;bad=0;n=0
 for f in data['frames']:
  now=f['pose']
  for i in range(11):
   pose=[last[j]+(now[j]-last[j])*i/10 for j in range(3)]
   b,c=check(pose,cones);bad+=int(b);minimum=min(minimum,c);n+=1
  last=now
 straight=sum(int(check([s.START[0],y,s.START[2]],cones)[0]) for y in np.linspace(s.START[1],s.GOAL[1],1000))
 report=dict(trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),poses_audited=n,polygon_floor_or_cone_violations=bad,min_polygon_clearance_m=minimum,straight_reference_contact_samples=straight,static_floor_scope='whole robot inside left slalom polygon',pose_interpolation='11samples every0.1s, maximum1.6mm translation betweenauditposes',pass_geometry=bad==0)
 return report
if __name__=='__main__':
 rows={p.stem:audit(p) for p in [(HERE/'results'/f'{n}.json') for n in s.configs()]}
 (HERE/'results/audit.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
