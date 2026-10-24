"""Truthful full-course storyboard with recorded planar slalom, never terrain gait."""
from pathlib import Path
import argparse,json,hashlib,math,subprocess
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
REV=REPO/'assets/competition-arena/revisions/corridor-parallel-20261024'
W,H,FPS=1280,860,12
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
def font(s):return ImageFont.truetype(FONT,s)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def xy(p):return (55+float(p[0])*100,740-float(p[1])*100)
def box(pose,hx=.405,hy=.28):
 x,y,a=pose;c,s=math.cos(a),math.sin(a)
 return [[x+c*u-s*v,y+s*u+c*v] for u,v in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]
def route(draw,points,color,width=4,dashed=False):
 for a,b in zip(points,points[1:]):
  a,b=np.array(xy(a)),np.array(xy(b));length=np.linalg.norm(b-a)
  if dashed:
   for t in np.arange(0,length,16):
    aa=a+(b-a)*t/length;bb=a+(b-a)*min(t+8,length)/length
    draw.line([tuple(aa),tuple(bb)],fill=color,width=width)
  else:draw.line([tuple(a),tuple(b)],fill=color,width=width)
def create(trace,render=True):
 data=json.loads(Path(trace).read_text());sem=json.loads((REV/'arena.semantic.json').read_text())
 assert data['metrics']['outcome']=='GOAL_REACHED'
 assert data['scene']['arena_revision'].startswith('corridor-parallel')
 frames=data['frames'];t0=frames[0].get('pose_t',frames[0]['t']);t1=frames[-1].get('pose_t',frames[-1]['t'])
 phases=[('OVERVIEW',4),('IN',3),('RAMP_CROSSING',5),('SLALOM',(t1-t0)/4),('STAIR_CROSSING',5),('P_APPROACH',3),('P_HOLD',5),('OUT',4),('SUMMARY',3)]
 planned={
 'IN':[[7.4,5.49],[5.8,5.49]],
 'RAMP_CROSSING':[[5.8,5.49],[4.45,4.15],[3.3,3],[2.15,1.85],[1.15,.95],[.5,.95]],
 'STAIR_CROSSING':[[.5,5.05],[1.2,5.05],[2.3,4.0],[3.3,3],[4.45,1.85],[5.99,.8],[5.99,3]],
 'P_APPROACH':[[5.99,3],[7.25,3]],
 'OUT':[[7.25,3],[5.99,3],[5.99,.509],[8.6,.509]]}
 p_pose=[7.25,3,math.pi/2];p_poly=box(p_pose)
 contained=all(6.5<=x<=8 and 2.25<=y<=3.75 for x,y in p_poly)
 report={'schema':'full-course-storyboard.v1','scope':'DRAFT_SEQUENCE_NOT_END_TO_END_SIMULATION','full_course_pass':False,'physical_gait_validated':False,'official_route_confirmed':False,'map_transform':sem['map_transform'],'arena_revision':sem['revision'],'inputs':{'semantic_sha256':digest(REV/'arena.semantic.json'),'trace_sha256':digest(trace),'trace_original_path':str(trace)},'validated_subsystem':{'name':'left slalom validated fixed-yaw baseline controller','candidate_selection':'New curved controller on the same tight layout was not adopted; this uses the previous validated baseline','metrics':data['metrics'],'limitations':'SIM_GT ideal sensing; no contact dynamics'},'parking_geometry_only':{'pose':p_pose,'projected_footprint':p_poly,'fully_contained':contained,'display_hold_s':5,'physical_stopped':None,'sit_pose_validated':False,'rule_parking_success':False},'unvalidated':['IN transfer','both terrain crossings','signal-linked stopping/departure','P approach','physical sitting and stop dwell','whole-body OUT crossing'], 'planned_diagram_routes':planned,'phases':phases,'slalom_playback_speed':4,'video_fps':FPS,'terminal':'SEQUENCE_PREVIEW_COMPLETE_NOT_MISSION_SUCCESS'}
 out=HERE/'output';out.mkdir(exist_ok=True)
 (out/'SEQUENCE_VALIDATION.json').write_text(json.dumps(report,indent=2))
 # Compact copy retains ALL recorded poses/commands/states; no synthetic interpolation saved as observation.
 compact={'scene':data['scene'],'metrics':data['metrics'],'source_sha256':digest(trace),'frames':[{k:f[k] for k in ['t','pose_t','pose','v','w','vx_world','vy_world','state'] if k in f} for f in frames]}
 (out/'slalom_pose_fixture.json').write_text(json.dumps(compact,separators=(',',':')))
 labels={'OVERVIEW':('IN > cross > slalom > cross > P > OUT','DRAFT order, not official course qualification'), 'IN':('1. IN entry (planned)','No controller result for this transfer'), 'RAMP_CROSSING':('2. NE ramp > center > SW ramp','NOT_VALIDATED: terrain gait and signal rule'), 'SLALOM':('3. Recorded 5-cone slalom','FIXED-YAW BASELINE / actual trace / 4x'), 'STAIR_CROSSING':('4. NW stairs > center > SE stairs','NOT_VALIDATED: stair gait and signal rule'), 'P_APPROACH':('5. P approach (planned)','No parking approach controller result'), 'P_HOLD':('6. Parking footprint + 5s display hold','GEOMETRY ONLY: not sensed stop or sitting'), 'OUT':('7. OUT crossing (planned)','Proposed opening only; crossing NOT_VALIDATED'), 'SUMMARY':('Sequence preview complete','NOT a full-course autonomous success')}
 if not render:return report
 process=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p',str(out/'full_course_sequence_preview.mp4')],stdin=subprocess.PIPE)
 idx=0;timeline=[]
 for phase,duration in phases:
  n=max(1,round(duration*FPS));start=idx
  for j in range(n):
   im=Image.new('RGB',(W,H),'#101a22');d=ImageDraw.Draw(im)
   d.text((30,20),'GO2 | FULL COURSE SEQUENCE PREVIEW',font=font(27),fill='white')
   d.text((30,57),'DRAFT / NOT END-TO-END VALIDATED / NO PHYSICAL TERRAIN GAIT',font=font(18),fill='#ffba64')
   for z in sem['semantic_zones']:
    if z['type']=='WALKABLE':d.polygon([xy(p) for p in z['polygon']],fill='#294854',outline='#79a0ab')
   for z in sem['semantic_zones']:
    if z['type'] in ('RAMP','STAIRS','STOP_ZONE'):
     d.polygon([xy(p) for p in z['polygon']],fill={'RAMP':'#6d5b43','STAIRS':'#6d5b43','STOP_ZONE':'#d97c28'}[z['type']],outline='#e2b47b')
   for name,p in [('IN',(7.1,5.5)),('P',(7.2,3)),('OUT',(7.1,.5))]:d.text(xy(p),name,font=font(25),anchor='mm',fill='white')
   for c in data['scene']['cones']:
    x,y=c['xy'];s=c['base_side_m']/2;d.polygon([xy(q) for q in [(x-s,y-s),(x+s,y-s),(x+s,y+s),(x-s,y+s)]],fill='#ef8b25',outline='#ffc788')
   for name,path in planned.items():route(d,path,'#5a6971',2,True)
   if phase in planned:route(d,planned[phase],'#ffb348',5,True)
   if phase=='SLALOM':
    source_t=t0+(t1-t0)*j/max(1,n-1);times=np.array([f.get('pose_t',f['t']) for f in frames]);fi=max(0,int(np.searchsorted(times,source_t,side='right')-1));f=frames[fi]
    route(d,[q['pose'][:2] for q in frames[:fi+1]],'#63dfd3',4)
    d.polygon([xy(p) for p in box(f['pose'])],fill='#7de3ef',outline='white')
    a=f['pose'][2];q=f['pose'];d.line([xy(q[:2]),xy([q[0]+.35*math.cos(a),q[1]+.35*math.sin(a)])],fill='#112d38',width=4)
    d.text((940,335),f'Trace t={source_t:.1f}s',font=font(19),fill='#63dfd3')
    d.text((940,365),f['state'],font=font(15),fill='white')
   elif phase=='P_HOLD':
    d.polygon([xy(p) for p in p_poly],outline='#71dfd3',width=3)
    d.text((940,335),f'Display hold {j/FPS:.1f}/5.0s',font=font(18),fill='#71dfd3')
   d.line((920,100,920,745),fill='#42525e',width=2)
   title,sub=labels[phase]
   def wrap(text,width=27):
    import textwrap
    return '\n'.join(textwrap.wrap(text,width))
   d.text((940,120),wrap(title),font=font(21),fill='white',spacing=8)
   d.text((940,225),wrap(sub),font=font(17),fill='#ffba64',spacing=7)
   d.text((940,450),'STATUS',font=font(18),fill='#8ca6b5')
   d.text((940,485),'Slalom: planar checked\nTerrain: NOT_VALIDATED\nSignals: NOT_VALIDATED\nSitting: NOT_VALIDATED\nExit: NOT_VALIDATED',font=font(16),fill='#b7ccd5',spacing=12)
   d.text((35,780),'Cyan solid = recorded planar execution | Orange dashed = planned, NOT executed',font=font(20),fill='#c2d5df')
   d.text((35,814),'Parking outline = containment calculation only. No synthetic sit/physical-stop claim.',font=font(17),fill='#95aebc')
   if j==n//2 and phase in ('OVERVIEW','SLALOM','P_HOLD','SUMMARY'):im.save(out/f'preview_{phase.lower()}.png')
   process.stdin.write(im.tobytes());idx+=1
  timeline.append({'phase':phase,'first_frame':start,'frame_count':n,'duration_s':n/FPS,'evidence':'recorded controller trace' if phase=='SLALOM' else 'parking containment visualization' if phase=='P_HOLD' else 'unexecuted schematic'})
 process.stdin.close();assert process.wait()==0
 (out/'timeline.json').write_text(json.dumps(timeline,indent=2));return report
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('trace');a.add_argument('--no-render',action='store_true');args=a.parse_args();print(json.dumps(create(args.trace,not args.no_render),indent=2))
