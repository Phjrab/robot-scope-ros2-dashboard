# Controller odometry clock recovery plan

## Status and safety boundary

The wireless controller-odometry transport is installed, but WNO-2 remains
fail-closed. This plan does not authorize changing either Jetson clock,
restarting `lidar-timesync.service`, changing NTP, calling an undocumented Go2
API, using `/api/bashrunner`, restarting the robot, launching Mapping/Nav2, or
moving the robot.

The fixed safety contract remains unchanged:

- preserve the original `/utlidar/robot_odom` header stamp;
- accept at most 500 ms of source age and 100 ms of future skew;
- require synchronized Jetson clocks, strict stamp advancement and one source
  publisher;
- never replace controller odometry with FAST-LIO `/Odometry`;
- never make stale input current by rebasing it to sender or receiver time.

## Measured clock ownership

The 2026-09-01 read-only audit found:

| Signal | Owner and result |
|---|---|
| `/utlidar/robot_odom` | one RELIABLE/VOLATILE bare-DDS publisher, `odom -> base_link` |
| `/utlidar/imu` | one RELIABLE/VOLATILE bare-DDS publisher from the same participant |
| source age | both headers were approximately 231 seconds behind robot-Jetson NTP realtime |
| Jetson clocks | robot-side and external hosts both reported NTP enabled and synchronized |
| robot-side legacy sync | enabled one-shot `lidar-timesync.service` copied `/utlidar/imu` time to the host at boot, then exited |
| XT16 | `192.168.123.20`; not the publisher owner for the Unitree `/utlidar/*` DDS participant |
| Go2 locomotion computer | `192.168.123.161`; publishes the fixed DDS observation and exposes no supported time-setting API in the official SDK |

The legacy one-shot was written for a Jetson with no RTC or NTP. That premise
no longer matches the deployed wireless system. Re-running it would move the
robot Jetson clock backward to the stale source domain and would still leave
the external NTP host in a different domain, so it is not a valid repair.

The official Unitree Go2 SDK and ROS 2 repository contain no supported Go2
clock-setting client. Unitree's separate LiDAR SDK exposes timestamp options
only for a driver that directly owns the sensor connection. Robot Scope does
not own the Go2 bare-DDS publisher, so it must not infer an undocumented
mutation from that unrelated interface.

## Software guard

Before any further hardware clock action, deploy a sender-side copy of the
existing receiver clock fence. The sender must:

1. measure `sender_realtime_ns - original_source_stamp_ns`;
2. reject age above 500 ms as `stale` and future skew above 100 ms as `future`;
3. count and report `source_stale`, `source_future` and bounded
   `source_stamp_age_ms` diagnostics;
4. transmit no datagram for a rejected sample;
5. preserve the original stamp byte-for-byte for accepted samples.

This moves failure detection to the source host. It does not make WNO-2 pass
and does not change the receiver, Navigation gateway or freshness limits.

## Guard deployment and stationary check

Exact robot-side replacement files:

- `scripts/wireless_odom_protocol.py`
- `scripts/wireless_odom_sender_foxy.py`

Deployment is transactional with `.pre-<commit>` backups. The unit remains
disabled at boot. No key, sudoers, firewall, network profile or external file
changes are required.

Stationary check `WOC-1`:

1. confirm no lease, deadman, non-zero command, Mapping, Nav2 or receiver;
2. start only the disabled sender through the existing restricted lifecycle;
3. require `source_stamp_age_ms` to expose the measured offset,
   `source_stale` to advance, and `sent=0`;
4. stop the sender and confirm inactive/PID zero with no UDP 46030 listener;
5. do not proceed to WNO-2 while the original stamp remains outside 500 ms.

Rollback restores the two previous script copies and verifies Python syntax
before a daemon-free retry. It does not remove the private key or touch any
other robot-side service.

After reviewing this exact guard-only scope, authorize its installation and
`WOC-1` with:

```text
APPROVE_WIRELESS_ODOM_SOURCE_CLOCK_GUARD
```

## Source-clock remediation gate

A later source-clock correction requires a separate vendor-supported method
that changes the authoritative Go2 `/utlidar/*` producer, not either transport
stamp. Before execution it must identify the exact API/tool and version,
document rollback, prove the robot is stationary and control-free, and receive
a new explicit approval. Until then WNO-2, WNO-3, WNO-4, localization and Nav2
remain blocked.
