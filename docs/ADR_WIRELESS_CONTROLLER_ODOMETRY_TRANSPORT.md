# ADR — Authenticated wireless controller-odometry transport

- Status: deployed; WNO-1 passed, WNO-2 blocked by stale source timestamps
- Date: 2026-09-01
- Scope: the single Go2 controller-odometry observation required by Nav2
- Related: [wireless control transport](ADR_WIRELESS_CONTROL_TRANSPORT.md),
  [bounded wireless XT16/FAST-LIO transport](ADR_WIRELESS_XT16_FASTLIO_TRANSPORT.md)

## Context

The accepted wireless topology leaves Go2 DDS on the robot-side Jetson at
`eth0=192.168.123.18/24`. Robot Scope and Nav2 remain on the external Orin at
`eno1=192.168.50.10/24`. The robot-side host publishes exactly one
`nav_msgs/msg/Odometry` endpoint on `/utlidar/robot_odom`; a 2026-09-01
read-only audit measured RELIABLE/VOLATILE QoS and the fixed frames
`odom -> base_link`. The external host has no direct Go2 DDS interface.

NAV0 proved that wireless XT16, authenticated IMU and FAST-LIO can become
ready. It then failed closed because the legacy navigation launcher required a
direct Unitree workspace/interface and the external graph had no fresh
controller odometry. FAST-LIO `/Odometry` cannot replace the controller source:
the two estimates have different safety roles and the Navigation gateway
intentionally requires both to advance during the current start session.

## Decision

Carry only the fixed numeric content of `/utlidar/robot_odom` through a new
purpose-specific binary UDP protocol:

~~~text
Robot-side 192.168.50.30:46030
  /utlidar/robot_odom -> authenticated fixed binary envelope
                         ------------------------------->
External 192.168.50.10:46030
  validated envelope -> /utlidar/robot_odom
~~~

The 784-byte datagram is below 1,200 bytes and contains only:

- protocol magic/version/type and a fixed sender ID;
- sender boot UUID, transport sequence, sender realtime/monotonic timestamps;
- the original ROS source timestamp;
- position, orientation, linear/angular velocity;
- the two fixed 36-element covariance arrays;
- HMAC-SHA256.

Topic names, frames, peers and port are constants. The sender accepts only one
RELIABLE/VOLATILE source publisher with `odom -> base_link`; it caps output at
100 Hz. The receiver binds and connects one UDP socket to the exact peer,
requires a separate owner-only 32-byte `/etc/robot-scope/wireless-odom.key`,
and republishes the original source stamp without rebasing it.

The receiver rejects wrong length, HMAC, magic/version/type, sender/boot ID,
duplicate/reordered/replayed sequence or timestamp, unsynchronized clocks,
stale/future packets, non-finite values, implausible numeric bounds and an
invalid quaternion. A new/recovered boot requires five consecutive fresh
samples. It publishes only when it is the sole publisher on the fixed external
topic. Receiver loss does not create a cached or locally rebased odometry
sample.

## Lifecycle and Navigation ownership

The existing wired profile remains unchanged and continues to source
`setup_go2_ros2_humble.sh`. Only explicit `go2-xt16-wireless` Navigation uses
`setup_wireless_mapping_ros2_humble.sh`; this ROS environment needs no Unitree
workspace on the external host.

The fixed Nav launcher owns the narrow odometry lifecycle:

1. use the existing restricted SSH channel to ensure the disabled robot-side
   odometry sender is started;
2. start one local receiver child;
3. require exactly one publisher and three fresh advancing samples;
4. only then start the Navigation runtime and fixed Nav2 children;
5. on stop or failure, terminate the receiver and stop the robot-side service
   only when this launcher started it.

The forced SSH helper gains only literal `odom-status`, `odom-start` and
`odom-stop` actions for the one fixed service. Sudoers grants only those exact
systemd commands. The browser cannot provide a service, command, topic, peer,
key or port. Units remain disabled and there is no automatic Nav, Mission, ARM,
lease, initial-pose or goal resume after recovery.

The external fixed firewall adds one allow rule for
`.50.30:46030 -> .50.10:46030` followed by a drop for all other input to the
destination port. It does not add FORWARD, route, NAT, IP forwarding, bridge,
multicast forwarding or DDS Router behavior.

## Failure policy

| Failure | Required result |
|---|---|
| missing/wrong key or peer | sender/receiver remains unavailable |
| source publisher count is not one | sender transmits nothing |
| HMAC/replay/clock/value rejection | receiver readiness resets immediately |
| packet age exceeds 250 ms | receiver is not ready; no current sample is synthesized |
| external publisher conflict | receiver publishes nothing |
| readiness timeout | Nav2 children are never started |
| receiver or Nav child exits | the complete launcher process group stops |
| Wi-Fi loss/recovery | no automatic Navigation activation, lease or goal resume |

The existing Navigation gateway's single-publisher, freshness and strict
source-stamp advancement checks remain unchanged.

## Rejected alternatives

- Copy FAST-LIO `/Odometry` to `/utlidar/robot_odom`: hides a missing independent
  controller observation and weakens the safety gate.
- Source the Unitree overlay from a rollback tree on the external host: restores
  neither the physical DDS interface nor a reviewed deployment owner.
- Route/NAT, Linux bridge, multicast forwarder or DDS Router: exposes a broader
  graph and bypasses the fixed observation contract.
- Generic ROS topic relay or configurable UDP proxy: adds an extensible network
  surface unrelated to this one requirement.
- Start either transport unit at boot: violates explicit lifecycle ownership and
  could publish stale authority before an operator requests Navigation.

## Acceptance boundary

Software tests prove serialization, authentication, replay/freshness state,
fixed peers/topics, bounded values, service confinement, launcher ordering and
the preserved wired path. They do not prove live packet rate, Wi-Fi loss,
external graph cardinality or Nav2 startup. Deployment and stationary no-goal
acceptance follow the separate reviewed plan and require explicit approval.
