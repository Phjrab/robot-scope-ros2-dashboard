# MS / MR handoff

Updated 2026-10-15 KST. Read PROGRESS and FINAL_REPORT (when present).
Preserve experiments, maps, images/bags and hardware/UI/resource work.

## Ownership / windows

- MS owns slam modules/router/scoped UI/tests/docs; sole common integrator for
  app/runtime/index/mapping hooks/scene hook and minimal existing lint fixes.
- MR owns mission coordinator/router, mission_routes modules/scoped UI/tests/docs.
  MR currently drafts outside checkout in /private/tmp/mr-implementation.
- MS checkout write window OPEN; full-test/Git window not yet started. After MS
  independent publication, return write window to MR for dedicated files. Then
  MS applies shared requests after latest MR HANDOFF/INTEGRATION_REQUESTS review.
- MR-MS-001 ACCEPTED/PENDING: router + configure_mission_routes after SLAM/mission
  setup, runtime/mission-routes storage. Runtime field already exists.
- MR-MS-002 ACCEPTED/PENDING: --mission-native-preview opt-in false default,
  pass native_planner_window. No automatic policy proof or Nav2 policy changes.
- No CI workflow edit, equipment deployment or performance window. MS is sole
  full-suite runner/Git publisher until explicit handback.

## Cross-subsystem contract

All transitions use runtime.pipeline_coordination_lock. MS blocks on mission
running/paused/cancel settlement, MR blocks_context_change, Nav, control lease,
capture and lifecycle ownership. Mapping.activity includes MS; legacy mutations
reject MS/MR except exact owned LiDAR save operation. MR start/resume/retry must
require_context_idle under this lock and reserve ownership before release.
Read-only preview uses immutable context_revision.

runtime.slam.navigation_context() projects actual navigation map id/revision/
frame; operational_pose source (localization_pose, normally /amcl_pose), separate
odometry_source (/Odometry), process generation, readiness/state; alignment and
context_revision. Unknowns null, alignment false/transform null. Selected engine
is never operational authority. Schema/methods in ARCHITECTURE.

## Validation / next

Focused suites pass; checkpoint files/tests in PROGRESS. Full suite/exact remote
candidate CI pending. Initial 1b0ae5b preserved; origin eb9026a CI38554448122
failed six lint issues now corrected. Finish runtime/UI review regressions/docs,
full verification, focused main commit/push. Hand back checkout; integrate shared
MR hooks only after MR modules exist. MS does not edit MR dedicated files.

Stage16 BLOCKED: exact candidate/live checkout, current camera/resource handoff,
approved service/environment changes and operator window. MAP-02 BLOCKED: no
verified full retained export beyond visualization cap. LOC-01 actual reuse and
PERF-01 new combined workload unverified. Stage17 NOT_RUN: calibrated camera/body
transform, clock, map alignment/revisions, single authority, motion/loss/stop
proof and explicit approval required before future operational selector. No
apply/initial-pose/goal action.

Latest unit: final camera/runtime/UI ownership regressions done; all internal
writers stopped. MS whole-suite/Git window OPEN. Initial full Python1851 found
only two stale API inventory assertions; updated exact SLAM inventory/direct
origin guards, final rerun running. Additional common test owner:
tests/test_api_contract_phase8.py (MR routes need inventory update later).
Native localize now requires explicit discard_unsaved consent when replacing
an unsaved mapping. app.py1598 lines; preserve<1600 budget in later MR integration.

Verification checkpoint: Python1853 (2 skips), JS368, Chromium80 PASS. Final
real-route audit corrections in progress: exact /api/v1/ws/slam URL and matcher,
fresh post-localize pose confirmation. MS retains window until reruns/publication.

## Final local verification / Git window

Final Python1855 PASS (2 environment skips), JS370 PASS, Chromium80 PASS;
coverage73%, Ruff/mypy/syntax/dependency audits/diff checks PASS. Source is frozen;
all internal writers/test servers stopped. VALIDATION.json records local log
hashes; FINAL_REPORT and acceptance matrix separate fixture/live/operational
outcomes. MS Git publication window OPEN; MR remains external until handback.
No equipment/performance window. MAP-02 and stage16 live checks remain BLOCKED.
