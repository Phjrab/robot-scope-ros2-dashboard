"""Replay stored flat traces; never animate unexecuted terrain transitions."""
from pathlib import Path
import sys,json,math,hashlib,subprocess,textwrap
import numpy as np
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'full_course_sequence_20261024'));import build_sequence as art
SLALOM=Path('/workspace/scratch/b09eacf6919d/robot-scope-left-slalom-20261024/experiments/competition_vm/arena_robot_sim/revisions/left_slalom_20261024/results/slalom_5.json')
W,H,FPS=1280,860,12
font,box,route=art.font,art.box,art.route
def xy(p):return (60+float(p[0])*90,735-float(p[1])*90)
art.xy=xy

def main():
 out=HERE/'output';sem=json.loads((art.REV/'arena.semantic.json').read_text());slalom=json.loads(SLALOM.read_text());data={n:json.loads((out/f'{n}.json').read_text()) for n in ('in','parking','out')};data['slalom']=slalom
 holdidx=next(i for i,f in enumerate(data['parking']['frames']) if f['state']=='ZERO_COMMAND_HOLD')
 sets={'IN':data['in']['frames'],'SLALOM':slalom['frames'],'P_APPROACH':data['parking']['frames'][:holdidx+1],'P_HOLD':data['parking']['frames'][holdidx:],'OUT':data['out']['frames']}
 speeds={'IN':2,'SLALOM':4,'P_APPROACH':2,'P_HOLD':1,'OUT':4}
 phases=[('OVERVIEW',3),('IN',None),('RAMP_GAP',5),('SLALOM',None),('STAIR_GAP',5),('P_APPROACH',None),('P_HOLD',None),('OUT',None),('SUMMARY',4)]
 labels={
 'OVERVIEW':('IN > cross > slalom > cross > P > OUT','PARTIAL recorded simulation, NOT full completion'),
 'IN':('1. IN flat approach','CLOSED LOOP / static map / 2x'),
 'RAMP_GAP':('2. NE > center > SW crossing','NOT EXECUTED: terrain + signal gap; reset before slalom'),
 'SLALOM':('3. Five-cone slalom','VALIDATED FIXED-YAW BASELINE / recorded / 4x'),
 'STAIR_GAP':('4. NW > center > SE crossing','NOT EXECUTED: stairs + signal gap; reset before P leg'),
 'P_APPROACH':('5. Flat approach into P','CLOSED LOOP / static map / 2x'),
 'P_HOLD':('6. P zero-command hold','5s simulated state hold, NOT actual sit or physical stop'),
 'OUT':('7. P > proposed OUT exit','CLOSED LOOP / scene-only opening + apron / 4x'),
 'SUMMARY':('Partial simulation complete','Terrain gaps remain. NOT end-to-end success')}
 diagrams={'RAMP_GAP':[[6.1,5.49],[4.45,4.15],[3.3,3],[2.15,1.85],[1.15,.95],[.5,.95]],'STAIR_GAP':[[.5,5.05],[1.2,5.05],[2.3,4],[3.3,3],[4.45,1.85],[5.99,1.5],[5.99,2]]}
 process=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-crf','20','-preset','fast','-pix_fmt','yuv420p',str(out/'full_course_partial_closed_loop.mp4')],stdin=subprocess.PIPE)
 timeline=[];idx=0;completed=[]
 for phase,seconds in phases:
  fs=sets.get(phase);t0=fs[0]['pose_t'] if fs else 0;t1=fs[-1]['pose_t'] if fs else 0
  if seconds is None:seconds=(t1-t0)/speeds[phase]
  n=max(1,round(seconds*FPS));start=idx
  for j in range(n):
   im=Image.new('RGB',(W,H),'#101a22');d=ImageDraw.Draw(im)
   d.text((30,20),'GO2 | PARTIAL CLOSED-LOOP COURSE DEMO',font=font(27),fill='white')
   d.text((30,57),'PLANAR / SEGMENT RESETS AT TERRAIN GAPS / NO GAIT PHYSICS / NO FULL-COURSE PASS',font=font(16),fill='#ffba64')
   for z in sem['semantic_zones']:
    if z['type']=='WALKABLE':d.polygon([xy(p) for p in z['polygon']],fill='#294854',outline='#79a0ab')
   for z in sem['semantic_zones']:
    if z['type'] in ('RAMP','STAIRS','STOP_ZONE'):d.polygon([xy(p) for p in z['polygon']],fill='#6d5b43' if z['type']!='STOP_ZONE' else '#d97c28',outline='#e2b47b')
   for label,p in [('IN',(7.1,5.7)),('P',(7.5,3.5)),('OUT',(7.1,.2))]:d.text(xy(p),label,font=font(23),anchor='mm',fill='white')
   for c in slalom['scene']['cones']:
    x,y=c['xy'];h=c['base_side_m']/2;d.polygon([xy(q) for q in [(x-h,y-h),(x+h,y-h),(x+h,y+h),(x-h,y+h)]],fill='#ef8b25',outline='#ffc788')
   for path in diagrams.values():route(d,path,'#5a6971',2,True)
   for done in completed:
    if done in sets:route(d,[f['pose'][:2] for f in sets[done]],'#386b74',3)
   if phase in diagrams:route(d,diagrams[phase],'#ffb348',5,True)
   if phase=='OUT':
    d.polygon([xy(q) for q in [[8,0],[9.2,0],[9.2,1.018],[8,1.018]]],outline='#ffba64',width=2)
    d.line([xy([8,0]),xy([8,1.018])],fill='#69edbf',width=3)
   if fs:
    st=t0+(t1-t0)*j/max(1,n-1);times=np.array([f['pose_t'] for f in fs]);fi=max(0,int(np.searchsorted(times,st,side='right')-1));f=fs[fi]
    route(d,[z['pose'][:2] for z in fs[:fi+1]],'#63dfd3',4);d.polygon([xy(q) for q in box(f['pose'])],fill='#7de3ef',outline='white')
    x,y,a=f['pose'];d.line([xy([x,y]),xy([x+.32*math.cos(a),y+.32*math.sin(a)])],fill='#112d38',width=4)
    d.text((940,350),f'Trace t={st:.1f}s',font=font(19),fill='#63dfd3');d.text((940,380),'\n'.join(textwrap.wrap(f['state'],25)),font=font(14),fill='white')
    if phase=='P_HOLD':d.text((940,420),f'Hold {st-t0:.1f}/5.0s',font=font(17),fill='#63dfd3')
   d.line((920,100,920,745),fill='#42525e',width=2)
   title,sub=labels[phase];d.text((940,115),'\n'.join(textwrap.wrap(title,26)),font=font(21),fill='white',spacing=8);d.text((940,225),'\n'.join(textwrap.wrap(sub,29)),font=font(17),fill='#ffba64',spacing=7)
   d.text((940,475),'COVERAGE',font=font(17),fill='#8ca6b5');d.text((940,510),'IN / P / OUT: planar\nSlalom: old baseline\nTerrain: NOT EXECUTED\nSignals: NOT VALIDATED\nSitting: NOT VALIDATED\nOUT opening: ASSUMED',font=font(15),fill='#b7ccd5',spacing=10)
   d.text((35,780),'Cyan = actual saved controller trace | Orange dashed = UNEXECUTED terrain transition',font=font(18),fill='#c2d5df')
   d.text((35,815),'P holds zero command for 5s; no sitting. OUT crosses a proposed plane, not a confirmed real gate.',font=font(16),fill='#95aebc')
   if j==n//2:im.save(out/f'preview_{phase.lower()}.png')
   process.stdin.write(im.tobytes());idx+=1
  timeline.append({'phase':phase,'first_frame':start,'frame_count':n,'video_duration_s':n/FPS,'source_time_start':t0 if fs else None,'source_time_end':t1 if fs else None,'playback_speed':speeds.get(phase),'mode':'recorded planar simulation' if fs else 'unexecuted schematic','reset_before':phase in ('SLALOM','P_APPROACH')});completed.append(phase)
 process.stdin.close();assert process.wait()==0
 (out/'timeline.json').write_text(json.dumps(timeline,indent=2))
 inputs={n:{'sha256':hashlib.sha256((SLALOM if n=='slalom' else out/f'{n}.json').read_bytes()).hexdigest(),'metrics':v['metrics']} for n,v in data.items()}
 (out/'DEMO_VALIDATION.json').write_text(json.dumps({'full_course_pass':False,'physical_gait_validated':False,'source_controller_note':'flat segments reuse VM A*/smoothing/bounded velocity family; slalom is prior fixed-yaw baseline, NOT new tight-layout curved success','inputs':inputs,'terrain_and_signal_gaps':'not executed','parking_physics':'not validated, planar position+zero command only','exit':'assumed opening and apron, original asset untouched','video_frames':idx,'fps':FPS},indent=2))
if __name__=='__main__':main()
