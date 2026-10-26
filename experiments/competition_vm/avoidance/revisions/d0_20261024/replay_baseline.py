"""Rerun the published 16x3 pure-core cases without overwriting old results."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from simulate import SCENARIOS,run
if __name__=='__main__':
 out=Path(__file__).resolve().parent/'results';out.mkdir(exist_ok=True)
 rows=[]
 for name in SCENARIOS:
  for seed in range(3):
   result,_=run(name,seed);rows.append(result)
   print(name,seed,result['status'],result['outcome'],result['reason'],flush=True)
 (out/'legacy_scenario_rerun.json').write_text(json.dumps(rows,indent=2)+'\n')
 raise SystemExit(any(r['status']=='FAIL' for r in rows))
