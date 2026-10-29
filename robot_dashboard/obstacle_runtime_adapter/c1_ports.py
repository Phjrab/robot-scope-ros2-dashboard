"""Explicit wire projection to C1 0.1 at SHA 2402c02c (classes injected).

No shared validator or schema is duplicated. C1 constructors perform all wire
validation. Source data remains unchanged; TF epoch and worker timing travel in
health/source metadata rather than being silently lost at the projection.
"""
from copy import deepcopy


class C1ObstacleProjection:
    def __init__(self, obstacle_type):
        self.obstacle_type = obstacle_type

    def __call__(self, frame):
        health = deepcopy(frame["health"])
        health["c4_source_identity"] = {k: deepcopy(frame.get(k)) for k in (
            "source_id", "tf_epoch", "received_ns", "receipt_clock_id", "provenance")}
        return self.obstacle_type(schema_version="0.1", evidence_kind=frame["evidence_kind"],
            producer=frame["producer"], sequence=frame["sequence"], source_epoch=frame["source_epoch"],
            frame_key=deepcopy(frame["frame_key"]), stamp_ns=frame["stamp_ns"], clock_domain=frame["clock_domain"],
            host_clock_id=frame.get("host_clock_id", frame.get("receipt_clock_id")),
            received_monotonic_ns=frame.get("received_monotonic_ns", frame.get("received_ns")),
            map_binding=deepcopy(frame["map_binding"]), calibration_id=frame.get("calibration_id"),
            input_sources=deepcopy(frame["input_sources"]), obstacles=deepcopy(frame["obstacles"]),
            health=health, dropped_counts=deepcopy(frame.get("dropped_counts", {})))


class C1SceneSink:
    """Call C1's one bounded scene ingestion service. No HTTP/registration hook."""
    def __init__(self, service, *, obstacle_projection):
        self.service, self.obstacle_projection = service, obstacle_projection

    def ingest(self, packet):
        frame = deepcopy(packet["obstacle_frame"])
        frame["health"]["c4_runtime"] = deepcopy(packet["health"])
        frame["health"]["c4_diagnostics"] = deepcopy(packet.get("diagnostics", []))
        frame["health"]["c4_source_observation"] = deepcopy(packet.get("source_observation"))
        wire = self.obstacle_projection(frame).to_dict()
        self.service.ingest("obstacle_frame", wire)


def c3_scene_wire(packet, *, obstacle_projection, scene_type):
    """Return a validated C1 ScenePacket for C3's read-only consumer."""
    return scene_type(schema_version="0.1", evidence_kind=packet["evidence_kind"],
        producer=packet["producer"], sequence=packet["sequence"], source_epoch=packet["source_epoch"],
        map_binding=deepcopy(packet["map_binding"]), stream_epoch=packet["source_epoch"],
        robot_pose=deepcopy(packet.get("robot_pose")),
        obstacle_frame=obstacle_projection(packet["obstacle_frame"]).to_dict(),
        global_path=deepcopy(packet.get("global_path")),
        controller_local_trajectory=deepcopy(packet.get("local_trajectory")),
        costmap_snapshot=deepcopy(packet.get("costmap_snapshot")),
        collision_assessment=deepcopy(packet.get("collision_assessment")),
        sources={"c4": {"health": deepcopy(packet["health"]),
                         "nav2_observation": deepcopy(packet.get("nav2_observation")),
                         "identity": {k: deepcopy(packet[k]) for k in (
                             "stamp_ns", "clock_domain", "received_ns", "receipt_clock_id", "tf_epoch")}}})
