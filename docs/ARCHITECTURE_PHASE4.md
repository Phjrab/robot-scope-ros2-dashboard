# Phase 4 RosAgent Observability-Plane Decomposition

This document records the Phase 4 responsibility move. It supplements the
Phase 0 baseline and Phase 3 application-container boundary. Control and
navigation extraction remain explicitly outside this phase.

## Compatibility facade

`robot_dashboard.ros_agent.RosAgent` remains the application-facing facade.
Its existing constructor and public observation methods are preserved so API
routers, dataset capture, application shutdown, and current tests do not need a
new ROS integration contract. Internally it constructs six focused components
that share the same single-process `RLock` used before this phase.

| Component | Owned responsibility |
| --- | --- |
| `ros/runtime.py` | ROS thread, stop event, node/executor handles, readiness/error state and start time. |
| `ros/graph.py` | Discovered topic graph, subscription handles, selected special subscription names, UI-only rate/freshness meters and topic snapshots. |
| `ros/sources.py` | Fixed point-cloud identity metadata, selected/requested topics, fail-closed pins, profile policy validation and mode-0600 atomic persistence. |
| `ros/telemetry.py` | Bounded sensor summaries, selected joint state, selected odometry pose, occupancy-grid validation/storage and freshness projections. |
| `ros/cameras.py` | Two fixed camera IDs, frame epochs/state, H.264 assembly, receiver callbacks, per-source demand tokens/viewer caps and camera catalog/snapshots. |
| `ros/pointcloud.py` | Point limit/rate budget, bounded XYZ extraction, spatial outlier rejection, immutable packed frame epoch and JSON/binary snapshots. |

Compatibility properties on `RosAgent` temporarily preserve a small set of
private state probes used by focused regression tests. They delegate to the
component owner and do not create a second source of truth.

## Preserved contracts

- `RosAgent.start()`/`stop()` still provide a single daemon ROS thread and stop
  navigation/control before shutting down the executor.
- DDS setup, offline behavior, topic QoS selection and subscription switching
  are unchanged.
- Graph publisher/subscriber cardinality and motion-safety receipts remain
  distinct: graph UI metrics cannot satisfy navigation safety freshness.
- Source selection accepts only current graph topics or the profile's exact
  `allowed_offline` entries. Profile scope, fail-closed defaults, size limit,
  ownership, `0600`, no-follow open, atomic replace and directory fsync remain.
- Camera IDs remain exactly `go2_front` and `realsense_color`; viewer limits,
  opaque source-bound tokens, first-viewer start, last-viewer stop, frame clear,
  JPEG/H.264 bounds and independent source epochs remain unchanged.
- Point-cloud limits remain 1,000 through 1,000,000 (or explicit all-points),
  each frame remains bounded to one million points, and the transport keeps an
  immutable process epoch plus packed float32 payload.
- Occupancy grids remain capped at 16,000,000 cells and telemetry summaries,
  joints and poses retain their freshness and payload bounds.
- Existing HTTP and WebSocket paths and response schemas are unchanged.

## Deliberately retained in `RosAgent`

Control transport and navigation ROS gateway methods remain in `RosAgent` for
Phase 4. Their signed bridge, exclusive leases, deadman, E-stop, fixed topics,
validated receipts, runtime-health interlocks and goal fencing were not
redesigned. Phase 5 is the designated boundary for extracting those two planes.

The ROS node setup still calls the facade's fixed control/navigation setup and
subscription synchronization methods. This avoids changing callback-group,
executor and shutdown order while runtime ownership moves first.

## Side-effect policy

This refactor used local unit/static tests only. It did not initialize a live
ROS graph, restart a service, start mapping or navigation, publish a motion
command, access map data, or connect to robot hardware.
