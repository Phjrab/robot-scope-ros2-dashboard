from pathlib import Path
import sys,time,json,numpy as np
from runtime_guard import CommandGate,PlannerProcess
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'curved_progress_20261024'));import simulate_curved as c
c.YAW_MAX=.12
f=np.load(HERE/'initial_open_observed_fixture.npz');gate=CommandGate().start();now=time.monotonic();gate.observe(now,now);gate.submit(1,(.1,0,0),gate.identity)
p=PlannerProcess(gate,budget=.10);start=time.monotonic();p.launch(c.build_path,(tuple(f['pose']),f['grid']),start)
while p.status=='PENDING':p.poll();time.sleep(.005)
cleanup=p.cleanup();gate.close();rows=[x for x in gate.records if x['wall_time']>=start]
result={'status':p.status,'elapsed_s':time.monotonic()-start,'planner_budget_s':p.budget,'worker_cleaned':cleanup,'output_samples':len(rows),'all_recorded_outputs_zero_after_launch':all(x['command']==[0.,0.,0.] for x in rows),'source':'frozen curved_progress_20261024 build_path with observed initial OPEN grid; no hidden truth raster','limitations':'real clock harness, not integrated robot/ROS navigation'}
Path('actual_planner_timeout.json').write_text(json.dumps(result,indent=2));print(result)
assert result['status']=='TIMEOUT' and cleanup and rows and result['all_recorded_outputs_zero_after_launch']
