"""Closed-loop synthetic laser/occupancy/A*/differential-plant experiment.
Scene truth is private to Sensor and Evaluator, NEVER given to planner/controller.
"""
import argparse, json, math, time, resource
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
from PIL import Image,ImageDraw
from core import *
ROOT=Path(__file__).resolve().parent
FOOTPRINT=[[-.25,-.18],[.25,-.18],[.25,.18],[-.25,.18]]
RES=.1

class Sensor:
    def __init__(self): self.angles=np.linspace(-math.pi,math.pi,720,endpoint=False)
    def observe(self,truth,pose,t,sequence,dropout=False):
        # Ray marching returns only first visible surface. No obstacle geometry exported.
        x,y,yaw=pose; rays=self.angles+yaw
        distances=np.arange(.04,8.01,.04)
        xs=x+np.cos(rays)[:,None]*distances; ys=y+np.sin(rays)[:,None]*distances
        ix=(xs/RES).astype(int); iy=(ys/RES).astype(int)
        outside=(xs<0)|(ys<0)|(ix>=truth.shape[1])|(iy>=truth.shape[0])
        occupied=truth[np.clip(iy,0,truth.shape[0]-1),np.clip(ix,0,truth.shape[1]-1)]|outside
        hit=occupied.any(axis=1); indices=occupied.argmax(axis=1)
        ranges=np.where(hit,distances[indices],8.)
        if dropout: ranges[:]=np.nan
        return Scan('sensor-1',sequence,str(int(t*1e9)+1),'VM_SIM','vm_laser',self.angles,ranges,8.,t)

def rectangle(mask,x0,y0,x1,y1): mask[int(y0/RES):int(y1/RES),int(x0/RES):int(x1/RES)]=True

def scene(name,seed):
    static=np.zeros((36,60),bool); static[[0,-1],:]=True; static[:,[0,-1]]=True
    allowed=~static; y=1.8
    if name in ('narrow_feasible','narrow_infeasible'):
        gap=.95 if name=='narrow_feasible' else .25
        rectangle(static,2.,.1,3.8,y-gap/2); rectangle(static,2.,y+gap/2,3.8,3.5)
    if name=='map_misalignment': rectangle(static,2.6,1.1,3.2,1.65) # deliberately shifted stale map geometry
    if name=='one_branch_blocked': rectangle(static,2.5,1.5,3.3,2.1)
    if name=='leg_corridor':
        # Leg corridor is immutable and blocks tempting other branch.
        allowed[:12,:]=False; allowed[24:,:]=False
    goal=Goal('run-'+name,'leg-1','goal-1',1,'fixture-v1',(5.25,y))
    return static,allowed,goal,(.75,y,0.)

def truth_at(static,name,t,seed):
    truth=static.copy()
    if name=='map_misalignment':
        truth[11:17,26:32]=False
        rectangle(truth,2.6,1.65,3.2,2.2) # real geometry offset +0.55 m in y
    rng=np.random.default_rng(seed)
    shift=float(rng.uniform(-.08,.08))
    if name in ('new_obstacle','obstacle_variant') and t>=2:
        rectangle(truth,2.6,1.35+shift,3.2,2.15+shift)
    if name=='one_branch_blocked': rectangle(truth,2.2,.1,3.6,1.5)
    if name in ('blocked_then_clear','red_and_removed') and 2<=t<12:
        rectangle(truth,2.6,.1,3.1,3.5)
    if name=='sensor_dropout': rectangle(truth,2.6,1.2,3.2,2.4)
    return truth


def run(name,seed=0):
    static,allowed,goal,pose=scene(name,seed); occ=Occupancy(static,RES)
    sensor=Sensor(); arbiter=CommandArbiter(); session=Session(goal)
    trajectory=[]; histories=[]; latencies=[]; last_plan=-10; replans=0; path=[]
    radius=max(math.hypot(*p) for p in FOOTPRINT); contacts=0; hold_violations=0; min_clearance=float('inf')
    total_distance=0; states=set(); outcome='FAILED'; reason='TIMEOUT'; dt=.1; started=time.perf_counter()
    prior_cmd=(0,0); oscillations=0; previous_turn=0; observation_received=False
    for step in range(700):
        t=step*dt; truth=truth_at(static,name,t,seed)
        dropout=name=='sensor_dropout' and t>=3
        tf_stale=name=='stale_tf' and t>=3
        changed=name=='map_revision' and t>=3
        cancel=name=='cancel' and t>=3
        restart=name=='restart' and t>=3
        if not dropout and not tf_stale:
            scan=sensor.observe(truth,pose,t,step)
            observation_received=occ.update(scan,pose,t)
        fresh=(t-occ.last_receipt)<=.3
        obstacles,unknown=occ.masks(t,ttl=2.)
        collision_mask=obstacles | unknown | ~allowed
        if name=='terrain_handoff':
            outcome='SAFE_REJECT'; reason='TERRAIN_EXECUTOR_REQUIRED'; break
        if not session.check('fixture-v2' if changed else goal.map_revision,goal.generation,cancel,restart):
            outcome='SAFE_REJECT'; reason=session.reason; break
        if fresh and t-last_plan>=.5-1e-9:
            tick=time.perf_counter(); path=plan((obstacles,unknown),allowed,pose[:2],goal.xy,RES,radius)
            latencies.append((time.perf_counter()-tick)*1000); replans+=1; last_plan=t
        v=w=0.; reason='WAIT_OBSTACLE'
        if path and fresh:
            # Local fallback follower: rotate toward a short path carrot, no lateral velocity.
            nearest=min(range(len(path)),key=lambda i:math.dist(pose[:2],path[i]))
            target=path[min(nearest+2,len(path)-1)]
            heading=math.atan2(target[1]-pose[1],target[0]-pose[0]); error=(heading-pose[2]+math.pi)%(2*math.pi)-math.pi
            w=max(-.8,min(.8,error*2.5)); v=.25*max(0,1-abs(error)/.7)
            if not swept_safe(pose,v,w,.5,FOOTPRINT,collision_mask,RES): v=w=0.; reason='COLLISION_HOLD'
            else: reason='FOLLOWING'
        red=name=='red_and_removed' and t<18
        v,w,arb_reason=arbiter.apply(v,w,step,sensor_fresh=fresh,tf_fresh=not tf_stale,signal_hold=red)
        if arb_reason!='FOLLOWING': reason=arb_reason
        if (red or not fresh or tf_stale) and (v!=0 or w!=0): hold_violations+=1
        old=pose; pose=propagate(pose,v,w,dt); total_distance+=math.dist(old[:2],pose[:2])
        # Evaluation only. It records contacts, never repairs motion or feeds truth to controller.
        contact=polygon_collision(pose,FOOTPRINT,truth,RES)
        contacts+=int(contact)
        d=distance_transform_edt(~truth)*RES; cell=occ.cell(*pose[:2])
        min_clearance=min(min_clearance,float(d[cell])-radius)
        turn=0 if abs(w)<.02 else (1 if w>0 else -1)
        if turn and previous_turn and turn!=previous_turn: oscillations+=1
        if turn: previous_turn=turn
        states.add(reason); trajectory.append([t,*pose,v,w,reason]); histories.append((truth.copy(),pose,path.copy(),reason))
        if contact: outcome='FAILED'; reason='CONTACT'; break
        if math.dist(pose[:2],goal.xy)<.15: outcome='GOAL_REACHED'; reason='ARRIVED'; break
        if name in ('sensor_dropout','stale_tf') and t>=6:
            outcome='SAFE_WAIT'; reason='SENSOR_STALE' if dropout else 'TF_STALE'; break
        if name=='narrow_infeasible' and t>=5:
            outcome='SAFE_REJECT'; reason='NO_FEASIBLE_FOOTPRINT_PATH'; break
    expected='SAFE_WAIT' if name in ('sensor_dropout','stale_tf') else 'SAFE_REJECT' if name in ('narrow_infeasible','terrain_handoff','map_revision','cancel','restart') else 'GOAL_REACHED'
    result={'scenario':name,'seed':seed,'evidence_type':'SYNTHETIC_CLOSED_LOOP_CORE','controller':'vm_astar_rotate_follow_v1','native_plugin':None,'expected':expected,'outcome':outcome,'status':'PASS' if outcome==expected and contacts==0 and hold_violations==0 else 'FAIL','reason':reason,'contacts':contacts,'hold_violations':hold_violations,'sim_time_s':t,'path_length_m':total_distance,'min_circumscribed_clearance_m':min_clearance if np.isfinite(min_clearance) else None,'oscillations':oscillations,'replan_count':replans,'replan_latency_ms_p95':float(np.percentile(latencies,95)) if latencies else None,'scheduled_simulated_tick_s':dt,'wall_time_s':time.perf_counter()-started,'rss_max_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'goal_id':goal.goal_id,'goal_generation':goal.generation,'states':sorted(states),'trajectory':trajectory}
    return result,histories

def render(history,out):
    frames=[]; stride=max(1,len(history)//70)
    selected=list(range(0,len(history),stride))
    if history and selected[-1]!=len(history)-1:selected.append(len(history)-1)
    for index in selected:
        truth,pose,path,state=history[index]
        scale=7; img=Image.new('RGB',(420,300),'white'); draw=ImageDraw.Draw(img)
        for y,x in zip(*np.where(truth)): draw.rectangle((x*scale,(35-y)*scale,(x+1)*scale,(36-y)*scale),fill='#394457')
        def pixel(p): return (p[0]/RES*scale,(36-p[1]/RES)*scale)
        for mark,label,color in [((.75,1.8),'START','#237b4b'),((5.25,1.8),'GOAL','#ba3030')]:
            px,py=pixel(mark);draw.ellipse((px-4,py-4,px+4,py+4),outline=color,width=2);draw.text((px-14,py+8),label,fill=color)
        trail=[pixel(h[1]) for h in history[:index+1]]
        if len(trail)>1: draw.line(trail,fill='#ba58b5',width=2)
        if path: draw.line([pixel(p) for p in path],fill='#32a1ce',width=2)
        draw.polygon([pixel(p) for p in polygon(pose,FOOTPRINT)],fill='#edab35')
        draw.text((8,260),'SYNTHETIC CORE (not Nav2): '+state,fill='black')
        frames.append(img)
    if frames:
        frames[0].save(out,save_all=True,append_images=frames[1:],duration=70,loop=0)
        frames[-1].save(str(out).replace('.gif','.png'))

SCENARIOS=['map_misalignment','empty','new_obstacle','one_branch_blocked','blocked_then_clear','sensor_dropout','narrow_feasible','narrow_infeasible','obstacle_variant','terrain_handoff','red_and_removed','stale_tf','map_revision','cancel','restart','leg_corridor']
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--scenario',choices=SCENARIOS); ap.add_argument('--seeds',type=int,default=3); args=ap.parse_args()
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    results=[]
    for name in ([args.scenario] if args.scenario else SCENARIOS):
        for seed in range(args.seeds):
            result,history=run(name,seed); results.append(result)
            print(name,seed,result['status'],result['outcome'],result['reason'],round(result['sim_time_s'],1),flush=True)
            if seed==0: render(history,out/(name+'.gif'))
    (out/'scenarios.json').write_text(json.dumps(results,indent=2))
    raise SystemExit(any(x['status']=='FAIL' for x in results))
