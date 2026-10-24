import json,hashlib
from pathlib import Path
import simulate_curved as c
from run_scenarios import OPEN
HERE=Path(__file__).resolve().parent
c.YAW_MAX=.12
b=c.run('open_normal',OPEN,c.static_grid(),HERE/'results/repeat_02')
a=json.loads((HERE/'results/final_regressions/open_normal.json').read_text())
for x in (a,b):x['metrics'].pop('wall_time_s',None)
aa=json.dumps(a,sort_keys=True);bb=json.dumps(b,sort_keys=True)
r={'identical_excluding_wall_time':aa==bb,'canonical_sha256':hashlib.sha256(aa.encode()).hexdigest()}
(HERE/'results/final_regressions/reproducibility.json').write_text(json.dumps(r,indent=2));print(r);assert r['identical_excluding_wall_time']
