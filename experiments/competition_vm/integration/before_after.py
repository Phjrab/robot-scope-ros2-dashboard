"""Replay exact fixed-base adapter source against D0 receiver-envelope cases."""
from pathlib import Path
import hashlib, json, sys, types
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from experiments.competition_vm.integration.adapter import ConstraintAdapter
from experiments.competition_vm.integration.d0_smoke import run

REV=Path(__file__).resolve().parent/'revisions/d0_20261024'
BASE_SHA='cfe1ae1934a456b8366ae1afe953e211f45887551775a8c025daa8eda3d354a5'

def evaluate():
    code=(REV/'fixtures/baseline_adapter.py.txt').read_bytes()
    assert hashlib.sha256(code).hexdigest()==BASE_SHA
    m=types.ModuleType('d0_exact_baseline_adapter');m.__file__=str(Path(__file__).resolve().parent/'adapter.py')
    sys.modules[m.__name__]=m;exec(compile(code,m.__file__,'exec'),m.__dict__)
    old_traffic=types.ModuleType('d0_exact_baseline_traffic');sys.modules[old_traffic.__name__]=old_traffic
    traffic_bytes=(REV/'fixtures/baseline_traffic_core.py.txt').read_bytes()
    exec(compile(traffic_bytes,'baseline_traffic_core.py','exec'),old_traffic.__dict__);m.traffic=old_traffic
    def c():return dict(owner_id='traffic_vm',run_id='r',step_id='s',generation=1,request_id='req',mode='RELEASE',max_vx=None,max_vy=None,max_wz=None,validity={'receipt_ttl_s':.25})
    def move(a,t=10.):return a.apply(.25,0.,1,receipt_s=t,now=t,sensor_fresh=True,tf_fresh=True)
    before=m.ConstraintAdapter('r','s',1);after=ConstraintAdapter('r','s',1)
    before.ingest(c(),sequence=1,receipt_s=10.,now=10.)
    after.ingest(c(),sequence=1,receipt_s=10.,now=10.,source_sequence=7)
    before.ingest(c(),sequence=2,receipt_s=10.,now=10.)
    after.ingest(c(),sequence=2,receipt_s=10.,now=10.,source_sequence=7)
    duplicate={'case':'same producer packet restamped with new receiver sequence','before':move(before),'after':move(after)}
    before=m.ConstraintAdapter('r','s',1);after=ConstraintAdapter('r','s',1)
    before.ingest(c(),sequence=1,receipt_s=10.,now=10.)
    after.ingest(c(),sequence=1,receipt_s=10.,now=10.,source_age_s=.2)
    aged={'case':'source age .2 s plus receiver residence .06 s','before':move(before,10.06),'after':move(after,10.06),'note':'baseline has no source-age input; same receiver-only receipt stays fresh'}
    f=m.traffic.StopGoFSM();f.begin('r','s','crossing-1','visit-1','signal_01',1)
    before=m.ConstraintAdapter('r','s',1)
    x=f.update(m.traffic.StopInput(receipt_s=0.,sequence=1,run_id='r',step_id='s',generation=1))
    before.ingest(x['motion_constraint'],sequence=1,receipt_s=0.,now=0.)
    trace=run()
    approach={'case':'fresh approach action self-HOLD','before':move(before,0.),'after':[trace[0]['simulated_v'],0.,trace[0]['arbiter_reason']]}
    assert duplicate['before'][0]>0 and duplicate['after'][0]==0
    assert aged['before'][0]>0 and aged['after'][0]==0
    assert approach['before'][0]==0 and approach['after'][0]>0
    return dict(evidence_type='SYNTHETIC_IN_PROCESS',base_commit='7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a',baseline_adapter_sha256=BASE_SHA,baseline_traffic_sha256=hashlib.sha256(traffic_bytes).hexdigest(),
                cases=[approach,duplicate,aged],status='PASS',native_ros='NOT_RUN',robot='NOT_RUN')

if __name__=='__main__':print(json.dumps(evaluate(),indent=2))
