# Current non-driving results — 2026-10-16

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
