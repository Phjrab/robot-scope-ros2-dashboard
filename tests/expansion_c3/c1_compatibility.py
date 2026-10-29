"""Call exact exported C1 contracts only in an isolated /tmp import root.

Usage: python c1_compatibility.py C3-fixture.json validated-wire.json
C1 is supplied by PYTHONPATH pointing at git-archive export, never copied here.
"""
import json
from pathlib import Path
import sys

from robot_dashboard.expansion_contracts import ObstacleFrame, CollisionAssessment, ScenePacket


raw = json.loads(Path(sys.argv[1]).read_text())
binding = dict(map_id=raw["map_identity"]["map_id"], revision=raw["map_identity"]["revision"], generation=0)


def common(value):
    return {k: value[k] for k in ("evidence_kind", "producer", "sequence", "source_epoch")} | {"schema_version": "0.1"}


def observation(value):
    if value is None:
        return None
    return value | dict(schema_version="0.1", frame_key=dict(source_epoch=value["source_epoch"], frame_id="map"),
                        map_binding=binding, host_clock_id="fixture-host", received_monotonic_ns=0)


o = raw["obstacle_frame"]
obstacle = ObstacleFrame(**common(o), frame_key=dict(source_epoch=o["source_epoch"], frame_id="map"),
                        map_binding=binding, stamp_ns=o["stamp_ns"], clock_domain=o["clock_domain"],
                        host_clock_id="fixture-host", received_monotonic_ns=0, calibration_id=o["calibration_id"],
                        input_sources=["LIDAR", "DEPTH"], obstacles=o["obstacles"], health={"state": "fixture"}, dropped_counts={})
c = raw["collision_assessment"]
collision = CollisionAssessment(**common(c), frame_key=dict(source_epoch=c["source_epoch"], frame_id="map"),
    map_binding=binding, stamp_ns=c["stamp_ns"], clock_domain=c["clock_domain"], host_clock_id="fixture-host",
    received_monotonic_ns=0, robot_pose_ref={"ref": c["robot_pose_ref"]}, joint_state_ref={"ref": c["joint_state_ref"]},
    robot_geometry_hash="e"*64, obstacle_frame_ref={"sequence": c["obstacle_frame_ref"]},
    path_ref={"generation": c["path_ref"]}, padded_envelope={"envelopes": c["envelopes"]}, unpadded_envelope=None,
    min_clearance=None, predicted_overlap=None, modeled_ttc=None, freshness={"kind": "SYNTHETIC"},
    validity_interval={"valid_until_ns": c["valid_until_ns"]}, reason="CONTACT_UNCONFIRMED", severity="CAUTION",
    recommendation="NO_LIVE_COMMAND")
wire = ScenePacket(**common(raw), map_binding=binding, stream_epoch=raw["stream_epoch"],
    robot_pose=observation(raw["robot_pose"]), obstacle_frame=obstacle.to_dict(), global_path=observation(raw["global_path"]),
    controller_local_trajectory=None, costmap_snapshot=observation(raw["costmaps"][0]), collision_assessment=collision.to_dict(),
    sources={"display": {"schema_version": "robot-scope.c3-display.v1", "stamp_ns": raw["stamp_ns"],
        "clock_domain": raw["clock_domain"], "calibration_id": raw["calibration_id"], "joint_state": observation(raw["joint_state"]),
        "sensors": [observation(s) for s in raw["sources"]], "provenance": ["SYNTHETIC C3 display profile through exact C1 validator"]}})
validated = ScenePacket.from_dict(wire.to_dict()).to_dict()
Path(sys.argv[2]).write_text(json.dumps(validated))
print(json.dumps({"C1_validator": "PASS", "evidence": "SYNTHETIC", "wire_bytes": len(json.dumps(validated)),
                  "module_path": sys.modules[ScenePacket.__module__].__file__}))
