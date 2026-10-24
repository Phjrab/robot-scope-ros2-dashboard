"""Run immutable fixed-base defects and corrected VM boundary side-by-side."""
from pathlib import Path
import sys,types,json,hashlib
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from experiments.competition_vm.traffic_signals.core import StopInput,TemporalFilter
from experiments.competition_vm.traffic_signals.lifecycle import TrafficLifecycle
source=Path(__file__).parent/'fixtures/base_core_7f2a707.txt'
base=types.ModuleType('d0_fixed_base_traffic');sys.modules[base.__name__]=base
exec(compile(source.read_text(),str(source),'exec'),base.__dict__)
f=base.StopGoFSM();f.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
old_approach=f.update(base.StopInput(0.,0))
new=TrafficLifecycle('vm-run','signal-step','crossing-1','visit-1','signal_01',0,'stop_zone_01','approach',1)
new_approach=new.observe(StopInput(0.,0),now=0.,pose_age_s=0.)
def replay(cls):
    f=cls(stability_s=.1);out=[]
    for seq,t,age in [(10,0.,0.),(11,.1,0.),(12,.2,1.),(10,.3,0.),(11,.4,0.)]:
        out.append(f.update('GREEN',identity=('e','sig'),sequence=seq,source_stamp_ns=str(seq),receipt_s=t,source_age_s=age))
    return out
r={'evidence':'SYNTHETIC_IN_PROCESS','base_commit':'7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a',
 'base_core_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'approach_self_hold':{'before':old_approach['motion_constraint']['mode'],'after':new_approach['motion_constraint']['mode'],
   'meaning':'Traffic gate inactive during acknowledged-owned approach, safety still checked. No actual goal sent.'},
 'stale_age_replay':{'before':replay(base.TemporalFilter),'after':replay(TemporalFilter)}}
assert r['approach_self_hold']['before']=='HOLD' and r['approach_self_hold']['after']=='RELEASE'
assert r['stale_age_replay']['before'][-1]=='GREEN' and r['stale_age_replay']['after'][-1]=='UNKNOWN'
print(json.dumps(r,indent=2))
