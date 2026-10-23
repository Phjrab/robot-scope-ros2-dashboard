# Latest follow-up — 2026-10-23 passive source capture preserved before power-off

After explicit additional user authorization to preserve measurements before01:00KST,
one passive10s subscriber recorded existing LiDAR inputs at00:39:26–37KST. No sensor,
service, camera or bridge was started/restarted; no control/TF publish or registration.
Three64k-point raw PointCloud2 frames and their three16k-point converted frames retain
original CDR, complete payload, full XYZ, field/clock/identity metadata; selected IMU,
odom and lowstate samples accompany10s count/statistics. This is not a continuous bag.

All55source files/19,291,074bytes match remote and Mac SHA256. Current map/config,
calibration CSV, prior11candidates/backend source and receipts form88frozen files.
Manifest SHA `5139c1035956290e6360f00c034620fc9275802e29ed0bb995ba108e242bf18a`;
archive SHA `e867f4ac665e9b58e7159a86185c45d26f9b0e304350b29ef05ee93dd7c6569b`.
Private root: `lidar-passive-20261022T1538Z/frozen/`; root README/ANALYSIS and
FROZEN_RECEIPT describe formats, limitations and hashes. The old missing scan was not
recovered; this is a new independently retained input.

Each converted scan exactly equals raw every-fourth XYZ/ring/intensity, retaining rings
0/4/8/12 of16. Relative point time matches raw timestamp differences; header clocks
remain different/unverified. No filtering/config changes were made. Local fixed-old-T
distance-only analysis (not registration/reselection) found23cm conditional residual
still present in both converted and all16raw rings; thinning alone is not proven cause.

Collector timeout PID/PGID193198 exited0/reaped/group absent. At00:42:57KST,180source
hashes and14clear ownership components were retained, dashboard PID75863/NRestarts0,
bridgeOFF/globalgen1/trackinggen0 unchanged. Robot access ended then; all later work
uses the Mac copy. No commit/push/deployment. The following zero-capture analysis was
completed earlier and is preserved as a historical scope, not this later authorized run.

# Previous follow-up — 2026-10-23 retained alignment analysis; local only

Stored job `1f554b10a68d0220b3d26667` was audited without new capture, registration,
benchmark, robot writes, restart, STOP or deployment. GitHub main and local HEAD both
remain `e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`; existing dirty changes are preserved.
The installed static history UI below remains the latest deployment, not this analysis.

The selected0-based index2 has **conditional inlier RMS0.230319m** at a0.75m gate,
full-scan RMS0.446447m, capped-full RMS0.319901m and14452/16000inliers. These are
directed nearest-point residuals, not body position errors. The11records include
index9 as a duplicate of2; there are10stored nonduplicate representatives. Candidate4
is4.254m/179.782deg away yet has93.65%overlap and0.329253m capped RMS. Repeated geometry
or partial overlap remains a hypothesis; no unique accurate pose was established.

Exact map bytes and float64 array hash match the job. Map self-neighbor median3.53cm
does not support treating query voxel0.5m as the verified original-map resolution.
Original map-time effective configuration remains unavailable. Latest scan SHA and
provenance are retained, but its numeric bytes were not found in the bounded local
inventory; older19Oct scans were not substituted. No latest residual recomputation
or spatial cause attribution is claimed. Constant rigid extrinsic alone can be absorbed
by unrestricted SE3; accumulated map/deskew/time distortion remains unverified.

Pinned7source files and adapter order were audited: existing compat removes the5cm
gate before branch ranking/retention, then explicit ambiguous selection chooses minimum
conditional RMS. This is not merely a display change. No gate/ranking/filter change was
made here. No demonstrated product metric bug required a code patch. Private bounded
aggregate/SE3/map-only analysis completed once in0.833s;11unique synthetic math/contract
tests passed (10initial plus2focused executions, one repeated). No full CI rerun.

Evidence/reproduction: private `lidar-integration-20261022/followup/alignment-cause-analysis/`
contains REPORT.md, analysis.json/CSV, bounded tool, tests and exact source hashes.
See [LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md) for provenance and limits.
Next minimum step is separately scoped exact raw/XYZ retention with effective config,
before any new residual experiment. No commit/push, tracking or operational application.

# Previous deployment — 2026-10-23 static history UI installed; actual retained-result display verified

**2026-10-23 00:12 KST 실제 후속 완료:** GET 전용 과거 job 선택/재조회 UI와
활성/pending sensor 관측의 간접 STOP 차단을 최소 static3파일로 반영했다. service
restart·STOP 없이 원본185hash/owner/battery 확인·새 백업·조건부 복구를 갖췄다.
정상 Maps 화면에서 기존 job1f554b10a68d0220b3d26667의 SUCCEEDED/HISTORICAL_ONLY,
원본 시각/epoch·모호성 경고·RMSE0.230319m/overlap0.90325 표시를 실제 확인했다.
새 합성64단위·4브라우저, runtime 동일64벡터·통합5, retained JSON replay6조건 PASS.
00:12:13 battery54%/age0.011초 fresh,14owner clear, PID75863/NRestarts0 유지,
bridge OFF/disabled, global generation1/tracking generation0다. 추가 정합·tracking·
카메라·제어·주행·commit/push는0회다. 설치3파일 SHA/원본 metadata/복구 경로와
증거는 [LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md) 최신절 및
private `followup/history-retrieval-ui/`를 따른다. 이전 b68d0c6·미배포 준비 기록은
과거 시점이며 최신3파일 설치 상태로 대체한다. 실제 tracking/본체 정확도는 미검증이다.

At23:42:32KST the exact runtime-specific JS one-file fix was installed and served with
SHA256 `b68d0c6471eb30618a1c4ec020e7bd6c4ad3cc95dd482d59ec7bb55df3e51313`.
183 source/config/map/pin/init guards matched; dashboard PID75863, InvocationID
`64042df9601349f1ad68e689ee8a8247`, NRestarts0 were unchanged. No restart, STOP,
camera, control, new global or tracking start occurred. The first attempt restored the
exact original after a post-install ownership snapshot was unclear. Its exact unavailable
component was not captured, so no cause is asserted. Read-only reconciliation proved
restoration and clear owners before one guarded retry passed. Fresh backup/metadata and
conditional one-file rollback reside in remote `static-contract-20261022T144218Z-7880e8b5`.

Actual browser verification loaded the18Oct3D PCD and observation panels with no captured
console warnings/errors. It remains IDLE/HISTORICAL_ONLY, with tracking disabled: a new
page has no pending request and there is no retained-job selection UI. The existing API
job remains succeeded/historical with the original ambiguity and quality warnings.
Offline retained replay PASS, installed/HTTP byte verification and actual panel load are
distinct from actual completed-result display, which remains NOT_VERIFIED. No controller
injection or new computation was used. Existing policy has no global-seed elapsed-time
TTL; current scan age≤1s and identity/resource checks still apply. Tracking stays0.

Final read23:44:37KST: battery63%/age0.008s fresh,14 owners clear, bridge OFF/disabled;
weekly remaining39%. Prior35/26 synthetic checks overlap and were not rerun. No commit
or push. Next minimum work is a separately scoped read-only retained-job retrieval UI.
The earlier not-deployed paragraphs below describe the23:31 historical snapshot.

At23:21KST, the existing owner's user-authorized stationary observation started one
fresh live global job through Maps: `1f554b10a68d0220b3d26667`. The exact18Oct3D map
25,666-point reference and complete16,000-point converted XYZ scan were used. The
job completed in20.959s (runner18.356s); candidate2 has RMSE0.230319m, overlap0.90325,
14,452inliers and `AMBIGUOUS_ALTERNATIVES`. API `succeeded` means retained computation,
not quality acceptance or body accuracy. Existing ambiguity policy/gates were unchanged.

Actual UID1000 user-scope admission verified memory2GiB/swap0/tasks64/runtime120s.
The exact scope/cgroup and all observed process identities disappeared; the finite
watcher ended `OBSERVED_SCOPES_CLEAN` at23:25:12KST. Source guards180/180 matched,
raw capture was consumed/not in flight,14owners had no busy/unknown, global history
was retained. No deployment-wrapper replay or history deletion was performed.

The actual browser rejected the completed response as `RESULT_CONTRACT_MISMATCH`:
the two captured contexts are semantically equal but the backend sorts object keys.
The tracking start button remained disabled, so tracking starts/stops were **zero**.
The UI check was not bypassed with an API start or browser injection. A local patch
compares JSON objects independent of key order while preserving every key/value/type,
array order, map/frame/epoch/stamp and historical restriction. Main related35 tests,
runtime-specific26 tests and an offline replay of the actual retained JSON passed.
These are software/replay checks, not a corrected on-robot UI acceptance run.

The running integration is d16fca6+7 approved overrides, while public main is e70ef825.
The prepared runtime-specific static1-file payload preserves that integration and has
SHA `b68d0c6471eb30618a1c4ec020e7bd6c4ad3cc95dd482d59ec7bb55df3e51313`.
It is **not installed**. A fresh one-file backup and guarded restore are described in
private `live-observation-execution/ui-fix-preparation/manifest.json`; no service
restart or final STOP is required for this static-only candidate. Its install decision
is separate from replay validation. The additional-scan clause of the earlier bundled
question was withdrawn; do not repeat global computation to verify this fix.

At23:30:29KST battery68% was fresh(age0.015s), cloud10Hz, odometry184.98Hz,
dashboard PID75863/NRestarts0, bridge OFF/disabled; weekly remaining41% was read.
This observation added no service restart, camera, control/drive/posture/ARM/bridge,
TF/initialpose/goal or commit/push. Tracking, body ground-truth accuracy, extrinsics,
deskew/source clock and sensor-to-photon latency remain unverified. See the latest
[LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md) section and private
`lidar-integration-20261022/live-observation-execution/` receipts/screenshots.

## Earlier approved deployment — preserved reconciliation record

The human approved manifest SHA
`7055f7ebf1779b39fdd6379db96b4a93c2a6385d3720cefc9279bbc4b888a0dc`
under a stationary/no-unsaved-or-active-work/no-new-work transition window, including
the normal final safety STOP path, owned Hesai/XT16 preview restart and guarded
original rollback. Seven product files and one two-key drop-in were installed
over the preserved d16fca6 integration runtime;173 protected hashes remain intact.
One dashboard restart was requested at22:55KST. PID75863, InvocationID
`64042df9601349f1ad68e689ee8a8247`, active/running, bridgeOFF/disabled.

The immediate deploy postcheck exited1/PRESERVED_ENVIRONMENT_DRIFT. Its exact
mismatch was not captured; do not assert a confirmed startup-transient cause.
Later inspect showed no preserved-environment differences and read-only
verify-installed passed without another restart. The initial error and
RESTART_INTENT journal remain unchanged; separate reconciliation receipts record
the verified installed state. No rollback was needed.

At22:59:03KST the actual loaded policy reports budget disabled/null, resource mode
user_scope_v1, startup30s/watchdog60s retained. Ownership GET returns200/no-store,
12 observed-clear plus2 optional-absent components, no busy/unknown; it remains
non-atomic and does not authorize restarts. Broker reservation remains empty,
preview resumed and CPU/parent cgroup limits are unchanged. Two pinned sensor
samples81.048s apart are fresh (cloud~10Hz, odometry~185–202Hz); this is sampled
existing-input observation, not continuous sensor tracing. Latest recorded
battery23:01:06KST76%,age0.014s/fresh; the existing relay watcher was reused.

Original bytes/metadata backup is under remote
`/home/unitree/robot-scope-deploy/ownership-budget-20261022-7055f7eb/backup`.
Private exact receipts and local verified backup are in
`lidar-integration-20261022/approved-deployment-execution/`; full source/runtime/
config details and limits are in
[LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md).
103 existing local checks were not rerun. No commit/push or new global/tracking
POST/native calculation occurred. Actual child admission/enforcement and new
live registration require a separate approved step. No driving/posture/ARM/
bridge activation/operational TF/initialpose/goal or physical accuracy assessment.

# Historical preparation — 2026-10-22 pure ownership readback implemented locally

The new `/api/v1/system/ownership-readback` copies fixed in-memory constraints
without control expiry/output, native cancellation, adapter status or sensor work.
Two product files and three test files extend the preserved resource candidate;
the frozen five resource files are unchanged. Focused26 and surrounding34 local
tests pass, with real constructor fixtures and side-effect spies. Independent
static review found no remaining P1/P2. Source freeze manifest:
`2881fdbed61eb81480f6decbcdb8779d4bb6246c4cf70a507a70b59755359334`.

Actual22:18KST source inventory matches the d16fca6 baseline. DashboardPID1006
remains active, bridgeOFF/disabled, and both budget/resource activation keys are
absent: operational0.6s is still active. Broker capability at22:25KST confirms no
broker camera/session reservation; it does not prove dashboard unsaved memory.
No service restart or native calculation has occurred in this follow-up. The
initial install still needs current operator quiescence/unsaved-work confirmation
and the disclosed normal final safety STOP plus owned preview restart. The new
endpoint is advisory, not globally atomic or a restart authorization. Exact
software/runtime/config/evidence and recovery preparation are recorded in
[LOCAL_VALIDATION_20261022.md](LOCAL_VALIDATION_20261022.md).

# Historical follow-up — local resource candidate frozen; operational deployment deferred

The preserved d16fca6 runtime snapshot has a five-product-file candidate that
explicitly disables the seeded processing budget only together with verified
UID1000 child resource scopes. Existing worker/adapter/legacy bytes, freshness1s,
finite startup/operation/session watchdogs and the non-control boundary remain.
Its manifest is64c589fba4e16102455f88911ebc37ea6adf37c04bb6071beffb2bcddf36c979.
Local mock/stdlib regressions:81 passed,1 macOS FD check skipped; independent
product review and patch checks passed. No saved-scan benchmark was repeated.

At20:19:51KST disk/owner readback still showed dashboardPID968/NRestarts0,
both activation keys absent, bridgeOFF/disabled and no active related jobs.
The operational0.6s limit has NOT been disabled. No product deployment or
service restart occurred. The deployment wrapper remains blocked: its SLAM
status GET indirectly reaches control manager.snapshot and may enqueue an
expired STOP. Preserve the dated receipt and do not call it a side-effect-free
read or infer zero control outputs from it. Product tests and deploy readiness
are distinct. Power-off was requested; the user was told normal shutdown is
compatible with the local-only work if no new capture/save was started after
the last readback. The latest query returned no result and only that SSH
connection was closed. Future hardware work requires fresh owner/source/config
checks and the concrete deployment/preview-restart/rollback observation scope.
No commit/push. Exact methods and limitations:
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md).

# Latest archived comparison — 2026-10-21 19:48 KST

The user superseded the former 0.6s requirement for the temporary processing
budget and requested no extra CPU quota for new experiments. Actual product
files are still unchanged; a local budget/watchdog candidate is separate from
deployment. The archived 10cm residual comparison is neither physical accuracy
nor an overall acceptance gate.

The new approved batch consumed three serial and three split trials with the
same exact seed/map/full scan/source pin and preserved branch dependency. Median
call time was 0.821718s vs 0.687252s (16.36% reduction), but fresh-process startup
through cleanup was 2.700431s vs 2.892947s (split 7.13% slower). Six numerical
trials and all children completed; the last split's unselected coarse diagnostic
rotation increment exceeded the original1e-8 comparison, so the overall receipt
remains FAILED_CLOSED_NO_RETRY/exit2. No tolerance was changed and split was not
adopted. The0.155819m value remains a registration residual, not body error.

No added CPU quota/thread cap was present: actual cpu.max=`max 100000`; memory2GiB,
swap0,tasks64,finite watchdogs and whole-group cleanup remained. systemd-run elapsed was
16.982s (service runtime16.949s); all new remote paths/cgroup/children were removed. At19:48:24KST dashboard
PID968/NRestarts0 and existing previews/broker/source hashes were unchanged,
bridge was inactive/disabled and global active/latest null. No deployment,
existing-service operation,new subscription,robot command,commit or push occurred.
Detailed methods/resource samples/limits are in
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md).

## Historical records below (preserved)

# Archived serial/process-split diagnostic closeout — 2026-10-21 19:14 KST

After the user explicitly authorized authenticated execution, the same transient
resource preflight passed at 19:05:20 KST. CPU 200%/100ms, memory 2GiB, swap 0,
tasks 64 and descendant cgroup membership were read back. No sudo policy or
parent controller changed; authentication was not stored in files or arguments.
The earlier 18:49 authentication failure below remains a historical record.

The exact archived scan-0 candidate-10 seed, map and scan pair, frames, stamps,
epoch and pinned sources passed admission before numerical imports. One serial
and one process-split diagnostic ran, with no retry, in the approved new path.
The numerical runtime was the preserved stage3 venv, receipt-generated pin
`47ea8760ff6a0522067850a6bd10b330ca8a21c9c5ed12c82a1936ba9541bcef`;
product/backend source, operational DDS and the 0.6-second deadline were unchanged.

| One-shot diagnostic | Startup/map preparation | Ready-to-validated-result wall |
| --- | ---: | ---: |
| Serial | 2.716791s | 0.822107s |
| Separate processes | 2.514348s | 0.622600s |

This pair reduced diagnostic call time by 24.27%, but **both exceeded 0.6s**.
It is not a stable tracking or product-owner latency acceptance. All three
branches scored the full 16,000-point scan against the 25,666-point map;
coarse-to-robust dependency and the original plane seed were preserved. Every
non-timing result field matched (233 floats, maximum difference zero). Selected
RMSE was 0.155819m, failing the 0.10m residual comparison; physical accuracy and
body pose remain unverified. No residual/ambiguity policy was changed.

The systemd run took 7.404s; stage-through-cleanup took 7.579s. All owned children,
the leaf cgroup/unit, runner and new folder were removed. At 19:14:44 KST existing
dashboard/preview/broker PIDs and commands, bridge inactive/disabled state, parent
properties and safe source hashes were unchanged; existing cloud/odometry were
fresh. No deployment, existing service operation, new sensor subscription, robot
command, TF/initialpose/goal, commit or push occurred. Eight private admission/
dependency tests passed; prior full suites were not repeated. Detailed timing,
resource sampling limits, exact runner hashes and the next offline critical-path
review are in [LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md).

# Local follow-up and deployment record correction — 2026-10-21

At 18:49:05 KST, the separately approved one-shot resource preflight attempted
the reviewed transient systemd service once. `sudo -n` refused execution with
`a password is required`; no transient unit or inert child was created and no
native calculation ran. The one newly staged runner and empty directory were
removed. Parent controller/limit properties and existing service PIDs/state were
unchanged. Final read-only checks at 18:50:04 KST confirmed cleanup and fresh
cloud/odometry. Resource enforcement remains untested; no password, policy or
permission change and no retry occurred. The latest detailed section is in
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md).

An explicitly resumed read-only follow-up at 18:07:45 KST found fresh existing
cloud/odometry/IMU/lowstate, battery 74%, dashboard active and control bridge
inactive/disabled. At 18:10:58 KST it verified the exact historical scan-0 seed
(candidate 10) against the remote preserved fixture and local published bytes.
The matrix, scan pair, map, frames, timestamps and session are now identified;
this does not identify the current robot pose. Seven additional local seed
contract tests passed. Remote diagnostic runs remain zero: CPU resource-limit
assurance is still unresolved and no cgroup/security workaround was performed.
See the newest section of
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md) for the dated evidence.

The October 19 deployment/undeployed statements below are historical. They do
not describe the subsequent October 20 product-file deployment. The current
reconciliation and local deadline checks are recorded in
[LOCAL_VALIDATION_20261021.md](LOCAL_VALIDATION_20261021.md).

- Local main at inspection: `e70ef825e9c7bc0c6bcbf3ef357504d523a748fc`.
  The separately published integration source inspected and tested was
  `d16fca6e2fb0c3528200b8c9bc8400f277ff1f02` on
  `codex/maps-localization-integration`; it has not been merged into this main.
- The [October 20 execution record](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d16fca6e2fb0c3528200b8c9bc8400f277ff1f02/docs/integration-acceptance/STAGE3_ARM_RUNTIME_20261020.md)
  records the applied 37 product files, dashboard restart, historical global
  observation, and local tracking loss at the unchanged 0.6-second deadline.
  Robot Git HEAD remained `d7807de8f15fb457942039bb90ab41cf68d384c6`;
  that HEAD alone does not identify the applied product bytes.
- The existing October 21 17:17:02 KST read-only receipt matched all 37 product
  paths plus the telemetry router to the integration reference. At that time
  the dashboard was active, the control bridge inactive/disabled, and there
  was no global job. These are dated observations, not refreshed live claims.
- This local follow-up ran 142 Python checks (141 passed, one Linux-only skip)
  and 56 JavaScript checks (all passed). Two new private synthetic regressions
  verify deadline rejection after pin preflight and result-validation overruns.
  Native backend latency and hardware accuracy were not tested. Product code,
  source pins, gates, deadlines and freshness limits were not changed.
- The separately approved remote process diagnostic stopped at its resource
  prerequisite: CPU cgroup delegation was unavailable. Serial/split runs were
  both zero, and the exact archived seed was not checked after that failure.
  The later read-only follow-up above subsequently resolved the seed identity.
  This does not block the completed local document and regression work.

No remote write, deployment, service operation, new sensor subscription, robot
control, commit or push is part of this local follow-up. Earlier records and
their test counts remain below with their original dates.

# Dashboard deployment and local asynchronous observation — 2026-10-19

Installed dashboard source is now `d7807de8f15fb457942039bb90ab41cf68d384c6`.
The explicitly approved dashboard restart (including its existing Hesai/XT16
preview) completed once. Source and 28 configuration / 3,721 retained data files
were verified; the one expected restart event appended to an unchanged history
prefix. Protected camera/broker identities stayed unchanged; control bridge
remained inactive/disabled. A 60-second read-only window received all 62 HTTP
samples successfully and the saved October 18 3D map displayed. This is input
and display verification, not localization or body-pose acceptance.

The separate [asynchronous historical observation](ASYNC_GLOBAL_OBSERVATION.md)
API/UI/worker changes remain undeployed. They preserve full received
XYZ and original map coordinates, pin the external backend, support cancellation,
and keep every result historical/sensor-only. No new real registration or device
window was run. The user subsequently authorized GitHub publication of code and
the [public desktop handoff](DESKTOP_HANDOFF.md). Further robot deployment remains
held. The handoff distinguishes source publication, installed source, test results
and private backend dependencies; private evidence is not uploaded.

The following records retain their original dates and pre-deployment status.

# LiDAR provisional observation — local candidate, 2026-10-19

Current read-only runtime/source inspection and the explicit 10cm residual-only
policy are recorded in [LIDAR_PROVISIONAL_OBSERVATION.md](LIDAR_PROVISIONAL_OBSERVATION.md).
Installed source is `fe5bc2b`; control bridge is inactive/disabled. New code stays
local pending separate deployment approval. The original 5cm results, raw point
clouds/maps and nonresidual gates remain preserved. No new registration, sensor
service, robot motion, pose/TF application or public push occurred in this stage.

The following sections are historical snapshots with their original dates.

# Saved 3D observation/editor integration — local candidate, 2026-10-18

Read [SAVED_3D_OBSERVATION.md](SAVED_3D_OBSERVATION.md) for the current source,
transform/identity/freshness contracts, numerical bounds and remaining field work.
The existing Maps view now separates approximate odometry propagation from an
opt-in scan-to-map candidate. The transferred 2D/3D editor preserves its original
source and exports local proposals/copies. No runtime map installation occurs.

A new offline calculation using the retained 25,666-point 3D reference and
424-point query produced a numerical candidate (~413 ms, RMSE 0.02663 m). This is
not independent pose accuracy or live acceptance; the previous rejection remains
preserved. Robot deployment/restart/sensor execution remain held pending readiness
after charging. The historical installed source is still `40276a5`; no new device
operation is claimed. Local validation and candidate hashes are in the private
`local-integration-qa` closeout. No push or public release is part of this stage.

## Previous records (preserved)

# Local recorded 3D diagnostics — 2026-10-18

Current work is stored-data analysis and local UI/regression only. No robot
access, deployment, services, TF, initialpose or driving was performed. The prior
runtime/state observations below are historical, not refreshed claims.

The existing experiment page now overlays recorded map/query points with a
before/after control and explicit rejected/unqualified diagnostics. The Go2
reference model retains metre scale under zoom. Input/session/body semantics,
source precision, residual support and limitations are documented in
[RECORDED_3D_DIAGNOSTICS.md](RECORDED_3D_DIAGNOSTICS.md). Private recordings and
screenshots remain outside Git. Software validation and the exact local commit
are recorded in the private closeout; Git publication and robot deployment are
not part of this change.

## Historical stage40 closure


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

2026-10-15 KST/UTC timestamps and exact byte identities are in [VALIDATION.json](VALIDATION.json).
The user requested stopping after36. Available software work is finished; full
SOFTWARE_CLOSURE is false because the remaining policy producer/enforcement and
native evidence are explicit dependencies. Stages40–43 are NOT_RUN.

Baseline clean main/origin/main: `2555f3763996c7b331389924bb5df48d62094736`.
[Source manifest](SOURCE_MANIFEST.json) pins the exact tested source and tests;
publication SHA and successful exact CI are recorded in VALIDATION.json.
Device disk checkout: `416d25c6e1c98b0c51097c9d6576b6ae34a690e9`; loaded
module/release and process invocation remain unproven. Last read-only supervisor
PID996, idle/uninitialized navigation, no active pipeline, can_send_goal=false.
Source config hashes and device disk hashes are separate; no aggregate loaded
config digest is invented.

The integration owner serialized shared writes, full tests and Git publication.
Partitioned localization, planner and completeness agents finished and reviewed
their source; no competing writer or pending delegated mutation remains.

| Stage | Actual change/result | Evidence and remaining condition |
| --- | --- | --- |
| 30 | Latest published MS/MR handoffs, clean source, exact baseline CI, runtime disk/config and private map/catalogue checked | Repository/device inspection; existing map revision matches, operator pose remains historical |
| 31 | Bounded input diagnostics, rejection invalidates old alignment, monotonic source progress, publisher/process invocation fences | Production-class ROS-shaped fixtures; historical live startup cause UNCONFIRMED |
| 32 | Async effective GetParameters/GetState readback → real default policy provider → context/admission; heartbeat excluded from semantic pins | Raw-observation tests; no qualified mask/global/local/controller/replanning witness, enforcement stays false |
| 33 | Own ROS Context executor, inherited environment and fixed action identity, owned UUID/path provenance, bounded late-goal cleanup | Transport fixtures; actual product native NOT_RUN |
| 34 | Full-snapshot attestation and raw-cloud binding; invalid/filtered count equality no longer yields complete; installed SDK header checked | MAP-02 PARTIAL/BLOCKED, native save/load/reuse NOT_RUN |
| 35 | Preview reserves resource while awaiting outside shared lock; compact dispatch provenance; archive/rollback procedure | live_plan/ETA/source/runtime provenance remain null/unavailable; no operational data cleanup |
| 36 | Full Python, JS, browser, static, dependency and secret checks; focused main publication and exact CI | Results and skip scope in VALIDATION.json; no deployment |

Local full suite:1987 Python tests,1985 pass/2 skip/0 fail;381 JS pass;
96 Chromium E2E pass. Coverage75%; configured mypy covers only four modules.
Private log copies and SHA256 identities are recorded in VALIDATION.json.
Existing fixtures with final policy=true are distinguished from raw-production
observer/default-factory tests; neither constitutes native enforcement proof.

[HANDOFF.md](HANDOFF.md) lists the smallest next software and separately gated
native tasks. No maps, annotations, history, receipts, bags, VSLAM installation,
services, camera owner, pipeline, pose or goal was modified. No device action or follow-up is scheduled.

Published source candidate: `4b189d1f59fb08667faaf3922f08b6e145f0db4b`. Exact source CI run: [38716730829](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38716730829); result: SUCCESS on Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12, recorded in VALIDATION.json and CI.json. Subsequent documentation tip CI is a separate run and is never inferred from this source run.
