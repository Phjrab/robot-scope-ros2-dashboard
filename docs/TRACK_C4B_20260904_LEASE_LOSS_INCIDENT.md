# Track C4B pre-goal lease-loss incident

Date: 2026-09-04

```text
NORMAL_NAV_START_PASS
NORMAL_SESSION_INITIAL_POSE_ONCE_PASS
C4_PREGOAL_READY_PASS
EXACT_GOAL_APPROVAL_RECEIVED
FINAL_LEASE_GATE_BLOCKED
GOAL_SUBMISSION_COUNT_0
MOVE_REQUEST_COUNT_0
ROBOT_MOTION_NOT_RUN
REVERSE_CLEANUP_PASS
ROOT_CAUSE_NOT_PROVEN
```

## Decision

The operator approved exactly one supervised goal from `(0.0, 0.0, 0.0)` to
`(0.25, 0.0, 0.0)` on `map_20260902_161903_edited`, map revision
`7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93`
and parameter revision
`4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad`.
The operator reconfirmed the standing and stationary robot, 0.40 m clear
forward corridor, physical E-stop/remote and on-site safety observer.

The goal was not submitted. The final fail-closed pre-submit check found that
the exclusive bound Navigation lease had already been revoked. The normal
Navigation session had deactivated with
`deactivation_reason="navigation control lease was lost"`, so the attempt was
aborted and cleaned up without calling `POST /api/v1/navigation/goal`.
A future retry requires a new Navigation session, a new one-shot initial-pose
confirmation and a new exact goal approval. This approval must not be reused.

## Verified pre-goal state

- Repository baseline: `3ede8425158fe5e46c1327e5f4ff328901685839`.
- Runtime release on the external Jetson: `47b9151`.
- The normal Navigation session started at `2026-09-04T02:56:25.944Z`.
- The approved initial pose `(0.0, 0.0, 0.0)` was published exactly once at
  `2026-09-04T02:59:09.930Z`.
- The exact C4 checker passed before approval with an idle goal, quiet raw
  command, stabilized controller odometry and known-free route clearance.
- Observed checker evidence included raw odometry `9.994654 Hz`, stable READY
  `300.797 s`, and minimum non-free clearance `0.947 m`.
- A later read-only snapshot still reported raw odometry `9.964064 Hz`, maximum
  gap `0.112624 s`, stable READY `368.296 s`, exact-zero command and an idle
  goal.
- The signed Bridge remained authenticated and reported the established Sport
  cardinality: one subscriber, one Robot Scope publisher, zero foreign named
  publishers, ten trusted anonymous Unitree publishers and eleven total.

## Fail-closed and no-motion evidence

- The final checker stopped on `navigation lease is not exclusively bound`
  before any goal request.
- The append-only operator timeline has no `goal_send` event for this attempt.
  It records Navigation start, one initial pose and the later explicit cleanup
  stop only.
- The public Navigation state showed goal `idle`, no goal ID and no active
  session after lease loss.
- Signed Bridge evidence showed zero Move, zero non-zero Move, zero action,
  zero malformed Move and zero unknown request counts. StopMove was the only
  published request class.
- No manual lease, browser ARM, deadman input or non-zero command was used.
- The robot did not move.

## Correlated transport evidence and limits of the diagnosis

The robot-side Control Bridge process did not restart. Its systemd unit kept
the same process and reported zero restarts. The Bridge logged a connected-UDP
command receive error at `11:55:33 KST`, while the external dashboard was being
restarted, and logged `command datagram transport recovered` at
`12:07:26 KST`. The recovery message means the first subsequent valid signed
command datagram was received; it coincides with the fail-closed StopMove
emitted when the external control manager revoked the lease.

This correlation does not prove the initiating cause of the lease revocation.
The Bridge status was fresh after the event and no Bridge epoch rotation or
service restart was observed. The current bounded API and append-only operator
timeline do not persist the control manager's first fail-closed reason, so the
available evidence cannot distinguish a transient status-freshness loss from a
missed internal heartbeat deadline. The existing 0.75 s signed-status timeout,
2 s lease heartbeat timeout, 200 ms command watchdog and all publisher
cardinality gates were left unchanged.

The external Jetson also attempted and failed to auto-activate an unrelated
disconnected Wi-Fi profile (`CHOSUN_Free`) during the incident window while
the wired management path remained in use. This is an operational noise source
to remove before retry, but the logs do not prove that it caused the lease
loss.

## Reverse cleanup

The Navigation stack was stopped through the normal endpoint at
`2026-09-04T03:10:08.276Z`. The temporary competition FAST-LIO profile was
replaced with the production `go2-xt16-wireless` profile and the dashboard was
restarted. Final state was:

- Navigation session, pipeline and goal idle;
- no control lease and deadman released;
- exact-zero accepted command;
- signed Bridge authenticated and READY;
- fresh LowState, battery 83%, and unchanged `1/0/10/11` Sport publisher
  classification;
- signed request evidence containing StopMove only and zero Move requests.

## Retry requirements

1. Remove or disable the unused auto-connect Wi-Fi profile without changing
   the active wired management path, in a separately approved maintenance
   step.
2. Add or use bounded diagnostics that preserve the first control lease
   revocation reason; do not weaken any timeout or fail-closed behavior.
3. Start a new exact normal Navigation session and prove continuous exclusive
   Navigation lease ownership.
4. Obtain a fresh one-shot initial-pose confirmation, publish it once, and
   rerun the full C4 readiness checker.
5. Display the pinned route and current safety evidence again, then wait for a
   fresh exact C4B goal approval before one submission.

