# Track C4B supervised short-goal retry acceptance

Date: 2026-09-03

```text
EXACT_ROUTE_APPROVAL_PASS
HARDWARE_FREE_REGRESSION_PASS
CLEAN_CANDIDATE_DEPLOYMENT_PASS
LEASE_FREE_C3_REGRESSION_PASS
NORMAL_NAV_START_PASS
NORMAL_SESSION_INITIAL_POSE_ONCE_PASS
C4_PREGOAL_READY_PASS
EXACT_GOAL_APPROVAL_PASS
SPORT_OBSERVER_CARDINALITY_BLOCKED
GOAL_SUBMISSION_COUNT_0
MOVE_REQUEST_COUNT_0
ROBOT_MOTION_NOT_RUN
REVERSE_CLEANUP_PASS
```

## Scope and decision

The operator approved exactly one supervised Nav2 goal from `(0.0, 0.0, 0.0)`
to `(0.25, 0.0, 0.0)` on `map_20260902_161903_edited`. The fixed map revision
was `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93`
and the C4 parameter revision was
`4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad`.
The operator also reconfirmed a clear 0.40 m forward corridor, a standing and
stationary robot, a physical E-stop/remote, an on-site safety observer and the
exact route preview.

The attempt is `BLOCKED`, not a motion acceptance. A temporary read-only ROS 2
subscriber was attached to `/api/sport/request` immediately before the goal so
that signed Bridge output could be observed independently. That observer
changed Sport subscription cardinality from the established one subscriber to
two. The Control Bridge correctly failed closed, the navigation lease was
lost, and the normal navigation session deactivated. The one-shot sender then
failed its own preflight on `can_send_goal=false` before reaching its sole HTTP
goal request. It did not retry.

No goal was submitted and the robot did not receive a Move request. This
approval is consumed and must not be reused for a future retry.

## Fixed route and pre-goal evidence

| Item | Evidence |
| --- | --- |
| Candidate release | clean external-Orin release `5057c5a413308d7c1492d23a236f3df0b5eb27dd` |
| Map ID | `f292601e2c8b269eb635cb0f` |
| Start / goal | `(0.0, 0.0, 0.0)` / `(0.25, 0.0, 0.0)` |
| Travel / stop corridor | 0.25 m / 0.40 m along map +X |
| Map resolution | 0.05 m/cell |
| Traversed centerline cells | `(179,41)` through `(187,41)`, all PGM value 255 (known free) |
| Minimum non-free clearance | 0.946986 m |
| Robot / inflation radius | 0.22 m / 0.25 m |
| Nav2 desired velocity | 0.10 m/s |
| Dashboard speed scale | 35%, configured to apply once |
| Server linear clamp | 0.30 m/s, unchanged |
| Last localized pose before the fault | approximately `(0.00861, -0.00716, 0.00235 rad)` |
| Battery before goal gate | 53-58% with fresh LowState |

The normal navigation session exclusively held a bound navigation lease. The
approved initial pose `(0.0, 0.0, 0.0)` was published once in that session.
The goal remained idle. Immediately before installing the observer, the exact
C4 checker passed with:

```text
[Robot Scope] Track C4 pre-goal readiness passed |
map=f292601e2c8b269eb635cb0f goal=IDLE raw_command=quiet
odom_raw_hz=10.097901 stable_ready_s=869.395
```

The signed Bridge was authenticated-ready with fresh LowState, one Robot Scope
Sport publisher, zero foreign named publishers, ten expected anonymous Unitree
publishers and eleven total. Deadman was false and the accepted command was
exact zero.

## Fail-closed evidence

The temporary observer made ROS report 11 publishers and two subscribers on
`/api/sport/request`. The dashboard then reported
`deactivation_reason="navigation control lease was lost"`, session mode
`idle`, localization uninitialized, lease inactive and
`can_send_goal=false`. The sender exited at preflight before calling
`POST /api/v1/navigation/goal`.

Independent evidence confirms the hard boundary:

- candidate operator-event records contain no `goal_send` event;
- the sender created no goal trace because it stopped before submission;
- the robot-side bounded capture contains 116 API 1003 `StopMove` requests;
- the same capture contains zero API 1008 `Move` requests;
- the navigation goal remained `idle` with no goal ID;
- no manual lease, ARM or deadman input was used.

The observer was terminated, its DDS subscription returned from two to one,
and the Nav stack was stopped in reverse order. The exact candidate process was
then terminated and production service `robot-scope.service` was restored to
clean release `1164553`. Final production state was service active, strict
`go2-xt16-wireless` profile, navigation/session/pipeline/goal idle, lease
inactive, deadman false and exact-zero command. The Bridge returned to
authenticated READY with `1/0/10/11` publisher cardinality and one Sport
subscriber.

## Acceptance table

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact map, route and physical approval | `PASS` | fresh operator approval after displayed route |
| C2/C3/C4A hardware-free regression | `PASS` | 81/81 focused tests before hardware execution |
| Baseline CI | `PASS` | GitHub Actions run `33714264727`, both supported platforms |
| Immutable candidate deployment | `PASS` | exact release `5057c5a`, archive SHA-256 `6fef167499469e5f20ad46105ad81559d5cc9804d3589ecf9f2cac1223481a49` |
| Lease-free C3 and NG1 regression | `PASS` | initial pose once, localized chain, goal/lease/motion closed |
| Normal Nav2 startup and exclusive lease | `PASS` | exact pins, navigation-only bound lease |
| Normal-session initial pose | `PASS` | separately approved and published once |
| Stable C4 pre-goal readiness | `PASS` | READY 869.395 s, raw odometry 10.097901 Hz |
| Independent Sport observation | `BLOCKED` | observer itself changed subscription cardinality 1→2 |
| Goal submission | `NOT_RUN` | fail-closed preflight exited before the sole POST site |
| Robot motion | `NOT_RUN` | zero Move requests; 116 StopMove requests |
| Reverse cleanup | `PASS` | production restored; idle, no lease, deadman false, exact zero |

## Required follow-up before another C4B attempt

Do not weaken subscriber or publisher cardinality to accommodate the observer.
Provide a non-intrusive evidence path instead, preferably Bridge-owned bounded
outbound request counters/maximum accepted velocity exposed in authenticated
status, or an independently reviewed passive capture that does not create a
DDS endpoint. Add hardware-free tests proving that the evidence path cannot
publish, subscribe, acquire a lease, arm, press deadman or alter commands.

After that focused change is reviewed, repeat the clean deployment, lease-free
C3 regression, normal-session one-shot pose, stable C4 checker and route
display. A new exact motion approval is required. Never auto-resume or reuse
the approval recorded here.

## Repository verification

- focused C2/C3/C4/health/gateway regression: 67/67 passed after the hardware
  cleanup; the broader pre-hardware focused set was 81/81 passed;
- dependency-complete Python suite: 1003/1003 passed;
- JavaScript unit suite: 270/270 passed;
- browser E2E: 32/32 passed in 1.1 minutes;
- the first two focused invocations used invalid `unittest` module addressing
  for this non-package `tests` directory and each reported five import errors;
  the corrected `PYTHONPATH=tests:.` invocation passed 67/67;
- the first browser invocation was sandbox-blocked from binding
  `127.0.0.1:4173`; the permission-enabled rerun passed 32/32.

These invocation/environment failures occurred after robot cleanup and are not
product regressions. No assertion was removed or weakened.
