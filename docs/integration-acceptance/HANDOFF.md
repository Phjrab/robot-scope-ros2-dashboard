# Local-only Stop, map view and calibration diagnostics — 2026-10-18

Read [OFFLINE_FOLLOWUP_20261018.md](OFFLINE_FOLLOWUP_20261018.md) first. From local
main `a79c67a`, preserved changes now distinguish Stop acceptance/cleanup/unconfirmed
readback/confirmed IDLE, fence stale responses, add display-only main-area FIT and
camera centering, and retain point-level calibration diagnostics on HTTP 422.
Original full FIT, cloud/export inputs and calibration thresholds are unchanged.
No push, release, robot access, service restart, deployment or motion occurred.
The last installed `40276a5` and IDLE/free/bridge-OFF observations below are historical.

Existing real October 17 samples were replayed through the actual local API and
Settings panel. Both nearby six-point selections pass neighborhood depth but have
only 4/6 plane inliers: angles and analysis export remain blocked. No new capture
or pitch adjustment occurred. A seed-by-seed SE3 inspection reuses existing tools:
three synthetic seeds produced rejection/candidate/rejection, while the recorded
manifest remains BLOCKED on provenance. Global relocalization/operating use are NOT_RUN.

Python 2,275 (3 skip), JS 452, and 150 unique browser cases passed. The initial
browser run passed 136; its 14 fixture-contract failures passed after fixture-only
correction, without repeating the whole suite. See the report for environment
mistakes, optional plot coverage, exact evidence and remaining field checks.
Wall duplication, absolute accuracy/body pose and actual Stop/camera behavior of
this new source remain unverified. Closeout is local only; no background robot
work or automatic next session is authorized or scheduled.

# Saved depth → deployed native Settings observation — 2026-10-17

Read [MOUNT_CALIBRATION_SETTINGS.md](MOUNT_CALIBRATION_SETTINGS.md) first for this
follow-up. Source `40276a51b2e08c77732317a856cc879cc23e1ef6` retains the existing `eb0a9c6` Settings UI and
`78e23ce` collector. The existing Settings panel now lists/selects/imports saved
samples with GET-only access, displays matching original IR pixels, and retains
original timestamps, frame counters and artifact provenance in relative analysis
exports. No duplicate camera controls or angle algorithm were added.

Exact original JSON/image downloads are verified against their stored hashes and
catalogue receipt. Pair/intrinsics/zero-distortion/identity-alignment evidence is
checked, the 1 ms gate stays unchanged, and changed catalogue entries or late
responses cannot restore previous results. Historical samples are not expired
merely by age; same-exposure replay is rejected with hardware clock epochs scoped
to their capture session when available. New exports include capture_session_id.

Exact-source CI [39024766108](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/39024766108)
passed in both Ubuntu/Python jobs. Under the user's bundled approval, source/config/
binding backups preceded deployment and dashboard/broker restart. The robot reached
clean `40276a5` at 10:35:54Z; all 1,345 source hashes matched. SDK 2.55.1 and its
broker-private binding, Isaac image, configuration and operational DDS were retained.
The earlier SDK-unavailable note is superseded by actual capture evidence. GitHub
publication, this hardware installation, and the later documentation closeout are
distinct; the installed runtime remains `40276a5`.

Before deployment, the old real archived sample was loaded into the product Settings panel on a local
no-hardware harness using the actual routers/store: IR display, original 640×480
pixel selection, six picks, metadata and one-sample estimate/export blocking passed.
No actual relative angle is claimed. A separate synthetic demo traversed the real
Python estimate/export APIs and returned RELATIVE_ONLY with 0/+9.999446/−8.000435°.
Whole Python 2,266 (2 skip), JavaScript 434, related browser 18, ruff/mypy/source
secret/diff checks passed. Private sensor evidence stays outside Git.

The user then skipped camera adjustment. Two fresh stationary **same-angle**
captures were saved: `0f301ed2870243e5bb0a6bac68dc5b94` at 10:36:36.616828Z and
`c92c6700bc5a4125b9bf3d9408d5fe8e` at 10:37:03.575887Z. Each 640×480 IR1/Z16
capture passed full raw/PNG/optical-Z(m) JSON and ZIP hash correspondence; valid
depth was 95.1712% / 95.2738%, source skew 0 ms. Actual SDK intrinsics/zero
distortion/identity extrinsics support same-pixel correspondence. The recorded
camera_info.json is derived from SDK observations, not an observed ROS CameraInfo
message. Body attitude is absent.

The deployed Settings page successfully listed/imported the two new captures,
displayed original IR pixels/metadata and accepted six native-coordinate picks.
The first visible-wall selection failed the existing neighborhood gate (only one
accepted point). A nearby selection, chosen solely by the unchanged neighborhood
gate and pixel distance, then failed `no reliable planar consensus`. Both deployed
estimate and export APIs returned 422; the UI kept result export disabled. Thus
**actual collection/import/picking passed, but relative-angle analysis and analysis
JSON export are BLOCKED by these samples' selected-plane quality**. Raw ZIP and
compatibility JSON exports passed. No actual angle or body calibration is claimed,
and no numerical/freshness/synchronization threshold was relaxed.

After depth cleanup, an explicit Stereo tracking-only session
`8c083c88e3914bf78c804efd227e6b40` (generation 3) reached TRACKING at 10:42:09.730Z.
The guard requested Stop at session age 60.546 s; clean IDLE/camera release followed
at 10:43:08.102Z (65.807 s from creation). Native IMU fusion, mapping and both TF
publish flags were false. This proves sequential mode return, not simultaneous
Stereo+depth, unchanged performance or full mapping regression. No new FPS/load/
WebSocket/display-latency measurement was made in this return window.

The final 10:45:54.954Z read-only check found clean installed `40276a5`, IDLE,
known-free camera with a fresh independent owner probe, bridge inactive/disabled,
unchanged configs/environment/entry/binding, unchanged map/package revisions and
all prior sample bytes. Only the two approved samples were added. No motion,
posture, ARM, bridge activation, operational TF, initialpose or goal was sent.
The approved window is finished; no camera session is left running or scheduled.

Private evidence is under `robot-scope-hardware-validation-private/mount-settings-20261017/`:
`deployment-result.json`, `actual-depth-contract-report.json`, both `depth-repeat-*`
directories, `actual-analysis-api-report.json`, `replay_actual_analysis.py`,
`settings-actual-wall-quality-blocked.png`, `stereo-return/`, and `final-runtime.json`.
The replay uses the same stored files/picks/provenance as the UI; it is not a claim
of intercepted browser request bytes. Sensor files and images remain outside Git.

Next minimum field work, when the user chooses to resume, is a stationary repeat
with a nearer, unobstructed textured wall that supplies broadly distributed stable
depth. Any robot repositioning requires a separate explicit manual-control scope;
do not send robot commands to arrange the scene. First obtain reliable plane
quality, then let the user adjust pitch only between released sessions and compare
new captures. The user skipped that adjustment now. Keep the bridge OFF. Changed-
angle validation, independent accuracy, body attitude/absolute extrinsics and
native SLAM wall duplication/trajectory jumps remain separate and unqualified.

# Earlier stationary depth collection on 78e23ce — 2026-10-17

Read [DEPTH_CAPTURE.md](DEPTH_CAPTURE.md) and [validation](DEPTH_CAPTURE_VALIDATION.json)
for the collection/export contract, actual evidence and limits. The user approved
exact source `78e23ce9edb59790a665055dfd23f230be018b43` and the current seated/fixed
conditions. Exact-candidate CI passed; clean deployment matched 1,335 source hashes.
This completed window supersedes the initial software-only/no-sample depth note.

The matching SDK 2.55.1 Python extension was extracted from an existing preserved
source image and exposed through broker-only private PYTHONPATH. No build, pip,
Isaac/SDK upgrade or device calibration write occurred. Existing dashboard DDS,
Stereo config, native library/image and protected data were preserved. Only the
separate private depth config and reviewed broker entry changed; dashboard/broker
restarted under the approval. Shared session/camera/domain ownership still applies.

One actual IR1+Z16 sample `a58f3549f327424f8b6241d89783974f` is stored in the robot's
`multi-slam/depth-samples/` directory. Actual D435I identity/firmware/profiles were
retained; 640×480×30 nominal profiles have zero source-time skew in global_time.
All 307,200 pixels of exported optical-Z JSON/PNGs were checked against raw data;
293,270 valid nonzero values and 13,930 nulls match exactly. Equal zero-distortion
intrinsics and identity extrinsics qualify same-pixel correspondence. Body attitude
is absent and body level is not assumed. The real panel selected/displayed the
sample; HTTP ZIP/JSON/image rereads passed, but native browser file-save completion
is unverified because its download wait timed out.

After depth cleanup an explicit 60-second Stereo tracking window confirmed actual
IR1/IR2 profiles and live `enable_depth=false`, `enable_sync=false`. Six retained
matched pairs had zero skew. 159 active WebSocket observations had image/camera
pose/tracking/current observations/trajectory; 157 had overlay. This is a return-to-
Stereo observation, not a no-regression claim: 93 native interframe-gap warnings,
25 libusb warnings and widening timestamp-cache spans were recorded. Whole-Jetson
CPU/GPU/RAM samples exist, but no matched pre/post baseline, sustained IR FPS,
USB-throughput measurement or calibrated display-latency result exists. Full
current ROS CameraInfo matrices/static-TF equality remain unrecorded; actual SDK
calibration and WebSocket intrinsics are available.

The windows completed cleanup (depth 10.56 s; Stereo 65.59 s from start, guard stop
at 60.22 s). Final state is IDLE, camera free/known, bridge OFF and disabled. No motion,
posture command, operating TF application, initialpose or goal occurred. Keep the
bridge OFF. The approved bounded window is complete; no next session is scheduled.
The final 10:03:00Z check stopped the observation-created domain 71 CLI daemon and
confirmed that only the existing broker Python remained in the camera container.
Deployed source stayed clean; original config hashes and package revisions matched. After the window,
the UI showed Go2 direct ROS disconnected at 19:01 KST; dashboard/API and the saved
sample still served. Its cause is unqualified, so do not report the overall robot
connection as currently healthy.

Next minimum work is operator-directed multi-angle collection with fresh stationary
confirmation per sample and use of the independently developed point-selection/
pitch UI. No angle solver or duplicate calibration UI was added here. Independent
accuracy, body extrinsics and native SLAM wall/trajectory diagnosis remain separate;
depth collection does not resolve those problems. Same-device concurrent
Stereo+depth is deliberately unsupported. Source is unchanged after its passing
software/CI checks; this closeout only records hardware evidence.

During closeout, concurrent commit `eb0a9c67c51b3c2805a42843baafe30ff5deb36e`
added Settings import/point-selection calibration. Its passing CI and code were
preserved in the documentation merge; no duplicate solver/UI was added here.
That newer Settings integration was **not deployed in this camera window**.
The actual device/evidence qualification remains pinned to `78e23ce`; validation
source hashes identify that deployed revision rather than the newer main.

# Latest manual Stereo observation — 2026-10-17

Read [SLAM_MANUAL_OBSERVATION.md](SLAM_MANUAL_OBSERVATION.md) and its JSON first.
The approved single session on unchanged `91f9006` is complete, including operator
remote movement/rotation. Codex sent no motion command. Real image/camera pose/
tracking were received; delivered map peaked at 17,027 points. At 10K–15K points,
receipt gaps had median 1.872 s; sampled displayed image age during rotation had
median about 1.25 s and maximum about 2.66 s, conditional on host-clock mapping.
These are not camera FPS or calibrated glass-to-glass latency.
Rotation return camera self-consistency was 0.139 m / 6.77 degrees with unmeasured
physical return error, not absolute accuracy. Rare distant map points dominate
full FIT; duplicated-wall cause and calibration repair remain unqualified.
All resource GET observations timed out, so no CPU/GPU bottleneck is established.
Dashboard Stop completed cleanup, but delayed readback left an old timeout label.
Final API and live owner probe confirm IDLE, camera free, bridge inactive/disabled;
all four Stereo configs and deployed implementation are unchanged. Keep bridge OFF.
No additional session, deployment, movement or background work is scheduled.

# Earlier deployment and stationary observation — 2026-10-17

Candidate `91f9006de6162d9e48f635f5f79a76e014950fd8` is deployed with both Linux
CI jobs passed. Read [SLAM_DISPLAY_RUNTIME.md](SLAM_DISPLAY_RUNTIME.md) and its
JSON record before the historical offline result below. One approved stationary
observation received 176 messages in 60.122 seconds; median receipt gap 0.334 s.
Real image/camera pose/tracking and overlays were displayed; a 158-point global
map used one full transfer plus 38 references. This is not a large-map FPS claim.
The guard stopped at session age 90.786 s and cleanup completed at 96.275 s.
SLAM is IDLE, camera free, source clean, and the control bridge is now confirmed
inactive AND systemd disabled after the user's administrator step. Keep it OFF.
No movement, operating TF/initialpose/goal, reuse or second camera window occurred.
Existing UI, environment/stereo configs and protected map metadata/revisions were
preserved. No further device action or background continuation is scheduled.

# Historical offline display optimization — 2026-10-16

The user authorized mapping-display software optimization and confirmed the
robot is powered OFF. No new device access, deployment or runtime observation
occurred. Read [SLAM_DISPLAY_PERFORMANCE.md](SLAM_DISPLAY_PERFORMANCE.md) and its
validation JSON first. Unchanged geometry references, bounded latest display
work and shorter callback lock sections passed hardware-free validation.
The frozen real-sample replay reduced repeated JSON bytes93.54%; actual robot
FPS/latency is unmeasured. All device work remains deferred, bridge restoration
excluded, and no background continuation is scheduled. The old3986a75 deployment
pack does not include these changes. The user's duplicated-wall report remains
an unqualified geometry/rotation-tracking issue, separate from display speed.

# Previous native/precision follow-up — 2026-10-16

The user reopened remaining non-driving work and confirmed that independent
truth/extrinsic measurements do not exist yet. Reviewed software and preparation
are in [NATIVE_PRECISION_FOLLOWUP.md](NATIVE_PRECISION_FOLLOWUP.md) and
[NATIVE_PRECISION_VALIDATION.json](NATIVE_PRECISION_VALIDATION.json).
Read this newer record before the historical acceptance below. Policy publication
does not authorize a true enforcement scope; precision/body claims remain blocked
on actual measurements. The control bridge must remain OFF. The user selected
**software-only closeout; defer device observation** on 2026-10-16. The prepared
deployment/camera/native-consumer window is not authorized to run; the earlier
operating localization window is not authorized to repeat.
Candidate3986a75 is published and its two Linux CI jobs passed. Separate copied-DB
CPU extraction observed13993 landmarks/175 keyframes/178 edges; retained
completeness and pose direction remain unqualified. The grouped approval request
is resolved as deferred, not pending; no new service/camera/native-consumer window
has started. Last readback
12:38:15Z still shows backendcdebee4 with preserved published UI, SLAM IDLE,
camera free and bridgeOFF. This is historical readback, not a new device check.
Software closeout reuses the exact implementation's passing test/CI evidence;
only documentation changed. No device action or background continuation is
scheduled. See the newer follow-up for source and binary hashes.

# Previous non-driving results — 2026-10-16

Actual clean deployment is cdebee4; software-only collision-mask source is
4497f7f. Dashboard Stereo start/image/camera6DoF/features/map/trajectory/save/
export/stop passed within bounded stationary windows. Native reuse failed
CUVSLAM_CAN_NOT_LOCALIZE. Isolated domain84 product NativePlanner HTTP/native
execution passed a narrow synthetic-map matrix; operating policy remained false.
The one operating diagnostic window ended ABORTED at the collector boundary,
with useful partial evidence and verified cleanup; stale startup did not recur.
See [NONMOTION_FOLLOWUP.md](NONMOTION_FOLLOWUP.md) and its validation JSON for exact
source/runtime/config, counts, failures, remaining work and evidence hashes.

Final readback11:23:39Z: SLAM IDLE, camera free, navigation/FAST-LIO stopped;
control bridge intentionally inactive and dashboard bridge-autostart disabled. Existing
Hesai preview remains running. No driving, initialpose or goal was issued.
Do not restore the bridge from this document. Historical approvals and results
below do not override this current record. No further runtime window is pending.

# Current integration priority — Stereo observation

The 2026-10-16 user request reopens work specifically for real dashboard-controlled
Stereo VSLAM mapping/observation. See [STEREO_OBSERVATION.md](STEREO_OBSERVATION.md)
for the current source, runtime, approval boundary, software changes and exact
next action. Policy/MR-MS-003/missions/full reuse/MAP-02/precision evaluation are
separate follow-ups, not Stereo observation gates. The closed stage40 record
below remains historical; it does not authorize current service/camera actions.

# Historical integration handoff — through40

Final user instruction: stop and finish here. Scope was briefly extended to41,
but no41 operation began before the stop request. No additional device action
or background continuation is pending.

Candidate `47c77af19246bd6a455ee873a7c55884ed6e4122` is now deployed, including
the a67c5f5 UI repairs and bounded policy diagnostics. The approved one-start,
no-initialpose policy window completed60 seconds and owned cleanup. All60 policy
samples were unavailable (59 readback-timeout reasons); independent graph samples
showed five unique authorities and ten ready services, without proving replies.
No deadline/freshness was relaxed. Exact source/runtime/config, tooling corrections,
preservation, regressions and limits are in [POLICY_RUNTIME_WINDOW.md](POLICY_RUNTIME_WINDOW.md)
and [POLICY_RUNTIME_WINDOW.json](POLICY_RUNTIME_WINDOW.json).

Final inspection at2026-10-15T13:03:52Z: clean main47c77af, dashboard PID54752,
HTTP200,1265 matching source files,54 maps and five selected-state files preserved.
Bridge/camera invocations remain unchanged. Navigation/session/goal idle,
initialpose0, lease/deadman false, command0 and no owned runtime/observer remain.
The five updated UI files are served with exact hashes and no-store. Global
HUD/STOP stays Settings-only by user choice; the Controls-page STOP remains.

This60-second diagnostic does not replace the prior localized180-second result.
Full live acceptance and SOFTWARE_CLOSURE remain false; NativePlanner product
execution, MS native reuse and MAP-02 completeness remain unverified. No41–43
operation or additional runtime window was performed. Next minimum policy work:
bounded per-endpoint future state and tick/batch timings, preserving500ms/750ms
and semantic revisions. Historical stale-startup cause remains UNCONFIRMED.
No background continuation is scheduled.

## Historical stage36 software snapshot

**Stages30–36 available software work is complete; SOFTWARE_CLOSURE remains
false. No deployment or stage40–43 action occurred.** Published source and exact
CI: [VALIDATION.json](VALIDATION.json); source/test byte pins:
[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json). Baseline was clean
`2555f3763996c7b331389924bb5df48d62094736`. No branch/worktree/PR was created.

The actual device was inspected read-only: clean disk checkout
`416d25c6e1c98b0c51097c9d6576b6ae34a690e9`, dashboard supervisor PID996,
Python3.10, active dashboard/bridge/on-demand relay; no container running.
Last navigation observation was idle/uninitialized with no active Nav2 pipeline
and goal admission false. This is a timestamped readback, not continuous proof of
current state. Loaded module/release/invocation and aggregate config digest remain
null. Existing map ID/revision and historical initial coordinates were found in
private evidence and current catalogue; physical pose validity is unconfirmed.

No runtime/camera/service owner was acquired. No initialpose, ARM/lease, goal,
movement, replay, subscription, GPU job, service restart, pipeline or deployment
was performed. No other chat response is required to close this scope. All three
delegated source owners are finished; no pending writer remains.

| Capability | Judgment | Smallest next action |
| --- | --- | --- |
| Localization diagnostics and reproduced defects | SOFTWARE_FIXED / live root cause UNCONFIRMED | Later approved exact-candidate localization-only trace; correlate callback/reject/accepted evidence within one invocation, without changing thresholds |
| MR-MS-003 real readback/provider/context | PARTIAL | Implement versioned mask/native collision profile and qualified global/local/controller/BT ingestion/map binding, then raw-positive production tests |
| NativePlanner product path | SOFTWARE_TEST PASS / actual native NOT_RUN | Qualified isolated Humble product HTTP matrix with exact server/plugin/config identity and owned cleanup; operating Jetson requires later window |
| MS native lifecycle/feature image projection | SOFTWARE_TEST PASS / actual NOT_RUN | Fixed helper/broker install manifest and shared camera lock ownership, then separately approved stationary native acceptance |
| Native map save/load/reuse | NOT_RUN / BLOCKED | Compatible official package, verified private map-to-camera hint, official callback and fresh corrected pose plus geometric alignment |
| MAP-02 every retained landmark | PARTIAL / BLOCKED | Obtain supported full/frozen/paged API guarantee with independent retained total or reviewed exhaustion contract; preserve native IDs/weights; qualify installed export above current cap |
| Runtime provenance/live_plan/ETA | unavailable/null | Managed startup artifact attestation and trustworthy active-goal path binding before values can be exposed |
| History capacity maintenance | procedure only | Verified terminal export, then separately designed tombstone/namespace-safe reclaim; no live JSON edits or cap increase |

Local regressions: Python1987/1985pass/2skip/0fail, JS381pass, Chromium96pass.
The two skips and limited mypy scope are explicit in VALIDATION.json. These are
hardware-free software fixtures; native and live rows are separate in
[ACCEPTANCE_MATRIX.json](ACCEPTANCE_MATRIX.json). Its original required_for flags
are retained, so unresolved native dependencies and policy software keep closure
false; fixture support does not silently turn those rows PASS.

Production path is gateway async readback → cached provider from real default
configure → NavigationContext → existing compile/start/dispatch coordinator.
Current policy scopes remain false because real unknown/KEEP_OUT enforcement
is absent. Preview uses the existing fixed planning-only action, no motion bypass;
its shared reservation survives repeated cancellation and uncertain cleanup.
Native path full evidence is returned by preview; run history stores compact
provenance and raw-path digest within the unchanged512KiB bound.

mission-plans.v1 remains the stored schema. Additive result/context evidence does
not backfill old history. Test old strict readers/rollback on copied fixtures;
keep active/paused/canceling/uncertain runs and idempotency receipts. Safe export
and separate source/data/service rollback are in [OPERABILITY.md](OPERABILITY.md).
Normal source rollback uses revert; deployment and data restoration need their
own manifest, never restore lease/ARM/active goals.

Private evidence and SHA256 manifest remain in the sibling
`robot-scope-hardware-validation-private/integration-20261015/`; original map and
pose records remain in `stage04-newmap-20261014T113809Z/`. Raw coordinates/native
bytes/secrets are absent from Git. No map, mission history, bag, environment,
container, installation or service was deleted or overwritten. Preserve them.

No continuation is scheduled. Reopen a later scope only on a new user request;
stages40–43 require their own current conditions and must not inherit software
publication authorization.

Published source candidate: `4b189d1f59fb08667faaf3922f08b6e145f0db4b`. Exact source CI run: [38716730829](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38716730829); result: SUCCESS on Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12, recorded in VALIDATION.json and CI.json. Subsequent documentation tip CI is a separate run and is never inferred from this source run.

Source CI per Linux job:1987 Python tests (1986pass,1 optional-rosbags skip,0fail),381 JS and96 Chromium E2E PASS. Linux /proc coverage runs there; no native ROS/camera/motion acceptance is included.
