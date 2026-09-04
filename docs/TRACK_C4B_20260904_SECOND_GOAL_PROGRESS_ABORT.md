# Track C4B second one-shot goal progress abort

Date: 2026-09-04

```text
EXACT_ROUTE_APPROVAL_PASS
NORMAL_NAV_START_PASS
NORMAL_SESSION_INITIAL_POSE_ONCE_PASS
C4_PREGOAL_READY_PASS
EXACT_GOAL_APPROVAL_PASS
GOAL_SUBMISSION_COUNT_1
NO_AUTOMATIC_RETRY_PASS
MOTION_RUN_CARDINALITY_PASS
SIGNED_MOVE_REQUEST_COUNT_59
ZERO_MALFORMED_ACTION_OTHER_COUNT_0
LOW_SPEED_ENVELOPE_PASS
SPORT_MODE_TELEMETRY_FRESH_PASS
SPORT_GAIT_TRANSITION_NOT_OBSERVED
ROBOT_SIDE_MOVE_ACCEPTANCE_UNCONFIRMED
FIRST_HEALTH_FAULT_CAPTURE_PASS
GOAL_PROGRESS_TOO_LOW_CONFIRMED
GOAL_COMPLETION_FAIL
PHYSICAL_FORWARD_MOTION_NO
PHYSICAL_FINAL_STOP_PASS
GOAL_CANCEL_PASS
NAVIGATION_STOP_PASS
FINAL_SIGNED_STOP_PASS
SUPERVISOR_FINAL_SAFE_PASS
PRODUCTION_PROFILE_RESTORE_PASS
TRACK_C4B_ACCEPTANCE_BLOCKED
```

## Decision

The operator-approved goal `(0.25, 0.0, 0.0)` was submitted exactly once.
The bounded supervisor canceled it after the persisted localization-health
evidence reported `GOAL_PROGRESS_TOO_LOW`; it then stopped the Navigation
session and released its lease. No automatic retry occurred.

The operator observed no physical forward motion and confirmed that the robot
was stopped. Signed Bridge evidence proves that bounded Move requests reached
the Bridge-owned ROS publisher, but it does not prove that the Go2 firmware
accepted or executed them. Track C4B therefore remains `BLOCKED`.

This run also exposed a deterministic progress-accounting defect. The first
finite Nav2 feedback was a startup `distance_remaining=0.0` sentinel. That
zero became the cumulative progress window's start and best distance. Later
feedback of `0.275 m` and `0.225 m` could therefore never make the calculated
minimum smaller than zero, so `goal_progress_rate_mps` remained zero. The
existing three-second stall rule then fired. This defect is separate from the
operator-confirmed lack of physical motion and must not be used as evidence
that the robot moved.

## Fixed identity and approval

| Item | Fixed value |
| --- | --- |
| Repository and deployed release | `f83f3fff08f0280954839f4e5b87110f314c6271` |
| Baseline CI | GitHub Actions run `33855071236`, success |
| Navigation profile | `go2-xt16-wireless-competition-fastlio` |
| Map | `map_20260902_161903_edited` |
| Map ID | `f292601e2c8b269eb635cb0f` |
| Map revision | `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93` |
| Parameter revision | `4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad` |
| Approved start / goal | `(0.0, 0.0, 0.0)` / `(0.25, 0.0, 0.0)` |
| Travel / stopping corridor | 0.25 m / 0.40 m along map +X |
| Minimum non-free clearance | 0.946986 m |
| Desired Nav2 speed | 0.10 m/s |
| Dashboard scale | 35%, applied once |
| Signed forward limit used by supervisor | 0.036 m/s |
| Server linear clamp | 0.30 m/s, unchanged |

The approval explicitly reconfirmed a standing, stationary robot, the exact
map/revisions and poses, a clear 0.40 m corridor, a physical E-stop/remote, an
on-site safety observer, and exactly one goal submission.

## Pre-goal gates

The normal Navigation session started with one exclusive bound Navigation
lease. The approved initial pose was published once. Localization converged,
the goal remained idle, the signed Control Bridge was authenticated and ready,
LowState was fresh, and publisher cardinality stayed `1/0/10/11` with one
Sport subscriber. The accepted command was exact zero with deadman released.

Immediately before the sole goal POST, the complete C4 checker passed:

```text
[Robot Scope] Track C4 pre-goal readiness passed |
map=f292601e2c8b269eb635cb0f goal=IDLE raw_command=quiet
odom_raw_hz=9.995134 stable_ready_s=1364.398
```

The one-shot supervisor source had SHA-256
`8f93b56bd1e5414e4639c06c41be34401080735b8279bb1411720ce337fda75b`.
It fixed the approved identities in code, contained one static goal POST site,
did not retry, enforced the speed envelope and all existing readiness,
freshness, cardinality, lease, deadman, map-identity, pose-corridor, rate and TF
guards, and used cancel followed by Navigation stop on any exception. Route
occupancy and clearance were proven by the immediately preceding complete C4
checker. A second read-only observer used only dashboard GET requests and did
not create a DDS endpoint.

## One-shot timeline

The append-only operator timeline contains this exact accepted sequence:

| UTC | Event | Result |
| --- | --- | --- |
| `09:26:18.885` | Navigation start | HTTP 202 accepted |
| `09:30:27.070` | normal-session initial pose | HTTP 200 accepted once |
| `09:54:32.050` | goal send | HTTP 200 accepted once |
| `09:54:35.124` | goal cancel | HTTP 200 accepted |
| `09:54:36.774` | Navigation stop | HTTP 200 accepted |

The goal ID was `c4d0457293352f6cdaae854072da3b49`. The supervisor ran from
`09:54:31.868` through `09:54:37.800` UTC. Its complete 27,853-byte JSON
evidence file was retained outside Git; its SHA-256 is
`83a92735da63ea852d66f0f43109fcc94905f6a869212655a658f8731e829b1e`.

## Signed motion and first-fault evidence

Bridge process-lifetime counters began at 4,624 published StopMove requests,
zero Move requests and motion-run ID zero. They ended at:

| Evidence | Final value / delta |
| --- | --- |
| Published / StopMove | `4689 / 4630` (`+65 / +6`) |
| Move / non-zero Move | `59 / 59` (`+59 / +59`) |
| Zero Move / malformed Move | `0 / 0` |
| Action / unknown request | `0 / 0` |
| Motion run | ID `1`, final active `false` |
| Maximum signed X / Y / yaw | `0.0291743403 / 0 / 0.00428817545` |
| Final request | API `1003` StopMove |

The first persisted non-READY snapshot was:

- state `DEGRADED`, hard fault true;
- reason `GOAL_PROGRESS_TOO_LOW`;
- threshold basis `goal_progress_rate_mps<0.01`;
- progress rate `0.0 m/s`, stall duration `3.038 s`;
- goal remaining distance `0.225 m` and navigation time `3.071 s`;
- cloud `9.995 Hz`, age `0.0469 s`;
- raw controller odometry `9.986196 Hz`, maximum gap `0.112883 s`, age
  `0.0244 s`;
- TF age `0.0009 s`, map-to-odom age `0.0005 s`;
- 14,426 accepted points and no jump, frame, source or calibration fault.

This proves a controller-progress abort rather than a generic XT16, odometry,
TF or publisher-cardinality failure.

The first monitored pose was approximately
`(0.000933, 0.004202, -0.002056 rad)` and the last pre-abort pose was
`(0.007181, 0.003034, -0.001401 rad)`. The independent observer saw only
millimetre-scale fluctuation and no sustained forward displacement. The
reported remaining-distance change from `0.275 m` to `0.225 m` is therefore
not accepted as physical-motion evidence.

Fresh `SportModeState` stayed at raw `mode=0`, `gait_type=0` and
`error_code=100` throughout the request window. No gait transition was
observed and reported velocity remained at stationary-noise scale. The error
value is recorded as an opaque vendor field because no authoritative mapping
has yet been established. Unitree's
[official ROS 2 documentation](https://github.com/unitreerobotics/unitree_ros2/blob/master/README.md#L181-L212)
defines `mode=0` as idle/default stand and `gait_type=0` as idle; the observed
values therefore do not establish locomotion entry.

## Deterministic progress defect

The production sequence was reproduced against the same HEAD without using
hardware:

```text
t=100.01  distance_remaining=0.000
t=100.10  distance_remaining=0.275
t=100.30  distance_remaining=0.225
```

It produced `initial_distance=0.0`, `window_start_distance=0.0`,
`best_distance=0.0`, `progress_rate_mps=0.0`, and the same
`DEGRADED/GOAL_PROGRESS_TOO_LOW` classification at `t=103.048`. Existing
coverage seeded its first feedback with a positive distance and therefore did
not exercise this startup sequence.

The safe correction is to treat an initial zero-distance sample for an active,
non-terminal goal as provisional. It must not seed the progress window or
refresh the stall timer. The first positive distance may seed the window;
zero-only input must still fail at the existing three-second deadline, and a
zero after a positive baseline must not be counted as progress without
terminal success or independent pose corroboration. The 5 mm significance,
0.01 m/s progress threshold, three-second stall timeout and every other safety
interlock remain unchanged.

## Cleanup and production restoration

The supervisor requested one cancel and one Navigation stop. Final candidate
state was session and pipeline idle, goal canceled, lease inactive, deadman
false, exact-zero accepted command, signed StopMove latest, inactive motion
run, fresh LowState and Bridge ready. The operator confirmed the physical robot
was stopped.

The private configuration backup was checked without exposing values; only
`ROBOT_SCOPE_MAPPING_PROFILE` differed. It was atomically restored to
`go2-xt16-wireless`, and only `robot-scope.service` was restarted through the
fixed lifecycle helper. Final production evidence was:

- dashboard active at release `f83f3ff`, `NRestarts=0`;
- Navigation pipeline/session/goal idle, no lease, deadman released and exact
  zero;
- Bridge authenticated/connected/ready, LowState fresh, one Sport subscriber
  and `1/0/10/11` publisher cardinality;
- Move count fixed at 59 while StopMove continued increasing;
- persistent XT16 preview recovered automatically with 16,000 source points,
  8,000 displayed points, frame `hesai_lidar`;
- robot-side Control Bridge and XT16 relay active with zero systemd restarts;
  wireless IMU/odometry senders inactive and no C4/Nav2 process remaining.

## Acceptance and required next gate

| Gate | Result |
| --- | --- |
| Exact route, initial pose and one goal approval | `PASS` |
| Stable C4 pre-goal readiness | `PASS` |
| One goal / one new motion run / no retry | `PASS` |
| Signed request bounds and forbidden request classes | `PASS` |
| First health-fault preservation and fail-closed cleanup | `PASS` |
| Goal completion | `FAIL` |
| Physical forward movement | `FAIL` |
| Physical and software final stop | `PASS` |
| Production-profile restoration | `PASS` |
| Track C4B | `BLOCKED` |

Before any third goal POST:

1. land and test the startup-zero progress-accounting correction without
   relaxing any threshold;
2. establish authoritative or characterized Go2 mode/gait readiness and
   request-response evidence; Bridge publish counts alone are insufficient;
3. confirm basic stock-controller stand and forward motion after boot, with no
   Robot Scope motion process active;
4. use a separately approved stationary micro-probe to determine whether the
   current approximately 0.03 m/s signed command is below the firmware's
   effective gait-entry threshold;
5. create a new normal Navigation session, obtain a new one-shot initial-pose
   confirmation, pass the full C4 checker, redisplay the fixed route, and wait
   for another exact one-shot goal approval.

Do not increase the goal distance, weaken the three-second/0.01 m/s progress
guard, auto-send StandUp/BalanceStand, or auto-retry a goal.

## Startup-zero correction and verification

The narrowly scoped correction is implemented in the same repository change
as this report. While a goal is active and non-terminal, a zero or sub-micro-
metre distance sample is retained as bounded raw diagnostic evidence but does
not initialize the accepted distance, progress baseline, best distance or
progress timer. The first positive distance initializes the baseline. A zero-
only stream still fails closed from the original goal-start time at the
unchanged three-second boundary, and a zero after a positive baseline cannot
claim progress. An authoritative succeeded action result alone restores the
terminal public remaining distance to `0.0`; canceled or failed results do not.

No Jetson deployment or additional robot command was performed for this code
correction. Production therefore remains on `f83f3ff`; a later deployment is a
separate, explicitly approved operation.

Verification performed against the corrected working tree:

- final focused Navigation gateway discovery: 20 tests passed;
- related navigation/health/coordinator discovery: 60 tests passed;
- final canonical virtual-environment Python suite: 1,049 tests passed;
- JavaScript unit suite: 270 tests passed;
- Playwright browser suite: 32 tests passed;
- Ruff, repository-configured mypy, Python compilation, frontend syntax,
  tracked-source secret scan and `git diff --check`: passed.

The repository-mandated system-Python command was also attempted. The host
`python3` is Python 3.13 without the repository dependency `fastapi`, so it
failed while importing `test_competition_state`; the same complete suite passed
inside the repository virtual environment. This is a local baseline environment
failure, not a regression introduced by the correction.
