"""Paired fresh VM benchmark; only the same saved observed grid reaches planners."""
from pathlib import Path
import hashlib, importlib.util, json, platform, sys, time
import numpy as np
import simulate_curved as candidate
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_progress',HERE.parent/'curved_progress_20261024/simulate_curved.py')
frozen=importlib.util.module_from_spec(spec);spec.loader.exec_module(frozen)
fixture=HERE.parent/'planning_watchdog_20261024/initial_open_observed_fixture.npz'
data=np.load(fixture);grid=data['grid'].copy();pose=tuple(data['pose'])
candidate.YAW_MAX=frozen.YAW_MAX=.12
# Correctness reference: same frozen planner and closed-cell narrowphase, without
# snapshot/memo acceleration. Never compare speed while silently changing input.
spec2=importlib.util.spec_from_file_location('corrected_reference',HERE.parent/'curved_progress_20261024/simulate_curved.py')
reference=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(reference)
reference.polygon_collision=candidate.polygon_collision;reference.YAW_MAX=.12
if __name__=='__main__':
 out=HERE/'validation';out.mkdir(exist_ok=True)
 names=['frozen_incorrect','closed_cell_reference','closed_cell_accelerated']
 functions=[frozen.build_path,reference.build_path,candidate.build_path]
 paths={};samples={n:[] for n in names}
 before=hashlib.sha256(grid.tobytes()).hexdigest()
 for k in range(5):
  for i in ([0,1,2] if k%2==0 else [2,1,0]):
   start=time.perf_counter();p=functions[i](pose,grid);elapsed=time.perf_counter()-start
   samples[names[i]].append(elapsed)
   if names[i] in paths:assert p==paths[names[i]]
   else:paths[names[i]]=p
   print(names[i],k,round(elapsed,6),len(p),flush=True)
 assert hashlib.sha256(grid.tobytes()).hexdigest()==before
 assert paths[names[1]]==paths[names[2]],'Acceleration changed corrected planner output'
 report={'scope':'VM ONLY, saved initial observed OPEN snapshot; no hidden cone truth',
 'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'grid_sha256':before,
 'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
 'corrected_acceleration_path_exact':True,'frozen_vs_corrected_path_exact':paths[names[0]]==paths[names[2]],
 'runs':{n:{'samples_s':v,'median_s':float(np.median(v)),'p95_s':float(np.percentile(v,95)),
 'path_points':len(paths[n]),'path_sha256':hashlib.sha256(json.dumps(paths[n],separators=(',',':')).encode()).hexdigest()} for n,v in samples.items()},
 'limits':'Shared VM timing, not realtime/Jetson measurement; experimental 0.1s tick / 0.25s freshness budgets unchanged.'}
 (out/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
