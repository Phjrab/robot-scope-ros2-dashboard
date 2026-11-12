# Reboot follow-up: proposal gate and raw-capture ownership

Date: 2026-11-12, Asia/Seoul. Base main: `1c288c2d29e33e80c43e2a6e35b95b2400f8cab7`.
The existing clean main checkout was fast-forwarded from `4b244d4`; both base
CI and I0 were re-read as successful. No branch, worktree or PR was created.
The supplied prompt pack and current AGENTS.md were read. Historical stationary
acceptance is not evidence of the current reboot, physical stop or localization.

## Initial read-only phase (before the later supervised trial)

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

At 18:44:40 KST a fresh GET readback showed STOPPED, inactive, not busy,
guard=null, STOP still latched, no lease and bridge Move count zero. The agent
sent no stop command; the ending action was external to the agent. The original
raw-capture failure remained retained. This is not physical-stop evidence.

Next task: establish authenticated read-only SSH access and verify the actual
dashboard process/release and its recovery selector/dependency links before
requesting deployment of the tested candidate. Do not clear STOP to make proposal
calculation available. Subsequent observation or movement needs its own current scope.
The small-first-feedback progress defect remains unfixed. No autonomous-driving
or saved-map localization acceptance was performed.

## Candidate publication and Linux verification

Code candidate `8d541acc0b8ed1fa581389a78d37e8f860500cfa` was committed and
pushed normally to origin/main. The following follow-up documentation does not
change the code candidate or claim that it was deployed.

- Linux Python 3.10 and 3.12 each ran 3,752 tests: 3,717 passed and 35 skipped,
  with zero failures/errors (239.345 s and 204.357 s). Both new real-thread
  regressions are present and passed in those full-suite logs.
- Both Linux hardware-free jobs passed their 765 JavaScript tests, static
  checks and real-API browser fixtures.
- Exact-candidate [CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43193099446):
  success, all 7 jobs successful; final run status re-read at 18:49:53 KST.
- Exact-candidate [I0](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43193099462): success.
- Source archive created with `git -c core.autocrlf=false archive --format=tar`
  against the exact candidate: 2,734 files, every content blob matched Git;
  SHA256 `eac36da8ac560ce6502cd451f10ab08c7a193232d8a3442179fac6c44b7b06a1`.
  The first Windows-default archive had 2,304 byte mismatches due to autocrlf;
  it was rejected and marked REJECTED-CRLF, never sent to the device. Repository
  or global Git settings were not changed. Neither source archive contains the
  device's `.venv` or `workspaces`; those still require actual dependency checks.

Windows full-suite attempt was bounded at 120 seconds and terminated without
completion; this remains an environment failure, not a local full-suite pass.
Successful Linux CI is separate evidence and does not erase that failed attempt.

## Later proposal report and explicitly approved stationary trial

The following supersedes the earlier no-observation-POST statement only for the
explicitly approved trial. Deployment and service restarts remain unapproved.

### User-triggered calculation before the trial

The latest user-triggered global job `10ab357c4894f6d301ff4bc4` completed in
15.744 seconds with `state=succeeded`, no worker failure and no cancellation.
It retained 11 candidates and `AMBIGUOUS_ALTERNATIVES` /
`AMBIGUOUS_UNVERIFIED_ESTIMATE`. Worker success is not accepted localization,
nor proof that the UI accepted a conditional candidate.

At 18:53:13 KST the UI had already discarded the proposal with the generic
map/observation-context-changed message, while the unsent draft was stale and
its stationary attestation was unchecked. A later proposal GET returned
`OPERATOR_PRIOR_EXPIRED`; this later expiry cannot explain the earlier event.
The UI deliberately invalidates a draft-linked proposal when the draft, pair,
source epochs or observation session changes. Blur/hidden-page suspension is
one possible trigger, but the user did not recall changing focus and no
contemporaneous focus event was captured. Its role in this field failure is
UNCONFIRMED. The existing local browser blur regression passed; that establishes
the software mechanism, not the user's actual event sequence.

By 18:57:37 KST that observation, `1e238ac6ca784462925b577f02421674`, was
INVALIDATED with `CONTROL_OWNER_UNKNOWN_DURING_OBSERVATION`. This later latched
failure is separate from the first generic proposal-discard message.

### Authorized retry and cleanup

The user explicitly confirmed current on-site stop supervision and authorized
exact-session observation stop, one new observation with STOP maintained, and
one proposal calculation. INITIAL POSE, Nav2, STOP release and motion were
excluded. The user was to set and attest a fresh current draft directly.

- At 19:01:14 KST the old exact session was re-read as INVALIDATED, active/busy,
  guard HELD. The agent used the normal observation-stop UI once. By 19:02:52,
  readback was STOPPED, inactive, not busy, guard absent, STOP latched, no lease,
  bridge Move count zero.
- The agent used the normal observation-start UI once. New session
  `908ba5fee65949df976341e4a9dbfb3b` was READY with guard HELD at 19:03:18.
  Pair generation remained `0a69d2f8551b414a88253261a96fab00`, with the same
  confirmed `map_20261109_1` / `map_20261109_1_edited` revisions. No coordinates
  were restored or attested by the agent. Calculation remained disabled because
  the old draft was stale and its checkbox unchecked.
- At 19:05:15.501 the sampled DOM changed to INVALIDATED. The retained first
  failure was `OBSERVATION_OWNER_CHANGED_OR_UNKNOWN`, monotonic
  `2550.137716078`, no busy components, unknown component `raw_capture`, reason
  `OWNER_LOCK_BUSY`. This reproduces the raw-capture failure on the existing
  device setup; the candidate lock fix has not been deployed or field-validated.
- No proposal calculation was submitted in this trial. The failed session was
  cleaned up with one normal exact-session stop. At 19:05:46 the UI showed
  STOPPED, inactive, not busy; the API confirmed guard=null and retained the
  failure diagnostic. Final control readback retained STOP=true, lease=false,
  Move count zero, signed bridge release `75dc81348c907d7c53def48b39ae8343940c7cae`.
  These are software readbacks, not measurements of physical stop.

The user's later response that they would enter the draft arrived after cleanup;
they were informed that observation had failed and calculation could not proceed.
No second start, INITIAL POSE, Nav2, goal, STOP release, device deployment or
service restart was performed. Code candidate remains
`8d541acc0b8ed1fa581389a78d37e8f860500cfa`; full dashboard process identity remains
unverified without authenticated SSH.

Next single task: establish authenticated read-only access to verify the actual
dashboard release and both `.venv`/`workspaces` links and recovery selector,
then present the exact tested candidate and recovery plan for deployment approval.
Do not repeat observation to work around the unresolved ownership failure.

For this documentation-only follow-up, related JavaScript tests passed 19/19
and `git diff --check` passed. The full Windows unittest command was rerun:
test-loader errors appeared and the worker test stalled; the 120-second bound
expired without a suite result. The attempted process-tree cleanup was denied
inside the sandbox, and a subsequent permitted process inventory confirmed no
Python processes remained. This attempt is not a pass or a skip. The unchanged
code candidate's successful Linux CI above remains separate evidence.
