"""Read-only semantic adapter. Never silently interpret arena_design as robot map."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARENA=ROOT.parents[2]/'assets/competition-arena/revisions/rulebook-20261015'
def inspect():
 a=json.loads((ARENA/'arena.semantic.json').read_text())
 assert a['frame_id']=='arena_design' and a['units']=='metre/radian'
 cases=[]
 for p in sorted(ARENA.glob('scenario_*.json')):
  s=json.loads(p.read_text());assert s['arena_revision']==a['revision'] and s['frame_id']==a['frame_id']
  assert not s['obstacles_baked_in_static_map'] and not s['gt_schedule_for_detector']
  cases.append({'id':s['scenario_id'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 return {'status':'CONTRACT_READ_ONLY_PASS','revision':a['revision'],'frame':a['frame_id'],'scenario_contracts':cases,'map_transform':a['map_transform'],'hardware_map_eligibility':False,'reason':'Map transform null, DRAFT course graph and unqualified provisional geometry','arena_closed_loop':'NOT_RUN','fixture_footprint_m':[.5,.36],'arena_assumed_footprint_m':[.6,.32],'footprints_interchangeable':False,'blocked_terrain':[z['id'] for z in a['semantic_zones'] if z.get('planar_navigation')=='BLOCKED_TERRAIN_HANDOFF']}
if __name__=='__main__':
 result=inspect();(ROOT/'results/arena_contract.json').write_text(json.dumps(result,indent=2));print(result['status'])
