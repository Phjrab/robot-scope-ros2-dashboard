"""Actual current-owner core + HTTP + JS evidence; default C3 failure exits 2."""
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
    paths = load()
    sys.path.insert(0, str(REPO/'tests'))
    from expansion_runtime import latest_fixtures as f
    from robot_dashboard.expansion_runtime import FinalIntentPort
    outcomes = {}
    for name, point, complete in [('scoped_clear',2.,True), ('model_overlap',.1,False),
                                   ('sparse_positive_distance',2.,False), ('empty_sparse',None,False)]:
        rt,p,s,c = f.setup(point_x=point)
        value = f.run(rt,p,s,complete=complete)
        assert value.assessment, value.intent.reason
        outcomes[name] = dict(severity=value.intent.severity, reason=value.intent.reason,
            min_clearance=value.assessment['min_clearance'], actual_cores=True)
    rt,p,s,c = f.setup()
    value = f.run(rt,p,s,complete=True)
    gate = FinalIntentPort(rt.context, mode=rt.mode)
    checked = gate.apply(value.intent, now_ns=c.now, issued_ns=c.now, expires_ns=c.now+100_000_000)
    assert not checked.hold
    responses = {}
    for version in ('0.2','0.1'):
        raw = f.http_snapshot(f.scene(rt,value,c,version=version))
        snapshot = json.loads(raw)
        assert snapshot['collision_assessment']['severity'] == 'CLEAR'
        assert snapshot['schema_version'] == version
        with tempfile.TemporaryDirectory(prefix='c4-current-c3-') as tmp:
            wire = Path(tmp)/'snapshot.json'; wire.write_text(raw)
            check = subprocess.run([node, str(Path(__file__).with_name('consumer_check.mjs')),
                str(paths['c3']/'robot_dashboard/static/features/obstacle_scene'),str(wire)],
                capture_output=True,text=True,timeout=20)
            consumer = json.loads(check.stdout)
        responses[version] = dict(actual_C1_ASGI_HTTP='PASS', sha256=hashlib.sha256(raw.encode()).hexdigest(),
            bytes=len(raw.encode()), C3_actual_consumer=dict(consumer, exit_code=check.returncode))
    source_files = []
    for directory in ('robot_dashboard/expansion_runtime','tests/expansion_runtime',
                      'experiments/expansion_20261029/c4_runtime/followup'):
        source_files += [p for p in (REPO/directory).iterdir() if p.suffix in ('.py','.mjs')]
    return dict(dependencies=PINS, contracts='C1 0.2; explicit opt-in C1-supported 0.1 only for safe host integers',
        actual_core_composition=outcomes, HTTP_response_profiles=responses,
        source_file_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_files)},
        coverage='GENERATED_CLOSED_SCENE_VOLUME synthetic fixture only; no physical/free-space claim',
        final_sink='MOCK_ONLY', mock_clear_velocity=list(checked.velocity),
        ROS_modules={k:importlib.util.find_spec(k) is not None for k in ('rclpy','sensor_msgs','tf2_ros','nav2_msgs')},
        ROS_lifecycle='NOT_RUN', native_costmap_mark_clear='NOT_RUN', adapter_published=False,
        native_costmap_ingestion_observed=False, browser_render='NOT_RUN', device='DEVICE_NOT_RUN',
        latency='NOT_BENCHMARK_DETERMINISTIC_FIXTURE_CLOCK',
        unresolved='C3 canonical 0.2 and command-assessment references remain unsupported; no fake pose/joints/path supplied')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--node',default='node')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = report(args.node)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('actual_core_composition','HTTP_response_profiles','unresolved')},indent=2))
    sys.exit(0 if result['HTTP_response_profiles']['0.2']['C3_actual_consumer']['status']=='PASS' else 2)
