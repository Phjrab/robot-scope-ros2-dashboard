# Reboot follow-up: proposal gate and raw-capture ownership

Date: 2026-11-12, Asia/Seoul. Base main: `1c288c2d29e33e80c43e2a6e35b95b2400f8cab7`.
The existing clean main checkout was fast-forwarded from `4b244d4`; both base
CI and I0 were re-read as successful. No branch, worktree or PR was created.
The supplied prompt pack and current AGENTS.md were read. Historical stationary
acceptance is not evidence of the current reboot, physical stop or localization.

## Current-session observations

- Read-only HTTP access and the user's in-app browser were available. No page
  reload, observation POST, INITIAL POSE, Nav2 start, match, goal, STOP clear,
  service restart or deployment was issued by the agent.
- The signed control bridge reports release
  `75dc81348c907d7c53def48b39ae8343940c7cae`. Served `preparation.js` exactly
  matches that Git blob (SHA256
  `7bb119b341d5447e14e7ff9bad3a10ad196826360552e9e693b3c84e9c7ea7c9`).
  Full dashboard process cwd/import hashes and dependency links remain unchecked:
  no usable current SSH authentication was established. Static-asset equality
  does not prove the whole dashboard release.
- Initially the browser and server had no selected 3D pair or user draft.
  While the agent read the page, external user interaction established the
  confirmed `map_20261109_1` / `map_20261109_1_edited` pair and a new unsent
  draft. No historical coordinates were restored by the agent.
- The current profile/binding readback is `go2-onboard`, `fastlio_body`,
  `/robot_scope/nav/controller_odom_fastlio`. Nav2 and goal were idle;
  INITIAL POSE confirmation was null. Map-relative height/roll/pitch were absent.
- During 18:26:39.893–18:26:56.345 KST, 60 DOM samples showed the observation
  start button switching disabled/enabled and opacity 0.45/1 with unchanged
  STOPPED state, can_start=true, empty blockers and matching pair generation.
  Label/display/background/color stayed constant. The browser tool did not
  expose Resource Timing, so request start/end correlation was NOT captured.
  This is a bounded visual reproduction, not complete causal network evidence.
  The user subsequently judged this button acceptable and redirected diagnosis;
  no frontend behavior or styling was changed.

## Why proposal calculation and driving were blocked

At 18:29 KST the observation was READY, the signed inhibit was HELD, paired
cloud/pose evidence was valid, but the draft's stationary-current-pose checkbox
was unchecked. `operatorPriorInput()` returns incomplete until the user confirms
that exact draft revision. Consequently `proposalReadyToRequest` is false.
The agent did not make that physical/positional attestation for the user.

At 18:30:55 KST the checkbox was checked, but the observation had become
INVALIDATED. Retained first failure:

```json
{
  "reason": "OBSERVATION_OWNER_CHANGED_OR_UNKNOWN",
  "owner_failure": {
    "sampled_monotonic_s": 448.147641287,
    "busy_components": [],
    "unknown_components": ["raw_capture"],
    "unknown_reasons": {"raw_capture": "OWNER_LOCK_BUSY"}
  }
}
```

The session had started at monotonic 285.683623, so this failure occurred about
162.464 seconds later. This is a new raw-capture lock failure, not proof that the
previous navigation/jobs filesystem fix regressed. Later ownership readback was
clear with raw_capture record=null/in_flight=false; that does NOT clear the
latched session failure or authorize a new start.

SOFTWARE STOP was latched (`operator_start_stopped`), lease inactive, bridge
process Move count zero. Observation remained active/busy with signed inhibit
HELD and exact-session stop available. Body motion evidence was INVALID; actual
physical stop is UNKNOWN. The agent neither ended this user-started session nor
released its inhibit.

The extra Nav2 `bridge_or_lowstate_unavailable` / `robot_offline` flags are not
independent physical-disconnect evidence here. `ControlTransport.status_callback`
intentionally suppresses manager bridge readiness while an observation inhibit
is retained. Navigation uses that readiness for both its blocker and robot_online,
while the signed transport readback still reports connected/ready with fresh
LowState. No readiness/safety rule is relaxed by this candidate.

## Software reproduction and candidate

`PointCloudHub` supplied its broad telemetry/context lock to the raw capture
latch. A real thread held that lock inside `raw_context_snapshot()` while copying
the context. The real ownership reader then raised OWNER_LOCK_BUSY with both
an idle latch and a pending capture. The regression failed against the unchanged
production implementation. This demonstrates a reachable software cause; the
field receipt did not identify the specific holder of the shared lock.

The candidate gives the raw capture latch its own RLock. Source-dependent
request/begin/finish/reset still hold hub-context then latch locks, and the latch
never acquires the hub lock. All capture record/in-flight mutations remain under
the latch lock. The same regression now reads idle or pending-busy correctly;
actual latch contention still raises UNKNOWN. No cached idle, retry extension,
ownership bypass, freshness relaxation or automatic recovery was introduced.

Local Windows/Python 3.12 validation:

- New real-thread regressions: 2 passed after the change; context-reader case
  failed before it with OWNER_LOCK_BUSY (both idle and pending subcases).
- Raw capture file: 21 run, 16 passed, 5 errors from Linux-only `resource` import.
  Before changes: 19 run, 14 passed, the same 5 import errors. These are not skips
  or passes. The ownership tests load the pure source module directly to avoid
  unrelated application package initialization; they do not mock ownership.
- Full `python -m unittest discover -s tests -v` attempted on Windows: import
  errors and a stalled worker test; no full-suite pass is claimed. Linux CI is
  required before considering deployment. No fake resource module was supplied.
- Related JavaScript: 13 passed. Browser mock regressions: 5 passed (draft
  attestation, exact-session stop during read, overlapping blocked/unblocked/read
  failure). Initial sandbox browser launch did not progress; the rerun outside
  the sandbox used localhost fixtures only and passed in 10.5 seconds.
- Ruff, configured mypy, tracked-source secret scan and diff whitespace passed.

## Deployment boundary and next task

This is a source candidate only. Device still reports the old bridge release;
no field pass is claimed for the new lock boundary. Full Linux CI, authenticated
read-only process/dependency verification, exact old release/selector recovery
details and current-session deployment approval are still required. Preserve both
`.venv` and `workspaces` links, maps and settings. Do not deploy from mutable main.

Next operational task: obtain authorization for normal exact-session termination
of the invalidated user-started observation, then verify inactive/guard released,
STOP still latched and no lease. Do not clear STOP to make proposal calculation
available. Subsequent observation or movement needs its own current scope.
The small-first-feedback progress defect remains unfixed. No autonomous-driving
or saved-map localization acceptance was performed.
