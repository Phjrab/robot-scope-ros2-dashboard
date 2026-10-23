# Same-start saved-map observation — 2026-10-23

The existing Maps observation panel can now track the installed FAST-LIO IMU
state against a pinned saved 3D map. This is display-only: no map→odom TF,
initialpose, goal, control output or body-extrinsic claim is added.

**Current result after manual movement:** stationary saved-map correction and
the 120-second stationary display remain demonstrated. Three operator-controlled
movement attempts have now been recorded, but continuous moving UI display has
**not passed**. The first two attempts encountered stale browser input while
passive device WebSockets continued receiving. The approved three-file transport
recovery patch was installed without restarting services. After reload, native
inputs were fresh, but the UI subsequently cleared its anchor with `MAP_CHANGED`
while the same map ID/revision was displayed. A same-revision reload defect was
then reproduced and fixed locally; this additional change is **not deployed**.
The one-hour observer has ended; final logs are retained locally. See the manual
movement section below for measured results and the remaining device check.

**Earlier standing result:** after the operator restored the robot to standing at
the reported mapping-start position and height, the existing dashboard accepted
and applied an actual saved-map correction under the unchanged provisional
10 cm policy. The exported fit has RMSE **0.078076 m**, overlap **1.0**, and
total worker time **94.50 ms**; the original 5 cm policy still rejects it.
A subsequent **120.0 s / 399-sample** stationary window retains the correction
and advances original IMU timestamps. A–F are demonstrated for this provisional,
subscription/graph-evidence IMU observation path. At that checkpoint manual
movement and absolute accuracy were unmeasured. Source `2b3b441` was installed;
that checkpoint performed no deployment or dashboard restart. The run started
at **16:47:27 KST**, with a one-hour maximum lifetime. Earlier failed runs below
are historical; the operator later identified their posture as seated. See the
final standing-run section for current evidence and remaining limitations.

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

## Approved standing run — 16:47 KST onward

The operator reported that the previous run was seated, powered the robot off
for charging, and then restored it to standing stationary at the reported
mapping-start position and height. A passive three-scan diagnostic placed a
floor-like plane near IMU z=-0.4837 m, versus approximately -0.2343 m in the
seated capture and -0.4929 m in the retained map prefix. These fitted planes
support the height difference; their physical-ground interpretation is not
independently measured. Posture/height is a material changed condition, not a
controlled proof of the entire earlier residual's cause.

After explicit approval, one isolated observation FAST-LIO run started under
`robot-scope-same-start-20261023-standing-1640.service` at **16:47:27 KST**.
Its wrapper PID is 12056, estimator PID 12115, and RuntimeMaxSec is 3600
(expected expiry **17:47:27 KST**). No competing estimator was present before
launch. Existing settings and installed code were reused, with separate private
Log/PCD bind mounts. Actual node/parameter readback confirms observation-only TF,
0.5 m filtering, online extrinsic estimation, and disabled map/path/PCD saving.
The dashboard remains the reboot-started PID 963, active with NRestarts=0;
this validation performed no deployment or dashboard restart.

The same 41,073-point map and approximate six-dimensional IMU start prior were
retained. The previous connection correctly became invalid after the reboot.
Fresh standing-session input was connected through the existing Maps controls,
using subscription/graph evidence mode. Early cold catalogue/reference work
still failed the unchanged 600 ms deadline, and an initial stale input cleared
the anchor. After warm, fresh input was available, the operator-provided prior
was connected again. Subsequent actual dashboard corrections were applied.
There is no claim of uninterrupted display from the first cold attempt.

The actual UI export at **16:56:18 KST** records
`MAP_CORRECTED_ESTIMATE_ACCURACY_UNVERIFIED` and
`anchor.accepted_registration=true`. Its backend response is
`CANDIDATE_SOURCE_UNVERIFIED`, qualified as a provisional observation hypothesis:

- Point-to-point RMSE **0.078075653 m**, overlap **1.0**, 428/428 inliers.
- Converged in 5 iterations; numerical time **34.73 ms**, total worker time
  **94.50 ms**, correspondence radius unchanged at 0.75 m.
- Provisional 10 cm assessment passes; original 5 cm assessment remains
  `REJECTED / HIGH_RESIDUAL`.
- Cloud and pose retain the identical original stamp
  **1792742177876285552 ns**, `FASTLIO_OUTPUT_STAMP_EXACT`, source delta 0 ns.
  Their host receipt delta is 27.50 ms. This does not establish physical sensor
  clock synchronization or deskew accuracy.
- Both ROS graphs identify one `laser_mapping` publisher. Installed Humble
  lacks per-message publisher evidence; source, body extrinsic, Go2 body pose,
  and independent absolute accuracy remain explicitly unverified.

The recorded timing snapshot contains 292 attempts: 148 completed numerical
HTTP 200 assessments and 144 HTTP 409 refusals. A 200 response alone is not an
accepted correction. Completed worker time is 65.47–583.86 ms, median
**108.80 ms**; dispatch-to-response time is 84.07–677.90 ms, median
**175.00 ms**. Cold loading, admission/pairing, completion and rate-limit
refusals remain visible. An exported `RATE_LIMIT_1HZ` state retains an already
accepted correction and continues current odometry. No score, deadline or
freshness gate was relaxed.

Repeated fitting was temporarily disabled at 16:56:37 KST to measure a single
corrected display segment. The **16:58:37 KST** export contains **399 samples**
over **120.000757 s** of source time (119.974 s browser time), **392 distinct
nondecreasing pose stamps**, and one retained alignment revision, 142. Maximum
sample interval is 642 ms and maximum pose source-stamp gap is 0.601 s. The
map revision/source identities are unchanged and accepted correction stamp
1792742196774750232 ns is retained. Median displayed IMU XYZ is approximately
(-0.31468, -0.11202, +0.02455) m, yaw about +8.6°. Maximum distance from the
stationary window's median position is **3.56 mm**. This is display stability,
not absolute accuracy; the prior and roughly 0.33 m / 8.6° correction are not
independent ground truth. Accepted corrections begin separate trail segments;
this window specifically measures propagation of one retained correction.

At this checkpoint the operator chose stationary validation; manual-motion
validation was **NOT_RUN** (superseded by the later attempts below). Repeated regional fitting was re-enabled for
the remaining approved observer lifetime, with live inputs and corrected IMU
display kept on. At expiry, stale inputs must stop being represented as current;
this is a bounded validation run, not a persistent localization service.
After re-enabling, the 17:02:31 KST UI export again records an applied candidate:
RMSE 0.076627273 m, overlap 1.0, total worker time 83.2 ms, with the original
5 cm rejection preserved.

Closeout hashes match all five installed Python files from the `2b3b441`
deployment manifest and the installed observation launcher. Original map,
FAST-LIO configuration and original mapping log hashes remain unchanged.
Robot Git base remains `d7807de8f15fb457942039bb90ab41cf68d384c6` plus retained
overlays/selective patches. `robot-scope-control-bridge.service` remains
inactive, disabled, MainPID=0. No motion, posture, Nav2, initialpose, or
operational TF application occurred.

Closeout software checks: full Python **2,427 tests passed (3 skipped)**,
related JavaScript **26 passed**, observation browser **7 passed**. This
publication updates evidence only. Private `standing-1640/` evidence contains
the accepted and rate-limit UI exports, continuity export/summary, timing log,
session manifest, preservation readback, and actual screenshots
`standing-map-view.png` and `standing-accepted-controls.png`; raw data remains
outside Git. The next verification is operator-controlled short movement and
turning when available, within an authorized observation run. Independent
absolute accuracy and Go2 body-frame calibration remain separate unmeasured
quantities.

## Manual movement and transport recovery, 17:16–17:47 KST

The operator subsequently made three manual movement attempts. No movement,
posture, control bridge, Nav2, initialpose or operational TF command was sent by
this task. The same standing observer/source generation and pinned map were
used throughout. These are observation attempts, not a passing moving-display
acceptance test.

1. The operator reported approximately 0.5 m straight movement. Browser cloud
   receipt became stale for roughly 13 seconds and invalidated the connection.
   At the arrival, a fresh same-generation native pose was combined with the
   historical correction as an explicitly approximate seed. A new actual
   registration at **17:21:31** was applied: RMSE **0.065930752 m**, overlap 1.0,
   406 inliers, 8 iterations, numerical time 40.75 ms, total 95.02 ms. Provisional
   10 cm passed; original 5 cm remained rejected. This arrival correction does
   not recover the missing continuous moving UI segment.
2. The operator then reported another short straight movement and left turn.
   Passive device WebSocket evidence contains 937 pose and 514 cloud samples in
   the analyzed 109.90-second segment, nondecreasing original source stamps and
   maximum receipt gaps of 0.460/0.532 s. Historical native odometry propagated
   through the fixed baseline map transform measures approximately **0.447 m**
   displacement and **+27.09°** yaw. Browser input became stale for about 19.7 s
   and invalidated its trail. These numbers are estimator observations, not
   independent ground truth or a recovered UI trail.
3. After the approved transport patch and browser reload, the operator made one
   more short movement/turn. A five-minute passive recording completed with
   **2,465 pose / 1,418 cloud** messages, nondecreasing source stamps and maximum
   receipt gaps **0.523/0.652 s**. Initial/final native pose medians differ by
   approximately **0.499 m / −29.82° yaw**. The operator confirmed completion
   without specifying the final direction; the sign here is the estimator's
   convention, not a ground-truth turn measurement.

Before the third attempt, the approximate arrival seed was XYZ
(0.881757, 0.049819, 0.037956) m and RPY (−0.774667, −0.546795, 39.190650) degrees.
It came from the second-motion baseline's historical `T_map_odom` multiplied by
a fresh matching observer/epoch/subscription `T_odom_imu`; the original mapping
start was not reused as the robot's current position. Fresh local registration
was attempted. The retained **17:43:31** assessment has RMSE **0.058632607 m**,
overlap 1.0 and total time **220.21 ms**, but reached 40 iterations without
convergence: **REJECTED / NOT_CONVERGED**. It was not applied despite passing
the provisional residual comparison. The UI remained an approximate odometry
estimate at that checkpoint.

At **17:45:26**, after the third movement, the visible status was `MAP_CHANGED`
with no current map pose or trail. Cloud and pose receipt ages were **116/85 ms**
and the source subscriptions were unchanged. At 17:46:45 the displayed map still
had the pinned ID, revision and 41,073 points. Thus the last failure is distinct
from the earlier stale-input failures. Continuous browser reception across the
entire movement was not instrumented, and the precise live event that triggered
the map reload has not been proven.

### Installed transport patch and local follow-up

Explicit approval covered `app.js`, `pointcloud_transport.js`, new
`socket_watchdog.js`, and browser reload only. The patch reconnects silent pose
and cloud sockets, fences callbacks from replaced sockets, and drains pending
binary cloud frames with a 100 ms timer fallback when animation frames pause.
It changes no source timestamps, freshness, convergence, residual or deadline
gate. The initial receive wait is 3 seconds, subsequent silence limit 600 ms.
Transport recovery alone did not complete moving UI validation.

The installation bundle was
`transport-recovery-20261023-1736`, archive SHA256
`1ea13146c34c5fab65e6163ab28f8783b5edffbebebd7fd79fced24c52d1531c`.
Original files were backed up; guarded install/rollback was rehearsed. Installed
and HTTP-served hashes matched:

| File | Installed SHA256 |
| --- | --- |
| `socket_watchdog.js` | `de5a16f92a994d43719fb095aac384b79f5b70714a110e21d2d4333e8271fcfe` |
| `pointcloud_transport.js` | `102be6e04099f926ece28867c03dd97fd21cc19f06ddbae372e557bdd96c1803` |
| `app.js` with retained device overlays | `3dc4b8464492580502e0110432a81c0471defc25127d8fff61e71125206e516a` |

Dashboard PID 963 and observer wrapper PID 12056 were unchanged after deployment.
Original map/config hashes matched. The robot Git base remains `d7807de8` with
retained overlays and selective patches; it is not the public main checkout.

Offline browser reproduction then demonstrated that a completed mapping-status
readback can clear the display cache and reload the same selected map. During
the asynchronous reload, `selectSavedMap` cleared the loaded reference; live
render ticks interpreted the temporary absence as a map change and discarded
the accepted connection. The added regression failed on that path before the
fix. The local follow-up retains the already-loaded reference only for the same
map ID and nonempty matching revision. A real revision change still clears it
immediately, and existing source/stale gates remain unchanged. The regression
now passes for both same-revision retention and changed-revision invalidation.
This reproduces a plausible cause of the observed failure, not proof of the
exact live trigger. **This additional app.js change has not been deployed.**
The private `reload-fix/` candidate merges only that follow-up into the installed
app variant. Its SHA256 is
`3c899d975bb14ec5393b1e3ca507de3f985c5c15a7b91bb042ca7371a0af8600`;
syntax and guarded install/restore rehearsal passed against a temporary local
checkout. No further robot write or restart was performed.

Validation after the follow-up: full Python 2,427 tests (3 skipped), all JS 601
tests, and 8 observation browser tests. The newly added transport unit coverage
includes silent sockets, late callbacks, suspended animation frames and demand
release. The full JS run initially hit the existing application line-count
limit after the new comment; the comment was shortened without changing code
behavior or the test limit, then the suite was rerun.
An initial final Python invocation used the system interpreter without FastAPI
and Pydantic (34 import errors); the full suite was rerun in the existing project
virtual environment. No dependency installation or test exclusion was used.

### End of authorized run and retained evidence

The original 17:47:27 maximum end time was not extended. At **17:47:35**, the
observer unit was inactive/dead, MainPID=0, Result=success. Dashboard PID 963
remained active; the control bridge was inactive/disabled, MainPID=0. Ownership
readback showed no busy components. Later source disappearance/change hid the
current pose as required; no old correction was reused as a current result.

Private `manual-motion-1716/` evidence includes the accepted first-arrival UI
export, second-motion baseline and historical motion summary, five-minute raw
WebSocket metadata recordings, `post-fix-arrival-prior.json`, rejected
`post-fix-ui-initial.json`, `post-fix-final-dom.json`, `post-fix-motion-summary.json`,
deployment manifests/backups, expiry readback, and `observer-log-final.tar`
(six entries, 10,482,825 uncompressed bytes). Actual device screenshots include
`post-fix-arrival-screen.png` and `expired-controls.png`; raw evidence stays
outside Git. The operator was told the robot could be shut down normally after
the observer exited and final logs were copied.

Next device step: apply the tested same-revision reload fix under a new explicit
deployment/run approval, then verify one continuous manually moved UI segment.
Until then, A–F retain their earlier stationary evidence; G is **attempted but
not passed for continuous UI display**. Absolute accuracy and Go2 body-frame
calibration remain unmeasured.
