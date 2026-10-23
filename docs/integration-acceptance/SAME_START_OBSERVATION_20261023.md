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

## First approved device execution and follow-up

Code `522e4bd6721ca356b84f27a3f68bec2e835576db` was published to main. Its
six-file patch was merged with the installed overlays and applied from private
manifest `b00ee5cc47ce19784cd1678e13320dff6d85781a6581bd46968e8f267aeeae68`.
The robot checkout remains `d7807de8f15fb457942039bb90ab41cf68d384c6` plus
those overlays and the patch; it is not a checkout of public main. The approved
dashboard restart produced PID 107139, active with NRestarts=0, and recovered
its owned LiDAR preview. Control bridge stayed disabled/inactive.

An isolated observation FAST-LIO was started at 14:14:03 KST under
`robot-scope-same-start-20261023.service`, with a 3,600 s lifetime. Compiled-in
Log/PCD directories are privately bind-mounted, and TF outputs are remapped.
The original map/config/mapping logs were preserved. `/Odometry` and
`/cloud_registered` were selected. The new map and approximate prior were
entered in the existing Maps view. Fresh FAST-LIO IMU pose propagation was
observed; no accepted live scan-to-map correction has yet been recorded.
Manual movement and absolute accuracy remain untested.

The first live attempts exceeded the unchanged 600 ms budget before ICP:
whole-catalogue metadata took 824–912 ms and data lookup 1,411–2,612 ms under
the dashboard process load. The reference was never cached. The follow-up
retains one catalogue-admitted observation record and revalidates its actual
contained file/header/revision before reads and at completion. It avoids
rescanning unrelated maps. Immutable reference preparation survives a bounded
failed attempt; every retry obtains fresh source samples and still uses the
600 ms deadline. A slow OS file read can overrun that deadline before returning,
but such an attempt cannot return a current candidate. No timing or residual
threshold was increased.

Continuous FAST-LIO display now handles independently sampled browser streams:
already registered points use `T_M_O × points_O`; the latest fresh IMU pose uses
`T_M_O × T_O_F(now)`. The UI labels this
`REGISTERED_FRAME_INDEPENDENT_CURRENT_POSE`. It does not claim exact pairing of
those two display samples. Backend corrections still require identical original
FAST-LIO output timestamps; the strict display mode retains its old pairing.
Stale, generation, map/source and jump invalidation remain in effect.

Follow-up validation: full Python 2,415 tests, 3 skipped; JavaScript 595 tests;
7 browser tests; 26 tests against the merged installed UI candidate. A separate
robot process reading the pinned map measured selected metadata 0.304 ms,
normalized data 85.825 ms, grid preparation 63.457 ms. These isolated numbers
are not proof of performance inside the running dashboard.

An offline diagnostic used a current captured cloud (original stamp
1792733268642336606 ns) and an approximate stationary seed. It converged in
32 iterations with point-to-point inlier RMSE 0.164048 m, overlap 0.997701,
and 468.6 ms on the Mac. The independently read pose stamp was
1792733268942628622 ns, so this is expressly not an exact-paired live result.
Four additional local yaw seeds in ±0.3 rad did not pass the unchanged 10 cm
policy (best RMSE about 0.16405 m, with convergence failures also retained).
None was applied. The installed config uses 0.5 m surface/map filtering, and
published saved points accumulate filtered scans; this is a relevant sampling
limitation, not proof that sampling alone explains the residual.

The four-file follow-up bundle is prepared with per-file hashes, original
backups and guarded restore. Its additional dashboard restart requires separate
approval because the first approval explicitly allowed one restart, already
performed. Until that approval and a successful real rerun, D (accepted regional
registration) and F (full stationary acceptance) remain incomplete.

The same follow-up aligner also uses `scipy.spatial.cKDTree` when SciPy is
already installed, with the existing RadiusGrid as the no-SciPy fallback. No
dependency was installed/upgraded on either machine. Search is exact (`eps=0`,
one worker), preserves the complete reference, recomputes squared distances,
resolves equal-distance ties by original point ID, and enforces the original
0.75 m gate after boundary over-fetching. Queries are checked against the same
deadline in 64-point batches. All solver/policy/source gates remain unchanged.

Eight search regression tests passed against the robot's installed SciPy,
including ties, radius boundaries and deadlines. On the same preserved real
cloud, the robot's isolated native-index run completed in 147.802 ms, 32
iterations, overlap 0.9977011494, RMSE 0.1640478345 m. This agrees with the
RadiusGrid diagnostic within floating-point precision and **remains rejected**.
A 508-point search against the pinned map took 3.071 ms versus 125.489 ms for
RadiusGrid in the same isolated process. This does not establish a successful
live registration or dashboard latency under load.

A real screen capture shows the selected 41,073-point map and the sensor axis
label `FAST-LIO IMU · BODY UNVERIFIED` after approximate reanchoring. The old
installed frontend can still lose the anchor on stale exact-pair browser history;
the prepared independent-display fix has not yet been applied. This screenshot
is evidence of same-start odometry display, not an accepted map correction.

Final acceleration validation: full Python 2,417 tests passed (3 skipped),
related JavaScript 26 passed, and the robot-native search tests above passed.
The prepared follow-up remains four deployed files and one additional dashboard
restart; the estimator's original one-hour lifetime is unchanged.
