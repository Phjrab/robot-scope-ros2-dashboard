# Track C4A odometry-rate gate acceptance

Date: 2026-09-03

## Scope

This phase stabilizes nominal-10 Hz odometry readiness for only the
`go2-xt16-wireless-competition-fastlio` profile. It does not allow
`DEGRADED` health, bypass the C4 checker, send a navigation goal, acquire a
navigation/control lease, ARM, press deadman or publish a non-zero command.

The working baseline was the newer fast-forward `main` commit `4082135`, which
contains the prompt's `44a1e09` baseline plus the persistent mounted-Jetson
network/NTP acceptance. The worktree and `origin/main` were aligned and the
latest baseline CI run `33634992129` was successful.

## Pre-change cleanup evidence

Before editing, the production dashboard reported no navigation goal, an idle
Nav2/localization session, no lease, deadman released and exact zero linear and
angular command. The signed Control Bridge was authenticated-ready with fresh
LowState and `1/0/10/11` publisher cardinality. No C4-owned Nav2, FAST-LIO,
wireless IMU or wireless odometry process was present. The established XT16
preview relay remained the only sensor relay active.

## Effective competition policy

| Setting | Value |
| --- | ---: |
| nominal odometry rate | 10.0 Hz |
| READY enter rate | 9.5 Hz |
| READY exit rate | 9.0 Hz |
| READY enter dwell | 10.0 s |
| READY exit dwell | 2.0 s |
| maximum inter-arrival gap | 0.25 s |
| odometry stale | unchanged, 0.50 s |
| odometry jitter | unchanged, 0.10 s |
| TF stale | unchanged, 0.50 s |

The policy source is the fixed server table keyed by the immutable navigation
profile. Existing strict wireless and other profiles retain their previous
instantaneous `odometry_min_hz` behavior.

## Software evidence

The rate window exposes separate raw and display frequency plus mean, median,
nearest-rank p95, maximum gap, window duration and bounded sample/interval
counts. The session-owned stabilizer advances on the runtime-health callback,
resets on session/initial-pose/process generation boundaries, and treats every
non-rate failure as immediate. The C4 checker still requires READY and now
also requires stable READY duration and exact policy evidence.

Focused tests cover exact/near-10 Hz windows, raw/display separation,
deterministic periods, bounded history, enter/exit dwell, hysteresis hold,
maximum gap, stale/non-rate faults, process generation reset, profile isolation
and C4 checker rejection paths.

## Repository verification

- focused C2/C3/C4, runtime, health and gateway suites: 81/81 passed;
- dependency-complete project Python suite: 1003/1003 passed;
- required host-Python suite: 999 tests ran with the existing single import
  error because the macOS host interpreter lacks declared `fastapi`;
- JavaScript unit suite: 270/270 passed;
- Cockpit JavaScript suite: 86/86 passed;
- hardware-free browser E2E: 32/32 passed;
- Ruff, configured mypy targets, Python compile, shell syntax, frontend syntax
  for 53 modules, tracked-source secret scan and `git diff --check`: passed.

## Exact deployment and operator-approved pose

The implementation commit `116455335b091d5962aef15f90e49b69c1fad0a9`
was pushed to `origin/main`; GitHub Actions run `33638739598` passed on both
Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12. Its Git archive SHA-256
was `970bc8cde343fba2f65169d0bd167ff6145677e0a453eede56350b566c4fff30`.
The archive was extracted into the clean external-Orin release directory
`/home/jetson_orin_nano/releases/robot-scope/1164553`. File hashes were
compared with the local commit before the service override, working directory,
process working directory and executable were all verified to resolve to that
release. The old dirty checkout was not pulled, reset or cleaned. The previous
release and private environment/service rollback copies remain available.

The temporary validation profile was
`go2-xt16-wireless-competition-fastlio`. The pinned inputs were:

| Item | Exact value |
| --- | --- |
| map | `map_20260902_161903_edited` |
| map ID | `f292601e2c8b269eb635cb0f` |
| map revision | `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93` |
| parameters revision | `194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77` |
| initial pose | `x=0.0, y=0.0, yaw=0.0` |
| map geometry | 297 x 156, 0.05 m/cell, origin `(-8.97357559204, -2.05925989151, 0)` |
| candidate cell | `(179, 41)`, value 0 (known free) |
| 0.22 m robot-radius clearance | 61/61 cells free |
| nearest non-free cell center | 0.982 m |

After the exact fresh operator confirmation `C4A 초기 위치 승인 —
map_20260902_161903_edited, x=0 y=0 yaw=0, 로봇 정지 및 E-stop`, the
localization-only API published `/initialpose` exactly once. It was not retried
or replayed. The observed localized pose was approximately
`(0.00038, -0.00098, -0.000093)`. The localized NG1 checker passed with
`localization=LOCALIZED`, a connected transform chain and quiet raw command.

## Stationary 10-minute no-goal evidence

The accepted bounded run collected 600/600 one-second samples over 599.06
seconds. Every health and instantaneous state sample was `READY`; the READY
transition count did not change. The first sample was taken only after the
required enter dwell had completed.

| Metric | Result |
| --- | --- |
| raw odometry rate | min 9.926524, median 10.000890, p95 10.043638, max 10.077452 Hz |
| display odometry rate | min 9.927, median 10.001, p95 10.044, max 10.077 Hz |
| mean period | maximum 0.100740 s |
| median period | median 0.100108 s, maximum 0.103030 s |
| p95 period | median 0.116299 s, p95 0.123861 s, maximum 0.130266 s |
| maximum gap | min 0.110570, median 0.121233, p95 0.130611, max 0.141802 s |
| odometry freshness/jitter | max age 0.0458 s; max jitter 0.0152 s |
| cloud rate | min 9.927, median 9.999, max 10.077 Hz |
| cloud freshness/jitter | max age 0.0653 s; max jitter 0.0113 s |
| accepted points | min 14,141, median 14,180, max 14,450 |
| TF freshness | max age 0.003 s |
| stable READY duration | 461.091 s through 1060.092 s on the session clock |
| resources | load1 max 8.92; managed RSS max 432.996 MiB; available memory min 5160.02 MiB; swap 0; temperature max 43.406 C |

All 600 API samples retained goal `idle`, localization-only motion disabled,
lease inactive, deadman false, exact-zero dashboard command and zero non-zero
raw-command observations. A simultaneous direct robot-side DDS monitor saw
1,159 `/api/sport/request` samples: all 1,159 were API 1003 `StopMove` and zero
were API 1008 `Move`. This is explicit no-motion evidence, not goal approval.

An earlier overnight waiting session independently demonstrated fail-closed
behavior when its odometry timestamp became stale; its initial-pose count
remained zero and it was discarded. The accepted session was started fresh.
A separate first measurement-script invocation was excluded because Jetson's
thermal sysfs produced a host-only `TypeError` before it collected a sample;
it did not alter robot or navigation state. Immediately after the one-shot
pose, `map -> odom` was briefly unavailable while localization converged, then
the full 10-second READY dwell completed normally.

## Final acceptance status

| Acceptance item | Status |
| --- | --- |
| `SOFTWARE_IMPLEMENTATION_PASS` | `PASS` |
| `RATE_WINDOW_METRICS_PASS` | focused tests pass |
| `HYSTERESIS_TESTS_PASS` | focused tests pass |
| `PROFILE_ISOLATION_PASS` | focused tests pass |
| `STRICT_GUARDS_UNCHANGED_PASS` | code review and focused tests pass |
| `FULL_TEST_SUITE_PASS` | `PASS` |
| `CI_PASS` | `PASS` — run `33638739598` |
| `CLEAN_DEPLOYMENT_PASS` | `PASS` — clean release `1164553`, archive and source hashes verified |
| `NG0_RECHECK_PASS` | `PASS` — command-isolated prelocalization checker |
| `INITIAL_POSE_ONCE_PASS` | `PASS` — exact fresh operator approval, count exactly one |
| `LOCALIZED_NG1_PASS` | `PASS` — localized checker and transform/costmap/lifecycle contract |
| `STATIONARY_10_MIN_SOAK_PASS` | `PASS` — 600/600 samples, 599.06 seconds |
| `C4_PREGOAL_NOT_RUN` | confirmed |
| `GOAL_NOT_RUN` | confirmed |
| `MOTION_NOT_RUN` | confirmed |
| `CLEANUP_PASS` | `PASS` — reverse session cleanup, strict profile restored, temporary files removed |

After the soak, the localization-only session was stopped in reverse order.
The navigation API returned session/pipeline/goal `idle`, no lease, deadman
released and exact zero. The private environment was restored to
`go2-xt16-wireless`; the dashboard remained on clean release `1164553`. The
robot-side release remained `140db78` because C4A changed no robot-side source.
Only the established production Control Bridge and XT16 preview relay remain
active. Temporary transfer, service-fragment and soak-script files were
removed; rollback backups and both clean releases were intentionally retained.

`C4_PREGOAL_NOT_RUN`, `GOAL_NOT_RUN` and `MOTION_NOT_RUN` are deliberate hard
boundaries. C4A approval cannot be reused for C4B.
