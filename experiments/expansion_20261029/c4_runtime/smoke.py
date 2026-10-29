"""SYNTHETIC end-to-end port exercise; never opens ROS, robot or a camera."""
import asyncio
import json
from dataclasses import replace
from robot_dashboard.obstacle_runtime_adapter.command import Binding, CommandGate, MockCommandSink, RawCommand, Constraint
from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter
from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
from robot_dashboard.obstacle_runtime_adapter.nav2 import observation
from robot_dashboard.obstacle_runtime_adapter.evidence import ObservationEvidence
from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
from expansion_c4.fixtures import identity, cloud, D2Fixture, C1Fixture


async def main():
    i = identity()
    d2, scene = D2Fixture(), C1Fixture()
    r = RuntimeAdapter(d2=d2, scene_sink=scene, validate_obstacle=lambda f: None,
        source_epochs={i.source_id:i.source_epoch}, binding=i.binding, receipt_clock_id=i.receipt_clock_id,
        config=RuntimeConfig(mode="synthetic"), clock_ns=lambda:i.received_ns)
    r.start()
    try:
        for n in range(1200):
            current = replace(i, sequence=n, stamp_ns=str(1_000_000_000+n))
            assert r.offer_raw(cloud(stamp=current.stamp_ns), current, pointcloud2, origin_m=(0,0,0))
        await asyncio.wait_for(r.worker.queue.join(), 3)
        assert scene.snapshot()["sequence"] == 1199
        obs = observation(pointcloud2(cloud(),i,origin_m=(0,0,0)), topic="/review/lidar_points",
                          source_kind="lidar", now_ns=i.received_ns, receipt_clock_id=i.receipt_clock_id)
        assert obs.clearing
        evidence = ObservationEvidence(binding=i.binding)
        # No publisher was opened; constructing a transport plan isn't publication.
        assert not evidence.snapshot()["published_to_nav2"]
        b = Binding("fixture-goal",1,"fixture-lease",i.source_epoch,"map/r1/tf1",i.receipt_clock_id)
        sink = MockCommandSink()
        raw = RawCommand(1,b,i.received_ns,i.received_ns+100_000_000,(.3,0.,.1))
        stop = Constraint(1,1,b,i.received_ns,i.received_ns+100_000_000,"STOP_REQUIRED")
        checked = CommandGate(sink,b).apply(raw,stop,now_ns=i.received_ns)
        assert checked.velocity == (0.,0.,0.) and sink.current.hold
        print(json.dumps({"evidence_kind":"SYNTHETIC", "D2":"fixture_called", "scene_sequence":1199,
            "health":r.health(), "mock_sink":{"velocity":checked.velocity,"hold":checked.hold,"reason":checked.reason},
            "native_evidence":evidence.snapshot(), "NATIVE_NAV2_SIM":"NOT_RUN_NO_ROS",
            "DEVICE_NOT_RUN":True},indent=2))
    finally:
        await r.close()


if __name__ == "__main__":
    asyncio.run(main())
