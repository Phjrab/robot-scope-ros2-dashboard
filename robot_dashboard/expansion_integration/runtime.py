"""Explicit installed C1 0.2 path; no ROS subscription or command sink."""
from robot_dashboard.expansion_runtime.async_adapter import AsyncRuntimeAdapter
from robot_dashboard.expansion_runtime.canonical_ports import CanonicalCorePorts
from robot_dashboard.expansion_runtime.composition import Runtime
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig


def create_review_runtime(flags, *, geometry, context, mapping, capture_provider,
                         clock_ns, source_id, mode="synthetic"):
    if not flags.runtime or not flags.scene:
        raise ValueError("FEATURE_DISABLED")
    if mode not in {"synthetic", "replay"}:
        raise ValueError("BLOCKED_NATIVE_IDENTITY")
    ports = CanonicalCorePorts.from_installed(geometry)
    runtime = Runtime(ports, context, mapping, mode="ADVISORY_ONLY", clock=clock_ns)

    def factory(current):
        return SceneSnapshotService(current.map_binding, host_clock_id=current.host_clock_id,
                                    clock=clock_ns, schema_version="0.2",
                                    stream_epoch=f"c4-{current.runtime_generation}")

    return AsyncRuntimeAdapter(runtime, capture_provider=capture_provider,
                               scene_factory=factory, source_id=source_id,
                               clock_ns=clock_ns, config=RuntimeConfig(mode=mode))
