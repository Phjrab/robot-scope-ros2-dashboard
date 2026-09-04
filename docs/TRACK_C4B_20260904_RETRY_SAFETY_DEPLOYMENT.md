# Track C4B retry safety deployment

Date: 2026-09-04

```text
TWO_METRE_GOAL_NOT_SENT
SAFETY_LIMITS_NOT_BYPASSED
LOW_SPEED_PROGRESS_FIX_DEPLOYED
FOXY_FLOAT32_TELEMETRY_FIX_DEPLOYED
SIGNED_STOP_HANDOFF_ACK_DEPLOYED
GOAL_SUBMISSION_COUNT_0
MOVE_REQUEST_COUNT_0
ROBOT_MOTION_NOT_RUN
FRESH_GOAL_APPROVAL_REQUIRED
```

## Decision

The requested immediate 2.0 m retry was not executed.  The only physically
confirmed corridor from the preceding C4B attempt was 0.40 m, and increasing
the goal distance would not increase the configured speed.  The existing
velocity clamps, watchdogs, freshness checks, publisher cardinality checks,
lease/deadman rules and exact-zero cleanup therefore remain unchanged.

Instead, the retry blockers that could be corrected without motion were
implemented and deployed.  No Navigation session, initial pose, goal, ARM,
deadman input, non-zero command or robot action was used during this work.

## Deployed implementation

The deployed release includes these focused commits:

- `718a625`: preserve the first Navigation health fault and evaluate bounded
  cumulative progress for supervised low-speed goals;
- `ee315d2`: accept the real Foxy `numpy.float32` SportModeState velocity
  representation without broadening the bounded numeric contract;
- `0921b4f`: require a signed exact-Stop handoff and matching Bridge ACK before
  a restarted UDP dashboard can become control-ready.

The handoff ACK is source-, sequence-, type- and Bridge-epoch-specific.  A
local UDP send is not sufficient for readiness, missing ACKs retry only Stop,
and delayed status from a retired Bridge epoch cannot restore readiness.
Drive or action packets rejected by the existing guards do not create a false
ACK.  ROS transport behavior was not changed.

## Verification before deployment

The final implementation verification produced:

- focused control transport and Bridge tests: 48/48 passed;
- complete Python suite: 1022/1022 passed;
- JavaScript suite: 270/270 passed;
- browser E2E: 32/32 passed;
- configured mypy targets, Ruff, Python compilation, tracked-source secret
  scan and `git diff --check`: passed.

GitHub Actions run `33841258343` had an overall `failure` conclusion despite
completing the Ubuntu 22.04/Python 3.10 matrix successfully.  The Ubuntu
24.04/Python 3.12 matrix was retried once, but both
attempts stopped at `npm audit` after the npm registry audit endpoint returned
HTTP 503 for seven minutes.  No vulnerability, static-check, test or browser
failure was reported; later steps in that matrix were skipped by the external
service failure.  The repeated 503 is recorded rather than being hidden or
converted into a passing audit.

## Clean release and rolling activation

The exact `0921b4fadb85561646649c3aa9a42dba06905540` Git archive had SHA-256
`19bc2b2301957b36933ca44105cdf2c48b6541d70eee0bfed69f673ddf4f0549`.
The archive and selected extracted files matched on both hosts.  It was
extracted into clean, inactive release directories before activation:

- robot Jetson: `/home/unitree/releases/robot-scope/0921b4f`;
- external Jetson: `/home/jetson_orin_nano/releases/robot-scope/0921b4f`.

The robot-side Bridge was stopped through the fixed dashboard lifecycle API,
its active symlink was switched, and it was started through the same API.  The
external dashboard was then switched and restarted.  This Bridge-first order
is required because the new dashboard intentionally remains unready when an
old Bridge cannot acknowledge the signed Stop.  Both systemd units retained
their pre-deployment `disabled` enable policy and reported zero restarts.

Rollback state was preserved as:

- `/home/unitree/robot-scope.pre-0921b4f ->` release `ee315d2`;
- `/home/jetson_orin_nano/robot-scope.pre-0921b4f ->` release `ee315d2`;
- `/home/jetson_orin_nano/.config/robot-scope/control.env.pre-0921b4f`, mode
  `0600`.

If rollback is needed, restore the external dashboard first and the robot
Bridge second.  Mixing the new dashboard with the old Bridge must remain
fail-closed.

## Stationary post-deployment evidence

The robot Bridge started as PID `296117` with process cwd resolving to the
`0921b4f` release.  The external dashboard started as PID `907672` with the
same release identity.  The expected connected-UDP error appeared while the
dashboard port was intentionally down, followed by `command datagram
transport recovered` when the new dashboard sent the signed Stop handshake.

Five consecutive one-second API samples then reported:

| Field | Result in all samples |
| --- | --- |
| Bridge ready / authenticated / connected | `true / true / true` |
| Control lease / deadman | `false / false` |
| Accepted command | exact `(0.0, 0.0, 0.0)` |
| Sport publisher classification | `1 / 0 / 10 / 11` |
| Move / non-zero Move / action / malformed Move | `0 / 0 / 0 / 0` |
| Motion run active | `false` |
| LowState age | `0` to `2 ms` |

StopMove count increased from 231 to 239 during the samples, which is the
expected idle watchdog behavior.  Navigation pipeline/session/goal,
localization-only session, mapping pipeline/operation and dataset capture all
remained idle.  The separately owned persistent XT16 preview recovered and
reported wireless preview readiness.

## Next supervised gate

The earlier pose and goal approvals were consumed by earlier attempts and
must not be reused.  Before another motion attempt, create a new normal
Navigation session, pin the exact map and parameter revisions, display and
confirm the candidate initial pose, publish it exactly once, and pass the full
C4 pre-goal checker with a continuously bound exclusive Navigation lease.

The next goal must be the shortest route justified by newly confirmed free
space.  A 2.0 m goal is deferred until the complete 2.0 m route plus stopping
margin is verified and shorter supervised stages have passed.  A fresh exact
route and physical-safety confirmation is required before any goal POST.

The subsequent one-shot execution is recorded separately in
`TRACK_C4B_20260904_SECOND_GOAL_PROGRESS_ABORT.md`. The deployment-phase
zero-goal and zero-motion counts above remain the correct facts for this
deployment record and are not retroactively changed by that later run.
