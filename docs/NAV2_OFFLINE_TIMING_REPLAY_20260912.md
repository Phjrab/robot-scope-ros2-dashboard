# Nav2 300 ms input timeout and offline replay

The operator deferred further live validation until a later approval. This
follow-up exercises the real `NavigationRosGateway` and `ControlManager` with
synthetic time, sensor readiness and ROS-shaped input messages. Emitted commands
are captured in memory. No ROS node, UDP transport, remote service, deployment,
initial pose or robot goal is used by the new test fixture.

The operator independently applied `708a683-nav300-20260912` and restarted the
dashboard. Read-only inspection found its `control.py`, `config/go2.json` and
`navigation_gateway.py` hashes matched the local change before the subsequent
default adjustment below. Existing rejection timing diagnostics are retained.
The operator's source-specific timeout change and our diagnostic work do not
overwrite each other.

At the operator's further request, Nav2 now defaults to 300 ms even without an
explicit `navigation_command_timeout_s`. The Go2 profile explicitly selects
300 ms. Manual input still uses 200 ms; the robot-side Bridge has its separate
200 ms receive watchdog. The public `/control` projection's `command_timeout_s`
is the manual-input value and does not currently expose the separate Nav2 field.

## Results

The 13 tests in `tests/test_navigation_command_timing.py` cover both the default
profile and the actual Go2 profile at 300 ms:

| Scenario | Result |
| --- | --- |
| 10 Hz commands, 20 Hz control ticks, five virtual seconds | Lease and goal remain active; requested forward velocity reaches 0.035 m/s under the existing 0.35 scale. |
| Next command at 299.999 ms | Accepted; lease remains active. |
| One omitted 10 Hz sample, next command at 201 ms | Accepted; ordinary cadence resumes under the same lease. |
| Next command at 301 ms | Command timeout, goal canceled, stop output before cancellation request. |
| Watchdog tick expires before the 301 ms callback | Original timeout remains visible in rejection; late command cannot resume the session. |
| Command arrives after 100 ms, then waits 250 ms for the operation lock | Timeout; journal shows 0.250 s lock wait and 0.000 s processing. |
| Command arrives after 100 ms, then sensor publisher check takes 250 ms | Timeout; journal shows 0.000 s lock wait and 0.250 s processing. |

The three injected-delay paths also verify inactive lease, canceled goal, stop
output preceding the asynchronous cancellation request, and refusal to resume
when another fresh callback arrives. `test_navigation_timeout_configuration.py`
covers exact 300 ms Nav2 expiry, default/upper bound, independence from manual
configuration, client age validation, manual 200 ms expiry and the Bridge cap.

## Interpretation

At a nominal 100 ms command period, a 201 ms gap is tolerated by the current
Nav2 configuration. A 301 ms gap still cancels the goal. These are synthetic
sequences; they do not establish what delayed the previous live command.

The Bridge receive watchdog and Nav2 input freshness measure different ages.
The dashboard can continue emitting a still-valid Nav2 drive on each control
tick; these fresh receipts keep the Bridge watchdog alive. Thus its 200 ms cap
does not turn the upstream 300 ms input budget back into a 200 ms budget.

The diagnostic fields distinguish lock wait from work performed after lock
acquisition in these replays. A long previous-submission age with short lock and
processing times places the unexplained delay before method entry. It cannot
separate publisher timing, DDS delivery, executor scheduling, or the publisher
count check at the start of the command callback. RMW receive timestamps were
unavailable in the earlier deployed environment, so those must not be invented.

## Next live evidence, deferred

The last inspected deployment is the operator's `708a683-nav300-20260912`.
Its explicit Go2 300 ms setting already selects the same timeout as the new
local default. No additional deployment or restart was performed in this
follow-up. After future approval, capture the rejection journal
entry and matching goal id/times for one supervised operator-selected goal.
Compare the three timings before choosing a scheduler, transport or callback
change. If time is unexplained before submission, collect command-callback or
publisher timing evidence before assigning a root cause.

No automatic goal submission or lease reacquisition is added.

The repeatedly timing-out supervisor ordering test now allows ten seconds for
its local shell subprocess. Its ordering assertions are unchanged; this
test-harness timeout does not change any runtime watchdog.

## Final checks

- Focused control, source-specific configuration and timing replay: 51 passed.
- Full project-venv Python discovery: 1422 tests, OK (one Linux-only skip).
- JavaScript unit tests: 293 passed.
- Required system Python discovery: 1405 tests, two missing-dependency import
  errors (FastAPI and Pydantic), one skip. The supervisor ordering test now passes
  in full discovery; its earlier two-second harness timeout was the flaky item.
- Full Python runs were sequential. `git diff --check` passed.
