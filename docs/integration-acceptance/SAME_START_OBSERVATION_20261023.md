# Same-start saved-map observation — 2026-10-23

The existing Maps observation panel can now track the installed FAST-LIO IMU
state against a pinned saved 3D map. This is display-only: no map→odom TF,
initialpose, goal, control output or body-extrinsic claim is added.

Select the saved PCD, enable current inputs, and on Humble explicitly select
subscription/graph evidence mode. Enable **동일 시작점 기반 연속 관측**, enter an
approximate start pose in the tracked frame, confirm stationary placement, and
connect the current pose. The transform is `T_M_F_start × inverse(T_O_F(t0))`.
Full XYZ/roll/pitch/yaw are retained. The zero defaults are not map-origin proof.
Enable the existing bounded regional scan-to-map calculation when ready.

The inspected FAST-LIO implementation publishes `/Odometry` as
`camera_init → body`. Here `body` is its IMU state, not Go2 `base_link`.
`/cloud_registered` is already in that estimator's `camera_init` frame. Both
outputs use `lidar_end_time`; matching requires their exact original source
stamps. No odometry or sensor extrinsic is reapplied to registered points.
This output-time relationship does not establish physical sensor clock sync or
independent deskew accuracy. Session/source identity and freshness still apply.

The same-start mode explicitly distinguishes initial odometry propagation,
map-corrected estimates, and unavailable correction with valid odometry
continuing. A prior accepted map connection remains usable within the same
source generation while fresh odometry advances. The original strict display
mode still hides rejected/stale correction geometry. Map revision, source,
backwards time, jump and stale input invalidate the connection in both modes.
Historical results never acquire a new source timestamp. IMU estimates use an
axis marker and their own trail; they do not place a Go2 body model.

The solver retains its 600 ms budget, maximum 1 Hz admission, 512 query samples,
full normalized reference, 0.75 m correspondence radius, overlap/geometry and
convergence requirements. Provisional 10 cm and original 5 cm residual
assessments remain distinct. Residual is not absolute position accuracy.

`ROBOT_SCOPE_FASTLIO_OBSERVATION_ONLY=1` reuses the existing launch environment
and FAST-LIO settings, remaps TF/map/path to observation topics and disables
PCD/path/map accumulation publication. The caller must first establish that no
competing estimator runs and preserve the binary's compiled-in Log directory.
The prepared device invocation uses a private systemd bind mount for logs/PCD;
it never uses the mapping launcher that resets an existing estimator.

## Current evidence

- GitHub and local pre-change HEAD: `e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`.
- Robot Git HEAD: `d7807de8f15fb457942039bb90ab41cf68d384c6`, with retained installed
  overlays. Device deployment must preserve those overlays rather than copying
  the complete public main tree.
- New original: `map_20261023_135003.pcd`, 41,073 points, `camera_init`.
- Map ID `b9087113da92a1f2b477e932`; catalogue revision
  `58991300bd1aac8c872fd45cafdda6f3eaf2026e4e578d411a4cdba439d31f6a`.
- Original SHA256 `628653237cc7fb146793a6b970a5636f6562b5b3b73b57cf64fcf9badaead97a`.
- Save family completion: 2026-10-23 13:50:05.605707 KST; mapping session
  `564db101a817904bc0c899cb`. Selection is based on the saved bundle/session and
  operator report, not merely filesystem recency.
- Retained first FAST-LIO pre-update state at relative LiDAR time 0.300335 s:
  XYZ `(-0.0000595627, -0.000114832, -0.0000871445)` m, RPY `(0,0,0)` degrees.
  Its original absolute source stamp is unavailable. It is an approximate
  prior supported by initialization code/logs, not an independently measured
  start pose. The inspected implementation has no loop-closure path.
- Mapping config `fastlio_xt16.yaml` SHA256
  `3d3fd83fe14c21d07d0b7108f4818d74c0557d67006aa00bc24295e8d30dd4bd`;
  configured IMU←LiDAR translation `(0.25,0,0)` m, rotation Rz(+90°), online
  extrinsic estimation enabled. Historical effective parameters are inferred
  from retained source/launch configuration; no past parameter dump is claimed.
- At first inspection FAST-LIO had exited; fresh manufacturer odometry was
  `/utlidar/robot_odom`, `odom → base_link`. This is not saved-map localization.

Software validation: full Python 2,412 tests, 3 skipped; all JavaScript 595 tests;
7 observation browser tests; 26 tests against the merged installed UI candidate.
The first full Python run hit 25 sandbox socket permission errors; the same
suite passed with socket access. Initial browser setup also required local
server permission. No test was removed or its gate relaxed.

Device application, stationary registration and manual-motion evidence are
recorded separately below after execution. Absolute accuracy remains unmeasured.
Raw map/logs, source backups and the six-file deployment manifest remain in the
private `same-start-20261023` evidence directory, outside Git.
