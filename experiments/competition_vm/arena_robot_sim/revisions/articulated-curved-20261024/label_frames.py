"""Annotate saved Blender renders without altering poses or state."""
import json,sys,argparse,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
here=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--trace-path');p.add_argument('--motion-label',default='VARIABLE YAW');p.add_argument('--title',default='CURVED EVASION');a=p.parse_args();case=a.case;root=here/'output'/case
source=json.loads(Path(a.trace_path).read_text()) if a.trace_path else None
joints=json.loads((here/'output'/f'{case}_joints.json').read_text())['records']
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
(root/'labeled').mkdir(exist_ok=True)
for item in json.loads((root/'rendered_frame_indices.json').read_text()):
 im=Image.open(root/'frames'/f"{item['image']:04}.png").convert('RGB');w,h=im.size;out=Image.new('RGB',(w,h+130),(16,23,31));out.paste(im,(0,64));dr=ImageDraw.Draw(out)
 title=('GO2 | '+a.title+' | KINEMATIC / SYNTHETIC PLANAR') if source else 'GO2 | KINEMATIC JOINT ANIMATION | SYNTHETIC / PLANAR'
 dr.text((16,8),title,font=font,fill='white')
 dr.text((16,37),f"{a.motion_label+' | ' if source else ''}Source trace t={item['t']:.2f}s | {item['state']} | 1x replay / SIM_GT",font=small,fill=(193,210,230))
 dr.text((16,h+71),'Joint IK + stance anchors, NOT contact dynamics / gait-policy validation',font=small,fill=(245,198,120))
 dr.text((16,h+94),'Virtual fences lowered for visibility ONLY; stored sensing/path unchanged',font=small,fill=(193,210,230))
 if source:
  panel=Image.new('RGB',(154,414),(21,35,42));dd=ImageDraw.Draw(panel)
  def xy(x,y):return (int(77+(x-.5)*70),int(388-(y-.5)*70))
  dd.text((8,7),'TRACE TOP VIEW',font=small,fill='white')
  for poly in source['scene']['allowed_floor_polygons'].values():dd.polygon([xy(*v) for v in poly],fill=(47,76,86),outline=(160,180,185))
  for c in source['scene']['cones']:
   x,y=c['xy'];half=c['base_side_m']/2;dd.rectangle([xy(x-half,y+half),xy(x+half,y-half)],fill=(243,104,22))
  current=min(range(len(joints)),key=lambda j:abs(joints[j]['t']-item['t']));path=[xy(*r['pose'][:2]) for r in joints[:current+1]]
  if len(path)>1:dd.line(path,fill=(240,205,50),width=2)
  x,y,yaw=joints[current]['pose'];body=[]
  for bx,by in source['scene']['footprint']:body.append(xy(x+bx*math.cos(yaw)-by*math.sin(yaw),y+bx*math.sin(yaw)+by*math.cos(yaw)))
  dd.polygon(body,fill=(190,230,245),outline='white');out.paste(panel,(w-166,83))
 out.save(root/'labeled'/f"{item['image']:04}.png")
