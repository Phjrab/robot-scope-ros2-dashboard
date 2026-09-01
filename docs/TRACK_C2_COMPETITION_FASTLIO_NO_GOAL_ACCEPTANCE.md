# Track C2 competition FAST-LIO no-goal acceptance

Status date: 2026-09-02

```text
SOFTWARE_PASS
STATIONARY_CONTROLLER_ODOM_PASS
NAV2_NG0_PASS
LOCALIZED_NG1_NOT_RUN
GOAL_NOT_RUN
MOTION_NOT_RUN
```

## Scope and evidence rule

This record covers the explicit profile
`go2-xt16-wireless-competition-fastlio`. `PASS` means the exact check was
executed; `BLOCKED` means a required live prerequisite was absent; `NOT_RUN`
is deliberate. Software evidence never upgrades a live hardware row.

C2 forbids initial pose, goal, lease, ARM, deadman and motion. The Control
Bridge must remain disconnected from Nav2 output. The strict wireless
controller-odometry path and the direct Humble profile are preserved.

## Fixed bindings

| Role | Binding |
|---|---|
| Localization odometry | `/Odometry`, `camera_init -> body` |
| Controller odometry | `/robot_scope/nav/controller_odom_fastlio`, `odom -> base_link` |
| Scan | `/scan` |
| Nav2 private command | `/robot_scope/nav/cmd_vel_raw` |
| Sport command monitor | `/api/sport/request` |
| Static map candidate | ID `97bae189b35182c688cecb3c`, revision `60becc42ecb58aca30834c92ed4778e0a38d31562950524a5871808d225ae4ae` |

The map candidate is `map_20260813_125411`, 120×169 at 0.05 m/cell. Inventory
does not authorize an initial pose or goal.

## NG0 and NG1

`scripts/check_competition_no_goal_ready.py --stage prelocalization` is NG0.
It requires every fixed Nav2 child to be present, active map/controller
lifecycle nodes, a map publisher, fresh scan,
FAST-LIO and canonical controller odometry, `odom -> base_link`, no lease,
deadman false, exact-zero dashboard velocity, quiet/zero-only private command
and no Sport request. It reports `WAITING_FOR_INITIAL_POSE` when
`map -> base_link` is absent.

The pre-localization lifecycle distinction is intentional: without
`map -> base_link`, Nav2's global costmap keeps planner activation pending.
Requiring every child to be active would indirectly reintroduce the same
initial-pose contradiction. `--stage localized` is NG1 and requires every
lifecycle node active plus `map -> base_link`, AMCL-pose and both costmap
publishers. NG1 is not executed by C2.

## Acceptance table

| Check | Result | Evidence |
|---|---|---|
| Repository implementation | `SOFTWARE_PASS` | focused profile/gate/checker tests and complete repository suites |
| PDF page crosswalk | `PASS` | attached originals 01–12 inspected; detailed crosswalk in Track C plan |
| External Humble packages/plugins | `PASS` | map server, controller/planner/behavior/BT lifecycle executables and RotationShim, RPP, Navfn, behaviors found under `/opt/ros/humble` |
| Stored map inventory | `PASS` | one current managed map and immutable revision identified without modification |
| Stationary XT16/IMU/FAST-LIO | `STATIONARY_CONTROLLER_ODOM_PASS` | one publisher each; XT16/cloud/FAST-LIO ≈10 Hz, IMU 494 Hz, Laser map 1 Hz; held over 30 s |
| Canonical controller odometry | `STATIONARY_CONTROLLER_ODOM_PASS` | one reliable/volatile publisher at 9.99–10.01 Hz, `odom -> base_link`, source/output stamp identical, 36 ms final host offset, no jump/error |
| NG0 Nav2 60 s | `NAV2_NG0_PASS` | 12 five-second checks PASS; final checker reports `WAITING_FOR_INITIAL_POSE`, raw command quiet |
| Localized NG1 | `NOT_RUN` | reserved for Track C3 |
| Initial pose | `NOT_RUN` | prohibited in C2 |
| Goal/lease/ARM/deadman/motion | `NOT_RUN` | prohibited in C2 |
| Reverse cleanup | `PASS` | Nav2 then mapping owners stopped; both Jetsons' services inactive, related publisher/socket/process counts zero |

## Stationary execution and stop conditions

Before start, verify robot stationary, physical remote/E-stop available,
Control Bridge motion output inactive, no lease, disarmed, deadman false,
exact-zero command, and Mapping/Nav2/Dataset idle. Start only the fixed owners
in the ADR order. Hold the sensor/controller-odometry chain for at least 30 s,
then NG0 for 60 s.

Immediately reverse-clean up on any lease, ARM/deadman, nonzero velocity, Sport
request, duplicate publisher, stale/future/reset/jump, child crash, resource
exhaustion, network loss, map revision mismatch or unclear process ownership.
Do not widen time or velocity bounds to obtain PASS.

## 2026-09-02 live result

The external Orin loaded managed map `map_20260813_125411` (120×169,
0.05 m/cell). The existing wireless owner produced `/lidar_points` 10.006 Hz,
`/imu/body` 494.342 Hz, `/velodyne_points` 9.996 Hz, `/Odometry` 10.000 Hz and
`/Laser_map` 1.001 Hz. Each had one publisher. FAST-LIO runtime diagnostics
reported 16,000 input points, 15,114 accepted points, odometry 10.006 Hz,
zero translation/heading jumps and fresh scan/odometry.

The C2 runtime published exactly one reliable/volatile canonical odometry at
about 10 Hz. Its final diagnostics were `ready=true`, age 24 ms, source and
output stamp `1788304956566518545`, host offset 36 ms, process generation
`426641`, frames `camera_init -> body` to `odom -> base_link`, and no error.

Initial hardware startup exposed two checker assumptions and both were fixed
with hardware-free regression tests before the accepted run:

1. requiring all lifecycle nodes active indirectly required the missing
   pre-localization map TF because planner activation waits in global costmap;
2. an absent `/api/sport/request` topic while the command bridge is disconnected
   was incorrectly treated as an observation failure instead of quiet.

The accepted 60-second run completed 12/12 checks. Every interval retained one
publisher for `/scan`, `/Odometry`, canonical odometry and `/map`; both owners
remained alive; Control stayed no-lease/deadman-false/exact-zero; no Sport
topic appeared; the private raw command capture remained exactly zero bytes.
Memory remained 4.7 GiB available, swap use stayed zero and the pre-Nav sensor
measurement was approximately 40–42°C. `map -> base_link` remained absent as
required for NG0. No initial pose, goal, lease, ARM, deadman or motion was
issued.

Reverse cleanup stopped the Nav2 owner first and the wireless mapping owner
second. External sensor/Nav/C2 topics all returned publisher count zero; the
fixed UDP ports had no listener. The mounted Jetson's Control Bridge, XT16
relay, IMU sender and odometry sender were all inactive with no related socket.
Final Control state was no lease, deadman false and `[0.0, 0.0, 0.0]`.
