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

## Safety and deployment status

This change creates no control publisher, lease, motion command, Mapping/Nav
start, network mutation or automatic service. It does not install or run the
new executable on either Jetson. Live `/velodyne_points` validation and HW-4
remain `NOT_RUN` until the later deployment gate and explicit approval.
