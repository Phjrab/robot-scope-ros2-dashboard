# Current asynchronous ROS owner profile

Use [ROS_ADAPTER.md](ROS_ADAPTER.md) and the
[executable host example](../../../experiments/expansion_20261029/c4_runtime/ros_bridge/README.md)
for the opt-in `AsyncRuntimeAdapter` connecting `ReviewRosPort.handoff` to actual
D2/D3/C1 0.2 through the existing bounded worker. It creates no subscription.
Latest exact C3 accepts the actual C1 0.2 TCP response; missing pose/joints still
make collision drawable unavailable. Native evidence and unproven clearing /
actuator boundaries are recorded separately there.

`CanonicalCorePorts` and the synchronous Runtime from [FOLLOWUP.md](FOLLOWUP.md)
remain the core path. The old interfaces and old C3 rejection below are preserved
as historical fixed-SHA evidence, not current results. Product command/lease/STOP
owners remain unchanged; this new connection is ADVISORY_ONLY.

# Historical round 2 boundary

The authoritative actual-owner ports are now `robot_dashboard/expansion_runtime/`.
See [ROUND2.md](ROUND2.md) for pins, limits and execution evidence. The old
fixture contract below is retained only as first-round history; do not use its
`clock_id/valid_from_ns/valid_until_ns` proposal for new traffic.

- `CorePorts.from_installed(geometry)` resolves the pinned actual D2
  `obstacle_fusion_core` and D3 `collision_geometry_core`; the package name in the
  follow-up prompt differs from the actual D2 tree at the supplied SHA.
- Existing owner normalizes raw PointCloud2 with the first-round `pointcloud2`
  reader. `sensor.packet_from_pointcloud` accepts that Sample plus an exact
  stamped, verified sensor-to-local transform and range/FOV metadata. It keeps
  raw frame/layout/reference/origin separate, performs only a frame transform,
  and creates **no clearing rays**. No latest-TF lookup or sensor subscription.
- Invoke `Runtime.process` serially in the existing bounded worker/harness with
  a trusted context, robot state, command sequence/velocity, clock mapping and
  explicit authority result. Pure synchronous entrypoint; do not call heavy
  cores in a ROS subscription callback. `Runtime.rebind` is serialized with
  processing and requires a newer runtime generation; the host must also retire
  queued old work and rebind/reset its C1 scene and final consumer.
- `ports.ingest_scene(actual_c1_service, result)` validates real C1 payloads,
  checks both ingest return values, and reads the actual snapshot. It does not
  synthesize a C3 display profile. That consumer presently rejects the response.
- `FinalIntentPort` demonstrates final arbitration using **MockCommandSink only**.
  Default ADVISORY_ONLY never writes a command. Explicit ACTIVE_CONSTRAINT uses
  the first-round CommandGate, including STOP/UNKNOWN latching and independent
  tick expiry; CAUTION without an owner speed policy rejects to zero. An active
  instance cannot silently downgrade mode. A new gate is not authority to clear
  a product stop: the existing arbiter owns STOP/estop/lease state and resume.
  Product hook remains the exact existing Go2BridgeCore.tick location below.

D3 local harness handoff: `Runtime.process` is the real-core wrapper;
`packet_from_pointcloud` is the packet entrypoint. Packet examples are executable
in `tests/expansion_runtime/fixtures.py` and the normalized-PointCloud2 composition
test. The existing review launch/config and ReviewRosPort remain opt-in,
unchanged, and **NOT_RUN** in this ROS-less environment. ReviewRosPort's runtime
interface is the first-round `offer_raw` worker interface, not the new synchronous
Runtime: a harness must schedule the new entrypoint through that owner worker;
passing the new Runtime directly as ReviewRosPort.runtime is unsupported. Raw
LiDAR/depth publication must retain the original Sample and actual per-sensor
ray proof; no D2 bounding box/centroid may be used to fabricate a free ray.

## Historical first-round integration proposal

# C4 integration proposal — default OFF

This document records future changes only. No product file, Nav2 production
parameter, bridge, camera owner, goal heading module, service or deployment was
changed. Existing 3D Nav2, Goal URDF and final heading work retain ownership.

## One sensor handoff

In `robot_dashboard/ros/pointcloud.py`, `PointCloudHub.process`, immediately after
`observation_identity.observe(...)` has accepted its context and before viewport
throttling/sampling, the existing subscription owner can hand off the immutable
original PointCloud2 plus its original observation identity. Do not use browser
preview bytes, polling sequence, latest TF or current wall time as source data.

Proposed call: `RuntimeAdapter.offer_raw(message, identity, pointcloud2,
origin_m=(0,0,0))` on the owner asyncio loop. A ROS thread uses the bounded
`ReviewRosPort.handoff`, not an unlimited `call_soon_threadsafe` per sample.
Identity requires publisher/source epoch, original sequence and stamp, source
clock, receiver-local receipt/clock ID, map ID/revision/generation, TF epoch and
SYNTHETIC/REPLAY evidence. Reset the source registry explicitly on epoch changes.
`navigation_runtime.py::_on_cloud/_process_cloud` remains unchanged; do not add
a second production sensor subscriber or alter its original LiDAR route.

Camera/depth owners supply already acquired Image, CameraInfo, alignment/device/
profile/calibration metadata and recorded timestamps through the same injected
port. `ReadOnlySource` accepts explicit owner, recorded or generated iterators.
It never opens a device/file in its constructor. Different RGB/depth devices
require D2's actual calibrated reprojection; C4 does not attach pixels by index.

## D2, C1 and C3 ports

`RuntimeAdapter` calls the injected `d2.process(Sample)` in the existing
`competition_traffic.worker.TrafficWorker` (one executing + one latest pending).
This adapter protocol is a fixture boundary; D2's actual `process_lidar`/
`lift_detections`/Tracker API still needs an external exact-SHA shim. No D2
algorithm or source was copied here. Full source layout/bytes/origin are retained
in Sample. No class/novelty/localization exclusion can remove input LiDAR points.

The synchronous `scene_sink.ingest(packet)` port must be bounded and nonblocking.
`C1SceneSink` calls the actual C1-documented
`SceneSnapshotService.ingest("obstacle_frame", wire)` signature.
`C1ObstacleProjection` injects C1's actual ObstacleFrame class; that class owns
validation. C1 0.1 requires map binding generation and host receipt fields; the
design pack's v1 names are projected explicitly without changing source stamps.
Runtime counters/diagnostics and sensor origin are retained under health.
`c3_scene_wire` injects C1's ScenePacket class and emits its exact 0.1 shape.
C3 displays snapshots only; toggling/closing its browser never controls the gate.
`ReviewRosPort.attach_observer` subscribes only to the isolated global/local
OccupancyGrid snapshots and `/review/plan`. `scene_with_observations` joins those
actual inputs to a ScenePacket under the same map/generation/TF fence; C3 wire
sources retain the separate native evidence. It does not construct a path or
convert mere publication into controller consumption.

C1 contract parsing at `2402c02c6f91ba54064894b21735e01b98610acd` was exercised in
a separate read-only export. C1 service and C3 consumer execution are not implied
by this contract check. Do not register a product router in this candidate.

## One final command connection

Future insertion point: `robot_dashboard/go2_bridge.py::Go2BridgeCore.tick`, in
the existing `if ready and command_fresh` branch immediately before
`self._move_request(self._target)`. The existing estop/STOP/deadman/lease/telemetry
decisions remain authoritative, and posture/action policy also needs D3 coverage
before any production integration. Do not insert a second SDK/velocity publisher
or bypass the existing signed envelope and `Go2ControlBridge._tick_locked`.

Topology: single goal owner -> existing raw selection/lease checks -> D3 pure
assessment -> final checked-command gate -> existing single consumer. C4's
candidate gate explicitly accepts only `MockCommandSink`; it cannot reach the
product bridge. D3 severity is never recalculated here. Proposed D3 port fields:
`freshness.c4_binding={goal_id,generation,lease_id,source_epoch,frame_key,clock_id}`,
`path_ref={command_sequence}`, and receiver-local `validity_interval` containing
clock ID, valid_from_ns and valid_until_ns. Absent/mismatched context fails closed.
These extension fields are fixture proposals pending D3's exact implementation.

STOP_REQUIRED and UNKNOWN write actual `(0,0,0)`/hold to the mock sink. A newer
CLEAR does not unlatch a collision stop. Explicit trusted resume must acknowledge
the exact stop revision and use a fresh sequenced assessment; resume emits ZERO
and requires a new command. Global STOP/estop/canceled lease cannot be released
by this adapter. Late/duplicate commands, unknown local clocks, expired or future
validity, goal/lease/source/generation mismatch are rejected to ZERO. The trusted
consumer calls `tick(now_ns=...)` independently of the UI to enforce TTL. This
candidate has no background watchdog or authority reset API; future placement
must schedule that tick in the existing consumer loop, never in a browser.

## Opt-in native review profile and readback

`prepare_profile.py` generates a separate YAML from the read-only canonical base.
D3 must provide the conservative projected envelope radius and padding. Tests
use synthetic 0.65/0.10 m; those numbers are not measured robot geometry. Radius
and padding cannot shrink the base values. NavFn remains a circular conservative
baseline; a polygon YAML is not full-body planning qualification.

`ros2/robot_scope_obstacle_adapter/launch/review.launch.py` defaults to disabled.
Only explicit enabled=true + generated namespace parameters can launch two
native costmaps, the existing NavFn planner and a lifecycle manager. No
controller, behavior server, bridge or motion publisher is launched. The supplied
plan-only BT has no recovery; D3's harness must drive explicit synthetic planning
requests/replanning and consume `/review/plan` (there is no fabricated detour).
Global/local ObstacleLayers both receive:

| Source | Topic | Mark | Clear | Origin |
|---|---|---|---|---|
| original synthetic/replayed LiDAR | `/review/lidar_points` | yes | yes | `review_lidar` at message stamp |
| depth geometry | `/review/depth_points` | yes | no | `review_depth`, retained separately |
| D2 full geometry | `/review/geometry_marking` | yes | no | original provenance; no single fictitious ray origin |

One shared inflation layer follows the union of marking sources. Track TTL,
YOLO misses, occlusion or source dropout do not generate free rays. Stale
observations are refused. Native occlusion/dropout/duplicate-inflation outcomes
remain NOT_RUN; UNIT checks verify transport/policy, not costmap simulation.

Before native init, local `/proc/net/udp{,6}` checks domain 171's port range;
ROS_LOCALHOST_ONLY=1, ROS_DOMAIN_ID=171, RMW_IMPLEMENTATION=rmw_fastrtps_cpp are
required and external DDS profiles/discovery servers are rejected. The check
does not reserve ports. No ROS graph command, DDS scan, robot subnet probe,
host-network container or physical device mount is used. Namespace is fixed
`/robot_scope_review_x`; test sensor and sink topics are `/review/*` only.
Installed package.xml versions must be 1.1.20. No `/opt/ros` or vendor .so writes.

Future native readback must capture effective global/local observation_sources,
per-source marking/clearing/sensor_frame/ranges, plugin class, inflation, actual
circle radius/padding, planner plugin and remaps, localhost/domain/namespace,
lifecycle state, actual OccupancyGrid snapshots and actual plan headers. C4
publishes no claims based on a generated YAML alone. `ObservationEvidence`
retains bounded full global/local snapshots and observed plan geometry. A
post-publication occupied-cell observation with consistent clock and generation
can record ingestion correlation; it never asserts controller enforcement.

The declared plugins/options/executable were checked against upstream
[Nav2 1.1.20 ObstacleLayer](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/plugins/obstacle_layer.cpp),
[plugin manifest](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/costmap_plugins.xml),
[costmap executable](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/CMakeLists.txt)
and [PlannerServer](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_planner/src/planner_server.cpp).
Native installation and effective parameter readback were unavailable here.

## Default-OFF and rollback

Imports/construction open no device, topic, process, thread or model. Runtime
defaults to offline, launch to disabled. Real endpoint URLs/device paths/LIVE
labels are rejected before start. No environment defaults, autostart service or
product profile is registered. To roll back a review harness, stop its isolated
nodes and discard the temporary generated profile; there is no product config
to restore. Product integration, main merge, deployment and device tests require
the user's later instruction after the ongoing validation work concludes.
