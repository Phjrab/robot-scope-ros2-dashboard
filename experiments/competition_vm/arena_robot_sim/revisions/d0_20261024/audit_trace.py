"""Independent offline audit of saved trace poses, not the online controller guard.
Checks all static floor/terrain cells, fence edges, cone bases and parking policy.
The audit linearly subdivides each recorded control interval into 10; it cannot
certify continuous contact dynamics, terrain traversal or measured safety margins.
"""
import json,math,hashlib,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import regression as r


def audit(path,static):
 doc=json.loads(path.read_text());scene=doc['scene'];strict=scene['policy']=='strict_no_parking'
 mask=r.allowed_grid(static,strict)
 # All actual cones remain in truth, including those already in the static map.
 truth=r.raster_cones(mask,scene['cones'])
 previous=scene['start'];violations=[];samples=0;minclear=math.inf
 for index,f in enumerate(doc['frames']):
  end=f['pose'];dyaw=(end[2]-previous[2]+math.pi)%(2*math.pi)-math.pi
  for j in range(11):
   u=j/10;p=(previous[0]+u*(end[0]-previous[0]),previous[1]+u*(end[1]-previous[1]),previous[2]+u*dyaw)
   samples+=1;geom=r.geometry_checks(p,scene['cones'],strict)
   grid=r.polygon_collision(p,scene['footprint'],truth,r.old.RES)
   minclear=min(minclear,geom['polygon_edge_clearance_m'])
   if grid or geom['physical_contacts'] or geom['forbidden_parking']:violations.append(dict(frame=index,fraction=u,pose=p,grid=grid,geometry=geom))
  previous=end
 return dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),samples=samples,violations=violations,min_sampled_exact_polygon_clearance_m=minclear,pass_=not violations)


def main():
 paths=sorted((HERE/'results').glob('*__repeat1.json'))
 if len(paths)!=24:raise SystemExit('INPUT_REQUIRED: full 24 repeat1 traces are local-only. Run regression.py first; no zero-case PASS.')
 static=r.old.static_grid();rows=[audit(p,static) for p in paths]
 data=dict(evidence='OFFLINE_SYNTHETIC_PLANAR_TRACE_AUDIT',source='saved poses, not a replay of planner commands',sampling='10 subdivisions per0.1s control interval',rows=rows,all_pass=all(x['pass_'] for x in rows),total_samples=sum(x['samples'] for x in rows))
 (HERE/'results/independent_trace_audit.json').write_text(json.dumps(data,indent=2)+'\n')
 print('audited',len(rows),'cases',data['total_samples'],'poses; pass=',data['all_pass'])
 if not data['all_pass']:raise SystemExit(1)

if __name__=='__main__':main()
