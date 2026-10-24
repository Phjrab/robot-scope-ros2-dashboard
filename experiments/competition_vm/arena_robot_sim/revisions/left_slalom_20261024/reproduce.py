from pathlib import Path
import json,hashlib
import simulate_slalom as s
P=Path(__file__).resolve().parent
static=s.static_grid();r={}
for name,cones in s.configs().items():
 a=json.loads((P/'results'/f'{name}.json').read_text());b=s.run(name,cones,static,P/'results/repeat_02')
 for x in (a,b):x['metrics'].pop('wall_time_s',None)
 aa=json.dumps(a,sort_keys=True);bb=json.dumps(b,sort_keys=True)
 r[name]={'identical_excluding_wall_time':aa==bb,'canonical_sha256':hashlib.sha256(aa.encode()).hexdigest()}
(P/'results/reproducibility.json').write_text(json.dumps(r,indent=2));assert all(x['identical_excluding_wall_time'] for x in r.values());print(r)
