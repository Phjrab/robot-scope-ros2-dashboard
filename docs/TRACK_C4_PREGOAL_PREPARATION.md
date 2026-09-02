# Track C4 pre-goal preparation

Date: 2026-09-02

Track status: `PREPARED_AWAITING_EXACT_ROUTE_APPROVAL`

Motion status: `NOT_RUN`

This record covers only the hardware-free and read-only preparation for the
first supervised Track C4 goal. The operator's general `승인완료` response was
interpreted as approval to prepare the checker and route preview. It did not
authorize a navigation lease, initial pose, goal, ARM, deadman or robot motion.

## Preserved safety boundaries

- Track A/B, `competition-pdf-direct`, the strict wireless
  `/utlidar/robot_odom` path and its 500 ms source-age/100 ms future-skew guard
  are unchanged.
- The absolute server clamp remains 0.30 m/s, the signed bridge watchdog and
  exact Sport/LowState graph cardinality remain fail-closed, and no publisher
  or filesystem restriction is weakened.
- C3's lease-free localization checker remains unchanged. C4 has a separate
  normal-navigation checker and does not reinterpret a localization-only
  session as motion-ready.
- The external Nav host cannot observe the robot-side `/api/sport/request`
  graph directly. The C4 checker therefore does not claim that it can; the
  robot-side signed bridge/cardinality evidence remains a separate required
  observation.

## Preparation correction

The safe Nav2 preset had `xy_goal_tolerance=0.35`, which is larger than the
maximum permitted first C4 goal distance of 0.30 m. A 0.25 m goal could
therefore complete without visible motion. C4 now requires these explicit
session values before startup:

| Parameter | C4 value |
| --- | ---: |
| `desired_linear_vel` | 0.10 m/s |
| `xy_goal_tolerance` | 0.05 m |
| `yaw_goal_tolerance` | 0.10 rad |
| `required_movement_radius` | 0.05 m |
| `robot_radius` | 0.22 m |
| `inflation_radius` | 0.25 m |

Starting from the observed safe preset revision
`194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`, the
candidate C4 revision is
`4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad`.
This is a calculated candidate only: the live revision must be read again and
updated through the existing compare-and-swap API after exact approval.

Normal Nav2 commands previously entered the control manager with
`speed_scale=1.0`. The gateway now submits the configured default scale to the
existing server-side scaler exactly once. With the C4 controller limit of
0.10 m/s and the fixed 35% scale, the effective straight-line command ceiling
is 0.035 m/s; the independent 0.30 m/s server clamp is still authoritative.
Zero, cancel and fail-safe StopMove paths remain unchanged.

## Pinned route candidate

| Item | Exact value |
| --- | --- |
| Map | `map_20260902_161903_edited` |
| Map ID | `f292601e2c8b269eb635cb0f` |
| Map revision | `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93` |
| Map geometry | 297 x 156 at 0.05 m/cell; origin `[-8.97357559204, -2.05925989151, 0]` |
| Occupancy | 21,505 free; 24,827 occupied; 0 unknown |
| Start pose | `x=0.00, y=0.00, yaw=0.00` |
| Goal pose | `x=0.25, y=0.00, yaw=0.00` |
| Direction and distance | straight forward `+X`, 0.250 m |
| Robot-radius corridor | 0.220 m radius |
| Stopping buffer | 0.150 m beyond the goal; checked through `x=0.40` |
| Minimum occupied/map-boundary clearance | 0.946985520695 m |
| Net clearance beyond robot radius | 0.726985520695 m |

The route calculation decodes the pinned row-major occupancy payload and
checks the full circular footprint every 0.01 m from the start through the
stopping-buffer endpoint. Unknown cells are treated as non-free. The current
edited map contains no unknown cells.

## Read-only live observation before code deployment

The external dashboard was still on the restored production profile
`go2-xt16-wireless`, with Navigation idle and unavailable for the competition
FAST-LIO controller profile. No session, initial pose or goal was active.
Control was bridge-ready and authenticated with fresh LowState, one Robot
Scope publisher, zero foreign named publishers, ten bare Unitree publishers
and eleven total publishers. The lease was inactive, deadman was false and
the command was exact zero. Battery telemetry reported 88% during this
snapshot. These observations are not a substitute for the mandatory fresh
pre-goal checks after deployment and exact approval.

## Distinct C4 checker

`scripts/check_track_c4_navigation_ready.py` is read-only and accepts only:

- the explicit competition FAST-LIO profile and ROS 2 Humble;
- the exact map ID/revision and the fixed route/stopping corridor above;
- the C4 parameter values and a valid parameter revision;
- a normal navigation session, never a localization-only session;
- localized/READY health, an idle goal and an exclusively bound navigation
  lease;
- exact bridge cardinality, fresh bridge/LowState, 35% speed scale, unchanged
  0.30 m/s clamp, false deadman and exact-zero command;
- all required lifecycle nodes, one fresh publisher for each fixed sensor,
  odometry, localization and costmap topic, complete TF, and quiet/zero-only
  raw command before the goal.

Any ambiguity is `BLOCKED`; the checker cannot send a goal or mutate runtime
state.

## Gate status

| C4 item | Status | Evidence |
| --- | --- | --- |
| Exact map/revision and route calculation | `PASS` | read-only map payload and 0.01 m corridor sampling |
| Hardware-free checker tests | `PASS` | focused C4/navigation gateway suite |
| Speed scale applied once | `PASS` (code) | unit test proves a 0.20 m/s Nav2 sample reaches the server scaler once at 35% and records 0.07 m/s output |
| Deployed C4 code | `NOT_RUN` | requires focused commit and exact-release deployment |
| C2/NG0/C3 live regression | `NOT_RUN` | permitted only after exact route approval |
| Standing/stationary pose and clear physical corridor | `BLOCKED` | must be reconfirmed by the on-site operator immediately before motion |
| Exact route approval | `BLOCKED` | candidate must be shown and approved verbatim |
| Navigation lease / initial pose / goal / motion | `NOT_RUN` | deliberately untouched |

After exact route approval, deploy the focused commit, apply the C4 parameter
revision through CAS, run the no-motion regression and reverse cleanup, then
start the normal session and show a final fresh pre-goal snapshot. Abort and
reverse-clean on any mismatch; never auto-retry a goal.
