"""Isolated experimental copy. Requires frozen simulate_curved on sys.path. Do not deploy."""
from simulate_curved import *
from functools import lru_cache
YAW_MAX=.12

def build_path_memoized(pose,grid):
 expanded=maximum_filter(grid,size=(87,61),mode='constant',cval=1)
 valid=distance_transform_edt(~expanded)*RES>RES*.71
 raw=plan((expanded,np.zeros_like(expanded)),np.ones_like(expanded),pose[:2],base.GOAL,RES,0.)
 if len(raw)<2:return []
 # Smooth only inside the same full-footprint configuration-space corridor.
 # No use of hidden cone truth, no hand-authored waypoint/path insertion.
 p=np.array(raw,float);p[0]=pose[:2]
 def allowed(q):
  return allowed_cached(tuple(q))
 @lru_cache(maxsize=None)
 def allowed_cached(q):
  iy,ix=int(q[1]/RES),int(q[0]/RES)
  return 0<=iy<grid.shape[0] and 0<=ix<grid.shape[1] and valid[iy,ix] and not polygon_collision((q[0],q[1],math.pi/2),CHECK_BODY,grid,RES)
 for _ in range(45):
  old=p.copy()
  for i in range(1,len(p)-1):
   q=old[i]+.35*(old[i-1]+old[i+1]-2*old[i])
   if allowed(q) and all(allowed(old[i]+(q-old[i])*t) for t in (.25,.5,.75)):p[i]=q
 # Clearance-gated desired body orientation follows the path gently, rather
 # than assuming a circle certifies arbitrary rotation of a long rectangle.
 out=[]
 for i,q in enumerate(p):
  lo=max(0,i-3);hi=min(len(p)-1,i+3);d=p[hi]-p[lo]
  offset=np.clip(math.atan2(d[1],d[0])-math.pi/2,-YAW_MAX,YAW_MAX)
  while abs(offset)>.001 and polygon_collision((q[0],q[1],math.pi/2+offset),CHECK_BODY,grid,RES):offset*=.5
  yaw=math.pi/2+offset
  if polygon_collision((q[0],q[1],yaw),CHECK_BODY,grid,RES):
   yaw=math.pi/2
   if polygon_collision((q[0],q[1],yaw),CHECK_BODY,grid,RES):return []
  out.append([*q,float(yaw)])
 build_path_memoized.last_cache_info=allowed_cached.cache_info()._asdict()
 return out
