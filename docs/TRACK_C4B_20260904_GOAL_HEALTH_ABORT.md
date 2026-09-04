# Track C4B one-shot goal health abort

Date: 2026-09-04

```text
EXACT_ROUTE_APPROVAL_PASS
NORMAL_NAV_START_PASS
NORMAL_SESSION_INITIAL_POSE_ONCE_PASS
C4_PREGOAL_READY_PASS
EXACT_GOAL_APPROVAL_PASS
GOAL_SUBMISSION_COUNT_1
SIGNED_MOVE_REQUEST_COUNT_73
LOW_SPEED_ENVELOPE_PASS
LOCALIZATION_HEALTH_ABORT
GOAL_CANCEL_PASS
NAVIGATION_STOP_PASS
REVERSE_CLEANUP_PASS
PHYSICAL_FORWARD_MOTION_NO
TRACK_C4B_ACCEPTANCE_BLOCKED
```

## Decision

The approved Track C4B goal was submitted exactly once.  The goal did not
complete.  The bounded supervisor canceled it and stopped the Navigation
stack when localization health left `READY` approximately 3.7 seconds after
the goal was accepted.  No automatic retry occurred.  The production
`go2-xt16-wireless` profile was restored and the final accepted command was
exact zero with no lease or active motion run.

Track C4B remains `BLOCKED`.  This run is evidence that the one-shot motion
path and fail-closed cleanup execute, not evidence that the short Nav2 goal is
accepted.  The operator subsequently confirmed that no physical forward
motion was visible during the run.  This observation is now recorded
explicitly and is consistent with the very small signed command envelope,
but it does not prove whether the Go2 firmware accepted or rejected those
requests.  Final software state after cleanup was exact zero; no separate
physical final-stop observation is inferred from telemetry.

The requested immediate 2.0 m retry was not sent.  Increasing only the goal
distance would leave the same approximately 0.035 m/s effective velocity
ceiling in place, while exceeding the C4 first-goal limit and the only
validated 0.40 m stopping corridor.  The next supervised retry must first
expose robot-side Sport mode/gait evidence, preserve the first health-fault
snapshot, and validate low-speed cumulative progress.  If those checks pass,
the shortest useful retry remains the same 0.25 m corridor with a separately
approved parameter revision; a 2.0 m run belongs to a later long-route stage
with its full route and stopping clearance verified.

## Fixed identity and approval

| Item | Fixed value |
| --- | --- |
| Repository baseline | `e7e2ef1f0248d31e0622ce7f46a2b977e9ce4632` |
| External-Orin runtime release | `47b9151` |
| Mounted-Jetson runtime release | `47b9151` |
| Map | `map_20260902_161903_edited` |
| Map ID | `f292601e2c8b269eb635cb0f` |
| Map revision | `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93` |
| Parameter revision | `4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad` |
| Approved start | `(0.0, 0.0, 0.0)` |
| Approved goal | `(0.25, 0.0, 0.0)` |
| Route / stopping corridor | 0.25 m / 0.40 m along map +X |
| Minimum non-free clearance | 0.946986 m |
| Desired Nav2 velocity | 0.10 m/s |
| Dashboard scale | 35%, applied once |
| Server linear clamp | 0.30 m/s, unchanged |

The operator separately confirmed the normal Navigation session, one initial
pose, and one goal.  The goal approval reconfirmed a standing and stationary
robot, a clear 0.40 m forward corridor, physical E-stop/remote availability,
and an on-site safety observer.

The unused `CHOSUN_Free` connection profile had `connection.autoconnect=no`
before this retry.  The active external-Orin path remained
`eno1=192.168.50.10/24` with default route via `192.168.50.1`; no retry-window
NetworkManager activation of `CHOSUN_Free` was observed.

## Pre-goal evidence

The new normal Navigation session retained one exclusive, bound Navigation
lease for a 30-second observation.  Every sample had a fresh signed Bridge and
LowState, `1/0/10/11` Sport cardinality, deadman released, exact-zero command,
zero Move requests and an idle goal.

The approved initial pose was published once.  Five seconds later the
localized pose was approximately `(0.00167, 0.00021, -0.00040 rad)`, all
readiness fields were true, the goal remained idle, and only the competition
odometry READY dwell remained.  The state then reached
`READY / HEALTHY_STABLE` and remained stable for more than 280 seconds.

The first lifecycle CLI invocation incorrectly used the shell's default ROS
middleware and could list nodes but could not obtain lifecycle responses.  It
made no mutation.  Re-running with the exact environment inherited from the
Nav2 `map_server` process (`rmw_cyclonedds_cpp`, the fixed `eno1` CycloneDDS
configuration) reported `map_server active [3]` and passed the same checker.
This was a checker-shell environment mismatch, not a Nav2 lifecycle failure.

The final one-shot supervisor reran the complete pre-goal checker immediately
before the POST and obtained:

```text
[Robot Scope] Track C4 pre-goal readiness passed |
map=f292601e2c8b269eb635cb0f goal=IDLE raw_command=quiet
odom_raw_hz=10.010165 stable_ready_s=622.300
```

No timeout, freshness, cardinality, speed, watchdog, source-clock, map,
filesystem or C4 checker rule was weakened to obtain this result.

## One-shot goal and fail-closed abort

The sole `POST /api/v1/navigation/goal` was accepted with goal ID
`1bcedd8e94e3da20756999129474abd1`.  The append-only operator timeline records
exactly one accepted `goal_send` at `2026-09-04T03:48:07.737Z`.

During the bounded observation:

- the goal stayed `active` and its reported remaining distance changed from
  0.275 m to 0.225 m;
- the localized pose samples ranged from approximately
  `(-0.00801, -0.00878, -0.00004 rad)` to
  `(0.00557, -0.01417, 0.00285 rad)` before the abort;
- the signed Bridge published 73 Move requests, all 73 non-zero;
- maximum absolute signed components were 0.0301918 m/s forward, 0.0 m/s
  lateral and 0.0129765 rad/s yaw;
- the Bridge remained authenticated, LowState remained fresh and Sport
  cardinality remained `1/0/10/11`;
- the bounded command and pose corridor checks did not trigger.

The observer stopped the run as soon as `localization_health.state` was no
longer `READY`.  Because the first non-READY snapshot's full reason was not
persisted by this observer and the Navigation runtime was then deliberately
destroyed during cleanup, the exact reason code is not proven.  The timing and
limited pose progress are consistent with the existing 3.0-second
`GOAL_PROGRESS_TOO_LOW` gate, but this is explicitly an inference rather than
a confirmed root cause.  Odometry-rate, sensor-freshness and TF causes also
remain open until the first transition snapshot is persisted.

The append-only event sequence is:

| UTC time | Event | Result |
| --- | --- | --- |
| `03:31:07.543` | new Navigation start | accepted |
| `03:37:09.142` | initial pose | accepted once |
| `03:48:07.737` | goal send | accepted once |
| `03:48:11.477` | goal cancel | accepted, about 3.740 s after send |
| `03:48:13.342` | Navigation stop | accepted, about 5.605 s after send |

The canceled goal reported `navigation_time=3.721 s` and
`distance_remaining=0.225 m`.  The supervisor did not execute its goal POST
site again.

## Reverse cleanup

After cancel, the normal Navigation stop endpoint released the lease and
destroyed the C4-owned stack.  The saved pre-retry configuration was restored
and the fixed dashboard lifecycle helper restarted only
`robot-scope.service`.  Final state was:

- production profile `go2-xt16-wireless`;
- dashboard active, `NRestarts=0` for the new invocation;
- Navigation pipeline, session and goal idle;
- no control lease, deadman released and exact-zero command;
- signed Bridge authenticated and READY with fresh LowState;
- one Sport subscriber and `1/0/10/11` publisher classification;
- motion run inactive and the latest signed request API `1003` StopMove;
- mounted-Jetson Control Bridge still active with its original PID and zero
  systemd restarts.

## Acceptance table

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact map, route and fresh physical-safety approval | `PASS` | exact operator approval consumed by this one-shot run |
| Initial pose exactly once | `PASS` | accepted `initial_pose` event at `03:37:09.142Z` |
| Stable C4 pre-goal readiness | `PASS` | raw odometry 10.010165 Hz; stable READY 622.300 s |
| Goal submission cardinality | `PASS` | one `goal_send`; one goal ID; no retry |
| Low-speed command envelope | `PASS` | maximum 0.0301918 m/s forward and 0.0129765 rad/s yaw |
| Goal completion | `FAIL` | canceled after localization health left READY |
| Physical forward movement | `FAIL` | operator reported no visible forward motion |
| Final stop | `SOFTWARE PASS / PHYSICAL UNRECORDED` | exact-zero final command and idle session; no separate physical observation claimed |
| Automatic safety abort | `PASS` | one cancel followed by Navigation stop |
| Reverse cleanup | `PASS` | production profile; idle; no lease; exact zero; Bridge READY |
| Track C4B acceptance | `BLOCKED` | health transition root cause and successful arrival remain unresolved |

## Verification

- latest baseline CI: run `33832823078`, `e7e2ef1`, completed successfully;
- focused C4/localization/control tests: 76/76 passed;
- dependency-complete Python suite: 1007/1007 passed;
- JavaScript unit suite: 270/270 passed;
- browser E2E: 32/32 passed in 1.1 minutes.

The expected synthetic dataset-start and offline RealSense messages appeared
in the Python test output; the suite exited successfully.  No test, assertion
or safety threshold was deleted or weakened.

## Required follow-up

1. Record the operator's physical movement and final-stop observation.
2. Persist the first localization-health transition reason and its complete
   metric snapshot before reverse cleanup, without relaxing the existing
   fail-closed gates.
3. Diagnose why the localized pose showed little forward progress while the
   Bridge published bounded non-zero Move requests.  Separate physical gait
   acceptance, odometry tracking and Nav2 progress feedback.
4. Do not send another goal until the cause is understood, a new normal
   Navigation session and initial pose are established, the full C4 checker
   passes, and the operator gives a new exact one-shot goal approval.
