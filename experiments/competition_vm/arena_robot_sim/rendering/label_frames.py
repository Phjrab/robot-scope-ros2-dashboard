"""Add visible provenance and replay timing to Blender frames, without pose edits."""
import json,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parent/'output'/sys.argv[1]
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13)
(root/'labeled').mkdir(exist_ok=True)
for item in json.loads((root/'rendered_frame_indices.json').read_text()):
 im=Image.open(root/'frames'/f"{item['image']:04}.png").convert('RGB');w,h=im.size;out=Image.new('RGB',(w,h+100),(16,23,31));out.paste(im,(0,56));dr=ImageDraw.Draw(out)
 dr.text((16,8),'GO2 | ACTUAL ARENA REVISION | VIRTUAL LiDAR',font=font,fill='white')
 dr.text((16,32),f"SIM t={item['t']:.1f}s | {item['state']} | Recorded kinematic replay",font=small,fill=(193,210,230))
 dr.text((16,h+64),'CYAN: sensed returns   YELLOW: executed path   GREEN: goal',font=small,fill=(100,230,211))
 dr.text((16,h+82),'SIM_GT pose, NOT VSLAM | Static stance, NOT gait/contact physics',font=small,fill=(245,198,120))
 out.save(root/'labeled'/f"{item['image']:04}.png")
