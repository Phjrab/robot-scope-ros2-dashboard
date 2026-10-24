"""Deterministic design geometry, not a measured navigation map. SI / Z-up."""
import math, random, json, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REV='rulebook-20261015-v1'
BASE='b1077e39e4ee456621c47eada49b1f0c85453661'
Q=2**-.5; C=(3.3,3.)
def p(u,v):return [C[0]+Q*(u-v),C[1]+Q*(u+v)]
def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
def oriented(u0,u1,v0,v1):return [p(u0,v0),p(u1,v0),p(u1,v1),p(u0,v1)]
N=p(.5,.5);W=p(-.5,.5);S=p(-.5,-.5);E=p(.5,-.5)
FLOORS={
'floor_left_straight':[[0,.491],[1.4,.491],[1.,1.6],[1.,4.4],[1.4,5.509],[0,5.509]],
'floor_nw_diagonal':[[1,4.4],W,N,[1.4,5.509]],
'floor_sw_diagonal':[[1,1.6],[1.4,.491],S,W],
'floor_center_base':[S,E,N,W],
'floor_ne_diagonal':[N,E,[5.482,4.982],[5.6,4.982],[5.6,6]],
'floor_se_diagonal':[S,[5.6,0],[5.6,1.018],[5.482,1.018],E],
'floor_in_bay':rect(5.6,4.982,8,6),
'floor_out_bay':rect(5.6,0,8,1.018),
'floor_right_straight':rect(5.482,1.018,6.5,4.982),
'floor_parking_bay':rect(6.5,2.25,8,3.75)}
# Virtual boundaries are separate from the visible zero-thickness wall surfaces.
OUTER=[[0,.491],[1.4,.491],S,[5.6,0],[8,0],[8,1.018],[6.5,1.018],[6.5,2.25],[8,2.25],[8,3.75],[6.5,3.75],[6.5,4.982],[8,4.982],[8,6],[5.6,6],N,[1.4,5.509],[0,5.509]]
HOLES=[[[1,1.6],W,[1,4.4]],[[5.482,1.018],[5.482,4.982],E]]

def dimension(id,value,status,page,uncertainty='',conflict=''):
 return dict(id=id,value=value,unit='m',source_page=page,evidence_status=status,uncertainty=uncertainty,conflict_notes=conflict)
DIMS=[dimension('overall_x',8,'RULEBOOK_TEXT',7),dimension('overall_y',6,'RULEBOOK_TEXT',7,conflict='Legacy6.018; not uniform scaled'),dimension('left_length',5.018,'RULEBOOK_TEXT',7,conflict='Figure5.000'),dimension('left_top_width',1.4,'RULEBOOK_TEXT',7,'Only top endpoint width; middle provisional'),dimension('left_bottom_width',1.4,'RULEBOOK_TEXT',7,'Only bottom endpoint width; middle provisional'),dimension('in_out_length',2.4,'RULEBOOK_TEXT',7),dimension('in_out_width',1.018,'RULEBOOK_TEXT',7,conflict='Figure1.000'),dimension('cross_left',2.608,'RULEBOOK_TEXT',7,'Unknown measurement line; not enforced on mesh', 'Legacy2.000'),dimension('cross_right',3.245,'RULEBOOK_TEXT',7,'Unknown measurement line; not enforced on mesh','Figure3.200'),dimension('parking_height',1.5,'RULEBOOK_TEXT',7),dimension('parking_width',1.5,'RULEBOOK_FIGURE',6,'Text does not specify width'),dimension('parking_gap_each',1.482,'RULEBOOK_TEXT',7,'Unknown baseline; NOT enforced','Stacking two gaps+bays+parking yields6.500 not6.000'),dimension('wall_height',.6,'LEGACY_DRAWING',None,'Legacy S01/S04; also Figure p7 nominal600'),dimension('ramp_run',1.1,'LEGACY_DRAWING',None),dimension('stair_tread',.25,'LEGACY_DRAWING',None),dimension('stair_riser',.06,'LEGACY_DRAWING',None),dimension('platform_height',.18,'LEGACY_DRAWING',None),dimension('stop_depth',.30,'PROVISIONAL',8,'Estimated; range0.2–0.5'),dimension('stop_width',.70,'PROVISIONAL',8,'Estimated; range0.5–0.9'),dimension('wall_marker_side',.1,'RULEBOOK_TEXT',8)]

def zones():
 z=[]
 for k,poly in FLOORS.items():z.append(dict(id=k,type='WALKABLE',polygon=poly,frame_id='arena_design',ground_height_m=0,evidence_status='PROVISIONAL',navigation_qualified=False))
 z += [dict(id='zone_in',type='START',polygon=FLOORS['floor_in_bay'],approach_heading=math.pi,entry=[8,5.491],exit=[5.6,5.491]),dict(id='zone_out',type='FINISH',polygon=FLOORS['floor_out_bay'],approach_heading=0,entry=[5.6,.509],exit=[8,.509]),dict(id='zone_parking',type='PARKING',polygon=FLOORS['floor_parking_bay'],approach_heading=0,entry=[6.5,3],exit=[6.5,3]),dict(id='zone_slalom',type='WALKABLE',subtype='SLALOM',polygon=FLOORS['floor_left_straight'])]
 for i,poly in enumerate(HOLES):z.append(dict(id=f'keepout_{i}',type='KEEP_OUT',polygon=poly))
 for i,(poly,heading) in enumerate([(oriented(-.5,-.2,-.2,.5),math.pi/4),(oriented(-.2,.5,-.5,-.2),-math.pi/4)],1):
  z.append(dict(id=f'stop_zone_{i:02}',type='STOP_ZONE',polygon=poly,signal_id=f'signal_{i:02}',approach_heading=heading,ground_height_m=.18,entry=poly[0],exit=poly[2],dimension_status='PROVISIONAL',allowed_feet_evidence=['SIM_GT','KINEMATIC','VISUAL'],proxy_is_qualification=False))
 for sign,label in [(-1,'sw'),(1,'ne')]:z.append(dict(id='ramp_'+label,type='RAMP',polygon=oriented(min(sign*.5,sign*1.6),max(sign*.5,sign*1.6),-.5,.5),ground_height_relation='linear0to0.18m',planar_navigation='BLOCKED_TERRAIN_HANDOFF'))
 for sign,label in [(1,'nw'),(-1,'se')]:z.append(dict(id='stairs_'+label,type='STAIRS',polygon=[p(-.5,sign*.5),p(.5,sign*.5),p(.5,sign*1),p(-.5,sign*1)],ground_height_relation='discrete0.06/0.12/0.18m',planar_navigation='BLOCKED_TERRAIN_HANDOFF'))
 for i,xy in enumerate([[2.292,3],[4.308,3]],1):z.append(dict(id=f'signal_{i:02}',type='TRAFFIC_SIGNAL',polygon=rect(xy[0]-.1,xy[1]-.1,xy[0]+.1,xy[1]+.1),height_m=.84,states=['RED','GREEN','OFF','AMBIGUOUS'],fixture_status='PROVISIONAL'))
 for x in z:x.setdefault('frame_id','arena_design');x.setdefault('ground_height_m',0);x.setdefault('evidence_status','PROVISIONAL')
 return z

def on_segment(pt,a,b,eps=1e-9):
 return abs((b[0]-a[0])*(pt[1]-a[1])-(b[1]-a[1])*(pt[0]-a[0]))<eps and min(a[0],b[0])-eps<=pt[0]<=max(a[0],b[0])+eps and min(a[1],b[1])-eps<=pt[1]<=max(a[1],b[1])+eps

def contains(poly,pt):
 inside=False
 for a,b in zip(poly,poly[1:]+poly[:1]):
  if on_segment(pt,a,b):return True
  if (a[1]>pt[1])!=(b[1]>pt[1]) and pt[0]<(b[0]-a[0])*(pt[1]-a[1])/(b[1]-a[1])+a[0]:inside=not inside
 return inside

def feet_inside(zone,left,right):return contains(zone['polygon'],left) and contains(zone['polygon'],right)
def polygon_inside(zone,footprint):
 # Zones used for containment are convex rectangles; reject arbitrary concave targets.
 poly=zone['polygon'];cross=[]
 for i in range(len(poly)):
  a,b,c=poly[i-2],poly[i-1],poly[i];cross.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
 if not(all(x>=-1e-9 for x in cross) or all(x<=1e-9 for x in cross)):raise ValueError('Convex zone required')
 return bool(footprint) and all(contains(poly,p) for p in footprint)
def finish_crossed(previous,current,line_x=8):
 # All footprint vertices must progress from not-complete to beyond line; center is insufficient.
 return bool(previous and current) and not all(p[0]>line_x for p in previous) and all(p[0]>line_x and 0<=p[1]<=1.018 for p in current)

def bundle():
 zz=zones();edges=[('zone_in','floor_ne_diagonal'),('floor_ne_diagonal','stop_zone_01'),('stop_zone_01','floor_sw_diagonal'),('floor_sw_diagonal','zone_slalom'),('zone_slalom','floor_nw_diagonal'),('floor_nw_diagonal','stop_zone_02'),('stop_zone_02','floor_se_diagonal'),('floor_se_diagonal','zone_parking'),('zone_parking','zone_out')]
 return dict(schema_version='0.1',arena_id='roboworld_quadruped',revision=REV,rules_version='2026-10-15',base_commit=BASE,frame_id='arena_design',units='metre/radian',handedness='right',quaternion_order='xyzw',origin='lower-left ground',bounds_xy_m=[[0,0],[8,6]],gltf_transform='(x,z,-y)',map_transform=None,dimensions=DIMS,semantic_zones=zz,directed_edges=[dict(id=f'leg_{i:02}',from_zone=a,to_zone=b,status='DRAFT',mandatory=True,shortcut_allowed=False)for i,(a,b)in enumerate(edges)],required_visits=['stop_zone_01','zone_slalom','stop_zone_02','zone_parking','zone_out'],course_graph_status='DRAFT_UNCONFIRMED',visual_asset='arena.glb',collision_asset='collision/virtual_fences.json',terrain_asset='arena.semantic.json',sources=[dict(id='RULEBOOK',pages=[6,7,8]),dict(id='LEGACY',path='../../arena.json')],navigation_qualified=False)

def scenarios(seed=20261015):
 rng=random.Random(seed)
 cases=[('empty',[]),('single_cone',[dict(id='cone_1',xy=[.5,2.8],radius_m=.12,height_m=.30)]),('slalom_multi',[dict(id=f'cone_{i}',xy=[.3+.35*(i%2),1.8+i*.55],radius_m=.10,height_m=.25)for i in range(5)]),('narrow_feasible',[dict(id='box_1',xy=[5.58,2],size_xy_m=[.12,.35],height_m=.3)]),('narrow_infeasible',[dict(id='box_1',xy=[5.99,2],size_xy_m=[1.0,.35],height_m=.3)]),('two_signals',[]),('parking_boundary',[])]
 for name,objects in cases:
  yield dict(schema_version='0.1',arena_revision=REV,scenario_id=name,seed=seed,evidence_type='SIMULATION_GT',frame_id='arena_design',obstacles=objects,obstacles_baked_in_static_map=False,signals=[dict(signal_id='signal_01',initial='RED',period_s=5),dict(signal_id='signal_02',initial='GREEN',period_s=5)],gt_schedule_for_detector=False,hard_negatives=['green_background','red_P','display_monitor','reflection'],footprint=dict(kind='SIMULATION_ASSUMPTION',polygon=[[-.3,-.16],[.3,-.16],[.3,.16],[-.3,.16]]),parking_probe=[[6.49,2.4],[7,2.4],[7,2.9],[6.49,2.9]] if name=='parking_boundary' else None)

def random_obstacles(count,seed):
 if not 0<=count<=10:raise ValueError('Rulebook maximum10')
 rng=random.Random(seed)
 return [dict(id=f'random_{i}',xy=[rng.uniform(.2,.8),rng.uniform(1,5)],radius_m=.07,height_m=.2)for i in range(count)]

def write_contracts(out=ROOT):
 out.mkdir(exist_ok=True,parents=True);(out/'collision').mkdir(exist_ok=True)
 b=bundle();(out/'arena.semantic.json').write_text(json.dumps(b,indent=2)+'\n')
 walls=[]
 for name,poly in [('outer',OUTER)]+[(f'inner_{i}',x)for i,x in enumerate(HOLES)]:
  for i,(a,c)in enumerate(zip(poly,poly[1:]+poly[:1])):walls.append(dict(id=f'wall_{name}_{i+1:02}',a=a,b=c,height_m=.6,kind='VIRTUAL_FENCE',physical_thickness_m=None))
 (out/'collision/virtual_fences.json').write_text(json.dumps(dict(frame_id='arena_design',evidence_type='SIMULATION_ASSUMPTION',walls=walls,default_profile='closed_legacy_outline',experimental_openings=dict(status='PROVISIONAL',remove_fence_at_x8_in_y=[[0,1.018],[4.982,6]]),sdf_load_status='NOT_RUN'),indent=2)+'\n')
 for s in scenarios():(out/f"scenario_{s['scenario_id']}.json").write_text(json.dumps(s,indent=2)+'\n')
 return b,walls
if __name__=='__main__':write_contracts()
