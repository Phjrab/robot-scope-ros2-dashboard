"""Read-only C1 exact-SHA contract test in a separate temporary export.

Export must be obtained at C1_SHA; no C1 code is copied into the C4 submission.
Run from repository root with PYTHONPATH=.:tests. No service/HTTP is opened.
"""
import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
import json

C1_SHA = "2402c02c6f91ba54064894b21735e01b98610acd"


async def check(export):
    import robot_dashboard
    robot_dashboard.__path__.append(str(export/"robot_dashboard"))
    from robot_dashboard.expansion_contracts import ObstacleFrame, ScenePacket, CollisionAssessment
    from robot_dashboard.obstacle_runtime_adapter.c1_ports import C1ObstacleProjection, C1SceneSink, c3_scene_wire
    from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter
    from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
    from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
    from robot_dashboard.obstacle_runtime_adapter.command import Binding, RawCommand, constraint_from_d3, CommandGate, MockCommandSink
    from expansion_c4.fixtures import identity, cloud, D2Fixture, C1Fixture
    i = identity(map_id="1"*24, revision="1"*64)
    projection = C1ObstacleProjection(ObstacleFrame)
    c3_packet = C1Fixture()
    received = []

    class ServicePortFixture:
        def ingest(self, kind, packet):
            # Actual C1 service was not present at the bootstrap SHA. This tests
            # its documented call signature with the actual contract parser.
            assert kind == "obstacle_frame"
            received.append(ObstacleFrame.from_dict(packet).to_dict())

    c1_sink = C1SceneSink(ServicePortFixture(), obstacle_projection=projection)

    class FanoutFixture:
        def ingest(self, packet):
            c1_sink.ingest(packet)
            wire = c3_scene_wire(packet, obstacle_projection=projection, scene_type=ScenePacket).to_dict()
            ScenePacket.from_dict(wire)
            c3_packet.ingest(wire)

    r = RuntimeAdapter(d2=D2Fixture(), scene_sink=FanoutFixture(), validate_obstacle=projection,
        source_epochs={"lidar": "epoch-1"}, binding=i.binding, receipt_clock_id=i.receipt_clock_id,
        config=RuntimeConfig(mode="synthetic"), clock_ns=lambda: i.received_ns)
    r.start()
    try:
        assert r.offer_raw(cloud(), i, pointcloud2)
        await asyncio.wait_for(r.worker.queue.join(), 3)
        assert received[0]["stamp_ns"] == i.stamp_ns
        assert received[0]["sequence"] == i.sequence
        assert c3_packet.snapshot()["obstacle_frame"]["source_epoch"] == i.source_epoch
        assert c3_packet.snapshot()["sources"]["c4"]["identity"]["tf_epoch"] == i.tf_epoch
    finally:
        await r.close()
    b = Binding("goal-1", 1, "lease-1", i.source_epoch, "map/r1/tf1", i.receipt_clock_id)
    assessment = CollisionAssessment(schema_version="0.1", evidence_kind="SYNTHETIC", producer="d3-port-fixture",
        sequence=1, source_epoch=i.source_epoch, frame_key=i.packet()["frame_key"], stamp_ns=i.stamp_ns,
        clock_domain=i.clock_domain, host_clock_id=i.receipt_clock_id, received_monotonic_ns=i.received_ns,
        map_binding=i.packet()["map_binding"], robot_pose_ref=None, joint_state_ref=None,
        robot_geometry_hash=None, obstacle_frame_ref=None, path_ref={"command_sequence": 1},
        padded_envelope=None, unpadded_envelope=None, min_clearance=None, predicted_overlap=True,
        modeled_ttc=None, freshness={"c4_binding": b.__dict__},
        validity_interval={"clock_id": b.clock_id, "valid_from_ns": i.received_ns, "valid_until_ns": i.received_ns+100_000_000},
        reason="PREDICTED_COLLISION", severity="STOP_REQUIRED", recommendation="HOLD").to_dict()
    constraint = constraint_from_d3(assessment, validate_assessment=CollisionAssessment.from_dict, binding=b, command_sequence=1)
    sink = MockCommandSink()
    command = RawCommand(1, b, i.received_ns, i.received_ns+100_000_000, (.2,0.,0.))
    checked = CommandGate(sink,b).apply(command, constraint, now_ns=i.received_ns)
    assert checked.hold and checked.velocity == (0.,0.,0.)
    return {"C1_contract_SHA": C1_SHA, "C1_ObstacleFrame": "PASS", "C1_ScenePacket": "PASS",
            "C1_CollisionAssessment_to_mock_ZERO": "PASS", "C1_service": "NOT_RUN_BOOTSTRAP_HAS_NO_SERVICE",
            "D2": "FIXTURE", "D3": "FIXTURE", "C3_consumer": "NOT_RUN_NO_EXACT_SHA",
            "evidence_kind": "UNIT", "device": "DEVICE_NOT_RUN"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.export.resolve())), indent=2))
