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

## MR apply window while publication approval is pending

MS local head d866a3b (only portable broker fixture + validation docs after source
72641da). Follow-up remote publication awaits explicit user approval. All MS
writers/runners/Git commands stopped. MR is granted the next dedicated-file copy
window only; no MR full suite/Git until copy completion. MR then returns a short
shared-hook window to MS for accepted MR-MS-001/002 and exact API inventory.
Preserve this MS handoff update and all MS dedicated files. Deployment/performance
windows remain closed. Publication will resume only after ownership returns.

## Current window: MR writes / whole tests / local Git

This section supersedes earlier window paragraphs. Shared integration is applied
on d866a3b after the MR35-file copy. MR-MS-001/002 now have source hooks and focused
validation; full combined candidate verification remains pending. MS modified:

- robot_dashboard/app.py
- robot_dashboard/application/runtime.py
- tests/test_api_contract_phase8.py
- tests/test_application_workflow_wiring.py (new)
- docs/multi-slam/PROGRESS.md
- docs/multi-slam/HANDOFF.md

Router is registered once; configure_mission_routes follows configure_slam and
receives the same runtime, navigation-runtime/mission-routes and an explicit CLI
flag defaulting false. Competition construction moved to runtime helper without
changing five live blockers or SAFE_STOP; app1590 lines. No fabricated policy
provider. HTTP163/mutations93/WS7. Focused51 plus competition8 PASS; Ruff, configured
mypy and diff checks PASS. Test log /private/tmp/robot-scope-ms-shared-integration.log.
Full Python/JS/E2E of the combined source is assigned to MR only.

MS stops writers/runners/Git and returns the window to MR. MR may include these
six exact MS files with its dedicated files in the coherent local integration
commit after required whole checks; do not publish an intermediate shared-only
commit with missing dependencies. MR owns minimal legacy-details-open test
compatibility edits in tests/e2e/dashboard.spec.mjs and reusable_points_orders.spec.mjs.
MR updates its own request statuses/docs and reports the exact candidate SHA,
results and handback. No other MS files may be edited without a new handoff.

d866a3b and all descendant remote publication remain awaiting the follow-up user
approval; MR must not push that history via another tool. No deployment/service/
camera/performance window. MAP-02, stage16 hardware and MR effective-policy proof
remain BLOCKED. Operational pose application and movement remain NOT_RUN.

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
