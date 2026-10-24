from pathlib import Path
import json,hashlib
import run_candidate as r
r.c.YAW_MAX=.12
p=Path(__file__).resolve().parent
old=json.loads((p/'results/candidate02/open_normal.json').read_text());new=r.c.run('open_normal',r.OPEN,r.c.static_grid(),p/'results/repeat02')
for d in (old,new):
 for k in ('wall_time_s','planning_wall_s','planning_p95_s'):d['metrics'].pop(k,None)
a=json.dumps(old,sort_keys=True);b=json.dumps(new,sort_keys=True)
v={'identical_excluding_wall_clock_measurements':a==b,'canonical_sha256':hashlib.sha256(a.encode()).hexdigest()}
(p/'results/candidate02/reproducibility.json').write_text(json.dumps(v,indent=2));print(v);assert a==b
