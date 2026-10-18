# Integration progress — through40

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
