"""Pixel plot replay of actual saved trace; no hand-authored success motion.
The rectangle is the unchanged Go2 model-derived envelope, not a gait animation.
"""
import argparse,hashlib,json,math,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import regression as r
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
F=ImageFont.truetype(FONT,16);SM=ImageFont.truetype(FONT,13);TITLE=ImageFont.truetype(FONT,20)
W,H=1200,840

def main():
 paths=[HERE/'results'/n for n in ['empty_0__strict_no_parking__repeat1.json','offset_1__legacy_parking_allowed__repeat1.json','offset_1__strict_no_parking__repeat1.json','dense_10__strict_no_parking__repeat1.json']]
 docs=[json.loads(p.read_text()) for p in paths];fps=10;duration=max(d['frames'][-1]['pose_t'] for d in docs);count=math.ceil(duration*fps)+20
 out=HERE/'rendering';out.mkdir(exist_ok=True)
 video=out/'d0_planar_policy_comparison.mp4'
 proc=subprocess.Popen(['ffmpeg','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(fps),'-i','-','-an','-c:v','libx264','-crf','20','-pix_fmt','yuv420p',str(video)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 chosen=[]
 for n in range(count):
  t=n/fps;im=Image.new('RGB',(W,H),'#101824');d=ImageDraw.Draw(im)
  d.text((24,10),'D0 | SYNTHETIC / PLANAR | seed 20261024',font=TITLE,fill='white')
  d.text((24,38),'Saved trace only. Static legs/envelope; NOT gait / SLAM / full-course validation.',font=F,fill='#e8b86c')
  indexes=[]
  for k,doc in enumerate(docs):
   tile=Image.new('RGB',(600,355),'#101824');d=ImageDraw.Draw(tile);ox=0;oy=0;sc=doc['scene'];frames=doc['frames'];idx=min(int(t*10),len(frames)-1);indexes.append(idx);f=frames[idx]
   d.rectangle((ox+10,oy,ox+590,oy+352),outline='#536575',width=1)
   d.text((ox+20,oy+10),f"{sc['name']} | {sc['policy']}",font=F,fill='white')
   d.text((ox+20,oy+34),f"t={f['pose_t']:.1f}s | {f['state']}",font=F,fill='#87dda9' if f['state']=='GOAL_REACHED' else '#f0c070')
   def xy(p):return (ox+180+(p[0]-5.2)*75,oy+325-(p[1]-1.2)*75)
   # zoom uses actual fixed arena coordinates, never changes simulation geometry.
   for name,poly in sc['floor_polygons'].items():d.polygon([xy(p) for p in poly],fill='#293e49',outline='#61737e')
   pp=[xy(p) for p in sc['floor_polygons']['floor_parking_bay']]
   d.polygon(pp,fill='#472d36' if sc['policy']=='strict_no_parking' else '#344b3c',outline='#c67f7f')
   d.text(xy([6.65,3.1]),'P: forbidden' if sc['policy']=='strict_no_parking' else 'P: legacy allowance',font=SM,fill='#edc8c8')
   for c in sc['cones']:
    x,y=c['xy'];s=c['base_side_m']/2;a=xy((x-s,y+s));b=xy((x+s,y-s));d.rectangle([a,b],fill='#ff7e36',outline='#ffd6a1',width=1)
   trail=[xy(a['pose']) for a in frames[:idx+1]]
   if len(trail)>1:d.line(trail,fill='#66d1ee',width=2)
   p=r.polygon(f['pose'],sc['footprint']);d.polygon([xy(v) for v in p],fill='#dce6ef',outline='#101824')
   head=(f['pose'][0]+.30*math.cos(f['pose'][2]),f['pose'][1]+.30*math.sin(f['pose'][2]));d.line([xy(f['pose']),xy(head)],fill='#ed524b',width=3)
   for label,point,col in [('S',sc['start'],'#85d9a3'),('G',sc['goal'],'#ffee99')]:
    xx,yy=xy(point);d.ellipse((xx-4,yy-4,xx+4,yy+4),outline=col,width=2);d.text((xx+6,yy-10),label,font=SM,fill=col)
   d.rectangle((0,0,599,59),fill='#101824')
   d.text((ox+20,oy+10),f"{sc['name']} | {sc['policy']}",font=F,fill='white')
   d.text((ox+20,oy+34),f"t={f['pose_t']:.1f}s | {f['state']}",font=F,fill='#87dda9' if f['state']=='GOAL_REACHED' else '#f0c070')
   d.rectangle((0,326,599,354),fill='#101824')
   d.text((ox+20,oy+330),f"cones={len(sc['cones'])} | actual terminal: {doc['metrics']['outcome']} / {doc['metrics']['reason']}",font=SM,fill='#b7c6d4')
   im.paste(tile,((k%2)*600,65+(k//2)*365))
  d=ImageDraw.Draw(im)
  d.text((24,815),'Goal success is not inferred from SAFE_WAIT. Terrain and parking posture are NOT_RUN.',font=F,fill='white')
  proc.stdin.write(im.tobytes());chosen.append(dict(video_frame=n,trace_indices=indexes))
  if n in (0,count-1):im.save(out/('start.png' if n==0 else 'terminal.png'))
 proc.stdin.close();err=proc.stderr.read().decode();code=proc.wait()
 (out/'ffmpeg.log').write_text(err)
 if code:raise RuntimeError(err)
 manifest=dict(video=video.name,fps=fps,frames=count,source_files=[dict(file=str(p.relative_to(HERE)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],frame_indexes=chosen,render_kind='2D exact trace envelope replay; not robot gait animation')
 (out/'render_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(video)

if __name__=='__main__':main()
