# Unitree support request — Go2 controller odometry source clock

## Purpose

This is a sanitized, ready-to-send support request for the authoritative clock
used by the Go2 `/utlidar/imu` and `/utlidar/robot_odom` producer. It contains
no device serial number, password, private key, HMAC key or unrestricted log.
The operator should add the device serial only in Unitree's private support
portal if Unitree requires it.

Robot Scope remains fail-closed while this request is pending. Do not start
localization or Nav2 from this document, and do not use it as approval to
change a clock, restart a service, update or downgrade firmware, or move the
robot.

## Sanitized system context

| Item | Observed value |
|---|---|
| Robot | Unitree Go2 EDU, hardware version `v2.0` |
| Go2 body software | `v1.1.15` after operator-performed update |
| Unitree Go app | `v2.0.0-8031e` |
| L1 firmware/build | unknown; a supported read-only reporting method is requested below |
| Robot-side ROS package | `unitree_ros2` `0.3.0`, deployed commit `3ff13ea08ec619496c2651fd21b172f7958dd5a5` |
| Authoritative topics | `/utlidar/imu` and `/utlidar/robot_odom` |
| Odometry frames | `odom -> base_link` |
| Publisher | one bare-DDS RELIABLE/VOLATILE publisher |
| Robot-side host time | NTP synchronized; measured timesync offset `+10.334 ms` |
| Receiving host time | NTP synchronized; measured timesync offset `+2.075 ms` |

The Go2 and XT16 are physically connected to the robot-side computer. The
receiving computer is on the robot's wireless management network and cannot
be connected directly to the Go2 sensor LAN in the deployed topology.

## Reproduction and measurements

All observations below were read-only. The robot was stationary, and no Robot
Scope controller, Mapping, localization, Nav2, wireless odometry sender or
receiver was started.

Before the `v1.1.15` body update, a sender-side stationary check observed the
original `/utlidar/robot_odom` header stamp approximately `227.874 seconds`
older than the robot-side NTP realtime clock. The source-clock safety guard
rejected every sample and transmitted zero packets.

After the `v1.1.15` update, three independent 30-sample windows produced these
results:

| Check | Result |
|---|---|
| Samples | 90 total; all source stamps strictly advancing |
| Source-stamp rate | `149.957-150.054 Hz` |
| Median source age | `-681.218` to `-681.229 ms` |
| Interpretation | source timestamp is approximately `681 ms` in the future relative to robot-side NTP realtime |
| Topic contract | one RELIABLE/VOLATILE bare-DDS publisher, `odom -> base_link` |

The existing safety contract accepts at most `500 ms` of stale source age and
at most `100 ms` of future skew. The post-update source therefore remains
outside the future-skew limit even though both computers report synchronized
NTP clocks.

## Exact questions for Unitree

Please provide a supported, documented answer for this Go2 EDU hardware and
software combination:

1. Which supported API, Unitree application workflow, service procedure or
   firmware operation changes the clock used by the authoritative
   `/utlidar/imu` and `/utlidar/robot_odom` producer?
2. Which exact Go2 body firmware, L1 firmware/build and Unitree app/tool
   versions does that procedure apply to? How can an operator report the body
   and L1 versions through a supported read-only method?
3. What timestamp domain should the two ROS 2 header stamps use, and what is
   the maximum expected error relative to an NTP-synchronized Linux host after
   the supported procedure?
4. Does the clock correction persist across a robot reboot? Does it require
   Internet access, the Unitree Go app, an OTA update or a recurring service?
5. What is the official rollback or downgrade procedure? Please state any
   impact on calibration, locomotion configuration and saved maps.
6. Is `v1.1.15` expected to produce `/utlidar/*` timestamps approximately
   `681 ms` in the future under the conditions above? If not, which diagnostic
   bundle should be collected, using what supported and bounded command or app
   workflow?

Please include the exact procedure, applicable version matrix, expected clock
error, persistence behavior and rollback instructions in the reply. If logs
are required, please specify the minimum files and time interval so that the
operator does not upload credentials or unrelated system data.

## Safety constraints and rejected workarounds

The integration must preserve the original producer header stamp. These are
not acceptable remedies:

- rebasing the ROS header stamp to sender or receiver time;
- widening the `500 ms` stale or `100 ms` future limits;
- stepping either Linux host clock with `date -s`;
- restarting the legacy robot-side `lidar-timesync.service`, which changes the
  Linux host rather than the authoritative producer;
- guessing an undocumented key for the generic SDK2 `ConfigClient`;
- substituting FAST-LIO `/Odometry` for controller odometry;
- probing private body endpoints or using `/api/bashrunner`.

Public audits of `unitree_sdk2`, `unitree_sdk2_python` and `unitree_ros2` found
no documented Go2 clock/NTP/time-sync client. A generic configuration API is
not treated as authorization to infer a private clock key.

## Private submission checklist

Before sending this request through Unitree's private support channel:

- attach this sanitized text;
- add the robot serial only in the portal's designated private field if
  required;
- attach screenshots showing Go2 body `v1.1.15`, hardware `v2.0` and Unitree
  Go app `v2.0.0-8031e`;
- do not attach passwords, SSH material, wireless-transport HMAC keys,
  environment files or unrestricted logs;
- request a written rollback before applying any proposed mutation;
- return the response to the project review before executing it.

## Ready-to-send message

**Subject:** Go2 EDU `/utlidar/robot_odom` and `/utlidar/imu` timestamps are
approximately 681 ms ahead of NTP after v1.1.15 update

Hello Unitree Support,

We are integrating a Go2 EDU (hardware v2.0) with ROS 2. After updating the Go2
body software to v1.1.15 using Unitree Go app v2.0.0-8031e, the authoritative
bare-DDS publisher for `/utlidar/robot_odom` and `/utlidar/imu` produces
strictly advancing timestamps approximately 681 ms in the future relative to
the robot-side NTP-synchronized Linux clock. The odometry publisher is unique,
uses RELIABLE/VOLATILE QoS and publishes `odom -> base_link` at approximately
150 Hz. Two Linux hosts are NTP synchronized; their measured timesync offsets
were +10.334 ms and +2.075 ms.

Before the update, the same source was approximately 227.874 seconds stale.
After the update, three read-only 30-sample measurements showed a median source
age from -681.218 to -681.229 ms. Our safety gate permits no more than 500 ms
stale or 100 ms future, so localization and Nav2 remain disabled. We will not
rebase the source timestamp, relax the limits, step a Linux host clock or call
an undocumented ConfigClient key.

Could you please provide the supported procedure that corrects the clock used
by the `/utlidar/*` producer, the applicable body/L1/app version matrix, a
supported read-only method to report the L1 build, the expected timestamp
domain and maximum NTP-relative error, reboot/Internet/OTA persistence, and the
official rollback or downgrade procedure including effects on calibration,
locomotion and saved maps? Please also confirm whether the observed 681 ms
future offset is expected on v1.1.15 and specify the minimum supported
diagnostic bundle if further evidence is needed.

Thank you.

## Resume gate

A Unitree response is actionable only if it identifies the supported method,
applicable versions, expected clock domain/error, persistence and rollback.
Any proposed change must receive a separate safety review and explicit
approval. Until then, WNO-2, localization and Nav2 remain blocked.
