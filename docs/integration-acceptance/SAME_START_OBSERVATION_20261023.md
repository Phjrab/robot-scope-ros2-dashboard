# Same-start saved-map observation — 2026-10-23

The existing Maps observation panel can now track the installed FAST-LIO IMU
state against a pinned saved 3D map. This is display-only: no map→odom TF,
initialpose, goal, control output or body-extrinsic claim is added.

**Current device result:** the separately approved five-file process-isolation
patch from `2b3b441` is installed. Actual dashboard computations now complete
(median worker 223.1 ms in the recorded window), but the exported latest result
still rejects RMSE 0.161319 m. A new 119.6 s same-start IMU display window is
preserved. No map correction has been accepted. The renewed observation run
started at 15:24:15 KST and has a one-hour maximum lifetime. Earlier pending
application and expired-run notes below are historical; see the final execution
section for the current installation and remaining limitations.

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


## Approved follow-up execution — 14:41–14:52 KST

After explicit approval, the four-file follow-up was installed with manifest
`ca59a1f97b9691056ab625933952cf40a71cf36c3ead13a70410951a0aa2444f` and the
additional dashboard restart was performed once. Dashboard PID is 138038,
active, NRestarts=0; owned LiDAR preview recovered. The original observation
FAST-LIO retained its process (wrapper 107991, estimator 108042) and its original
15:14 KST lifetime limit. Control bridge is inactive/disabled. No robot motion,
posture, Nav2 or operational TF application was performed.

Installed source and all four protected original backups matched the manifest.
The pinned PCD, FAST-LIO config and original mapping `Log/mat_pre.txt` hashes
remain unchanged. Robot Git HEAD is still `d7807de8f15fb457942039bb90ab41cf68d384c6`
plus retained installed overlays and the patches through public source commit
`6333dca5c5f66fc886cb8dbce10f123b76773ccb`. Git publication and deployment are
separate events; no wholesale checkout was installed.

The map, subscription evidence mode, same-start continuous mode and recorded
six-dimensional prior were reselected in the existing Maps panel. The anchor
used current pose stamp 1792734152044028759 ns. The exported observation window
contains 400 samples spanning 119.598786354 s, with 398 distinct, nondecreasing
pose stamps, unchanged map revision, alignment revision 0 and
`accepted_registration=false`. The UI remained `SAME_START_ODOMETRY_ESTIMATE`
after numerical failures, with independently advancing registered-cloud and
current IMU timestamps. This establishes stationary display continuity in that
window, not physical pose accuracy or manual-motion tracking.

The first catalogue admission still took about 896 ms and the first SciPy
import/reference build took about 2.8 s; both attempts were correctly rejected.
Prepared data/index were retained. Warm selected-map metadata took roughly
10–33 ms instead of rescanning the full catalogue. Nevertheless, dashboard
worker attempts reached the 600 ms wall deadline after only 7–9 nearest-search
calls, with about 109–135 ms of worker CPU. SciPy was loaded in the actual
service. A nearby historical fit used only as a numerical search seed also
hit the same deadline. No such rejected seed/result was applied to the UI.
Repeated dashboard alignment was then disabled; IMU display remains enabled.

To distinguish computation contention from numerical fit quality, a separate
read-only process used the **installed** aligner with a prepared identical
reference. It captured real pointcloud/pose WebSocket messages with the exact
same original source stamp 1792734562542991399 ns, host receipt delta
0.012136981 s, and the dashboard's unmodified subscription evidence. It used
fresh same-start prior initialization and the same 600 ms deadline. Completion
re-read the latest dashboard cloud/pose and revalidated map revision, source,
graph evidence and original-pair freshness. No timestamps were refreshed and no
ROS publisher, UI result injection or operational application was involved.

That actual live-input diagnostic completed in **268.852 ms total** (149.906 ms
solver), converged in 29 iterations with 435/435 inliers, overlap **1.0**, and
point-to-point RMSE **0.164951548 m**. Its sole gate reason is `HIGH_RESIDUAL`;
both original 5 cm and provisional 10 cm policies reject it. The result remains
a private diagnostic and is not the dashboard's current map correction.

A/B/C are established for the pinned new map and approximate IMU connection.
E is demonstrated for same-start odometry display only. Actual regional
registration was executed but did not qualify; D and full F acceptance therefore
remain incomplete. G (operator manual movement) and absolute accuracy are
unmeasured. The remaining blockers are shared-process live computation delay
and the roughly 16.5 cm point-to-point residual. The next minimum implementation
step is isolated numerical execution with the same source/map/deadline fences;
this alone cannot turn the residual failure into an accepted correction.

Private evidence includes the protected backup manifest, deployment hash check,
`stationary-ui-export.json`, `stationary-ui-summary.json`, exact-pair isolated
probe JSON, actual service timing log, `deployed-map-view.png` and
`deployed-observation-controls.png`. Raw maps, source backups and credentials are not included in Git.

Post-deployment documentation validation: full Python 2,417 tests passed
(3 skipped) and related JavaScript 26 passed; no additional source changes
or service restarts were performed during this evidence update.

## Follow-up implementation — isolated numerical worker (not deployed)

The original one-hour FAST-LIO run is now over. Read-only inspection at
15:14:56 KST found its unit inactive/dead, MainPID=0, Result=success. Dashboard
PID 138038 remained active and the new worker file was absent. No additional
restart, estimator start or product deployment was performed for this follow-up.
The previous 119.6 s display record remains historical stationary evidence;
there is no claim of a fresh FAST-LIO pose after the estimator exits.

The API now selects one private numerical subprocess per dashboard. It imports
no ROS runtime, inherits only its private IPC descriptor, and opens no network
listener. Reference preparation can survive an over-budget attempt; scan work
cannot. Every retry selects fresh parent inputs. The parent still enforces the
single-flight lock, 1 Hz admission, unchanged 600 ms elapsed deadline, complete
reference, exact FAST-LIO source pairing and completion map/source/evidence/
freshness checks. The child receives that same absolute monotonic deadline.
Partial/blocked IPC writes are bounded. A timed-out solve is terminated and
reaped, and request/map identifiers reject a mismatched response. Shutdown
closes the worker after the existing control shutdown boundary; dataset close
retains its original ordering before mapping/ROS cleanup.

Inline diagnostics and the child call the same extracted numerical function.
Correspondences, iterations, convergence, residual/overlap/geometry policies
and the displayed response contract are unchanged. No surface-based candidate,
point exclusion, threshold change or historical timestamp refresh was added to
the product. No dependency, ROS/OS or FAST-LIO configuration was changed.

Five exact-source-stamp cloud/IMU pairs were passively copied while the original
observer was still running, covering 1792735459645022869–1792735463746481180 ns.
Historical local fits retain 431–435 uniformly sampled query points and the
41,073-point normalized new reference. RMSE spans 0.159028–0.164699 m, overlap
0.997680–1.0; two fits also fail convergence at the unchanged 40 iterations.
Two diagnostic surface-based initializations on the first pair, rescored by
unchanged point-to-point ICP, converge near 0.160889 m and remain rejected.
They are not installed algorithms or live corrections.

On the first pair, 0–2 m returns account for 22.3% of squared error, 2–5 m for
39.5%, and 5–10 m for 38.2%. Removing near returns would not explain away the
remaining approximately 15 cm range-bin residuals. Several largest errors
match query returns around z=0.52–0.55 m to saved neighbours near z=-0.03 m.
These spatial mismatches require further scene/geometry investigation; they do
not prove calibration error, moving objects or map sparsity as a sole cause.
No returns were excluded from qualification.

A local historical benchmark with an additional Python CPU-contention thread
compared identical inputs and policies. Inline work exceeded its deadline at
605.36 ms; the prepared subprocess returned in 472.29 ms (440.98 ms numerical),
with the identical RMSE 0.164698838 m and REJECTED/HIGH_RESIDUAL. This supports
the process-isolation change; it is not installed-dashboard latency evidence.

A five-file deployment candidate preserves the actual installed overlays:
`app.py`, `application/runtime.py`, `api/routers/observation_alignment.py`,
`relocalization/observation_alignment.py`, and new
`relocalization/observation_worker.py`. Private per-file before/after hashes,
four original-file backups, new-file absence/guarded removal, atomic replacement
and guarded rollback are prepared. A disposable local install/rollback rehearsal
passed, including refusing to overwrite subsequent edits. Deployment needs one
additional dashboard restart and a new isolated, maximum-one-hour observation
FAST-LIO run because both previously approved restarts and the original run
have been consumed. Original map/config/mapping logs remain protected.

Validation details are recorded after the final runs below. The browser fixture
previously reanchored after only one of two independent source replacements;
it now delivers and observes both replacements before reanchoring. The product
continues to invalidate an anchor on either source change. Architecture size
limits and dataset shutdown-order checks remain enforced through the extracted
runtime cleanup helper.

Final follow-up software validation: Python 2,427 tests passed (3 skipped),
related JavaScript 26 passed, observation browser 7 passed, and 49 targeted
Python tests passed against the exact merged installed-source candidate. Ten
new worker/lifecycle tests cover numerical equivalence, reuse, preparation,
backpressure, death, timeout/reaping, stale/mismatched responses, completion
fences and cleanup failure. Full-suite intermediate failures identified the
app size ceiling and a source-location-dependent shutdown assertion; cleanup
was extracted and the assertion now follows that function without relaxing
shutdown ordering or size limits. No device performance or localization pass
is inferred from these software results.

A further finite historical comparison perturbed the first fit's XY seed by
±0.3 m in eight directions. All converged, with RMSE 0.160892–0.164749 m and
unchanged overlap scoring; all remain rejected. The comparison is diagnostic
only and does not add multi-start search to the live path.


## Approved isolated-worker execution — 15:23–15:33 KST

The operator explicitly approved main publication, the five-file deployment,
one additional dashboard restart and one new maximum-one-hour observation run.
Public main source commit `2b3b441` was pushed, then its overlay-preserving
candidate was installed under private manifest
`fb118dca394a72385a84f23eeffb17cb73451e15577daf9cad93dee7cd13b7dd`.
Robot Git base remains `d7807de8f15fb457942039bb90ab41cf68d384c6`; this is a
selective installation with retained local overlays, not a public-main checkout.

Dashboard restarted once to PID 183435, active with NRestarts=0. Its LiDAR preview
recovered; the control bridge remained inactive/disabled. Fresh ownership
readback reported no busy or unknown component before application. All five
installed hashes and all four original backups matched. The original map,
FAST-LIO config and original mapping log hash remained unchanged. The new
numerical worker was observed as an actual child of the dashboard process.
No motion, posture, Nav2 or operational TF application was performed.

`robot-scope-same-start-20261023-fix2.service` started at **15:24:15 KST**, with
wrapper PID 184366 and estimator PID 184424. RuntimeMaxSec remains 3600, so the
new run is expected to end around **16:24:15 KST**. Its Log/PCD directories are
separately bind-mounted and TF/map/path outputs remain observation-only. The
old run had already ended; no duplicate estimator was started.

The same pinned new map, six-dimensional approximate start prior and existing
Maps observation controls were used. Current IMU anchor source stamp is
1792736734047701358 ns. The final UI export contains 400 samples spanning
119.600332022 s, 394 distinct nondecreasing pose source stamps, alignment
revision 0, unchanged map revision and accepted_registration=false. State stays
SAME_START_ODOMETRY_ESTIMATE through failed correction attempts. This verifies
stationary display continuity, not independent pose accuracy or manual motion.

The final exported **actual dashboard** response used an exact FAST-LIO
cloud/pose source-stamp pair and returned REJECTED/HIGH_RESIDUAL:

- point-to-point RMSE **0.161318901 m**;
- overlap **0.997674419**, 429/430 inliers;
- converged in 30 iterations;
- numerical time **135.84 ms**, total worker time **183.74 ms**;
- both original 5 cm and provisional 10 cm assessments fail.

The captured 15:25:30–15:28:42 service interval contains 162 attempts, 92
numerically completed HTTP 200 responses and 70 HTTP 409 refusals. HTTP 200
means a numerical assessment was returned, not an accepted map correction.
Completed worker elapsed time spans 181.18–562.28 ms, median **223.06 ms**;
whole dispatch-to-response time spans 194.76–662.38 ms, median **284.58 ms**.
The latter includes scheduling/serialization outside the existing worker budget.
Completed isolated numerical exchange time has median 176.68 ms. Cold catalogue
admission took 929.31 ms and correctly failed. Some warm attempts still fail
because of admission/pairing, numerical deadline or catalogue-lock contention
at completion. Those refusals remain; no deadline was raised or failure hidden.

Repeated numerical alignment was turned OFF after the recorded window; current
inputs and same-start IMU display remain ON for the bounded observer lifetime.
Actual screenshots are retained privately as `fix-2/deployed-map-view.png` and
`fix-2/deployed-observation-controls.png`, alongside the full UI exports, service
log, timing summary and installation hash verification.

A subsequent six-second-maximum passive subscription probe retained three
current registered-cloud/pose exact pairs and nearby existing converted raw
scans, then exited normally. It changed no producer, parameter or selected
source. Historical raw comparison used the configured extrinsic and a stationary
pose approximation; raw scan-time/deskew qualification was not claimed. With the
same final point-to-point scoring, 500 strided raw samples give RMSE
0.145473–0.146825 m and overlap 0.964–0.968, also rejected. Simply bypassing the
published filtered cloud therefore did not demonstrate a qualifying alternative.
No raw diagnostic result was applied to the display.

The mapping log shows online extrinsic estimates varied (roll roughly -1.43°
to 0°, pitch -0.09° to 1.12°, yaw 89.68° to 90.08°), whereas the stopped new
run remains near its configured start values. A constant extrinsic difference
can be absorbed by rigid alignment; this variation alone does not prove the
residual's cause. Spatial missing support, scene changes, accumulated-map
geometry and sampling remain distinct hypotheses. Surface seeds, eight local
XY seeds and raw diagnostics all preserve their failed original scores.

The computational blocker is substantially reduced and actual dashboard
numerical results are now visible. D (qualifying saved-map correction), full F,
G (manual movement) and absolute accuracy remain incomplete. The next task is
to resolve the observed map/scan shape mismatch with the operator's scene-change
information and preserved inputs, while retaining existing scoring and the
working same-start display. No claim of completed saved-map localization is made.

Closeout readback at 15:35:59 KST: dashboard PID 183435 and renewed observer
PID 184366 remain active, NRestarts=0; numerical child PID 189025 is retained
idle after repeated fitting was disabled. Control bridge remains inactive and
disabled. Closeout documentation checks: full Python 2,427 tests passed
(3 skipped), related JavaScript 26 passed. No further deployment or restart was
performed while recording these results.
