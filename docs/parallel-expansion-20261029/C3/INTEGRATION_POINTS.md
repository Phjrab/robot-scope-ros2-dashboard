# C3 integration points — product wiring deferred

Status: MODULE_IMPLEMENTED / OFFLINE_TESTED (see HANDOFF for executed results) / PRODUCT_WIRING_DEFERRED / DEVICE_NOT_RUN.

No shared product entrypoint is changed. Existing Navigation Goal/Initial URDF, heading fix and 3D Nav2 work retain ownership. A later explicitly authorized integration owner should use the following small ports after pinning C1/D2/D3/C4 results.

## Actual module and host

`robot_dashboard/static/features/obstacle_scene/index.js` exports:

```js
const feature = mountObstacleScene(panelElement, {
  scene: { canvas, project, viewKey, setRobot, setReferenceVisible },
  subscribe, getMap, theme, clock,
});
feature.snapshot();     // displayed snapshot (frozen display while paused)
feature.diagnostics();  // bounded retention/drop/draw counters
feature.destroy();     // idempotent unsubscribe, cancel rAF, clear owned UI
```

- `host` is a DOM element for the controls/inspector. Its document supplies the rAF lifecycle. Load `obstacle_scene.css` once through the eventual entrypoint. The existing scene canvas must already have a parent with the same viewport bounds; C3 appends one transparent canvas there and never creates another RobotScene3D.
- `scene.canvas`: existing host canvas. `project([x,y,z]) -> {x,y,depth}|null` returns CSS pixel coordinates using that exact camera. C3 does no TF lookup, unit repair or origin estimation. Canvas is a depth-unaware diagnostic overlay; wire boxes and planar cells do not provide surface occlusion or collision proof.
- `viewKey() -> string`: changes when camera, viewport or projection changes; this triggers overlay redraw. C3 otherwise refreshes at most every 100ms plus accepted packets/UI changes. One rAF loop watches freshness and camera. A fixed 192-byte box scratch buffer is reused, and no mesh/cache/history grows per render.
- `setRobot(null | {pose,joints,evidence_kind})`: an explicitly delegated **current robot display slot**. Never a goal/initialization preview slot. Clear/hide on null; render only this pinned pose and joints and label provenance. Fresh display is bounded by pose/joint TTL and pair skew. The port must not send ROS commands or fall back to a standing robot/goal pose.
- `setReferenceVisible(boolean)`: optional presentation-only toggle for the existing pinned map/cache. The host owns map loading, content-hash validation and map-change clearing. C3 restores visibility on destroy; host should scope this port to the feature's display slot. Missing this optional port means the map toggle cannot change the reference (fixture supplies it).
- `subscribe(callback) -> unsubscribe`: read-only, prevalidated C1 ScenePacket feed. The callback owns immutable packet references until the next rAF; one pending packet is retained and newer arrivals coalesce. Never inject API mutation methods. Unsubscribe must detach the actual transport listener. Reconnect updates the trusted context **before** publishing packets.
- `getMap()` is the trusted authority: `{map_id,revision,generation,frame_id,units:'m',source_epoch,stream_epoch,clock_domain,calibration_id,source_identity?}`. These pins are not adopted from incoming packets. Change pins when selecting a map, changing calibration or reconnecting, including while paused. C3 discards paths, tracks, selected objects, robot and collision state on the next rAF; old-context packets cannot revive them. The host must synchronously clear old reference map data before publishing new pins. `source_identity` should include merged/reference asset hash and source lineage; missing source identity is explicitly displayed.
- `clock() -> monotonic milliseconds` is only for local receipt aging. `theme` is `'dark'|'light'` or a zero-argument getter. Source stamps remain decimal ns strings/BigInt and are never subtracted from host clocks.

The only actual mounted host in this submission is `experiments/expansion_20261029/c3_scene_ui/host.js`, served by its loopback-only static server. It instantiates the existing renderer, preloads the existing public Go2 asset once, and injects these ports with entirely generated synthetic packets.

## Exact future shared hooks (not applied)

1. `robot_dashboard/static/features/cockpit/scene_host.js:createCockpitSceneHost`: its local `renderer`, `activate()`, `deactivate()`, `setMapState()` and `setRobotState()` already own lifecycle and model loading. Add a narrow display-port accessor while active, mount C3 once after `activate()`, and destroy it before `deactivate()` destroys the renderer. Existing `renderState()` must keep sole authority over the current robot display; delegate the C3 `setRobot` slot there rather than letting two writers race. Do not change the existing Goal URDF flow.
2. `robot_dashboard/static/scene3d.js:RobotScene3D._project(point)` and camera/`resize()` currently implement the required CSS projection. The fixture calls `_project` read-only through an injected wrapper; product integration should expose a public `projectWorld(point)` and camera revision notification. No monkey patch, copied renderer or prototype mutation is used here. A future after-draw notification could replace the camera watcher without changing the C3 packet API.
3. `robot_dashboard/static/go2_official_model.js:loadOfficialRobotModel`, `configureOfficialRobot`, `setRobotJointPositions`, `resetRobotJointPositions`: reuse the existing `sharedLoads` asset cache and visualization mesh. Preserve `setObservedRobotModel`'s FASTLIO_IMU approximate origin contract; C3 does not falsely set its `body_extrinsic_verified` flag or use it for map-frame poses. D3 envelope hash/provenance stays independent of the official web asset hash.
4. `robot_dashboard/static/features/maps/saved_scene.js:createSavedMapScene`: alternate future read-only map scene host; use the same ports with its existing saved renderer, not a second saved scene or second source download.
5. `robot_dashboard/static/features/route_planner/spatial_editor.js:gridToWorld`: **already reused** for occupancy-grid origin/yaw conversion. Image-down to grid-up index mapping is explicit in C3 drawing. The helper is pure on import. C3 accepts only already map-bound layers; an odom/base `ObstacleFrame` without a producer-supplied map transform is blocked. No latest-TF fallback exists.
6. `robot_dashboard/static/features/sensors/pointcloud_transport.js:createPointcloudTransport`: existing latest-only/generation/watchdog pattern was inspected. Do not create a new pointcloud socket. The eventual C1 read-only stream subscription should share that transport/cache and normalize validated packets into the profile below.

Feature remains default OFF: neither `app.js`, `navigation.js`, `index.html`, nor any renderer, application, configuration, package manifest or CI file is modified. Removing the explicit mount and stylesheet returns the host to its existing behavior. Destroy the mount before the host renderer.

## Internal fixture/display profile (wire mapping updated in round 2)

`consumer.js` implements fail-closed display guards and bounded presentation copies; it is **not** a second authoritative schema validator. C1 owns the common wire validators. The following is the retained internal fixture profile, not a second public wire version. Current actual C1 snapshot mapping is documented below; it no longer requires sources.display. Integration must inject C1 validation/adaptation at `subscribe`, with exact pinned mapping, rather than assuming field names are already a published common API.

The executable field reference is `fixture.js:makePacket`:

- `schema_version:'robot-scope.scene-packet.v1'`, `evidence_kind`, `producer`, safe integer `sequence`, decimal string `stamp_ns`, `source_epoch`, `stream_epoch`, `clock_domain`, `map_identity:{map_id,revision,generation,frame_id,units:'m'}`.
- Every displayed sublayer carries `frame_key:{map_id,revision,frame_id}`, `stamp_ns`, `clock_domain`, `source_epoch`, `calibration_id` where sensor/body geometry requires it, and bounded string-array `provenance`.
- `robot_pose:{ref,position_m:[x,y,z],rpy_rad:[roll,pitch,yaw]}` and `joint_state:{ref,positions_rad:{12 named Go2 joints}}`. Missing/stale joints hide the robot; no goal pose is substituted.
- `sources:[{id:'LIDAR'|'DEPTH',kind,health:'OK',points_m:[[x,y,z],...]...}]`; points are already transformed using the pinned producer calibration. Disabled display, missing receipt, stale data and bad health are distinct. No local association is attempted.
- `obstacle_frame` follows the design ObstacleFrame fields, with oriented bbox geometry (`center_m`, `extent_m`, normalized `orientation_xyzw`), unknown class allowed, `sensor_support` source IDs and `OBSERVED|OCCLUDED|STALE`. Geometry with mismatched/unavailable support or >250ms source/frame skew is suppressed. Occlusion/deletion does not set any clearing or Nav2 ingestion flag.
- `global_path` and `local_trajectory` are nullable `{generation,dimensions:2|3,representation:'2D_GROUND_PLANE'|'XYZ',points_m,plane_z_m? ,replanning_reason?}`. Two-dimensional input must declare its display plane. Missing local input remains missing; no curve/interpolation/planning is performed. History is at most 3 distinct input generations and expires; gray dashed lines are previous supplied plans, blue is the current supplied plan, purple dashed is supplied local trajectory. Planar display height is never measured elevation.
- `costmaps` is at most 2 bounded snapshots, each `{id,width,height,origin:[x,y,yaw],resolution_m,plane_z_m,representation:'2D_GROUND_PLANE',cells}`. Rows are grid-up, cells are -1 or 0..255; unknown is gray, lethal 253/254 is orange, other nonzero values amber. 255 is unknown, never lethal proof. No costmap marking/clearing or inferred free space is calculated.
- `collision_assessment` is nullable and references exact `robot_pose_ref`, `joint_state_ref`, `obstacle_frame_ref` (sequence), `path_ref` (generation or null), `robot_geometry_hash`, `valid_until_ns`. Severity, contact state, clearance and TTC are displayed as supplied; no intersection/TTC computation exists. Accepted contact labels: MODEL_OVERLAP / PREDICTED_COLLISION / CONTACT_UNCONFIRMED. Physical contact confirmation is not synthesized. `envelopes:[{id,kind,geometry}]` carry D3-supplied padded/unpadded/body/leg/mount/sweep boxes. A missing/incompatible input makes risk UNKNOWN, not CLEAR. Production must obtain the independently validated D3 geometry/hash; the synthetic fixture deliberately labels its envelope unvalidated for real robots.

Current explicit display budgets (not safety thresholds): 4 sources × 4096 points, 128 objects, 2048 points/path × 3 distinct generations, 2 costmaps × 4096 cells, 64 envelope boxes, 12000 inspector characters. Over-limit geometry is blocked rather than relabeled as full data. TTLs: source/obstacle/joints 1200ms, pose/collision 500ms, path 5000ms, costmap 1500ms, pair skew 250ms. These conservative local presentation defaults need agreement with pinned C1/D3 freshness policy before future live wiring.

Pausing freezes the displayed snapshot, explicitly labeled PAUSED; new input stays latest-only. Step consumes that one pending packet, not a hidden unbounded replay queue. The external replay producer owns the timeline. Map/context changes still clear a paused display. No control/safety stop is invoked.

## Current exact C1 service boundary — 0.2 continuation

Current source/contract pins, evidence and remaining input are in
[ROUND2_V02](ROUND2_V02.md). C1 `4e1dd519a707169da5f88cf2a92a20ed3e701cc7`
provides canonical 0.2 with decimal host ns and explicit slot status. Legacy 0.1
continues to work through the lossless token parser. D3
`356d0a036eb62d546e159e12a0691d7f5ea278f6` calls the actual C1 normalizer; no
consumer alias schema, ref truncation or receipt-time TTL restart is needed.

A future authorized host can inject this read-only boundary:

```js
const start = performance.now();
const wire = parseC1SceneJSON(await response.text());
const displayAssets = await assetCache.resolve(wire);
const {packet, reason} = adaptC1ScenePacket(wire, trustedContext, {
  transportAgeMs: performance.now() - start,
  displayAssets,
});
if (packet) publishToDisplay(packet);
```

Start timing before the request. Host clocks are never compared with browser
monotonic clocks. The C1 status `expired`/`unavailable` fences that slot sequence,
including late HTTP responses. Context/epoch/generation reset clears these fences.
The original validity interval, conversion provenance, receipt, clock and full
refs remain available to inspection. 25-digit source stamps match C1's bound;
host ns remain bounded to 2^63-1. UNKNOWN and positive clearance coexist.

`createC1AssetCache({fetchAsset,decode})` accepts only C1 opaque ID/revision refs
and calls `/api/v1/extensions/scene/assets/{id}/{revision}` through trusted
transport. Maximum 8 refs, 2 MiB each, 8 MiB total; media/length/SHA256 checked.
The host supplies authentication and an explicitly chosen geometry decoder.
Unknown formats fail visibly. C1 does not define asset cloud/costmap geometry;
`c3-test-display-v1` belongs only to the isolated C3 test host. No arbitrary URL,
filesystem path or new common v1 is resolved. Cache entries retire on omission,
map reset, revision replacement or dispose; stale asynchronous results cannot
repopulate a new context. Immutable successes/failures are not refetched per poll.

The adapter's optional display costmap must match the current observation's
asset ref and map generation. Bytes cannot replace canonical timestamp, source,
clock or sequence. Cell encoding explicitly distinguishes OCCUPANCY_PERCENT
(100 occupied) from NAV2_COST_0_255 (253/254 lethal,255 unknown). Native display
reduction preserves original grid bounds and unknown cells; safety inputs stay
unchanged. A bulk response does not refresh source age.

Generic pose/path/joint geometry remains host-defined. Missing native joints,
calibration, local trajectory and assessment stay unavailable. Scalar D3
envelopes are never drawn as invented boxes. Reported ACTIVE constraints retain
UNKNOWN/HOLD on missing evidence; downgrade remains visible. Neither the test
host nor this feature has a command sink. Shared app/renderer/goal hooks above
are proposals only, not connected by this submission.
