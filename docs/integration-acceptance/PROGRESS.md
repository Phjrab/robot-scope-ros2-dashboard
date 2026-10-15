# Integration progress — through40

The user reopened software investigation within40. Bounded policy observer
diagnostics now survive incomplete readback, optional gateway setup/readback
failures preserve STOP, and partial request dispatch cleans up every owned future.
See [POLICY_DIAGNOSTICS_FOLLOWUP.md](POLICY_DIAGNOSTICS_FOLLOWUP.md) and its exact-byte
[validation record](POLICY_DIAGNOSTICS_VALIDATION.json). This source is not deployed;
the read-only device check confirms the earlier UI/backend invocations. Separate
UI changes appearing during validation remain untouched and excluded. No live row
is promoted; no localization retry or41–43 action was initiated.

Stages30–36 software integration and the authorized stage40 deployment/localization window are finished. Candidate863682e was deployed; existing initialpose1 and180s stationary observation completed, with goal/motion0 and owned cleanup confirmed. Full live acceptance and SOFTWARE_CLOSURE remain false. Actual policy evidence was unavailable; full TF authority and independent map alignment remain unproved. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md).

The user additionally requested the current dashboard UI changes, explicitly choosing the global control-status HUD and its SOFTWARE STOP only in Settings (the existing Controls-page STOP remains). UI381 JS/96 Chromium/83-module syntax checks passed; commit1656e4d was applied without restart and all3 HTTP static hashes matched. See [UI_ACCEPTANCE.md](UI_ACCEPTANCE.md). This does not reopen localization or41–43.

Smallest next work: use the bounded diagnostics in a qualified current runtime
window to isolate effective parameter/lifecycle readback, then implement qualified
policy ingestion/enforcement. NativePlanner product execution, MS native map reuse
and complete retained-map export still require their own qualified native conditions.
Historical stale startup cause remains unconfirmed. No follow-up is scheduled.

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
