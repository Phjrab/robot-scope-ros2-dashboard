# ADR: Competition FAST-LIO controller odometry

Status: accepted for the explicit C2 profile on 2026-09-02

## Decision

Add the opt-in profile `go2-xt16-wireless-competition-fastlio`. It keeps the
existing wireless XT16 and authenticated body-IMU owners on the Go2-mounted
Jetson and the existing Hesai bridge and FAST-LIO owners on the external
Humble Orin. The navigation runtime validates each `/Odometry` sample and is
the sole publisher of:

```text
/robot_scope/nav/controller_odom_fastlio
nav_msgs/msg/Odometry
odom -> base_link
reliable, volatile, keep-last 5
```

The source `/Odometry` remains the localization odometry. The derived topic is
only the controller odometry for this profile. The strict wired, wireless and
`competition-pdf-direct` profiles continue to select
`/utlidar/robot_odom`; their 500 ms past/100 ms future transport guard and
their sender/receiver ownership are unchanged.

## Context and physical topology

- Go2-mounted Jetson: management `192.168.50.30`, sensor LAN
  `192.168.123.18/24`, Ubuntu 20.04 / ROS 2 Foxy. It physically reaches Go2
  and XT16 and owns only the fixed wireless relay and authenticated IMU sender
  needed by this profile.
- External Orin: `192.168.50.10`, Ubuntu 22.04 / ROS 2 Humble. Its existing
  pinned workspaces own Hesai decode, cloud bridge, FAST-LIO, map load and
  Nav2.

The education architecture describes a single direct host. That topology
cannot be executed here without moving hardware or mixing ROS distributions:
the only direct sensor host is Foxy and the Humble host has no sensor-LAN NIC.
Porting the entire navigation stack to Foxy would introduce a second plugin
and dependency baseline. C2 therefore reuses the previously accepted external
Humble wireless perception path before considering that larger fallback.

## Data, frame and time contract

The accepted source is exactly one `/Odometry` publisher with
`camera_init -> body`. The output preserves the complete validated source
stamp, pose, twist and both covariance arrays; only the existing runtime frame
projection changes the identity to `odom -> base_link`. It never replaces the
stamp with `now()`.

Publication is blocked for a zero or non-increasing stamp, source age over
500 ms, future skew over 250 ms, NaN/Inf, invalid quaternion, implausible
twist, translation/yaw discontinuity, input silence over 750 ms, input or
output publisher cardinality other than one, or runtime process-generation
change. These constants are code-owned and cannot be selected by HTTP.

The output is not a fallback source. A stale/reset/conflicting source makes
readiness false. A process-generation change requires a new runtime owner;
recovery never creates a lease, initial pose, goal, ARM or deadman state.

## Profile and Nav2 ownership

The server startup profile fixes both mode and topic. Arbitrary topic, frame,
peer, port and timestamp settings are not accepted from requests. Only this
profile deterministically patches `bt_navigator`, `controller_server` and an
installed velocity smoother to the derived topic. The canonical tuned Humble
configuration and private output `/robot_scope/nav/cmd_vel_raw` remain
unchanged. The NG0 launcher does not start the onboard wireless odometry
sender/receiver or any `cmd_vel_to_sport` bridge.

NG0 is pre-localization: lifecycle nodes, map publisher, fresh scan, fresh
FAST-LIO and derived odometry, and `odom -> base_link` are required, while
`map -> base_link` is expected to be absent before an initial pose. NG1 adds
the initial-pose/localization and costmap contract. C2 executes NG0 only.

## Startup, cleanup and rollback

The order is fixed: XT16 relay, authenticated IMU, external Hesai, bridge,
FAST-LIO, navigation runtime/derived odometry, then no-goal Nav2. Every owner
must have one publisher and fresh data before the next stage. Cleanup is the
reverse order and must leave no owned child, topic publisher or fixed UDP
socket. Nothing is enabled at boot and there is no auto-resume.

Rollback selects the prior explicit profile, removes no data, and restarts no
service automatically. The derived topic then has no publisher and the strict
source remains `/utlidar/robot_odom`. An actual initial pose is reserved for
Track C3; a navigation goal, lease and robot motion require later approval.
