"""Small actual-composition report. C3 incompatibility is FAIL, never hidden."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from .dependencies import load, PINS, REPO


def report(node):
    paths=load()
    sys.path.insert(0,str(REPO/'tests'))
    from expansion_runtime.fixtures import setup, run
    from robot_dashboard.expansion_runtime import FinalIntentPort
    from robot_dashboard.expansion_runtime.ports import ingest_scene
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    rt,p,s,c=setup(); result=run(rt,p,s,complete=True)
    service=SceneSnapshotService(rt.context.map_binding,host_clock_id=rt.context.host_clock_id,clock=c)
    snapshot=ingest_scene(service,result)
    assert snapshot['collision_assessment']['severity']=='CLEAR'
    gate=FinalIntentPort(rt.context,mode=rt.mode)
    checked=gate.apply(result.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+100_000_000)
    assert not checked.hold
    wire=json.dumps(snapshot,sort_keys=True,separators=(',',':'),allow_nan=False)
    with tempfile.TemporaryDirectory(prefix='c4-round2-consumer-') as tmp:
        file=Path(tmp)/'snapshot.json'; file.write_text(wire)
        c3=subprocess.run([node,str(Path(__file__).with_name('consumer_check.mjs')),
            str(paths['c3']/'robot_dashboard/static/features/obstacle_scene/c1_adapter.js'),str(file)],capture_output=True,text=True)
        consumer=json.loads(c3.stdout)
        consumer['exit_code']=c3.returncode
    modules={k:importlib.util.find_spec(k) is not None for k in ('rclpy','sensor_msgs','tf2_ros','nav2_msgs')}
    outcomes={}
    for name,point,complete in [('scoped_clear',2.,True),('model_overlap',.1,False),('sparse_positive_distance',2.,False),('empty_sparse',None,False)]:
        engine,packet,state,clock=setup(point_x=point)
        value=run(engine,packet,state,complete=complete)
        outcomes[name]=dict(severity=value.intent.severity,reason=value.intent.reason,
            min_clearance=value.assessment['min_clearance'],actual_cores=True)
    return dict(dependencies=PINS,contract_version='C1 0.1 at '+PINS['c1'],
        canonical_snapshot_sha256=hashlib.sha256(wire.encode()).hexdigest(),
        source_file_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((REPO/'robot_dashboard/expansion_runtime').glob('*.py'))},
        actual_core_composition=outcomes,actual_C1_snapshot='PASS',C3_actual_consumer=consumer,
        final_sink='MOCK_ONLY',mock_clear_velocity=list(checked.velocity),
        ROS_modules=modules,ROS_lifecycle='NOT_RUN_MISSING_ROS' if not all(modules.values()) else 'AVAILABLE_NOT_RUN',
        native_costmap_mark_clear='NOT_RUN',physical_contact='NOT_RUN',device='DEVICE_NOT_RUN',
        latency='NOT_BENCHMARK_DETERMINISTIC_FIXTURE_CLOCK',timing=result.timing)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--node',default='node')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    value=report(args.node)
    args.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value,indent=2))
    # A real downstream mismatch remains a failed check even with core PASS.
    sys.exit(0 if value['C3_actual_consumer']['status']=='PASS' else 2)
