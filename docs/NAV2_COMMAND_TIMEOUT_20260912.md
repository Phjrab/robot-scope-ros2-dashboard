# Nav2 goal cancellation: command timeout evidence

On deployed eafce22, the operator sent goal
`43e80f70ccf7a30587e521dec35dad72` to approximately
(-0.4002, 3.5092, yaw 1.5564), after stationary localization was READY.

The runtime log records navigation beginning at 2026-09-12 01:29:42.445 UTC,
controller startup at .466, and cancellation at .867-.868. The goal snapshot
contains `navigation command rejected: invalid or expired control lease:
command_timeout`, initial/remaining distance 1.693 m and navigation feedback
time 0.271 seconds. `first_nonready_health` is null. Five nonzero bridge
publications were reported for motion run 1, with maximum requested forward
velocity 0.035 m/s; publication counts are not proof of actual displacement.

The goal was already canceled with no active lease and a zero command when
inspected. Navigation was explicitly stopped, then idle mode, inactive lease
and zero command were confirmed. No replacement goal was sent.

## Confirmed versus unknown

ControlManager expires an outstanding deadman drive when its age reaches
0.2 seconds. A later submission checks this expiration before accepting a new
drive. Lease heartbeat and drive freshness are separate: merely increasing
heartbeat frequency is not a demonstrated fix. The inactive localization-health
snapshot after cancellation is a consequence of deactivation, not proof that
localization caused this cancellation.

The current evidence does not distinguish controller publication delay, DDS
delivery delay, executor scheduling, operation-lock contention or synchronous
checks inside the submission path. No specific one is established as root cause.

## Added journal diagnostics

Only on ControlError in nonzero velocity submission, record exception class and:

- `lock_wait_s`: submission method entry to control operation lock acquisition.
- `processing_s`: lock acquisition through rejection (includes manager snapshot,
  interlock checks and submission).
- `previous_submit_age_s`: rejection minus the previous successful submission's
  completion timestamp; `unavailable` before any previous submission.

All times use the dashboard monotonic clock. These are NOT source/DDS timestamps
and do not measure delay before this method is entered. The last field is not an
exact copy of the manager drive age. No tokens, velocities or exception values
are journaled. No retry, timeout change, callback-group change, automatic goal or
lease reacquisition is added. Unit tests verify timing values, absent prior
submission, redaction and one submission followed by deactivation.

Next live evidence requires deploying this diagnostic change and an explicitly
supervised operator goal. Publication alone does not update the Jetson service.

## Local verification

- Gateway suite: 21 tests passed. JavaScript unit suite: 293 passed.
- Project virtual environment full discovery: 1402 tests, OK (one Linux-only skip).
- Required system Python discovery: 1385 tests, three errors (FastAPI/Pydantic
  missing and a two-second supervisor subprocess timeout), one skip. The timed-out
  supervisor test passed on a separate system-Python rerun in 1.217 seconds.
- Full discoveries ran serially. `git diff --check` passed.
