"""Independent fast-path differential and exhaustive geometry review."""
from pathlib import Path
import sys,math,json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'review'))
from collision import Snapshot as Generic
from fast_snapshot import Snapshot as Fast
from independent_geometry_review import oracle

def main():
 tested_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['collision.py','fast_snapshot.py']}
 rng=np.random.default_rng(2026102502);counts={};issues=[];differences=[]
 def check(group,mask,res,origin,pose,body):
  g=bool(Generic(mask,res,origin).collides(pose,body));f=bool(Fast(mask,res,origin).collides(pose,body))
  o,gap=oracle(pose,body,mask,res,origin)
  row=counts.setdefault(group,dict(cases=0,false_clears=0,generic_differences=0,conservative_differences=0));row['cases']+=1
  detail=dict(group=group,pose=list(pose),body=np.asarray(body).tolist(),origin=origin,res=res,generic=g,fast=f,oracle=o,gap_m=gap,occupied=np.argwhere(mask).tolist())
  if o and not f:row['false_clears']+=1;issues.append(detail)
  if f!=g:row['generic_differences']+=1;differences.append(detail)
  if f and not o:row['conservative_differences']+=1
 square=np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
 for origin in [(0.,0.),(-8.,-12.),(1e8,-1e8)]:
  mask=np.zeros((12,12),bool);mask[5,5]=True
  for yaw in [0.,math.pi/2,math.pi,-math.pi/2,np.nextafter(math.pi/2,math.inf),.123]:
   for body in [square,square[::-1],square*np.array([2.,.3])]:
    c,s=math.cos(yaw),math.sin(yaw);rotated=body@np.array([[c,s],[-s,c]])
    for axis in [0,1]:
     for side in [-1,1]:
      for gap in [0.,-1e-8,-1e-12,1e-14,1e-12,1.2e-12,1e-10,1e-7,.01]:
       pose=np.array(origin)+5.5
       pose[axis]=origin[axis]+(5 if side<0 else 6)-(max(rotated[:,axis]) if side<0 else min(rotated[:,axis]))+side*gap
       check('edges_and_gaps',mask,1.,origin,(*pose,yaw),body)
   for axis in [0,1]:
    for side in [-1,1]:
     for gap in [0.,-1e-8,1e-14,1e-12,1e-10,1e-7,.01]:
      pose=np.array(origin)+6;pose[axis]=origin[axis]+(.25+gap if side<0 else 11.75-gap)
      check('map_edges',np.zeros((12,12),bool),1.,origin,(*pose,yaw),square)
 # ULP-neighbor probes at the documented tolerance boundary catch index-rounding mismatches.
 for origin in [(0.,0.),(-8.,-12.),(1e8,-1e8)]:
  mask=np.zeros((12,12),bool);mask[5,5]=True
  for side in [-1,1]:
   x=origin[0]+(4.75 if side<0 else 6.25);y=origin[1]+5.5
   scale=max(1.,abs(x)+.25,abs(y)+.25,*map(abs,origin),12.)
   tol=1e-12+64*np.finfo(float).eps*scale;t=x+side*tol
   xs=[t];low=high=t
   for k in range(10):
    low=np.nextafter(low,-math.inf);high=np.nextafter(high,math.inf);xs.extend([low,high])
   for xx in xs:
    for yaw in [0.,math.pi/2,math.pi,-math.pi/2]:
     check('tolerance_boundary_ulps',mask,1.,origin,(xx,y,yaw),square)
 for i in range(18000):
  res=float(rng.choice([.001,.01,.1,1.,2.]));origin=tuple(rng.uniform(-100,100,2))
  mask=rng.random((12,13))<rng.choice([0.,.01,.1,.5,1.])
  if i%3:
   body=square*rng.uniform(.1,5.,2)*res
   yaw=float(rng.choice([0.,math.pi/2,math.pi,-math.pi/2]))
  else:
   n=int(rng.choice([3,5,8]));angles=np.arange(n)*2*math.pi/n
   body=np.column_stack((np.cos(angles),np.sin(angles)))*rng.uniform(.1,2.,2)*res
   yaw=float(rng.uniform(-10,10))
  pose=(* (np.array(origin)+rng.uniform(-1,14,2)*res),yaw)
  check('random_rectangle_or_fallback',mask,res,origin,pose,body)
 for res in [1e-11,1e-9,1e-7]:
  for origin in [(0.,0.),(-1.,-1.),(1e8,-1e8)]:
   mask=np.zeros((12,12),bool);mask[5,5]=True
   for yaw in [0.,math.pi/2,math.pi,-math.pi/2]:
    for offset in [(-1.,0.),(-.75,0.),(-.5,0.),(0.,0.),(.5,0.),(.75,0.),(1.,0.),(1.,1.)]:
     pose=(*(np.array(origin)+(np.array([5.5,5.5])+offset)*res),yaw)
     check('tiny_resolution_and_interior',mask,res,origin,pose,square*res)
 # Reuse each optimized snapshot across mask mutations and template changes.
 source=np.zeros((12,12),bool);old=Fast(source,1.);p=(5.5,5.5,0.)
 clear_before=not old.collides(p,square);source[5,5]=True
 old_stays_clear=not old.collides(p,square);new=Fast(source,1.);new_blocked=new.collides(p,square)
 source[5,5]=False;new_stays_blocked=new.collides(p,square);latest=Fast(source,1.)
 a=np.arange(5)*2*math.pi/5;star=np.column_stack((np.cos(a),np.sin(a)))[[0,2,4,1,3]]
 malformed=[star,'bad',[[0,0],[1,0],[0,1,2]],[[0,0],[1,0],[2,0]],[[0,0],[1,0],[1,0],[0,1]]]
 invalid=[]
 for shape in malformed:
  try:invalid.append(bool(old.collides(p,shape)))
  except Exception:invalid.append(False)
 lifecycle=dict(clear_before=clear_before,old_snapshot_stays_clear=old_stays_clear,new_snapshot_sees_addition=bool(new_blocked),new_snapshot_owns_blocked_copy=bool(new_stays_blocked),latest_snapshot_sees_removal=not latest.collides(p,square),template_cache_not_shared=old._templates is not new._templates,integral_cache_not_shared=old._integral is not new._integral,source_not_shared=not np.shares_memory(source,old._mask),all_malformed_fail_closed=all(invalid))
 result=dict(seed=2026102502,sha256=tested_hashes,groups=counts,total_cases=sum(x['cases'] for x in counts.values()),false_clears=sum(x['false_clears'] for x in counts.values()),generic_differences=len(differences),lifecycle=lifecycle,issues=issues,differences=differences[:30],limitations='Finite sampling, not proof; generic fallback and longdouble all-cell SAT are independent comparisons. No scenario or hardware claims.')
 (ROOT/'review/fast_geometry_review.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['issues','differences']},indent=2))
 return int(bool(issues) or not all(lifecycle.values()) or bool(differences))
if __name__=='__main__':raise SystemExit(main())
