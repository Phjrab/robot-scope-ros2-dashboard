# WP02 offline registration comparison matrix — 2026-09-29

Status: `SYNTHETIC_SOFTWARE_PASS`; `REAL_DATA_REPLAY_BLOCKED`; `LIVE_NOT_RUN`.

This work keeps `bounded-se2-icp` as the default 3DoF backend. It adds an
opt-in `--suite extended` to the existing offline benchmark; the original
ten-case default and `--require-acceptance` behavior remain unchanged. No ROS,
HTTP, map runtime, control, robot, Jetson service, or pose-application path is
created or invoked by the matrix.

## Reproduction

The measured source started at commit `89a104c20f5d2f6ca477e2a1de1eb8baca13c971`.
The benchmark report records the executable, benchmark, registration source,
and generated input hashes, plus source dirty state. On macOS 26.3 arm64,
Python 3.13.2 and Apple clang 21, the portable executable was built with:

```sh
WP02_DIR=$(mktemp -d /tmp/robot-scope-wp02.XXXXXX)
clang++ -std=c++17 -O2 -Wall -Wextra -Wpedantic \
  -I ros2/robot_scope_registration/include \
  ros2/robot_scope_registration/src/registration_core.cpp \
  ros2/robot_scope_registration/src/offline_registration_cli.cpp \
  -o "$WP02_DIR/robot_scope_offline_registration"
python3 scripts/benchmark_offline_registration.py \
  --executable "$WP02_DIR/robot_scope_offline_registration" --require-acceptance
python3 scripts/benchmark_offline_registration.py \
  --executable "$WP02_DIR/robot_scope_offline_registration" \
  --suite extended --build-label 'Apple clang 21 -std=c++17 -O2' \
  --output "$WP02_DIR/matrix.json" --require-acceptance
```

The local structured result from this run is
`/tmp/robot-scope-wp02-matrix.json`. It is not committed because wall time and
peak RSS are host/run dependent; rerun the commands to generate a new report.
The `manifest_sha256` covers fixed input PCD hashes and seeds. The Python
test runs the matrix twice and checks the manifest and categorical outcomes.

## Observed results

| Measure | Original ten-case baseline | Extended matrix |
| --- | ---: | ---: |
| Cases | 10 | 29 |
| Converged | 10 | 21 |
| Policy accepted | 10 | 20 |
| Expected invalid cases falsely accepted | not applicable | 0/6 |
| Injected timeout / abrupt child termination | not applicable | 1 / 1 |
| Translation median / p95, accepted cases with synthetic truth | 0.00511 / 0.01658 m | 0.00719 / 0.01658 m |
| Yaw median / p95, accepted cases with synthetic truth | 0.173 / 0.281 degrees | 0.162 / 0.281 degrees |
| Child runtime p50 / p95 | 229 / 246 ms | 229 / 299 ms |
| Engine child peak RSS (Darwin bytes) | 2,015,232 | 2,097,152 |

The extended corpus contains ten baseline transforms, asymmetric corridor,
height-varying pillars, partial field of view, 30/50% density dropout,
Gaussian noise, outliers, three initial-seed variants, a repeated symmetric
corridor, six invalid-input cases, and two bounded process-failure injections.
Every case records input hashes, seed, outcome, convergence and policy label
when available, wall time, and known-truth errors when applicable. `observe`
cases are not counted as acceptance assertions. The known truth comes from
transforming the same generated reference cloud, **not an independent sensor
measurement**.

The large initial-yaw-error case reported `converged=true` but
`confidence=REJECTED`, illustrating why convergence is not acceptance. The
repeated corridor was `MEDIUM`, not `HIGH`. The wrong-seed case produced an
invalid child JSON response after a zero exit; it is recorded as a process
error, not as a successful registration. The other five invalid cases failed
closed during preprocessing. The failure-injection child terminates only its
own PID with `SIGKILL`; it does not signal any other process. No acceptance
threshold was relaxed.
The failure-injection Python child had a separate 15,466,496-byte peak and is
not included in the engine RSS figure. Runtime percentiles cover only cases
that returned a parsed registration result; wall times also cover failures.

## Data and backend limits

WP01 found two lineage-linked PCD maps and 13 occupancy maps on the external
Jetson, but no replayable raw LiDAR+IMU or processed cloud+odometry sequence
in the bounded surveyed paths, and no independent ground truth. Those map
PCDs are references, not independent time-stamped queries. Consequently no
real-data accuracy or temporal-replay result is claimed. No rosbag runner was
added without a suitable bag. PCL NDT2D/GICP are compile-time opt-in and no
matching current-source executable was prepared for this run; the ADR records
historical NDT seed/runtime sensitivity and a GICP optimizer crash. Neither
was selected as a default or compared as if it had run here.

The next real-data experiment requires a provenance-checked query sequence
with frame/calibration and map family revision. Ground truth must be supplied
independently before absolute position error is reported. The aarch64
benchmark remains unmeasured in this WP; an isolated Jetson build can be run
later without touching the deployed release or services.
