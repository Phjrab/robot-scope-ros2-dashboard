"""Bounded offline SE(2) witness search; never a Nav2 reference trajectory.
Search uses SAT padded rectangles. Independent sweep uses segment distances and
point containment on the unpadded actual body, with a continuous Lipschitz bound.
"""
import hashlib, heapq, json, math, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
DX=.025; DY=.025; ANGLES=36; MAX_SECONDS=90.; EPS=1e-10

def canonical_hash(scene):
    return hashlib.sha256(json.dumps(scene,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def boxes(scene):
    out=[]
    for c in scene['cones']:
        x,y=c['xy'];h=c['base_side_m']/2
        out.append([[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]])
    return out + list(scene['forbidden_polygons'])

def vertices(poses,body):
    poses=np.atleast_2d(poses);b=np.asarray(body)
    c=np.cos(poses[:,2]);s=np.sin(poses[:,2]);rot=np.array([[c,-s],[s,c]]).transpose(2,0,1)
    return np.einsum('nij,kj->nki',rot,b)+poses[:,None,:2]

def point_inside(points,poly):
    p=np.asarray(points);out=np.zeros(p.shape[:-1],bool)
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        if a[1]!=b[1]:
            out ^= ((a[1]>p[...,1])!=(b[1]>p[...,1])) & (p[...,0] < (b[0]-a[0])*(p[...,1]-a[1])/(b[1]-a[1])+a[0])
    return out

def sat_overlap_batch(robot,poly):
    """Closed SAT for convex polygons; all exported forbidden polygons convex."""
    poly=np.asarray(poly);edges=np.roll(poly,-1,axis=0)-poly
    redges=np.roll(robot,-1,axis=1)-robot
    separated=np.zeros(len(robot),bool)
    for axis in np.column_stack((-edges[:,1],edges[:,0])):
        a=robot@axis;b=poly@axis
        separated |= (a.max(1)<b.min()-EPS)|(a.min(1)>b.max()+EPS)
    for i in range(2):
        axes=np.stack((-redges[:,i,1],redges[:,i,0]),1)
        a=np.einsum('nki,ni->nk',robot,axes);b=np.einsum('ki,ni->nk',poly,axes)
        separated |= (a.max(1)<b.min(1)-EPS)|(a.min(1)>b.max(1)+EPS)
    return ~separated

def search_valid(poses,scene,circle_radius=None):
    margin=scene['clearance_m']+.001
    if circle_radius is not None:
        # Circumscribed 64-gon has circle vertices, so add discretization reserve.
        radius=circle_radius/math.cos(math.pi/64)+margin
        body=[[radius*math.cos(a),radius*math.sin(a)] for a in np.arange(64)*2*math.pi/64]
    else:
        body=np.asarray(scene['footprint']);body=body+np.sign(body)*margin
    robot=vertices(poses,body);floor=np.asarray(scene['boundary_polygon'])
    valid=point_inside(robot,floor).all(1)
    # Require every boundary segment to be disjoint from body. This also rejects
    # concave floor indentations that corner-only tests would miss.
    for a,b in zip(floor,np.roll(floor,-1,axis=0)):
        valid &= ~sat_overlap_batch(robot,np.array([a,b]))
    for poly in boxes(scene):valid &= ~sat_overlap_batch(robot,poly)
    return valid

def search(scene,circle_radius=None):
    started=time.monotonic();floor=np.asarray(scene['boundary_polygon'])
    xs=np.arange(math.ceil(floor[:,0].min()/DX),math.floor(floor[:,0].max()/DX)+1)*DX
    ys=np.arange(math.ceil(floor[:,1].min()/DY),math.floor(floor[:,1].max()/DY)+1)*DY
    yaw=np.arange(ANGLES)*2*math.pi/ANGLES
    xx,yy,aa=np.meshgrid(xs,ys,yaw,indexing='ij');poses=np.stack([xx,yy,aa],-1)
    valid=search_valid(poses.reshape(-1,3),scene,circle_radius).reshape(poses.shape[:3])
    def index(p):return (int(round((p[0]-xs[0])/DX)),int(round((p[1]-ys[0])/DY)),int(round(p[2]*ANGLES/(2*math.pi)))%ANGLES)
    start=index(scene['start']);goal=index(scene['goal']);visited={start:None};cost={start:0.};q=[(0.,0.,start)];expanded=0;found=False
    if valid[start] and valid[goal]:
        while q and time.monotonic()-started<MAX_SECONDS:
            _,g,u=heapq.heappop(q)
            if g!=cost[u]:continue
            expanded+=1
            if u==goal:found=True;break
            for d in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
                v=(u[0]+d[0],u[1]+d[1],(u[2]+d[2])%ANGLES)
                if not (0<=v[0]<len(xs) and 0<=v[1]<len(ys)) or not valid[v]:continue
                ng=g+(DX if d[0] else DY if d[1] else .493*2*math.pi/ANGLES)
                if ng>=cost.get(v,float('inf')):continue
                # Yaw midpoint prunes coarse rotation candidates. Translation edges are
                # candidates only: the independent continuous sweep certifies the result.
                mid=(poses[u]+poses[v])/2
                if abs(poses[u][2]-poses[v][2])>math.pi:mid[2]+=math.pi
                if d[2] and not search_valid([mid],scene,circle_radius)[0]:continue
                cost[v]=ng;visited[v]=u
                h=abs(v[0]-goal[0])*DX+abs(v[1]-goal[1])*DY
                heapq.heappush(q,(ng+h,ng,v))
    path=[]
    if found:
        u=goal
        while u is not None:path.append(poses[u].tolist());u=visited[u]
        path.reverse();path[0]=scene['start'];path[-1]=scene['goal']
        for i in range(1,len(path)):
            while path[i][2]-path[i-1][2]>math.pi:path[i][2]-=2*math.pi
            while path[i][2]-path[i-1][2]<-math.pi:path[i][2]+=2*math.pi
    return path,dict(status='WITNESS_CANDIDATE' if found else 'NO_WITNESS_WITHIN_BOUNDS',expanded_states=expanded,valid_states=int(valid.sum()),lattice_states=int(valid.size),elapsed_s=time.monotonic()-started,position_resolution_m=[DX,DY],yaw_bins=ANGLES,yaw_resolution_degrees=360/ANGLES,yaw_extent_radians=[0,2*math.pi],xy_extent_m=[[float(xs[0]),float(xs[-1])],[float(ys[0]),float(ys[-1])]],time_limit_s=MAX_SECONDS,start_valid=bool(valid[start]),goal_valid=bool(valid[goal]))

# Independent continuous verifier: no SAT, occupancy raster or candidate collision import.
def cross(a,b):return a[...,0]*b[...,1]-a[...,1]*b[...,0]
def edge_distance(robot,poly):
    a=robot;b=np.roll(a,-1,axis=1);c=np.broadcast_to(poly,(len(a),len(poly),2));d=np.roll(c,-1,axis=1)
    v=b-a;w=d-c;delta=c[:,None,:,:]-a[:,:,None,:]
    den=cross(v[:,:,None,:],w[:,None,:,:]);safe=np.where(abs(den)<1e-15,np.nan,den)
    t=cross(delta,w[:,None,:,:])/safe;u=cross(delta,v[:,:,None,:])/safe
    hit=((t>=0)&(t<=1)&(u>=0)&(u<=1)).any(axis=(1,2))
    def points_edges(p,x,y):
        z=y-x;delta=p[:,:,None,:]-x[:,None,:,:]
        frac=np.clip((delta*z[:,None,:,:]).sum(-1)/(z*z).sum(-1)[:,None,:],0,1)
        return np.linalg.norm(delta-frac[...,None]*z[:,None,:,:],axis=-1).min(axis=(1,2))
    dist=np.minimum(points_edges(a,c,d),points_edges(c,a,b))
    return np.where(hit,0.,dist)

def sweep(path,scene):
    if len(path)<2:return {'certified':False,'reason':'need at least two witness poses'}
    radius=max(math.hypot(*p) for p in scene['footprint']);minimum=float('inf');count=0
    for p,q in zip(path,path[1:]):
        p=np.asarray(p);q=np.asarray(q);motion=np.linalg.norm(q[:2]-p[:2])+radius*abs(q[2]-p[2])
        n=max(1,math.ceil(motion/.001));samples=p+(q-p)*np.linspace(0,1,n+1)[:,None]
        # Independently construct rotation rather than call search transform.
        c=np.cos(samples[:,2]);s=np.sin(samples[:,2]);b=np.asarray(scene['footprint'])
        robot=np.stack([samples[:,0,None]+c[:,None]*b[:,0]-s[:,None]*b[:,1],samples[:,1,None]+s[:,None]*b[:,0]+c[:,None]*b[:,1]],-1)
        floor=np.asarray(scene['boundary_polygon']);clear=edge_distance(robot,floor)
        clear=np.where(point_inside(robot,floor).all(1),clear,0.)
        for poly in boxes(scene):
            poly=np.asarray(poly);dist=edge_distance(robot,poly)
            contained=point_inside(robot,poly).any(1)
            for j,r in enumerate(robot):contained[j] |= point_inside(poly,r).any()
            clear=np.minimum(clear,np.where(contained,0.,dist))
        minimum=min(minimum,float(clear.min())-motion/(2*n));count+=n+1
    return dict(certified=bool(minimum>=scene['clearance_m']-EPS),minimum_continuous_clearance_lower_bound_m=minimum,samples=count,max_vertex_motion_per_sample_m=.001,method='independent segment distance + containment; translation plus corner-radius*yaw Lipschitz bound')

def main():
    from export_fixtures import scenes
    output={'scope':'OFFLINE_GEOMETRIC_FEASIBILITY_ONLY_NOT_NATIVE_NAV2','search_note':'Lattice candidate edges require independent continuous certification; search timeout is checked between expansions, not hard process preemption. No witness is not a continuous impossibility proof.','results':{}}
    for name,scene in scenes().items():
        path,result=search(scene);result['input_sha256']=canonical_hash(scene)
        result['independent_sweep']=sweep(path,scene)
        if result['independent_sweep']['certified']:
            result['status']='CERTIFIED_FEASIBLE_WITNESS'
            file=HERE/'witnesses'/f'{name}.json';file.write_text(json.dumps({'scenario':name,'input_sha256':result['input_sha256'],'use':'FEASIBILITY_ONLY_NEVER_NATIVE_PLANNER_ANSWER_PATH','poses':path},separators=(',',':'))+'\n');result['witness']=str(file.relative_to(HERE))
        output['results'][name]=result;print(name,result,flush=True)
    scene=scenes()['original_tight5'];radius=math.hypot(.405,.28)
    path,r=search(scene,radius);r['input_sha256']=canonical_hash(scene);r['radius_m']=radius;output['circumscribed_circle_diagnostic']=r
    output['clearance_accounting']={'actual_rectangle_m':[.81,.56],'padded_rectangle_m':[.87,.62],'margin_once_m':.03,'raw_circumscribed_radius_m':radius,'radius_plus_margin_m':radius+.03,'padded_rectangle_circumscribed_radius_m':math.hypot(.435,.31),'corridor_width_m':1.,'cone_base_width_m':.26,'fixed_yaw_passage_after_left_cone_m':1.-(.18+.13),'padded_transverse_width_m':.62,'remaining_fixed_yaw_lateral_slack_m':.07,'cone_pair_free_longitudinal_gap_m':3.-.13-(1.83+.13),'padded_body_longitudinal_length_m':.87,'remaining_switch_y_slack_m':.04,'warning':'Do not apply circumscribed robot inflation, padded footprint, and .03 clearance cumulatively. Existing rectangular grid expansion is configuration-space candidate generation; full polygon validation does not itself add another margin. .01m closed-cell rasterization and EDT threshold add discretization conservatism, not physical geometry.'}
    (HERE/'feasibility_results.json').write_text(json.dumps(output,indent=2)+'\n')
if __name__=='__main__':main()
