# Multi-SLAM progress

Updated 2026-10-15 KST. Scope: stages 10–15 software. No deployment, camera
handover, GPU replay, operational pose application, goal or movement performed.

## MS-10 — baseline / CI correction

Clean main initially 1b0ae5b (existing hardware follow-up preserved), fresh
origin/main eb9026a. CI38554448122 failed six Ruff issues before tests.
Changed app public re-export, relocalization PROFILE alias, three semicolon
statements in evaluate_recorded_se3 and doctor path-bootstrap E402 annotation.
No workflow, safety threshold or experiment change. Ruff/mypy/frontend syntax/
diff checks PASS; full suite/remote candidate pending.

## MS-11 — adapters / lifecycle / camera

Added slam_sessions, slam_camera, slam_ros_runtime, slam_broker, slam_wiring,
api/routers/slam and scripts/slam/managed.launch.py. Actual FAST-LIO coordinator
and Isaac GetParameters/FilePath/LocalizeInMap/subscriptions wired. Added app/
runtime/mapping coordinator/camera/dataset/relay ownership hooks. Private broker
preserves observer DDS isolation and independent camera flock.
Focused session26, camera11, API14, broker18, runtime22, wiring15 tests PASS at
this checkpoint; subsequent regressions recorded in final report.
Review fixes: pure health snapshots cannot overwrite lifecycle transitions;
save/localize recheck health; failed save releases localized scratch; finite
request validation yields422; ARM/service changes see SLAM ownership.
BLOCKED: installed readback, real camera owner/handoff and cleanup.

## MS-12 — features / projection

Added slam_features and real stream: strict PointCloud2 parsing, exact source
timestamps, optical pose/calibration/epoch projection, LOST/stale suppression,
independent global snapshots and trajectory.37 focused PASS including calibrated
camera view. Runtime/frustum connection final review in progress.
BLOCKED: installed binary semantics, actual optical/time pairing and live rate.

## MS-13 — native packages

Added slam_packages: atomic publication, hashes/revision, bounded archive CRUD,
active references, compatibility, original-preserving scratch.17 focused PASS.
Camera pixels excluded from stored preview. MAP-02 BLOCKED: visualization cap
32768 cannot prove full retained map; total null, global extent separately shown.

## MS-14 — existing UI

Added scoped features/slam/dashboard.js and slam.css mounted by index.html;
engine/mode/start/save/stop, input overlay, global scene/trajectory and native
catalog/preview/manage/load connected to real endpoints. Initial JS5/E2E5 PASS
(synthetic fixture). Save-then-stop now explicitly discards only post-save data;
matching regression and additive calibrated scene frustum follow-up in progress.

## MS-15 — delivery in progress

BASELINE/CAPABILITY_AUDIT/ARCHITECTURE/API_CONTRACT/FEATURE_OVERLAY/MAP_FORMAT and
this log/HANDOFF exist. README/deploy/rollback/matrix/report next. Finish focused
review regressions, exclusive whole suite, main commit/push/exact-SHA remote CI,
then return checkout window to MR.

## Execution ownership

MS sole checkout writer/shared integrator. Internal agents own disjoint files.
MR drafts in /private/tmp/mr-implementation; no MR checkout edits. Full-suite/Git
window not started. CI workflow unchanged; no equipment/performance window.
docs/mission-route/INTEGRATION_REQUESTS.md absent on latest check; recheck before
MR integration. Accepted requests and blockers are in HANDOFF.

## MS-15 review closure / exclusive verification

All internal writers stopped. Focused final counts: sessions34, camera12,
broker22, features37, runtime24, wiring17, packages17, API14; UI8 and existing
scene9, SLAM E2E7 PASS. Added optical frustum/source epoch quarantine, uncertain
reservation/release ACK recovery, off-thread broker cleanup, and explicit
unsaved-map replacement consent for native localize. Map originals remain intact.
Shared app line budget retained via close_slam helper (1598 lines).

First complete Python run:1851 tests/97.554s, two failures only in old API
inventory/guard structural expectations;2 skipped. Added explicit16 HTTP/1 WS
inventory and direct origin guards, preserving existing policy. Focused contract7
and API14 PASS. Final full rerun in progress; sole MS test/Git window OPEN.
No MR checkout writes, no deployment/performance window.

Second complete Python:1853 PASS (2 environment skips), coverage73%; JS368 PASS;
first full Chromium80 PASS. Final real-route audit found the browser fixture's
broad WS matcher masked /ws/slam versus /api/v1/ws/slam. Correcting live URL and
narrowing fixture to the exact server route. Native localization success is also
being tightened to require post-response fresh corrected pose/tracking, with
separate official callback/native-load and observation results. Final repeat
checks follow these corrections. RGB reservation now reads local active engine
without synchronous broker status on the async viewer route.

Real-route audit correction: exact WS URL and fixture enforced; runtime26 focused
PASS with fresh pose/epoch/timeout cases. Failed localization exposes persistent
result/retry condition. Python3.10 grammar172 files PASS; no runtime dependency
changes. Final complete validation below will supersede prior checkpoints.

## Final local verification / Git window

Final Python1855 PASS (2 environment skips), JS370 PASS, Chromium80 PASS;
coverage73%, Ruff/mypy/syntax/dependency audits/diff checks PASS. Source is frozen;
all internal writers/test servers stopped. VALIDATION.json records local log
hashes; FINAL_REPORT and acceptance matrix separate fixture/live/operational
outcomes. MS Git publication window OPEN; MR remains external until handback.
No equipment/performance window. MAP-02 and stage16 live checks remain BLOCKED.

## Publication

Source commit `72641da309bf041826a70469d6cc32f60a16fe03` published to origin/main after explicit user approval.
Initial automatic push review required direct approval; approval was obtained,
then the same push succeeded. Existing1b0ae5b remains intact. Exact source CI:
[38689015528](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38689015528), running. Both matrices passed setup/static/secret/dependency
checks; Python/JS/E2E completion still required. MS retains publication window
until CI evidence is recorded; no local test runners or device actions.

## CI portability correction

CI38689015528 failed both Linux matrices solely on broker fixture setUp22 errors:
macOS-only /private/tmp did not exist. Changed tests/test_slam_broker.py to use
short /tmp and resolve its canonical path. Product source and workflow unchanged.
Broker22 PASS; full Python Ran 1855 tests in 96.338s, PASS with2 environment skips. Existing JS370/
Chromium80 results unchanged. CI correction publication window remains MS-owned.

## MR shared integration applied; whole-test/local-Git window returned

Base d866a3b; MR dedicated files were applied by MR and preserved. MS changed
app.py, application/runtime.py, tests/test_api_contract_phase8.py and added
tests/test_application_workflow_wiring.py. Registered the additive MR router once;
configured MR after SLAM with the existing runtime and a separate mission-routes
state directory. --mission-native-preview defaults false; no policy proof is
invented. Extracted unchanged competition admission into configure_competition
to keep app.py at1590 lines. Exact inventory:163 HTTP,93 mutations,7 WebSockets.

Focused shared/API/CLI/architecture/SLAM/MR integration51 PASS; competition8 PASS;
changed-file Ruff, configured mypy and diff checks PASS. The shared tests exercise
the actual CLI/call nodes, default/explicit flag, final SLAM hook ordering and live
competition blockers. Actual MS/MR integration fixtures cover running/paused/
canceling exclusion and source generation; they do not establish device evidence.
Log: /private/tmp/robot-scope-ms-shared-integration.log. Initial harness-only AST
location and test-module-name errors were corrected before the passing result.

MR-MS-001/002 source hooks APPLIED and focused checks PASS; coherent full-suite
candidate/commit still pending. MR-MS-003 remains BLOCKED. No shared CI/Nav2/CSS
policy change, device operation or performance measurement. MS writers/runners
are stopped; MR receives the write/full-test/local-Git window next, including the
six MS shared integration/doc files explicitly listed in HANDOFF. Remote push of
d866a3b or descendants remains pending the follow-up user approval; the earlier
approval covered72641da and1b0ae5b only.

## Approved standalone publication and exact CI PASS

This section supersedes earlier approval-pending and running-CI checkpoints.
The user explicitly approved follow-up CI corrections and validation-document
publication. MR returned a short exact-SHA Git window; MS published `d866a3be78b34cbd16c68f3c8cf27e768c491216`
and immediately returned it. [CI38691471690](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38691471690) completed SUCCESS in both
Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12. Each matrix: Python1855
(1 optional rosbags skip), coverage73%, JS370 and Chromium80 PASS; static, secret
and dependency checks PASS. Prior CI38689015528 failure is retained as history.

MS then received a separate five-document window for FINAL_REPORT.md,
ACCEPTANCE_MATRIX.json, VALIDATION.json, PROGRESS.md and HANDOFF.md. Only those
documents are included in this follow-up commit. Exact CI JSON/logs and their
hashes are recorded in VALIDATION. Source is unchanged since the passing SHA,
so existing full local and exact remote checks apply; document consistency,
JSON parsing, secret scan and diff checks are the checks for this unit.

MR dedicated source and shared app.py/runtime.py/API inventory/new workflow
wiring tests remain uncommitted and are excluded from this published candidate.
MR owns their coherent full-suite validation and local integration commit.
The earlier allowance to include MS PROGRESS/HANDOFF in the MR commit is
superseded: those two documents are now included in this MS docs-only commit.
After this publication, MS returns write/full-test/local-Git ownership to MR and
only observes remote CI. No shared CI/Nav2 policy edit, deployment, service
restart, camera takeover, performance run or motion. MAP-02 full retained export,
stage16 live validation and effective planner-policy proof remain BLOCKED;
operational pose application/initial pose/goal/movement remain NOT_RUN.
