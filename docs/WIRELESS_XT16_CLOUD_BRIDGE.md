# Wireless XT16 cloud-only C++ bridge

## Gate 5 boundary

The ROS package now installs two explicit executables from the same reviewed
C++ conversion source:

| Executable | Input | Output | Intended profile |
| --- | --- | --- | --- |
| `robot_scope_xt16_bridge_node` | `/lidar_points`, `/lowstate` | `/velodyne_points`, `/imu/body` | existing wired legacy profile |
| `robot_scope_xt16_cloud_bridge_node` | `/lidar_points` | `/velodyne_points` | wireless profile only |

The cloud-only target is compiled with `ROBOT_SCOPE_XT16_CLOUD_ONLY=1`. Its
translation unit therefore excludes the Unitree `LowState` header, topic,
subscription, callback, IMU message, publisher and counters. Wireless IMU
ownership remains exclusively with the authenticated receiver documented in
`docs/WIRELESS_IMU_PROTOCOL.md`.

Gate 5 does not replace the existing executable or runner. The legacy target
still builds with `unitree_go`, subscribes to `/lowstate` using best-effort,
volatile, keep-last depth 5 and publishes `/imu/body` exactly as before. The
existing wired preview continues to invoke `scripts/run_xt16_bridge_humble.sh`.

## Shared cloud contract

Both executables compile the same high-rate C++ cloud path. There is no Python
runtime converter and no duplicate conversion implementation. The shared path
retains:

- exact `/lidar_points` input and `/velodyne_points` output;
- input frame `hesai_lidar`, one-row layout and 4,000–100,000 point bound;
- exact input fields `x`, `y`, `z`, `intensity`, `ring`, `timestamp`;
- four-to-one decimation with at least 1,000 finite output points;
- exact 22-byte output fields `x`, `y`, `z`, `intensity`, `time`, `ring`;
- reliable, volatile, keep-last depth 1 input and depth 5 output QoS;
- scan-duration, device/header agreement, residual, stale, future and
  monotonically increasing timestamp rejection;
- initial clock calibration and bounded stable relock without rebasing a
  rejected sample.

`scripts/run_xt16_cloud_bridge_humble.sh` accepts no arguments and names only
the new installed C++ executable. Network ownership, the fixed receive-buffer
ceiling and wireless readiness checks remain Gate 6 responsibilities; this
runner does not bypass or reconfigure them.

The default package build still produces both executables and therefore keeps
the wired legacy `unitree_go` dependency. An external mapping host that does
not install Unitree message packages uses the separate fixed
`scripts/build_xt16_cloud_bridge_humble.sh` entrypoint. It selects only
`ROBOT_SCOPE_XT16_BUILD_LEGACY=OFF`, builds the same cloud-only target and does
not install, emulate or stub `unitree_go`. The option defaults to `ON`, so the
existing wired build and runner do not silently lose their legacy executable.

## Registered contract test

CTest registers `robot_scope_xt16_cloud_contract`, which invokes the shared
conversion contract directly without initializing rclcpp or spinning a ROS
node. Synthetic 4,000-point inputs verify the exact output fields, 22-byte
stride, four-to-one decimation, calibrated timestamp and finite-value rules.
Fail-closed cases cover stale device time, clock-residual discontinuity, wrong
frame, malformed or duplicate fields, short payload and insufficient finite
decimated points. The test target links `rclcpp` and `sensor_msgs` only; it does
not link `unitree_go` or exercise the legacy LowState/IMU path.

## Safety and deployment status

This change creates no control publisher, lease, motion command, Mapping/Nav
start, network mutation or automatic service. At Gate 7, only an isolated
external-Orin `/tmp` build/test tree existed and HW-4 remained `NOT_RUN`. The
later separately supervised deployment and live `/velodyne_points` result are
recorded as `CLOUD_PASS` in `docs/WIRELESS_MAPPING_ACCEPTANCE.md`; repository
tests alone still do not claim live hardware behavior.
