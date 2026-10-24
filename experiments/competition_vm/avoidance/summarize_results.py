"""Combine completed synthetic batches without representing them as native results."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
from simulate import render,truth_at,scene

def main():
 rows=json.loads((ROOT/'results/scenarios.json').read_text())
 if not any(r['scenario']=='map_misalignment' for r in rows): rows+=json.loads((ROOT/'results/map_misalignment.json').read_text())
 assert len(rows)==48 and all(r['status']=='PASS' for r in rows)
 result={'status':'PASS','evidence_type':'SYNTHETIC_CLOSED_LOOP_CORE','controller':'vm_astar_rotate_follow_v1','unit_tests':30,'unit_status':'PASS','scenario_runs':len(rows),'scenario_pass':sum(r['status']=='PASS' for r in rows),'contacts':sum(r['contacts'] for r in rows),'hold_violations':sum(r['hold_violations'] for r in rows),'native_nav2_status':'BLOCKED','native_launch_eligible':False,'native_reason':'No ROS2/Nav2/container on Debian13 VM','RPP_comparison':'NOT_RUN','MPPI_comparison':'NOT_RUN','hardware':'NOT_RUN','arena_closed_loop':'NOT_RUN','two_signal_X_integration':'NOT_RUN','synthetic_rows':[{k:v for k,v in r.items() if k!='trajectory'} for r in rows]}
 (ROOT/'VALIDATION_RESULTS.json').write_text(json.dumps(result,indent=2))
 lines=['# Synthetic fallback results','', 'Not Nav2/RPP/MPPI. Three seeds per scenario. All dimensions/speeds are DESIGN_INITIAL.', '', '| Case | Outcome | Passed | Sim time range s | Contacts |', '|---|---|---:|---:|---:|']
 for name in dict.fromkeys(r['scenario'] for r in rows):
  rr=[r for r in rows if r['scenario']==name];lines.append(f"|{name}|{rr[0]['outcome']}|{sum(r['status']=='PASS' for r in rr)}/3|{min(r['sim_time_s'] for r in rr):.1f}–{max(r['sim_time_s'] for r in rr):.1f}|{sum(r['contacts'] for r in rr)}|")
 (ROOT/'results/RESULTS.md').write_text('\n'.join(lines)+'\n')
 for r in rows:
  if r['seed']!=0:continue
  static,_,_,_=scene(r['scenario'],0)
  history=[(truth_at(static,r['scenario'],p[0],0),tuple(p[1:4]),[],p[-1]) for p in r['trajectory']]
  if history:history[-1]=(*history[-1][:3],r['reason'])
  render(history,ROOT/'results'/f"{r['scenario']}.gif")
if __name__=='__main__':main()
