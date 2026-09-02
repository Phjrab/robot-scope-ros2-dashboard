# Track C4A odometry-rate gate acceptance

Date: 2026-09-02

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

## Acceptance status before hardware deployment

| Acceptance item | Status |
| --- | --- |
| `SOFTWARE_IMPLEMENTATION_PASS` | `PASS` |
| `RATE_WINDOW_METRICS_PASS` | focused tests pass |
| `HYSTERESIS_TESTS_PASS` | focused tests pass |
| `PROFILE_ISOLATION_PASS` | focused tests pass |
| `STRICT_GUARDS_UNCHANGED_PASS` | code review and focused tests pass |
| `FULL_TEST_SUITE_PASS` | `PASS` |
| `CI_PASS` | pending implementation commit |
| `CLEAN_DEPLOYMENT_PASS` | `NOT_RUN` |
| `NG0_RECHECK_PASS` | `NOT_RUN` |
| `INITIAL_POSE_ONCE_PASS` | `NOT_RUN` — fresh operator confirmation required |
| `LOCALIZED_NG1_PASS` | `NOT_RUN` |
| `STATIONARY_10_MIN_SOAK_PASS` | `NOT_RUN` |
| `C4_PREGOAL_NOT_RUN` | confirmed |
| `GOAL_NOT_RUN` | confirmed |
| `MOTION_NOT_RUN` | confirmed |
| `CLEANUP_PASS` | pre-change cleanup confirmed; post-soak pending |

Hardware results must be appended only after exact-commit clean deployment and
fresh operator confirmation of the pinned map revision and candidate pose. A
momentary READY sample must never be recorded as a soak pass.
