# Robot Scope integration handoff — stopped after40

Latest device check at2026-10-15T12:19:36Z confirms the separately deployed UI
a67c5f5, HTTP200, unchanged post-reboot service invocations and54 preserved maps.
Policy source a328879 remains undeployed. See the follow-up validation record.

User-requested software continuation within40: bounded policy failure diagnostics
and partial-dispatch future cleanup are implemented and regression-tested. The new
backend is not deployed; the last successful device/UI snapshot is1656e4d with the backend invocation
from863682e. An access recheck failed; after the user reported reboot, the12:10:57Z check
restored HTTP200 with clean1656e4d checkout, new service invocations and idle/zero
control state. Initialpose count reset to0; no pose was replayed. See [POLICY_DIAGNOSTICS_FOLLOWUP.md](POLICY_DIAGNOSTICS_FOLLOWUP.md)
and [POLICY_DIAGNOSTICS_VALIDATION.json](POLICY_DIAGNOSTICS_VALIDATION.json). Separate
UI edits appearing during this continuation are preserved and excluded from this
policy publication. Exact a328879 CI38732453021 passed on both Linux jobs
(1998 Python with1 skip,381 JS,100 Chromium). No new localization window or41–43
action was performed.

Stages30–36 software integration and the authorized stage40 deployment/localization window are finished. Candidate863682e was deployed; existing initialpose1 and180s stationary observation completed, with goal/motion0 and owned cleanup confirmed. Full live acceptance and SOFTWARE_CLOSURE remain false. Actual policy evidence was unavailable; full TF authority and independent map alignment remain unproved. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md).

The user additionally requested the current dashboard UI changes, explicitly choosing the global control-status HUD and its SOFTWARE STOP only in Settings (the existing Controls-page STOP remains). UI381 JS/96 Chromium/83-module syntax checks passed; commit1656e4d was applied without restart and all3 HTTP static hashes matched. See [UI_ACCEPTANCE.md](UI_ACCEPTANCE.md). This does not reopen localization or41–43.

Smallest next work: apply the diagnostic candidate in a qualified current window,
isolate effective parameter/lifecycle readback using its bounded reason, then
implement qualified policy ingestion/enforcement. NativePlanner product execution,
MS native map reuse and complete retained-map export still require their own
qualified native conditions. Historical stale startup cause remains unconfirmed.
No follow-up is scheduled.

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
