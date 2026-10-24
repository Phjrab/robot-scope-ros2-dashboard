from pathlib import Path
import sys,json,numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'left_slalom_20261024'));import audit
OLD=HERE.parent/'curved_slalom_20261024/results/final_regressions'
def measure(p):
 d=json.loads(p.read_text());v=np.array([[f['vx_world'],f['vy_world']] for f in d['frames']]);acc=np.diff(v,axis=0)/.1;j=np.diff(acc,axis=0)/.1
 return {'metrics':d['metrics'],'geometry':audit.audit(p),'motion':{'max_recorded_accel':float(np.linalg.norm(acc,axis=1).max()),'max_jerk':float(np.linalg.norm(j,axis=1).max()),'rms_jerk':float(np.sqrt(np.mean(np.sum(j*j,axis=1)))),'velocity_total_variation':float(np.linalg.norm(np.diff(v,axis=0),axis=1).sum()),'terminal_zero':all(abs(d['frames'][-1][k])<1e-9 for k in ['vx_world','vy_world','w'])}}
if __name__=='__main__':
 r=HERE/'results'/ (sys.argv[1] if len(sys.argv)>1 else 'candidate02');out={'previous_open':measure(OLD/'open_normal.json')}
 for name in ['open_normal','tight_normal','open_dropout','open_delay','blocked_5']:
  p=r/f'{name}.json'
  if p.exists():out[p.stem]=measure(p)
 (r/'comparison.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
