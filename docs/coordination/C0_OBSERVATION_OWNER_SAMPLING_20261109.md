# C0 observation ownership sampling checkpoint

## 2026-11-11 status-file I/O fix

After restoring the native dependency link, release `5a28dd2` reported a running
XT16 preview and one publisher each for `/velodyne_points` and `/imu/body`.
Three idle ownership samples all identified the `jobs` lock, with concurrent
`NavigationJobManager.snapshot()` / `_missing_prerequisites_locked()` frames at
`path.lstat()`. This establishes a blocking filesystem operation inside the
ownership lock, independently of any real navigation start.

The advisory snapshot now probes constructor-configured prerequisite paths
outside that lock, then copies current process state under the lock. Actual
start admission still rechecks prerequisites under its lock. Missing files,
permissions, closing state and parameter errors retain the same availability
checks. No cached result or bypass of process ownership is introduced.

A real-manager regression holds `Path.lstat()` in another thread. The old
snapshot produces unknown navigation ownership; the new snapshot permits an
idle ownership read, still reports a subsequently started process as busy, and
returns the latest closing/process state after the file probe finishes.
The old implementation failed this exact regression; the modified navigation
manager suite passed all 19 tests. Full Python validation passed: 3,750 run,
3,715 passed, 35 skipped in 148.790 seconds. Seven navigation JavaScript smoke
files, Ruff, configured mypy, credential scan and whitespace checks also passed.
Field verification on exact release `75dc81348c907d7c53def48b39ae8343940c7cae`:
46 samples over 93.305 seconds were all `READY`, with no owner failure, signed
bridge inhibit `HELD`, STOP latched, no control lease, and zero Move requests.
Fresh paired `/Odometry` and `/cloud_registered` preparation evidence passed.
The dashboard then stopped the exact session: `STOPPED`, inactive, not busy,
no remaining bridge guard, STOP still latched, no lease and zero Move requests.
This is a bounded stationary observation pass, not Nav2 or autonomous-driving
acceptance. Map-relative height/tilt and the user's current pose still need
confirmation. No INITIAL POSE, Nav2 start, goal, STOP clear or motion was sent.
The separate small-first-feedback progress defect remains unrepaired.

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
and whitespace checks.

Field retest of `b575b43` did **not** pass: it remained `WAITING_INPUTS`, then
latched navigation `OWNER_LOCK_BUSY` after about 32 seconds of sampling. The
bridge inhibit remained held. Exact-session stop completed with STOP latched,
no lease and zero Move requests. This budget does not resolve the field issue.

The diagnostic follow-up distinguishes the startup, process-manager and gateway
locks, retaining the first failing lock plus at most 12 concurrent code locations
from those three modules. Locations contain only component, function and line;
no paths, thread locals, tokens or sensor payloads. Concurrent frames are clues,
not proof of which thread owns a lock. Admission rules and the read budget stay
unchanged. FAST-LIO input readiness remains a separate unresolved field issue;
neither Nav2 localization nor autonomous driving is validated.

The input wait was subsequently traced to a deployment omission: both new
release directories lacked the original release's `workspaces` symlink to the
existing native build. The XT16 bridge launcher therefore exited during startup;
the dashboard saw no `/imu/body` publisher and no `/velodyne_points`. The follow-up
deployment must preserve both `.venv` and `workspaces`, check the existing XT16
executable, and verify preview health and both publishers after restart. This is
a deployment repair, not a sensor calibration or estimator change. The diagnostic
candidate passed Python 3,749 run / 3,714 passed / 35 skipped (149.677 s), five
observation JavaScript smoke files, Ruff, mypy and tracked-source credential scan.

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
