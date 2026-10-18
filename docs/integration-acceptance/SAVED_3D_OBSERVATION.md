# Saved 3D map observation and editor integration — 2026-10-18

This candidate adds an opt-in observation layer to the existing Maps 3D view.
It displays current LiDAR and an **unverified Go2 pose estimate** against the
selected saved 3D reference. It also integrates the transferred 2D/3D map editor
into the existing editor panel. These are local source changes. Robot deployment
and live validation are held pending readiness after charging.

## Use and scope

1. Select a saved **3D point cloud** in Maps and select the 3D view.
2. Enable **현재 점군·pose 읽기**. This consumes existing dashboard observations;
   it does not start a LiDAR producer, FAST-LIO, Nav2, camera or bridge.
3. While stopped, enter approximate map XYZ (m) and roll/pitch/yaw (degrees),
   confirm the estimate and connect the current pose to that anchor. Default
   zero is not a verified map origin. The display says
   `ODOMETRY_PROPAGATED_UNVERIFIED` until scan-to-map is explicitly enabled.
4. Optionally enable repeated scan-to-map numerical calculation. A valid local
   hypothesis is labelled `SCAN_TO_MAP_CANDIDATE_UNVERIFIED`. Rejection, missing
   input, stale results or source change hide dynamic geometry; the saved map
   remains visible. Source changes and jumps require an explicit new anchor.
5. Observation JSON exports the bounded current display segment and source
   metadata. A new accepted correction starts a new segment; it does not join
   old and new map estimates into a misleading continuous trajectory.
6. Disable observation to release its point-cloud demand. No sensor session is
   owned by this view, so it has no sensor stop or movement action.

The map editor switches between existing 2D editing and 3D XY-polygon/Z-interval
annotations while retaining each unsaved draft. Visibility, localization exclusion
and keepout remain distinct local proposals. Edited-copy export preserves the
original. **Annotations are not consumed by the observation solver or installed
into runtime navigation.** See [MAP_EDITOR_3D.md](MAP_EDITOR_3D.md).

## Numerical and source contract

`POST /api/v1/observations/map-alignment` is a same-origin, stateless numerical
request over the server's cached observations. It never publishes ROS messages,
starts processes, changes sources, applies poses or mutates maps. Request pins:
24-hex map ID, 64-hex revision, observed dashboard identity and both publisher
epochs, plus a rigid `T_map_odom_seed`. Input matrix dimensions and finite values
are bounded. Unavailable/busy/changed inputs return HTTP 409.

- Reference: all usable points from the selected catalogue entry, 60–100,000.
  Capped references and source/used-count mismatch are rejected. This is the
  **normalized catalogue reference**, including 0.0001 m rounding, not a claim
  of raw-PCD byte identity. Catalogue frame/origin remain unverified.
- Query: at most 512 uniformly strided points from one cached scan; at least 60.
  Raw input supports only `/lidar_points` + `raw` and `/velodyne_points` +
  `converted`, with the explicit configured sensor/body relation. A cumulative
  `/Laser_map` or unknown stage cannot be reinterpreted as a raw scan.
- Raw transform: `T_odom_body * inverse(T_sensor_body) * p_sensor`.
  `/cloud_registered` + `registered` in the paired odometry frame receives no
  additional odometry/extrinsic transform. Display pose is
  `T_map_odom * T_odom_body`, not the solver's odometry-origin translation.
- Pairing: nearest **host receipt** within 150 ms, both received within one second.
  Exact source stamps remain decimal strings; source clocks and raw scan deskew
  are **unverified**. Receipt-nearest is not source-time synchronization.
- Identity: actual RMW `MessageInfo.publisher_gid`, one observed publisher and a
  dashboard observation epoch. Epoch changes on source/frame/GID/count change,
  reversed source time or >1 s receipt gap. Stalled source stamps fail closed.
  This does not assert a verified native map session: `native_session_id=null`.
- ICP: unchanged 0.75 m correspondence gate, 60% minimum overlap, 0.05 m maximum
  inlier RMSE, 0.002 minimum geometry eigen ratio, 40 iterations. Matched local
  reference geometry has the same eigen-ratio gate, so a large 3D map cannot
  qualify a locally planar correspondence set on its global geometry alone.
- Exact radius-grid neighbours use every reference point within the gate.
  Reusable candidate indices are bounded to 500,000 (4 MB) and 2,048 cells;
  exceeding the cache limit never truncates the candidate set.
- One worker per dashboard, at most one admission per second. A 600 ms elapsed
  budget is checked through index build, search and completion. Catalogue file
  I/O and an individual NumPy operation are not forcibly preempted, but an
  overrun returns no candidate. The lock remains held until the worker returns,
  including after browser cancellation. Total runtime includes preparation.
- Completion rechecks the actual pair freshness, map revision and both source
  epochs. Browser generation/map/source checks reject late results. Browser
  fetch timeout is 2 s and a response older than 1 s from request start cannot
  become a new candidate. Current input freshness remains 1 s. No timeout,
  correspondence or acceptance threshold was relaxed to obtain a candidate.

The display uses raw odometry before existing UI smoothing/IMU fusion. It detects
>1 m or >60 degree input/correction jumps at the current displayed body, clears
old samples on source/map changes, and hides the fallback robot on invalid input.
Body extrinsic qualification, independent accuracy, global relocalization and
motion application remain unverified. Residual is never assigned to accuracy.

## Offline recorded diagnostic

The existing October 18 reference `map_20261018_162315.pcd` has 25,666 points;
its SHA256 is `c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8`.
A retained registered query has 424 points, original stamp
`1792309179130175352`, SHA256
`0bc7a3e9a7fd67fd1edc4bcdcde075ebd04a6022bafafd84ea6ec7b34dec22ff`.
These files were read locally; no new capture or fresh receipt/GID was invented.

The first full-reference run hit the unchanged 600 ms budget. After eliminating
repeated neighbour-index construction, the new calculation completed in about
413 ms on the Mac: 38 iterations, overlap 1.0, inlier RMSE 0.0266336 m and matched
geometry ratio 0.0359465. This is a **new offline numerical CANDIDATE**, not a
live/localization acceptance. The earlier 4,000-reference
`REJECTED/HIGH_RESIDUAL` result remains unchanged. Repeated-structure ambiguity,
body relation and absolute accuracy are not resolved by this new fit.

Private files are under the existing evidence directory's `local-integration-qa/`:
`check_recorded_grid.py`, `recorded-grid-result.json`,
`check_recorded_grid_cached.py`, `recorded-grid-cache-result.json`. Each result
retains input and implementation hashes. Recorded map/query bytes are not in Git.

## Software validation

The complete Python suite passed: 2,288 tests, 3 skipped. The complete JavaScript
suite passed: 501 tests. New coverage includes exact radius-grid comparisons,
full-reference and local-plane rejection, noncommuting sensor transforms,
source/reset races, time/budget failures, single-flight admission, API origin and
bounds, stale/late UI results, source/map changes and candidate segment separation.
Browser validation covered all 159 cases: the complete run passed 152 and found
seven preview/inspector layout regressions. Moving the observation controls out
of the bounded shared preview row fixed all seven; the 16 affected layout/live
checks passed, followed by the two final visibility/style checks. The complete
suite was not repeated after that focused repair. Screenshots were inspected
and retained in the private closeout. This does not claim installed Jetson or actual manual-motion validation.

## Runtime and remaining field work

Last **historical** read-only inspection: 2026-10-18 09:37:06 UTC. Robot source
`/home/unitree/robot-scope` was clean at
`40276a51b2e08c77732317a856cc879cc23e1ef6`; dashboard active, control bridge inactive
and disabled. ROS Humble, domain 0, CycloneDDS, go2-onboard mapping profile and
`/run/robot-scope-slam/broker.sock` were observed. Config hashes:

- `config/go2-onboard.json`: `7b2addb78470d055f76cbdd97f6192da59f2f5e20f168346d896704e47de8150`
- `config/fastlio_xt16.yaml`: `3d3fd83fe14c21d07d0b7108f4818d74c0557d67006aa00bc24295e8d30dd4bd`

They are not refreshed claims while charging. No current-stage remote deployment,
service restart, sensor start, TF, initialpose, goal or movement was performed.
The local candidate also contains earlier calibration/Stop/recorded-view changes
since the installed source; deployment is not a viewer-only patch. The prepared
package enumerates this difference and preserves config, maps and runtime data.

Next minimum field step after readiness: read current exact source/config/session
and ownership; preserve any running or unsaved work; apply the approved dashboard
source change and dashboard restart only; verify actual MessageInfo/GID/publisher
count, selected scan/odom pair, stationary anchor and candidate/rejection behavior.
Jetson compute load/600 ms budget and actual 3D display have not been measured.
Only after stationary validation and current manual-operation conditions should
operator-driven movement observation be considered. No automatic driving,
Nav2/bridge activation or posture command is part of this feature.
