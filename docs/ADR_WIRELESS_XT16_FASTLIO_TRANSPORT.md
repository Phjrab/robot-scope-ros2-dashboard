# ADR — Bounded wireless XT16 and FAST-LIO transport

- Status: accepted for implementation; deployment not authorized
- Date: 2026-08-31
- Scope: XT16 packet, minimum Go2 IMU, FAST-LIO and mapping input boundary
- Related: [dual-Jetson workload split](ADR-001_DUAL_JETSON_WORKLOAD_SPLIT.md),
  [wireless control transport](ADR_WIRELESS_CONTROL_TRANSPORT.md)

## Context

The accepted competition topology keeps Robot Scope, ROS 2 Humble, FAST-LIO,
map lifecycle and Nav2 on the external Orin. Only the robot-side Jetson owns
the Go2 and sensor Ethernet network. The 2026-08-31 read-only audit measured:

| Role | Verified interface and address |
| --- | --- |
| Robot-side management | `wlan0=192.168.50.30/24` |
| Robot-side sensor LAN | `eth0=192.168.123.18/24`, no default gateway |
| External dashboard | `eno1=192.168.50.10/24` |
| Go2 body | `192.168.123.161` |
| XT16 | `192.168.123.20` |

The robot-side host reached the Go2, XT16 and external Orin with zero packet
loss in the bounded audit. Both hosts reported synchronized NTP clocks. The
robot-side LowState graph contained one bare Unitree publisher and delivered
fresh samples. The signed Control Bridge was DISARMED, lease-free, deadman
released and exact zero.

The former passive relay was still validating about 5,000 XT16 packets per
second but copied them to the absent wired address `192.168.123.99:2368`.
It was stopped and disabled with explicit operator approval; its installed
files were preserved. The external Orin consequently has zero publishers for
`/lidar_points`, `/velodyne_points` and `/imu/body`. Mapping, navigation and
Dataset Capture are idle.

Both hosts have platform Docker/L4T bridges and `net.ipv4.ip_forward=1`. The
robot-side filter policy was verified as `FORWARD DROP`; its forwarding and
MASQUERADE exceptions apply only to `docker0` and `172.17.0.0/16`. There is no
`wlan0` to `eth0` forwarding or sensor-LAN NAT rule. The external host has no
sensor-LAN interface or route. Its later privileged audit also confirmed
`FORWARD DROP`, Docker-only forwarding/NAT and an empty nftables ruleset. No
firewall rule was changed by either audit.

## Decision

Keep mapping and navigation ownership on the external Orin. Carry only the two
sensor inputs FAST-LIO requires across purpose-specific, fixed-peer transports:

```text
XT16 raw UDP
  192.168.123.20:10000 -> robot-side 192.168.123.18:2368
  passive validation on eth0
  validated 568-byte payload only
  robot-side 192.168.50.30:46236 -> external 192.168.50.10:2368
  -> Hesai driver -> /lidar_points
  -> cloud-only C++ bridge -> /velodyne_points

Go2 /lowstate
  robot-side extraction of quaternion + gyro + acceleration only
  HMAC-authenticated fixed binary envelope over a separate fixed UDP port
  -> external receiver -> sensor_msgs/Imu on /imu/body

/velodyne_points + /imu/body
  -> external FAST-LIO -> /Odometry + /Laser_map + /cloud_registered
  -> existing mapping and Nav2 readiness gates
```

The exact minimum-IMU UDP port is reserved by the Gate 4 implementation and
must be frozen in source and deployment documentation before any service is
installed. It may not be selected by a browser, API, command-line option,
hostname, CIDR or arbitrary environment value. It must not collide with the
accepted control port `46010`, Go2 camera relay source port `46120` or XT16
wireless source port `46236`.

### Allowed data

- the existing strictly validated XT16 UDP payload: IPv4/UDP checksums and
  lengths, no fragmentation, exact source/destination/ports, 568-byte payload,
  fixed header and advancing sequence;
- a canonical bounded binary IMU envelope containing only version/type,
  sender identity, boot identity, transport/source sequence, realtime and
  monotonic timestamps, quaternion, gyro, acceleration and HMAC-SHA256;
- a fixed one-client PTC connection only if the approved one-time, read-only
  JT16 correction acquisition cannot produce the exact offline artifact.

### Forbidden data and mechanisms

- PointCloud2 over management Wi-Fi;
- full `/lowstate` or any arbitrary ROS message;
- full ROS 2 DDS graph, DDS Router or multicast forwarding;
- route, NAT, Linux bridge or IP-forwarding rule between management and sensor
  networks;
- generic TCP/UDP proxy, SOCKS endpoint or arbitrary port forward;
- browser/API-selected peer, source, destination, port, interface or topic;
- reuse of the Control Bridge HMAC key;
- payload, HMAC key, calibration file, map, PCD, rosbag or private environment
  in Git, diagnostics or logs.

### Host ownership

| Responsibility | Robot-side Jetson | External Orin |
| --- | --- | --- |
| XT16 packet capture and exact validation | owner | never |
| XT16 sender health and sequence counters | owner | validated consumer |
| `/lowstate` subscription and minimum IMU extraction | owner | never subscribes |
| IMU signing key | sender copy, mode 0600 | receiver copy, mode 0600 |
| Hesai driver and `/lidar_points` | never | owner |
| cloud-only C++ conversion and `/velodyne_points` | never | owner |
| `/imu/body` publication | never | single authenticated receiver owner |
| FAST-LIO and map lifecycle | never | owner |
| Nav2, Mission and motion coordination | never | existing product owner |

The legacy wired C++ bridge remains supported for a directly connected
external host. Wireless mode uses a separate cloud-only executable and may not
weaken the existing point layout, timestamp, QoS, receive-buffer or freshness
contracts.

### PTC and calibration

Gate 3 must first determine whether the pinned Hesai driver can start from
private, sensor-associated correction and firetime artifacts without a live
PTC connection. The artifacts remain outside Git with sensor identity and
SHA-256 recorded in a private manifest. A fixed PTC proxy is a fallback only;
it requires separate approval, one exact external client, one exact XT16
destination, bounded buffers and connect/idle timeouts. No generic proxy is
authorized by this ADR.

### Clock contract

The XT16 bridge preserves and validates the measured sensor timestamp instead
of stamping receipt with `now()`. The IMU envelope carries source realtime and
monotonic timestamps separately. The receiver validates source clock skew,
receive monotonic age, boot identity, sequence progression and finite values.
It does not rebase stale data to the current time. Unsynchronized clocks,
future timestamps, replay, reorder, invalid quaternion norm or authentication
failure make the mapping input unavailable.

## Failure and recovery policy

| Failure | Required behavior |
| --- | --- |
| XT16 relay stale or sequence stops | mapping readiness false; no stale packet replay |
| Wi-Fi send error | bounded counter; capture may remain alive; readiness false |
| Wi-Fi recovers | fresh counters may recover, but mapping/Nav does not auto-start |
| IMU auth, identity or replay failure | packet rejected; IMU readiness false |
| IMU/clock stale or unsynchronized | no `/imu/body` readiness; mapping blocked |
| Hesai or cloud bridge stale | FAST-LIO readiness false |
| FAST-LIO exits | only children owned by that launch are cleaned up |
| Mapping or Nav was active during loss | stop/cleanup; never automatic resume |

Recovery never creates a control lease, arms the robot, holds deadman, resumes
Mapping, Nav2 or Mission, republishes a goal, saves a map or changes a network
profile. The operator must review a fresh preflight and explicitly start the
next stage.

## Service and resource policy

Every future service is disabled by default, uses a fixed executable and fixed
peer contract, runs non-root with only the exact required capability, and has
bounded queues, counters, logs and restart behavior. Startup and shutdown are
ordered and clean only processes created by the same transaction. No Gate 1
work installs, starts, restarts or enables a service, changes sysctl/firewall,
changes XT16/Go2 configuration, saves a map, starts Nav2 or moves the robot.

Wireless bandwidth, loss, jitter, RSSI, socket drops, CPU/RAM/temperature and
camera/control coexistence are hardware evidence. A hardware-free test cannot
promote relay, LiDAR, IMU, cloud, FAST-LIO or soak status to PASS.

## Rejected alternatives

- generic route/NAT/Linux bridge, multicast forwarder or DDS Router;
- forwarding PointCloud2 or the full LowState topic over Wi-Fi;
- moving Mission or motion authority to a new robot-side application;
- replacing the existing C++ converter with a Python high-rate converter;
- changing the XT16 destination or Go2 network profile for convenience;
- weakening timestamp, QoS, graph, lease, clamp or watchdog bounds.

## Consequences and next gates

Gate 2 implements and tests only the fixed wireless XT16 payload relay. Gate 3
freezes the Hesai receive/PTC decision. Gate 4 implements the separately keyed
minimum IMU transport. Gate 5 separates the C++ cloud-only mode. Gate 6 adds a
wireless mapping profile and bounded readiness reasons. Gate 7 runs the full
repository and C++ verification. Deployment remains forbidden until the
deployment plan is reviewed and the operator supplies
`APPROVE_WIRELESS_XT16_DEPLOY`.
