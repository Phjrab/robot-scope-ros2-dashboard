"""Validate saved render mapping against recorded source state and joint timestamps."""
import json,argparse,hashlib,subprocess
from pathlib import Path
H=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);a=p.parse_args();out={}
for name in ('slalom_5','blocked_5'):
 source=a.source_root/'experiments/competition_vm/arena_robot_sim/revisions/left_slalom_20261024/results'/f'{name}.json';d=json.loads(source.read_text());joint=json.loads((H/'output'/f'{name}_joints.json').read_text());meta=json.loads((H/'output'/name/'rendered_frame_indices.json').read_text());assert hashlib.sha256(source.read_bytes()).hexdigest()==joint['validation']['trace_sha256']
 assert len(meta)==len(joint['records'])
 for m in meta:
  r=joint['records'][m['trace_index']];assert abs(m['t']-r['t'])<1e-12
  previous=max((f for f in d['frames'] if f['t']<=m['t']+1e-10),key=lambda x:x['t']);assert m['state']==previous['state']
  assert (H/'output'/name/'labeled'/f"{m['image']:04}.png").is_file()
 video=H/'output'/f'go2_articulated_{name}.mp4';probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height,r_frame_rate,nb_frames','-show_entries','format=duration','-of','json',str(video)]));assert int(probe['streams'][0]['nb_frames'])==len(meta)
 out[name]={'source_sha256':joint['validation']['trace_sha256'],'frame_count':len(meta),'source_t_range':[meta[0]['t'],meta[-1]['t']],'terminal_state':meta[-1]['state'],'state_mapping_verified':True,'probe':probe,'video_sha256':hashlib.sha256(video.read_bytes()).hexdigest()}
(H/'output/RENDER_VALIDATION.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
