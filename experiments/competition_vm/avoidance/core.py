"""VM-only navigation core, NOT Nav2/RPP/MPPI. SI units and receiver-local time."""
from dataclasses import dataclass
import heapq, math
import numpy as np
from scipy.ndimage import distance_transform_edt

@dataclass(frozen=True)
class Scan:
    epoch: str
    sequence: int
    source_stamp_ns: str
    source_clock: str
    frame_id: str
    angles: np.ndarray
    ranges: np.ndarray
    max_range: float
    receipt_s: float

@dataclass(frozen=True)
class Goal:
    run_id: str
    step_id: str
    goal_id: str
    generation: int
    map_revision: str
    xy: tuple

class Occupancy:
    """Static immutable mask plus observed dynamic cells; missing rays never clear."""
    def __init__(self, static, resolution=.1):
        self.static=np.asarray(static,dtype=bool).copy(); self.static.flags.writeable=False
        if self.static.ndim!=2 or min(self.static.shape)<1 or not math.isfinite(resolution) or resolution<=0: raise ValueError("invalid grid")
        self.resolution=resolution
        self.dynamic=np.zeros(self.static.shape,dtype=np.int8) # immutable map supplies prior known-free cells
        self.observed=np.full(self.static.shape,-np.inf)
        self.retired_epochs=set()
        self.last_receipt=-np.inf; self.epoch=None; self.sequence=-1; self.stamp=-1
    def cell(self,x,y): return math.floor(y/self.resolution),math.floor(x/self.resolution)
    def inside(self,c): return 0<=c[0]<self.static.shape[0] and 0<=c[1]<self.static.shape[1]
    def update(self,scan,pose,now,tf_age=0):
        if not isinstance(scan.epoch,str) or not scan.epoch or len(scan.epoch)>128: return False
        if type(scan.sequence) is not int or not 0<=scan.sequence<2**63: return False
        if not isinstance(scan.source_stamp_ns,str) or not scan.source_stamp_ns.isdigit() or len(scan.source_stamp_ns)>19: return False
        if not math.isfinite(scan.receipt_s): return False
        if scan.frame_id!='vm_laser' or scan.source_clock!='VM_SIM' or not math.isfinite(tf_age) or tf_age<0 or tf_age>.2: return False
        if not np.all(np.isfinite(pose)) or not math.isfinite(scan.max_range) or scan.max_range<=0: return False
        if len(scan.ranges)!=len(scan.angles) or not np.all(np.isfinite(scan.angles)): return False
        if not np.any(np.isfinite(scan.ranges) & (scan.ranges>0)): return False
        if not np.isfinite(now) or now-scan.receipt_s<0 or now-scan.receipt_s>.3: return False
        try: stamp=int(scan.source_stamp_ns)
        except (ValueError,TypeError): return False
        if not 0<=stamp<2**63: return False
        if scan.epoch in self.retired_epochs: return False
        if scan.epoch!=self.epoch:
            if self.epoch is not None: self.retired_epochs.add(self.epoch)
            self.dynamic[self.dynamic!=0]=-1; self.observed.fill(-np.inf)
            self.sequence=-1; self.stamp=-1; self.epoch=scan.epoch
        if scan.sequence<=self.sequence or stamp<=self.stamp: return False
        if len(scan.ranges)!=len(scan.angles): return False
        self.sequence=scan.sequence; self.stamp=stamp; self.last_receipt=scan.receipt_s
        x,y,yaw=pose; occupied=[]
        for a,r in zip(scan.angles,scan.ranges):
            if not np.isfinite(r) or r<=0: continue # dropout != free
            hit=r<scan.max_range
            end=min(r,scan.max_range)
            for d in np.arange(0,max(0,end-self.resolution*.7),self.resolution*.45):
                c=self.cell(x+d*math.cos(a+yaw),y+d*math.sin(a+yaw))
                if not self.inside(c): break
                self.dynamic[c]=0; self.observed[c]=now
            if hit:
                c=self.cell(x+end*math.cos(a+yaw),y+end*math.sin(a+yaw))
                if self.inside(c): occupied.append(c)
        # Mark after all clearing rays, so quantized adjacent beams do not erase hits.
        for c in occupied: self.dynamic[c]=1; self.observed[c]=now
        return True
    def masks(self,now,ttl=1.5):
        expired=(now-self.observed)>ttl
        dynamic=self.dynamic.copy(); dynamic[expired & (dynamic!=0)]=-1
        return self.static | (dynamic==1),dynamic==-1


def plan(occupancy,allowed,start,goal,resolution,radius):
    # Fallback A* on observed/inflated cells. This is explicitly not NavFn.
    obstacle,unknown=map(np.asarray,occupancy)
    allowed=np.asarray(allowed)
    if obstacle.ndim!=2 or obstacle.shape!=unknown.shape or obstacle.shape!=allowed.shape or min(obstacle.shape)<1: return []
    if not math.isfinite(resolution) or resolution<=0 or not math.isfinite(radius) or radius<0: return []
    if len(start)!=2 or len(goal)!=2 or not np.all(np.isfinite([*start,*goal])): return []
    if any(not (0<=p[0]<obstacle.shape[1]*resolution and 0<=p[1]<obstacle.shape[0]*resolution) for p in (start,goal)): return []
    blocked=obstacle | unknown | ~allowed
    clearance=distance_transform_edt(~blocked)*resolution
    valid=clearance>radius+resolution*.71
    sy,sx=int(start[1]/resolution),int(start[0]/resolution)
    gy,gx=int(goal[1]/resolution),int(goal[0]/resolution)
    if not (0<=gy<valid.shape[0] and 0<=gx<valid.shape[1]) or not valid[gy,gx]: return []
    if not valid[sy,sx]: return []
    queue=[(0,0,(sy,sx))]; cost={(sy,sx):0}; prev={}
    while queue:
        _,g,u=heapq.heappop(queue)
        if u==(gy,gx):
            out=[u]
            while out[-1] in prev: out.append(prev[out[-1]])
            return [((c[1]+.5)*resolution,(c[0]+.5)*resolution) for c in out[::-1]]
        if g!=cost.get(u): continue
        for dy,dx in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            v=(u[0]+dy,u[1]+dx)
            if not (0<=v[0]<valid.shape[0] and 0<=v[1]<valid.shape[1]) or not valid[v]: continue
            if dx and dy and not (valid[u[0],v[1]] and valid[v[0],u[1]]): continue
            ng=g+math.hypot(dx,dy)+.03/max(clearance[v],.01)
            if ng<cost.get(v,float('inf')):
                cost[v]=ng; prev[v]=u
                heapq.heappush(queue,(ng+math.hypot(v[0]-gy,v[1]-gx),ng,v))
    return []


def polygon(pose,footprint):
    x,y,t=pose; c,s=math.cos(t),math.sin(t)
    return np.asarray([(x+c*a-s*b,y+s*a+c*b) for a,b in footprint])

def sat_overlap(poly,box):
    # Convex polygons, contact counts as intersection.
    for shape in (poly,box):
        for p,q in zip(shape,np.roll(shape,-1,axis=0)):
            edge=q-p; axis=np.array([-edge[1],edge[0]])
            a=poly@axis; b=box@axis
            if max(a)<min(b) or max(b)<min(a): return False
    return True

def polygon_collision(pose,footprint,mask,res):
    p=polygon(pose,footprint)
    if min(p[:,0])<0 or min(p[:,1])<0 or max(p[:,0])>=mask.shape[1]*res or max(p[:,1])>=mask.shape[0]*res: return True
    x0,x1=int(min(p[:,0])/res),int(max(p[:,0])/res)
    y0,y1=int(min(p[:,1])/res),int(max(p[:,1])/res)
    for y,x in zip(*np.where(mask[y0:y1+1,x0:x1+1])):
        x+=x0; y+=y0
        b=np.array([[x*res,y*res],[(x+1)*res,y*res],[(x+1)*res,(y+1)*res],[x*res,(y+1)*res]])
        if sat_overlap(p,b): return True
    return False

def propagate(pose,v,w,dt):
    x,y,t=pose
    if abs(w)<1e-10: return x+v*dt*math.cos(t),y+v*dt*math.sin(t),t
    return x+v/w*(math.sin(t+w*dt)-math.sin(t)),y-v/w*(math.cos(t+w*dt)-math.cos(t)),t+w*dt

def swept_safe(pose,v,w,dt,footprint,mask,res):
    if not np.all(np.isfinite([*pose,v,w,dt,res])) or dt<0 or res<=0: return False
    if len(footprint)<3 or not np.all(np.isfinite(footprint)): return False
    radius=max(math.hypot(*p) for p in footprint)
    n=max(2,int((abs(v)*dt+abs(w)*dt*radius)/(res*.2))+1)
    return all(not polygon_collision(propagate(pose,v,w,dt*i/n),footprint,mask,res) for i in range(n+1))

class CommandArbiter:
    """Each tick requires a new command; holds never replay a cached nonzero command."""
    def __init__(self): self.last_command_seq=-1
    def apply(self,v,w,sequence,*,sensor_fresh,tf_fresh,signal_hold=False,estop=False,collision=False,cap=.25):
        if type(sequence) is not int or not 0<=sequence<2**63 or not np.all(np.isfinite([v,w,cap])) or cap<0: return 0.,0.,'INVALID_COMMAND'
        if sequence<=self.last_command_seq: return (0.,0.,'DUPLICATE_COMMAND')
        self.last_command_seq=sequence
        for stop,reason in ((estop,'ESTOP'),(not sensor_fresh,'SENSOR_STALE'),(not tf_fresh,'TF_STALE'),(collision,'COLLISION'),(signal_hold,'SIGNAL_HOLD')):
            if stop: return 0.,0.,reason
        return max(0.,min(v,cap)),max(-.8,min(w,.8)),'FOLLOWING'

class Session:
    def __init__(self,goal): self.goal=goal; self.active=True; self.reason=''
    def check(self,map_revision,generation,cancel=False,restart=False):
        if cancel or restart or map_revision!=self.goal.map_revision or generation!=self.goal.generation:
            self.active=False; self.reason='CANCELLED' if cancel else 'RESTART' if restart else 'IDENTITY_CHANGED'
        return self.active


def ground_filter(points,plane=(0,0,1,0),body_half=(.25,.18),max_range=8.,height=.035):
    """Known gravity-aligned support plane baseline, NOT fitted terrain/Patchwork++."""
    normal=np.asarray(plane[:3],float); norm=np.linalg.norm(normal)
    if not np.isfinite(norm) or norm<1e-9: raise ValueError('invalid support plane')
    result={'ground':[],'obstacle':[],'unknown':[]}; counts={'input':len(points),'invalid':0,'self':0,'range':0}
    for p in points:
        if len(p)<4 or not np.all(np.isfinite(p[:4])): counts['invalid']+=1; continue
        x,y,z,ring=p[:4]
        if abs(x)<body_half[0] and abs(y)<body_half[1]: counts['self']+=1; continue
        if math.sqrt(x*x+y*y+z*z)>max_range: counts['range']+=1; continue
        h=(np.dot(normal,p[:3])+plane[3])/norm
        category='ground' if abs(h)<=.015 else 'obstacle' if h>=height else 'unknown'
        result[category].append(list(p))
    counts.update({k:len(v) for k,v in result.items()}); return result,counts


def ring_sample(points,per_ring=32):
    buckets={}
    for p in points: buckets.setdefault(int(p[3]),[]).append(p)
    return [bucket[i] for _,bucket in sorted(buckets.items()) for i in np.linspace(0,len(bucket)-1,min(len(bucket),per_ring),dtype=int)]


def transform_cloud(points,transform,*,source_kind,source_frame,target_frame,tf_age):
    """Explicit raw/converted point transform; registered/map clouds must not transform twice.
    Row points: p_target = R @ p_source + t, metres, right handed. Extra fields preserved.
    """
    if source_kind not in ('raw','converted','registered','map'): raise ValueError('unknown source kind')
    if not source_frame or not target_frame or not math.isfinite(tf_age) or not 0<=tf_age<=.2: raise ValueError('invalid frame or stale transform')
    p=np.asarray(points,float);t=np.asarray(transform,float)
    if p.ndim!=2 or p.shape[1]<4 or t.shape!=(4,4) or not np.all(np.isfinite(t)): raise ValueError('invalid cloud/transform')
    if not np.allclose(t[3],[0,0,0,1]) or not np.allclose(t[:3,:3].T@t[:3,:3],np.eye(3)) or not np.isclose(np.linalg.det(t[:3,:3]),1): raise ValueError('nonrigid transform')
    if source_kind in ('registered','map') and (source_frame!=target_frame or not np.allclose(t,np.eye(4))): raise ValueError('double registration forbidden')
    out=p.copy();out[:,:3]=p[:,:3]@t[:3,:3].T+t[:3,3]
    return out # NaNs preserved for explicit invalid counter in ground_filter
