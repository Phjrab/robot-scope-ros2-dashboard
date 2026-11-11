# C0 observation ownership sampling checkpoint

## 2026-11-11 native reader contention follow-up

The user-authorized stationary dashboard trial deployed `00cdb7e` with verified
release contents and preserved configuration/map files. Observation still
invalidated: the retained first failure was navigation `OWNER_LOCK_BUSY`, with
no observed busy component. Exact-session stop completed and the signed bridge
reported STOP latched, no lease, and zero Move requests. This identifies lock
contention; it does not prove which native reader held the lock.

Observation admission and monitoring now give that specific read collision a
100 ms acquisition budget, yielding between fresh copies on the event loop.
The shared pipeline admission lock remains held and an active session retains
its bridge inhibit. No new start or cached idle result is accepted while the
owner is unknown. Actual busy owners, other unreadable owners, bridge guard
loss, and contention that outlasts the budget still fail closed. A latched
failure still requires exact-session cleanup; this is not automatic recovery.

Real-thread regressions cover brief contention at both start and refresh,
event-loop responsiveness, persistent contention, busy work appearing during
retry, and loss of the bridge inhibit. The historical checkpoint below records
the earlier immediate-rejection behavior. Local validation passed: all six
focused regressions, Python 3,748 run / 3,713 passed / 35 skipped (149.284 s),
JavaScript 765 passed, Ruff, configured mypy, tracked-source credential scan
and whitespace checks. Field retest of this follow-up is still pending;
neither Nav2 localization nor autonomous driving is validated.

Result ID: `C0-OBSERVATION-OWNER-SAMPLING-20261109-01`

The preparation UI's “stored 3D localization not applied” message is an execution
state, not proof of a failed map selection. Actual initialization still requires
current sensor evidence, confirmed geometry, Nav2 startup, the user's current
initial pose, and saved-map matching with fresh runtime/TF evidence. This change
does not mark any of those steps complete.

## Implemented scope

Observation admission, monitoring, and the preparation start advisory now copy
in-process ownership on the ASGI event loop while holding the existing pipeline
coordination boundary. Systemd reads remain in the thread executor. Previously,
the ownership copy itself ran in a worker; a reentrant navigation lock held by an
event-loop reader could therefore appear unavailable and reject or invalidate
the observation even without an ownership change.

Unknown ownership is still unknown. Foreign-thread lock contention, unsupported
owner state, actual busy owners, bridge loss and invocation changes continue to
fail closed. No timeout, retry, quality threshold, map selection, sensor source,
calibration, stop gate or motion policy was relaxed.

The first observation owner failure now retains bounded component names,
unknown-reason codes and the sampling monotonic timestamp. Exception text,
paths, lease tokens, maps and point clouds are not included. A clean later sample
does not clear a latched failure. Normal exact-session stop remains available.

## Evidence and limits

- Before the change, a real-executor synthetic test rejected observation start
  while an event-loop reader held the navigation RLock. No ownership fields were
  changed. This is a software reproduction, not proof of the field trigger.
- The first two-test run also had an incorrect test expectation about a
  not-yet-requested handoff receipt. The expectation was corrected to check the
  stop transaction and to verify that new handoff admission is refused.
- Focused observation, bridge, ownership and preparation suite: 74 passed.
- Final full Python suite: 3,427 run, 3,425 passed, 2 optional-dependency skips
  in 138.131 seconds, including all four new real-executor regressions.
- Preparation, draft and observation Node smoke: three test files passed.
- Local synthetic observation browser suite: 32 passed in 2.0 minutes.
- Ruff, configured mypy, tracked-source credential scan and diff whitespace
  checks passed. These are software checks, not field localization proof.
- The precise earlier field trigger remains undetermined because the deployed
  code did not capture the failed component at the time of invalidation.
- Native-worker contention can still invalidate a session. This checkpoint does
  not introduce a grace period or treat an unavailable owner as idle.

## Existing CI failure, separate from this change

Previous commit `d70e58c92e6039be13dea4d485920459ec8218e3`, CI
[42604747963](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42604747963),
completed with failure. It was not rerun.

- Ubuntu 22.04 / Python 3.10: `test_session_timeout_invalidates_generation_cancels_capture_and_clears_pose`
  did not observe the synthetic worker's expected `SENSOR_CANDIDATE` state.
  The exact scheduling or implementation cause is unconfirmed.
- Ubuntu 24.04 / Python 3.12: three `pre_nav_draft.spec.mjs` cases timed out
  clicking the disabled map-pair button. Those cases omit the explicit pairing
  confirmation checkbox introduced by d70e58c. They remain unrepaired here.
- Competition offline integration passed. Later skipped steps are not passes.

## Device and remaining work

No deployment, observation start/stop, INITIAL POSE, Nav2 start, matching start,
goal or movement was performed for this checkpoint. Existing physical trial
windows are not reused. The user requested finishing only the current work.

The last read-only device release was `59714317c5abefca43b25fe8c78015f7843f387c`,
which contains newer functionality absent from the C0 branch. A future deployment
must reconcile and preserve that actual base, including its manual-2D guards;
old deployment scripts must not be run against it unchanged. Full live source and
protected-file verification, a reviewed deployment/recovery package, CI failure
resolution, current user pose confirmation, and a fresh stationary test window
remain prerequisites. Stored 3D localization is still not applied on the device.
