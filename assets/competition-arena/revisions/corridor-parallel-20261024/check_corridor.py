"""Geometric regression, independent cross-sections and orthographic comparison.
Run with numpy/matplotlib/shapely installed in a project-local environment.
"""
from pathlib import Path
import importlib.util,json,hashlib,math
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'rulebook-20261015'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path/'geometry.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load(OLD,'old_geometry');b=load(ROOT,'new_geometry')
def union(m):return unary_union([Polygon(p) for p in m.FLOORS.values()])
old,new=union(a),union(b)
def section_at(m,arm,d):
 center=m.p(d,0) if arm=='NE' else m.p(0,-d)
 line=LineString([m.p(d,-1),m.p(d,1)] if arm=='NE' else [m.p(-1,-d),m.p(1,-d)])
 pieces=union(m).intersection(line)
 parts=list(pieces.geoms) if hasattr(pieces,'geoms') else [pieces]
 return next(p for p in parts if p.distance(Point(center))<1e-8)
checks={}
assert new.is_valid and new.geom_type=='Polygon'
# Single ground union must be exactly bounded by exported outer + hole polygons.
expected=Polygon(b.OUTER,b.HOLES)
checks['floor_boundary_symdiff_m2']=new.symmetric_difference(expected).area
assert checks['floor_boundary_symdiff_m2']<1e-10
assert new.bounds==(0.,0.,8.,6.)
for name in b.FLOORS:
 assert Polygon(b.FLOORS[name]).is_valid
 if name not in ['floor_ne_diagonal','floor_se_diagonal']:assert b.FLOORS[name]==a.FLOORS[name]
rows=[]
for arm in ['NE','SE']:
 for distance in [.6,1.,1.5,2.,2.5]:
  endpoints=([b.p(distance,-1),b.p(distance,1)] if arm=='NE' else [b.p(-1,-distance),b.p(1,-distance)])
  line=LineString(endpoints)
  before=section_at(a,arm,distance).length;after=section_at(b,arm,distance).length
  assert abs(after-1)<1e-10,(arm,distance,after)
  rows.append(dict(arm=arm,axis_distance_m=distance,before_width_m=before,after_width_m=after))
for arm in ['NE','SE']:
 for i in range(201):
  distance=.50001+(2.5-.50001)*i/200
  assert abs(section_at(b,arm,distance).length-1)<1e-9
checks['dense_cross_sections_checked']=402
# All right ramp/stairs ground projections now supported by floor.
terrain=json.loads((ROOT/'collision/terrain_meshes.json').read_text())
for ob in terrain['closed_solids']:
 if '_ne' in ob['id'] or '_se' in ob['id']:
  p=Polygon([v[:2] for v in ob['vertices']]).convex_hull
  assert p.difference(new).area<1e-10,ob['id']
# Semantic geometry and fences must be generated from this source, not old data.
semantic=json.loads((ROOT/'arena.semantic.json').read_text())
zones={z['id']:z for z in semantic['semantic_zones']}
for name,poly in b.FLOORS.items():assert zones[name]['polygon']==poly
fences=json.loads((ROOT/'collision/virtual_fences.json').read_text())['walls']
for wall in fences:assert expected.boundary.distance(LineString([wall['a'],wall['b']]))<1e-10
assert semantic['map_transform'] is None and not semantic['navigation_qualified']
# Before snapshot hashes are informational; git verifies immutable revision below.
hashes={str(p.relative_to(OLD)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OLD.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
(ROOT/'original_revision_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(14,7),constrained_layout=True)
for ax,m,title in zip(axes,[a,b],['BEFORE: nonparallel right corridor edges','AFTER: parallel 1.000 m design corridor']):
 for name,poly in m.FLOORS.items():
  xy=poly+[poly[0]];ax.fill(*zip(*xy),color='#427080' if 'parking' not in name else '#3b946c',alpha=.8)
 for poly in [m.OUTER]+m.HOLES:
  xy=poly+[poly[0]];ax.plot(*zip(*xy),color='#111111',linewidth=1.5)
 for arm,d in [('NE',1),('NE',2.5),('SE',1),('SE',2.5)]:
  line=LineString([m.p(d,-1),m.p(d,1)] if arm=='NE' else [m.p(-1,-d),m.p(1,-d)])
  section=section_at(m,arm,d)
  xs,ys=section.xy;ax.plot(xs,ys,color='#ffcc33',lw=2.5)
  cx,cy=section.centroid.coords[0];ax.text(cx+.1,cy,f'{section.length:.3f} m',fontsize=10,color='#8b2600',bbox=dict(facecolor='white',alpha=.85,edgecolor='none'))
 ax.text(7,5.45,'IN',ha='center',fontsize=16);ax.text(7,.45,'OUT',ha='center',fontsize=16);ax.text(7.25,3,'P',ha='center',fontsize=16)
 ax.set(xlim=(-.2,8.2),ylim=(-.2,6.2),aspect='equal',title=title,xlabel='Design X (m)',ylabel='Design Y (m)');ax.grid(alpha=.2)
fig.suptitle('Orthographic geometry audit | PROVISIONAL design, not a measured or registered map',fontsize=12)
fig.savefig(ROOT/'previews'/'corridor_before_after.png',dpi=150)
result=dict(status='PASS',base_commit=b.BASE,revision=b.REV,cross_sections=rows,checks=checks,unchanged_floor_count=len(b.FLOORS)-2,physical_measurement='NOT_RUN',map_registration='NOT_RUN',native_navigation='NOT_RUN',scope='Right NE/SE diagonal corridors only; left-side geometry unchanged',dimension_status='1m width and 45deg retained from provisional central platform, NOT a new official measurement')
(ROOT/'corridor_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
