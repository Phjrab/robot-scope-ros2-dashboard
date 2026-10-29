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

PINS = {
    "C1": "54629c793ad4ae0ea88127f00ed1b7f8805fc4e2",
    "D2": "c0d266e290a2d29c173d3b83520f8c96efea9447",
    "D3": "09b68b692fa4b7ccdea39b1a16e3ff150794e12d",
}
TOKEN = "public-c3-synthetic-offline-test-bearer"
CASES = ("PREDICTED_CONTACT", "NEAR", "UNKNOWN_PARTIAL", "SCOPED_SYNTHETIC_CLEAR", "ACTIVE_UNKNOWN", "EXPIRED")


def verify_exports(deps, root):
    """Fail if the read-only import tree differs from any claimed Git blob."""
    paths = {
        "C1": ("robot_dashboard/expansion_contracts", "robot_dashboard/expansion_services",
               "experiments/expansion_20261029/c1_service_host/host.py"),
        "D2": ("robot_dashboard/obstacle_fusion_core",),
        "D3": ("robot_dashboard/collision_geometry_core",),
    }
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


def build(deps, root, output):
    verified = verify_exports(deps, root)
    sys.path.insert(0, str(root))
    import robot_dashboard
    robot_dashboard.__path__.insert(0, str(deps / "robot_dashboard"))
    from robot_dashboard.obstacle_fusion_core import core as d2
    from robot_dashboard.collision_geometry_core import assess, RobotGeometry, transform
    import robot_dashboard.collision_geometry_core.assessment as d3
    from robot_dashboard.expansion_contracts import CollisionAssessment, ContractError, ObstacleFrame
    spec = importlib.util.spec_from_file_location("c1_exact_offline_host", deps / "experiments/expansion_20261029/c1_service_host/host.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    from starlette.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse
    apps, raw_reports, contexts = {}, {}, {}
    for i, name in enumerate(CASES, 1):
        app = host.create_test_host(output / f"private-host-{i}", TOKEN)
        scene = app.state.c1[2]
        # Virtual monotonic host clock enables deterministic expiry tests; it is
        # not the browser clock and never used as a real acquisition timestamp.
        host_ns = 9_007_199_254_740_993  # deliberately beyond JS safe integers
        binding = dict(map_id="a" * 24, revision="b" * 64, generation=i)
        epoch, stream = f"sensor-{i}", f"scene-{i}"
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
        coverage = "COMPLETE_SYNTHETIC" if name=="SCOPED_SYNTHETIC_CLEAR" else "SPARSE"
        raw = assess(model,state,obstacle,path,now_stamp_ns=host_ns,now_clock_domain=meta["clock_domain"],coverage=coverage)
        # Prove the direct incompatibility instead of calling it a passing wire.
        try:
            CollisionAssessment.from_dict(raw)
        except ContractError as exc:
            incompatibility = str(exc)
        else:
            raise AssertionError("Expected pinned D3/C1 validity mismatch disappeared; inspect pins")
        c = copy.deepcopy(raw)
        interval = c["validity_interval"]
        assert interval["clock_domain"] == meta["clock_domain"] and meta["stamp_ns"] == str(meta["received_monotonic_ns"])
        c["freshness"].update(original_validity_interval=interval, clock_mapping={"kind":"SYNTHETIC_IDENTITY_ONLY", "source_epoch":epoch,
            "sensor_ns":meta["stamp_ns"],"host_ns":str(host_ns),"host_clock_id":"test-host"}, coverage=coverage,
            protection_mode="ACTIVE_CONSTRAINT" if name=="ACTIVE_UNKNOWN" else "ADVISORY_ONLY")
        c["validity_interval"] = dict(host_clock_id="test-host",start_monotonic_ns=int(interval["from_ns"]),end_monotonic_ns=int(interval["until_ns"]))
        c["obstacle_frame_ref"] = {"source_epoch":epoch,"sequence":obstacle["sequence"]} # C1 snapshot requires exact two-key reference
        collision = CollisionAssessment.from_dict(c).to_dict()
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
        snapshot = scene.snapshot()
        if name=="PREDICTED_CONTACT": assert raw["reason"]=="PREDICTED_COLLISION",raw
        elif name=="SCOPED_SYNTHETIC_CLEAR": assert raw["severity"]=="CLEAR",raw
        else: assert raw["severity"]=="UNKNOWN" and raw["min_clearance"]>0,raw
        if name=="EXPIRED": assert snapshot["collision_assessment"] is None
        raw_reports[name] = dict(raw_d3=raw,direct_c1_validation="EXPECTED_CONTRACT_FAILURE",error=incompatibility,
            projection="EXPLICIT_SYNTHETIC_CLOCK_MAP",snapshot=snapshot,scene_metrics=scene.metrics())
        contexts[name] = dict(binding,frame_id="map",source_epoch=epoch,stream_epoch=stream,clock_domain=meta["clock_domain"],
            calibration_id=meta["calibration_id"],units="m",source_identity="SYNTHETIC_SELECTED_IDENTITY_NOT_D1_MERGED_ARTIFACT")
        apps[name]=app
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
    report=dict(pins=PINS,verified_dependencies=verified,contract="0.1",modules=modules,source_mode="ACTUAL_C1_SERVICE",evidence="SYNTHETIC",
                native="NOT_RUN",ros="NOT_RUN",merged_map="INPUT_REQUIRED",cases=raw_reports)
    (output/'core-results.json').write_text(json.dumps(report,indent=2)+'\n')
    return wrapper


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--deps',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--port',type=int,default=4184)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    args.out.mkdir(parents=True,exist_ok=True)
    # C1 temporary source/bundle files must never enter repository evidence.
    with tempfile.TemporaryDirectory(prefix='c3-c1-round2-') as private:
        app=build(args.deps,root,Path(private))
        raw=(Path(private)/'core-results.json').read_bytes()
        (args.out/'core-results.json').write_bytes(raw)
        print(json.dumps(dict(status="READY",core_report_sha256=hashlib.sha256(raw).hexdigest(),port=args.port)),flush=True)
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__': main()
