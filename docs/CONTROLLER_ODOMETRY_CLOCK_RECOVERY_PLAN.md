# Controller odometry clock recovery plan

## Status and safety boundary

The wireless controller-odometry transport is installed, but WNO-2 remains
fail-closed. This plan does not authorize changing either Jetson clock,
restarting `lidar-timesync.service`, changing NTP, calling an undocumented Go2
API, using `/api/bashrunner`, restarting the robot, launching Mapping/Nav2, or
moving the robot.

The sender-side guard from commit `ae821ba` was transactionally installed on
the robot Jetson on 2026-09-01 after the exact guard-only approval. Stationary
check WOC-1 passed: the guard reported an approximately 227.874-second-old
source stamp, advanced `source_stale` while keeping `sent=0`, and was then
stopped. Both wireless odometry units remain disabled and inactive. This
deployment does not clear WNO-2 or authorize any later gate.

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

## Vendor-supported remediation audit — 2026-09-01

The post-WOC-1 audit checked the deployed source and the current official
public sources without publishing a request or changing either host:

| Source | Audited identity | Result |
|---|---|---|
| robot-side `unitree_ros2` | version `0.3.0`, commit `3ff13ea08ec619496c2651fd21b172f7958dd5a5` | no tracked clock, NTP or time-sync client; local setup/workspace changes were preserved |
| [official `unitree_sdk2`](https://github.com/unitreerobotics/unitree_sdk2/tree/9754cd153af3da471b0fe5f3aa535e426fb11db3) | commit `9754cd153af3da471b0fe5f3aa535e426fb11db3` | public Go2 clients expose config, robot-state, obstacle, sport, tracking, video and VUI surfaces, but no clock client |
| [official `unitree_sdk2_python`](https://github.com/unitreerobotics/unitree_sdk2_python/tree/65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5) | commit `65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5` | no clock, NTP or time-sync API/example |
| [official `unitree_ros2`](https://github.com/unitreerobotics/unitree_ros2/tree/668d1ec5a05d1c38d3306bdca7d59f2ba3581a88) | version `0.3.0`, commit `668d1ec5a05d1c38d3306bdca7d59f2ba3581a88` | no clock, NTP or time-sync API/example |
| robot LowState | public `version` field observed as `[0, 0]` | insufficient to identify the body/L1 firmware build |

SDK2's generic Go2 `ConfigClient` is not an authorization to guess a private
time key. The official source publishes only generic Set/Get/Delete/Meta
operations and contains no documented time configuration name, schema,
applicable firmware or rollback. Calling it with an inferred key would be an
undocumented mutation and remains prohibited.

The enabled local `lidar-timesync.service` is also not a vendor remediation.
Its local Python script explicitly runs `date -s` on the robot Jetson from one
`/utlidar/imu` sample and was written for a no-RTC/no-NTP premise. It does not
change the authoritative Go2 producer and cannot align the separate external
NTP host. Its service and script SHA-256 values at audit time were
`852747f6fe5b310fe11c4b6325ebb5392432598f7da6bf32cbf9ffebaf11ac38`
and `e478160e1e2ae1ffd7604b8af8d873d266d0873b3c669b51a8fd8ccf85b4cd84`.
They were read only; the inactive one-shot was not restarted, disabled or
edited.

### Vendor response required

No execution approval token can be defined until Unitree identifies all of the
following for this exact Go2 EDU Plus/L1 configuration:

1. the supported API, application workflow or service procedure that changes
   the clock used by the authoritative `/utlidar/imu` and
   `/utlidar/robot_odom` producer;
2. the applicable Go2 body/L1 firmware and Unitree app/tool versions, plus a
   supported read-only way to report those versions;
3. whether the method persists across reboot and whether it requires Internet,
   the Unitree app or an OTA update;
4. the vendor rollback or downgrade procedure and its effect on calibration,
   locomotion and saved maps;
5. the expected source timestamp domain and maximum error relative to an NTP
   host after the procedure.

The support request should include the measured 227.874-second source age, the
fact that both Jetsons are NTP-synchronized, the fixed frames
`odom -> base_link`, the single bare-DDS publisher observation, SDK/ROS commit
identities above and the statement that transport timestamp rebasing is not
acceptable. Do not include private keys, host passwords or unrestricted logs.

Until a vendor answer supplies the exact method and rollback, source-clock
remediation is **BLOCKED**. An app OTA, generic ConfigClient mutation, direct
body endpoint probe, `/api/bashrunner`, host clock step or legacy time-sync
restart is not an approved substitute.

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
