from pathlib import Path
import sys,json,math,hashlib
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'left_slalom_20261024'))
import audit
R=HERE/'results/final_regressions'
def motion(d):
 f=d['frames'];vel=np.array([[x['vx_world'],x['vy_world']] for x in f]);acc=np.diff(np.vstack([[0,0],vel]),axis=0)/.1
 recorded_acc=np.diff(vel,axis=0)/.1
 moving=np.linalg.norm(vel,axis=1)>.01; lateral=(abs(vel[:,0])>.01)&(abs(vel[:,1])<.01);both=(abs(vel[:,0])>.01)&(vel[:,1]>.01)
 return dict(max_recorded_linear_accel_m_s2=float(np.max(np.linalg.norm(recorded_acc,axis=1))),max_linear_accel_including_assumed_initial_rest_m_s2=float(np.max(np.linalg.norm(acc,axis=1))),lateral_only_s=float(np.sum(lateral)*.1),simultaneous_forward_lateral_s=float(np.sum(both)*.1),moving_s=float(np.sum(moving)*.1),yaw_excursion_deg=float((max(x['pose'][2] for x in f)-min(x['pose'][2] for x in f))*180/math.pi),terminal_zero=all(abs(f[-1][k])<1e-9 for k in ('vx_world','vy_world','w')))
if __name__=='__main__':
 results={}
 for name in ['open_baseline','open_normal','open_dropout','open_delay','blocked_5']:
  p=R/f'{name}.json';d=json.loads(p.read_text());results[name]=dict(metrics=d['metrics'],motion=motion(d),geometry=audit.audit(p))
 (R/'COMPARISON.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 fig,axs=plt.subplots(1,3,figsize=(14,6));colors={'open_baseline':'#89949d','open_normal':'#087ca7'}
 for name,color in colors.items():
  d=json.loads((R/f'{name}.json').read_text());p=np.array([f['pose'] for f in d['frames']]);t=[f['t'] for f in d['frames']]
  axs[0].plot(p[:,0],p[:,1],color=color,label=name)
  axs[1].plot(t,[f['vx_world'] for f in d['frames']],color=color,label=name)
  axs[2].plot(t,[f['vy_world'] for f in d['frames']],color=color,label=name)
 from matplotlib.patches import Rectangle
 for c in d['scene']['cones']:axs[0].add_patch(Rectangle((c['xy'][0]-.13,c['xy'][1]-.13),.26,.26,color='#e88019'))
 axs[0].set_xlim(0,1);axs[0].set_ylim(.49,5.51);axs[0].set_aspect('equal');axs[0].set_title('Same OPEN diagnostic layout');axs[0].set_xlabel('x (m)');axs[0].set_ylabel('y (m)')
 axs[1].set_title('Lateral world velocity');axs[2].set_title('Forward course velocity')
 for ax in axs[1:]:ax.set_xlabel('Simulated time (s)');ax.set_ylabel('m/s')
 for ax in axs:ax.grid(alpha=.25);ax.legend(fontsize=8)
 fig.suptitle('SYNTHETIC / HOLONOMIC PLANAR | Different from original tight five-cone layout');fig.tight_layout();fig.savefig(R/'open_layout_comparison.png',dpi=160)
