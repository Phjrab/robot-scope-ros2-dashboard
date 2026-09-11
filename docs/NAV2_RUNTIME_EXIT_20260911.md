# Nav2 stationary follow-up: ROS runtime exit

## Observed on deployed bfcedf4

- After a no-goal session stopped, the dashboard HTTP process remained alive
  but `/api/v1/state` reported `agent_ready=false` and
  `InvalidHandle: cannot use Destroyable because destruction was requested`.
- Control reported `configured=false`, `available=false`, no active lease,
  and zero command. Cached bridge ready/connected flags remained true despite
  a status age exceeding 190 seconds. These cached flags are not freshness proof.
- The robot remained reachable by ping and SSH. The onboard bridge journal
  reported UDP `Connection refused`. No stack trace for the ROS failure was
  present in the dashboard journal.
- The ROS agent exception handler exits into navigation deactivation and
  control transport shutdown; this explains the closed socket. The particular
  handle and originating callback are not yet established. Dynamic subscription
  destruction is an investigation lead, not a confirmed root cause.

## Recovery and stationary verification

- Dashboard service restart restored agent readiness and fresh control status.
- The first navigation startup failed with `XT16 PACKETS STALE` during preview
  startup. Preview subsequently reported readiness; a later attempt started.
- The operator sent the initial pose. A 60-second localized READY observation
  collected 66 snapshots, with maximum odometry arrival gap 0.114999 seconds
  and source gap 0.100143 seconds. Translation and heading jump counts were zero.
- No new motion/action evidence was observed. Navigation stop and lease release
  passed, and a subsequent HTTP read confirmed agent ready, no runtime error,
  navigation idle, fresh control status and zero command.
- RMW receive metadata remained unavailable (1975 missing observations); this
  run does not establish DDS-level latency or prove actual navigation motion.

## Diagnostic change

Fatal ROS runtime errors now log exception class and traceback frame locations
to the journal, without logging exception values, source lines or locals. The
existing status error remains unchanged. Tests cover raised and traceback-less
exceptions, value exclusion, and the agent's stop/cleanup path after spin failure.

No exception retry, watchdog relaxation, motion command, source selection or
automatic service restart is added. This change improves evidence collection;
it does not fix or establish the cause of InvalidHandle. Deployment is separate
from publication. Next: deploy the diagnostic release with authorization, repeat
stationary start/stop transitions, and use any captured call path to target a
regression test and fix. Goal-cancellation investigation remains open as well.

## Local verification

- ROS-focused discovery: 118 tests passed.
- Project virtual environment full discovery: 1401 tests, OK (one Linux-only skip).
- JavaScript unit suite: 293 passed.
- Required system `python3 -m unittest discover -s tests -v`: 1384 tests,
  two import errors for absent system FastAPI/Pydantic dependencies, one skip.
  Full discoveries were run serially to avoid shared test-fixture collisions.
- `git diff --check`: passed.
