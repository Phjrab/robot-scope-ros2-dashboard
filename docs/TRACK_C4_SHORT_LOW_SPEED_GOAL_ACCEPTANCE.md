# Track C4 supervised short-goal acceptance

Status date: 2026-09-02

```text
EXACT_ROUTE_APPROVAL_PASS
HARDWARE_FREE_REGRESSION_PASS
C2_NG0_PASS
NORMAL_NAV_START_PASS
PREGOAL_CHECK_BLOCKED
GOAL_NOT_RUN
MOTION_NOT_RUN
REVERSE_CLEANUP_PASS
```

## Scope and final decision

The operator approved the exact stationary route from `(0.0, 0.0, 0.0)` to
`(0.25, 0.0, 0.0)` on managed map `map_20260902_161903_edited`, with a clear
0.40 m forward corridor, physical remote/E-stop and an on-site observer. This
approval allowed the fail-closed C4 sequence and exactly one goal only after
every pre-goal gate passed.

No goal was submitted. The final C4 checker remained blocked because the
measured controller-odometry frequency crossed the strict 10.0 Hz boundary in
both directions instead of remaining stably ready. The guard was not relaxed
and a momentary `READY` sample was not selected as acceptance evidence.

## Fixed route and safety limits

| Item | Exact value |
| --- | --- |
| Map ID | `f292601e2c8b269eb635cb0f` |
| Map revision | `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93` |
| Start / goal | `(0.0, 0.0, 0.0)` / `(0.25, 0.0, 0.0)` |
| Route / stopping check | straight +X through 0.40 m |
| Minimum occupied/map-boundary clearance | 0.946985520695 m |
| Robot radius / inflation radius | 0.22 m / 0.25 m |
| Desired Nav2 velocity | 0.10 m/s |
| Dashboard speed scale | 35%, applied once |
| Independent server clamp | 0.30 m/s |
| Goal tolerances | 0.05 m / 0.10 rad |

The temporary C4 parameter revision was
`4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad`.
Cleanup restored the exact pre-C4 `go2-safe` revision
`194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`
through the compare-and-swap API.

## Execution evidence

The first lease-free NG0 startup failed closed on `CLOCK NOT SYNCHRONIZED`.
The mounted Jetson clock itself was close to the external host, but its NTP
client selected an Internet-inaccessible default route through the isolated
`192.168.123.0/24` Go2/XT16 sensor network. The sensor-network default route
was removed for the current boot only; its direct subnet route was retained.
NTP then synchronized against `0.pool.ntp.org` with one observed offset of
`+889.068 ms`, 9.043 ms delay and `NTPSynchronized=yes`. No source-clock guard
was weakened.

The next NG0 startup failed closed while the freshly requested XT16 relay was
still transitioning. The fixed lifecycle path stabilized the relay and IMU
sender before the final retry. The accepted read-only C2 checker then reported
`WAITING_FOR_INITIAL_POSE` and `raw_command=quiet`; no lease, initial pose or
goal existed. That lease-free session and all of its owners were stopped in
reverse order before C4 parameter mutation.

Normal C4 Nav2 started with the exact map and parameter revisions. The signed
Bridge was ready and authenticated with fresh LowState, one Robot Scope
publisher, zero foreign named publishers, ten anonymous Unitree publishers
and eleven total publishers. The navigation lease was exclusively bound,
deadman remained false and the command was exact zero.

The first normal session exposed an API projection defect: the ROS gateway
reported `action_server=true` and exact publisher counts, but
`NavigationCoordinator.view()` omitted those fields. The checker therefore
failed closed. Nav2 was stopped and the lease was released before code was
changed. Commit `7e2fd9b` projects only the existing readiness evidence and
adds regression coverage; it changes no velocity, clock, lease, watchdog,
publisher-cardinality or filesystem guard.

After deploying that commit to isolated release directories on both Jetsons,
the second normal session exposed all required readiness fields correctly.
The approved initial pose was published once in each isolated normal session;
there was no replay within either session, but the pre-goal restart means two
total initial-pose publications occurred during this C4 attempt. This is
recorded as a procedural restart, not counted as a completed single-session
C4 run. Neither session received a goal.

The final localization measurements included:

- PointCloud approximately 10.01 Hz, age about 0.04 s;
- controller odometry `9.984`, `9.999`, `9.997`, then `10.013` Hz;
- zero translation and heading jumps;
- host clock offsets about 0.032-0.046 s;
- connected `map -> odom -> base_link`, one publisher for each required input
  and one active Nav2 action server.

The health state briefly reached `READY` at 10.013 Hz and returned to
`DEGRADED` before the exact checker snapshot. The checker correctly returned
`TRACK C4 BLOCKED: localization health is not READY`. No retry loop was used
to cherry-pick a passing instant.

## Acceptance table

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact route approval and physical supervision | `PASS` | operator supplied the exact C4 approval string |
| Hardware-free C2/C3/C4 regression | `PASS` | focused suites passed 16, 13, 11, 9 and 16 tests |
| Immutable candidate release | `PASS` | `1f0c220`, then readiness fix `7e2fd9b`, installed separately on both hosts |
| C2 lease-free NG0 | `PASS` | exact checker: `WAITING_FOR_INITIAL_POSE`, raw command quiet |
| Clock/source guards | `PASS` | NTP synchronized; strict source-age/future-skew rules unchanged |
| XT16/IMU/FAST-LIO/controller odometry | `PASS` | exact raw, relay and preview preflights; fixed topic/frame ownership |
| Bridge cardinality and zero command | `PASS` | `1/0/10/11`, fresh LowState, deadman false, exact zero |
| Normal Nav2 startup | `PASS` | exact map and parameter revisions; exclusive navigation lease |
| Initial-pose procedure | `FAIL` | one publish per isolated session, but two sessions were required before final gate |
| Stable pre-goal localization health | `BLOCKED` | odometry frequency oscillated across strict 10.0 Hz threshold |
| C4 exact checker | `BLOCKED` | `localization health is not READY` |
| Goal submission | `NOT_RUN` | blocked before goal endpoint |
| Robot motion | `NOT_RUN` | no goal or manual command was issued |
| Reverse cleanup | `PASS` | goal/session idle, lease inactive, exact zero, C4 owners absent |

## Repository verification

- focused Python suites: 71/71 passed across the C2, C3, C4, gateway and API
  groups before hardware work; the readiness projection change then passed
  46/46 focused tests;
- dependency-complete project Python suite: 993/993 passed;
- required host-Python suite: 989 tests ran, with the existing single import
  error because the macOS host interpreter lacks declared `fastapi`;
- JavaScript unit suite: 270/270 passed;
- frontend syntax: 53/53 modules passed;
- focused Ruff and `git diff --check`: passed;
- repository-wide Ruff continues to report 11 pre-existing test-file style
  findings outside this change.

## Cleanup and remaining risk

The external production dashboard and mounted Control Bridge were restored to
clean release `140db78`. The production profile is `go2-xt16-wireless`; Nav2,
localization-only session and goal are idle; lease is inactive; deadman is
false; command is exact zero; and the Bridge is authenticated-ready with
`1/0/10/11` publisher cardinality. The dashboard's established XT16 preview
policy reacquired only the relay/preview path. IMU, wireless odometry, Nav2 and
FAST-LIO C4 owners are inactive.

The mounted Jetson's sensor-network connection still contains a persistent
default gateway configuration even though that network has no Internet. The
current-boot route correction is not a persistent fix. Before another C4
attempt, make the isolated wired connection `never-default` (while retaining
its direct `192.168.123.0/24` route), reboot or reconnect under supervision,
and prove NTP persistence. Separately resolve the 10 Hz health-margin problem
without lowering the 10.0 Hz gate or republishing synthetic odometry. A new
exact C4 approval is required after those prerequisites and a fresh route
preview; this approval is consumed and must not be reused.

Follow-up: the persistent network/NTP prerequisite was completed and verified
after a real reboot on 2026-09-02. See
`docs/MOUNTED_JETSON_NETWORK_TIME_ACCEPTANCE.md`. The separate 10 Hz
controller-odometry margin remains unresolved.
