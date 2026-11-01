"""Exact-pin D2 -> D3 -> C1 real offline HTTP runner. Synthetic inputs only.

Dependencies are git-archive exports, never vendored into C3. Generic pose/path/
costmap data below are explicit test-host payloads, NOT native ROS observations.
The sole clock mapping is a synthetic identity correspondence, asserted below.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from dataclasses import replace

from prepare_dependencies import PINS, PATHS

TOKEN = "public-c3-synthetic-offline-test-bearer"
CASES = ("PREDICTED_CONTACT", "NEAR", "UNKNOWN_PARTIAL", "SCOPED_SYNTHETIC_CLEAR", "ACTIVE_UNKNOWN", "EXPIRED")


def verify_exports(deps, root):
    """Fail if the read-only import tree differs from any claimed Git blob."""
    paths = PATHS
    verified = {}
    for role, directories in paths.items():
        records = subprocess.check_output(["git", "ls-tree", "-r", "-z", PINS[role], "--", *directories], cwd=root)
        count = 0
        for row in records.split(b"\0"):
            if not row:
                continue
            metadata, name = row.split(b"\t", 1)
            expected = metadata.split()[2].decode()
            raw = (deps / name.decode()).read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if actual != expected:
                raise ValueError(f"Exact dependency mismatch: {role} {name.decode()}")
            count += 1
        assert count > 0, role
        verified[role] = dict(sha=PINS[role], verified_git_blobs=count)
    return verified


def build(deps, root, output, native_zip=None):
    verified = verify_exports(deps, root)
    sys.path.insert(0, str(root))
    import robot_dashboard
    robot_dashboard.__path__.insert(0, str(deps / "robot_dashboard"))
    from robot_dashboard.obstacle_fusion_core import core as d2
    from robot_dashboard.collision_geometry_core import assess, RobotGeometry, transform
    import robot_dashboard.collision_geometry_core.assessment as d3
    from robot_dashboard.expansion_contracts import CollisionAssessment, ObstacleFrame
    from robot_dashboard.expansion_contracts.time_binding import ClockBinding, normalize_collision_assessment
    from robot_dashboard.collision_geometry_core.contracts import canonical_assessment
    spec = importlib.util.spec_from_file_location("c1_exact_offline_host", deps / "experiments/expansion_20261029/c1_service_host/host.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    from starlette.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse
    apps, raw_reports, contexts = {}, {}, {}
    # One short actual D1->C1 save/reload supplies a real merged synthetic identity
    # for C3; C2's already verified UI is not rebuilt or retuned.
    import experiments.expansion_20261029 as experiments_root
    experiments_root.__path__.append(str(deps / 'experiments/expansion_20261029'))
    map_spec=importlib.util.spec_from_file_location('c2_exact_map_host', deps / 'experiments/expansion_20261029/c2_map_ui/exact_service_host.py')
    map_host=importlib.util.module_from_spec(map_spec);map_spec.loader.exec_module(map_host)
    from robot_dashboard.expansion_contracts.fixtures import request
    (output / 'merged-map').mkdir()
    composition=map_host.compose(output / 'merged-map',include_bundles=True)
    try:
        sources=[v.descriptor for v in composition.resolved.values()]
        request_wire=replace(request(),request_id='c3-merged-reference',sources=[v.to_dict() for v in sources],
            anchor_source_key=sources[0].key,source_pins={v.key:v.sha256 for v in sources},
            initial_guesses=[dict(source_key=v.key,T_anchor_source=t.reshape(16).tolist()) for v,t in zip(sources,composition.poses)],
            correspondences=[],mode='seeded',options={}).to_dict()
        job=composition.manager.enqueue(request_wire)
        for _ in range(400):
            job=composition.manager.status(job['job_id'])
            if job['state'] not in ('QUEUED','RUNNING'):break
            time.sleep(.025)
        assert job['state']=='SOLVED_CANDIDATE',job
        reviewed=composition.manager.review(job['job_id'],job['proposal_revision'],True)
        merged=composition.manager.export(job['job_id'],'c3_synthetic_display_reference',reviewed['proposal_revision'])
        saved=composition.store.reload(merged['id'])
        preview=composition.catalogue.preview(saved.descriptor.map_id)
    finally:composition.manager.close()
    assert merged['point_count']==800
    map_report=dict(manifest=merged,preview=preview,source='ACTUAL_D1_CORE_C1_BUNDLESTORE_SYNTHETIC')
    for i, name in enumerate(CASES, 1):
        app = host.create_test_host(output / f"private-host-{i}", TOKEN)
        scene = app.state.c1[2]
        # Virtual monotonic host clock enables deterministic expiry tests; it is
        # not the browser clock and never used as a real acquisition timestamp.
        host_ns = 9_007_199_254_740_993  # deliberately beyond JS safe integers
        binding = dict(map_id="a" * 24, revision="b" * 64, generation=i)
        epoch, stream = f"sensor-{i}", f"scene-{i}"
        binding.update(map_id=merged["id"],revision=merged["revision"])
        scene.schema_version="0.2"
        scene.reset(binding, stream)
        scene.clock = lambda n=host_ns, expired=name == "EXPIRED": n + (2_000_000_000 if expired else 0)
        meta = dict(schema_version="0.1", evidence_kind="SYNTHETIC", producer="c3.synthetic-input",
                    sequence=1, source_epoch=epoch, frame_key=dict(source_epoch=epoch, frame_id="map"),
                    stamp_ns=str(host_ns), clock_domain="synthetic-host-correspondence", host_clock_id="test-host",
                    received_monotonic_ns=host_ns, map_binding=binding, calibration_id="synthetic-calibration")
        center = 0.7 if name == "PREDICTED_CONTACT" else 0.44 if name == "NEAR" else 2.0
        pts = [[center+x, y, 0.3+z] for x in (0,0.02) for y in (-0.02,0.02) for z in (-0.02,0.02)]
        # Original points/origin are forwarded by actual D2 input_sources. This
        # optional data profile is explicit, not claimed as a C1 standard.
        sensor_meta = dict(meta, source_age_ns=0, sensor_id="LIDAR", kind="LIDAR", health="OK",
                           points_m=pts, origin_m=[0.08,0,0.4], provenance={"kind":"SYNTHETIC_INPUT"})
        observation = d2.process_lidar(pts, sensor_meta)
        tracked = d2.Tracker().step(observation)
        obstacle = ObstacleFrame.from_dict(tracked["obstacle_frame"]).to_dict()
        model = RobotGeometry('<robot><link name="base"><collision><geometry><box size="0.716 0.324 0.35"/></geometry></collision></link></robot>',
                              provenance="SYNTHETIC_body_box_NOT_official_visual_collision_equivalence")
        joints = {f"{leg}_{joint}_joint": q for leg in ("FL","FR","RL","RR") for joint,q in (("hip",0),("thigh",0.75),("calf",-1.5))}
        state = dict(meta, pose=transform((0,0,0.3)).tolist(), joints={}, joint_stamp_ns=meta["stamp_ns"],
                     calibration_known=True, pose_uncertainty_m=0.01, joint_uncertainty_m=0.)
        path_meta = dict(meta, producer="c3.supplied-path")
        path = {"ref": {"source_epoch":epoch,"sequence":1}, "poses":[{"time_s":0.,"pose":state["pose"]},
                {"time_s":1.,"pose":transform((0.6 if name=="PREDICTED_CONTACT" else 0.,0,0.3)).tolist()}]}
        coverage = None
        if name=="SCOPED_SYNTHETIC_CLEAR":
            coverage=dict(kind="GENERATED_CLOSED_SCENE_VOLUME",complete_for_motion=True,evidence_kind="SYNTHETIC",
                source_refs=[{"generator":"c3.closed.synthetic.scene","sequence":1}],horizon_s=1.,
                volume_min=[-3,-3,-1],volume_max=[3,3,2],valid_from_ns=meta["stamp_ns"],valid_until_ns=str(host_ns+1_000_000_000),
                **{k:copy.deepcopy(state[k]) for k in ("source_epoch","clock_domain","frame_key","map_binding")})
        raw = assess(model,state,obstacle,path,now_stamp_ns=host_ns,now_clock_domain=meta["clock_domain"],coverage=coverage)
        clock_binding=ClockBinding(meta["clock_domain"],epoch,"test-host",0,0,"c3-synthetic-identity-only")
        collision=canonical_assessment(raw,normalize=normalize_collision_assessment,clock_binding=clock_binding)
        collision["freshness"]["protection_mode"]="ACTIVE_CONSTRAINT" if name=="ACTIVE_UNKNOWN" else "ADVISORY_ONLY"
        CollisionAssessment.from_dict(collision)
        assert collision["validity_interval"]["start_monotonic_ns"]==str(host_ns)
        assert collision["freshness"]["time_conversion"]["original_interval"]==raw["freshness"]["source_validity_interval"]
        def generic(data, producer):
            return {k:meta[k] for k in ("schema_version","evidence_kind","sequence","source_epoch","frame_key","stamp_ns","clock_domain","host_clock_id","received_monotonic_ns","map_binding")} | {"producer":producer,"data":data,"health":{"state":"SYNTHETIC_SUPPLIED"}}
        pose = generic(dict(position_m=[0,0,0.3],rpy_rad=[0,0,0],calibration_id=meta["calibration_id"],
                    joint_state=dict(positions_rad=joints,stamp_ns=meta["stamp_ns"]),provenance={"visual_joints":"SYNTHETIC_DISPLAY_ONLY","collision_model":"BODY_BOX"}),"c3.supplied-pose")
        supplied_path = generic(dict(points_m=[p["pose"][0][3:4]+[p["pose"][1][3],p["pose"][2][3]] for p in path["poses"]],
                                    dimensions=3,representation="XYZ",generation=f"plan-{i}",replanning_reason="SUPPLIED_SYNTHETIC"),path_meta["producer"])
        cost = generic(dict(id="synthetic-costmap",width=2,height=2,cells=[0,254,-1,0],origin=[0,0,0],resolution_m=.2,
                            plane_z_m=0,representation="2D_GROUND_PLANE"),"c3.supplied-costmap")
        for slot,value in (("robot_pose",pose),("obstacle_frame",obstacle),("global_path",supplied_path),
                           ("costmap_snapshot",cost),("collision_assessment",collision)):
            assert scene.ingest(slot,value),slot
        reference_bytes=json.dumps(dict(profile="c3-test-display-v1",map_binding=binding,
            points_m=[preview['points'][j:j+3] for j in range(0,len(preview['points']),3)],
            provenance=dict(kind="ACTUAL_D1_SYNTHETIC_MERGED_PREVIEW",manifest=merged)),separators=(',',':')).encode()
        scene.publish_asset('saved_reference_cloud','d1-merged-preview',reference_bytes,media_type='application/json')
        snapshot = scene.snapshot()
        if name=="PREDICTED_CONTACT": assert raw["reason"]=="PREDICTED_COLLISION",raw
        elif name=="SCOPED_SYNTHETIC_CLEAR": assert raw["severity"]=="CLEAR",raw
        else: assert raw["severity"]=="UNKNOWN" and raw["min_clearance"]>0,raw
        if name=="EXPIRED": assert snapshot["collision_assessment"] is None
        raw_reports[name] = dict(raw_d3=raw,canonical_d3=collision,direct_c1_validation="PASS_V02_CANONICAL",
            projection="ACTUAL_D3_CANONICAL_ASSESSMENT_AND_C1_CLOCK_BINDING",snapshot=snapshot,scene_metrics=scene.metrics())
        contexts[name] = dict(binding,frame_id="map",source_epoch=epoch,stream_epoch=stream,clock_domain=meta["clock_domain"],
            calibration_id=meta["calibration_id"],units="m",source_identity="ACTUAL_D1_C1_SAVED_MERGED_SYNTHETIC")
        apps[name]=app
    native_report=None
    if native_zip:
        from native_replay import add_native_replay
        native_report=add_native_replay(native_zip,host,output,apps,contexts,TOKEN)
    from fastapi import FastAPI
    @host.asynccontextmanager
    async def lifespan(_app):
        try: yield
        finally:
            for child in apps.values(): child.state.c1[0].close()
    wrapper=FastAPI(lifespan=lifespan)
    @wrapper.get('/c3-context/{name}')
    def context(name: str):
        return JSONResponse(contexts[name])
    for name, app in apps.items(): wrapper.mount(f"/actual/{name}",app)
    wrapper.mount('/',StaticFiles(directory=root),name='owned-static-test-host')
    modules={label:str(module.__file__) for label,module in {"D2":d2,"D3":d3,"C1":host}.items()}
    for value in modules.values(): assert str(deps) in value
    output.mkdir(parents=True,exist_ok=True)
    # Inputs/snapshots are bounded synthetic JSON; never captured point clouds.
    report=dict(pins=PINS,verified_dependencies=verified,contract="0.2",modules=modules,source_mode="ACTUAL_C1_SERVICE",evidence="SYNTHETIC",
                native="RECORDED_REPLAY" if native_report else "NOT_RUN",ros="NOT_RUN_LOCAL",merged_map=map_report,native_replay=native_report,cases=raw_reports)
    (output/'core-results.json').write_text(json.dumps(report,indent=2)+'\n')
    return wrapper


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--deps',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--port',type=int,default=4184)
    parser.add_argument("--native-zip",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    args.out.mkdir(parents=True,exist_ok=True)
    # C1 temporary source/bundle files must never enter repository evidence.
    with tempfile.TemporaryDirectory(prefix='c3-c1-round2-') as private:
        app=build(args.deps,root,Path(private),args.native_zip)
        raw=(Path(private)/'core-results.json').read_bytes()
        (args.out/'core-results.json').write_bytes(raw)
        print(json.dumps(dict(status="READY",core_report_sha256=hashlib.sha256(raw).hexdigest(),port=args.port)),flush=True)
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__': main()
