# Phase 14 — Localization, TF and Calibration Health

Phase 14 turns the Navigation page's binary readiness indicators into bounded,
explainable localization diagnostics. It does not change a motion gate, ROS
topic, timestamp tolerance, transform publisher, Nav2 parameter, mapping
process, or calibration file. Live Go2/XT16 verification remains deferred until
the user explicitly requests the robot-connected Phase 11 procedure.

## Data ownership

The fixed `navigation_runtime.py` process already owns PointCloud projection,
FAST-LIO odometry validation and the `map -> odom -> base_link` broadcasts. It
now keeps two 32-sample monotonic arrival windows and bounded counters for:

- PointCloud frequency, jitter, age, input points and accepted points;
- FAST-LIO odometry frequency, jitter and age;
- last `odom -> base_link` and `map -> odom` broadcast age;
- translation and heading discontinuity count and most recent age;
- advancing cloud and odometry sequence numbers;
- fixed frame, extrinsic and timestamp-domain descriptions.

Those additive fields travel inside the existing fixed, topology-validated
`/robot_scope/nav/runtime_health` schema. `NavigationRosGateway` still verifies
that the publisher is unique, the topics and frame are fixed, counters and
numbers are bounded, and freshness comes from navigation-owned callbacks rather
than UI graph metrics. Invalid health cannot open an existing safety gate.

The gateway adds goal remaining distance, bounded progress rate, controller
stall duration, successful costmap-clear count and observed host/device clock
offsets. The application coordinator only projects this read-only result into
the existing `GET /api/v1/navigation` response.

## Explicit health model

There is deliberately no synthetic confidence percentage. Every snapshot has
one state, one reason code and the exact threshold basis:

`READY`, `DEGRADED`, `STALE`, `DISCONTINUITY`, `FRAME_MISMATCH`,
`CALIBRATION_SUSPECTED`, or `UNAVAILABLE`.

Thresholds are declared under `navigation_health` in `config/go2.json` and are
bounded again when loaded. The classifier is observation-only; it is not an
alternate motion authority. `READY` requires at least three distinct advancing
cloud/odometry sequences after a stale period. Repeated cached health messages
cannot advance the sequence, and a stale source resets it.

An active runtime without an initial pose is `DEGRADED` with
`INITIAL_POSE_REQUIRED`, not falsely `READY`. Missing telemetry is
`UNAVAILABLE`; age violations are `STALE`; recent estimator resets are
`DISCONTINUITY`; fixed-frame errors are `FRAME_MISMATCH`. Performance thresholds
cover rate, jitter, accepted point count and active-goal stall duration.

## Calibration Assistant

The Navigation page contains a read-only assistant for:

- LiDAR-to-base extrinsic and PointCloud `frame_id`;
- FAST-LIO odometry parent/child frames;
- static-TF publisher review without claiming that publisher count proves a
  duplicate transform;
- pointcloud, host ROS and robot/device clock-domain observations;
- cloud direction versus the configured robot-model pose.

Each row provides a suspected cause, observed value, expected contract,
related config key/file and a safe manual verification step. The assistant has
no form controls or mutation endpoint and reports
`writes_configuration: false`. It never writes YAML/JSON, calls a ROS parameter
service, launches a process, publishes a transform, or substitutes `now()` for
sensor timestamps.

## Hardware acceptance linkage

The Phase 11 recorder now adds `navigation.localization_health`. A running and
localized session passes only when the Phase 14 model is `READY`; an idle
pipeline or supervised initial-pose prerequisite remains `BLOCKED`; other
running states fail with bounded state, reason, rate, age, TF and fresh-sequence
evidence. This does not turn hardware-free CI into hardware proof.

## Compatibility and safety

- Existing routes and mutation payloads are unchanged; the Navigation GET
  response receives additive `localization_health` and
  `calibration_assistant` objects.
- Existing scan/odom/runtime freshness, exact-one publisher, frame, map
  revision, lease, deadman, goal and cleanup gates are unchanged.
- The Go2 profile gains diagnostic thresholds only. Generic and TurtleBot
  capabilities are not widened.
- Browser rendering uses `textContent`, caps assistant rows, and contains no
  calibration command or editable field.
- No robot, service, mapping/Nav2 process, map or dataset was touched during
  repository verification.

## Hardware-free acceptance

Tests cover all seven states, threshold bounds, fresh-sequence recovery,
bounded rate windows, additive health validation, read-only assistant source,
profile completeness, Navigation projection and UI rendering. The complete
Python, Node, browser E2E, syntax, compile, dependency, secret and diff results
were 632/632 Python tests, 157/157 Node tests, 10/10 Playwright fake-backend
scenarios, 19 frontend modules, Python compileall, repository secret scan,
`pip check`, npm production audit and diff check all passing. Ruff and Mypy
remain CI-owned and were not installed locally. Actual rates, TF ages, clock
offsets and cloud/model direction must be rechecked on the deployed Jetson
with the robot and XT16 available.
