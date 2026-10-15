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
