# Track D2 stationary live candidate acceptance

Status: `D2_REPOSITORY_SOFTWARE_PASS`; live source qualification blocked

```text
D2_REPOSITORY_SOFTWARE_PASS
STATIONARY_LIVE_CANDIDATE_BLOCKED
CANDIDATE_APPLIED=false
LOCALIZED_NG1_NOT_RUN
GOAL_NOT_RUN
MOTION_NOT_RUN
```

## Implemented and tested

- strict REGION/POSE/NONE request contract; global search defaults disabled;
- exact D0 occupancy/PCD family snapshots with post-registration revision
  recheck;
- one active generation-fenced job and bounded result retention;
- fixed `/cloud_registered`, `camera_init`, one-publisher collection contract;
- increasing stamp, duration, frame, raw/filtered point and stationary limits;
- deterministic voxel preprocessing and private binary PCD staging;
- D1 fixed process invocation with cancel TERM-to-KILL cleanup;
- `T_map_base = T_map_odom × T_odom_base` convention;
- occupancy bounds, known-free footprint, KEEP_OUT rejection and advisory zone
  labels;
- top-three results, ambiguity handling and bounded path-free previews;
- same-origin mutations and Competition Lock start policy;
- no apply endpoint and no control/navigation mutation dependency.

## Hardware-free acceptance matrix

| Check | Result |
|---|---|
| family/map/PCD revision mismatch | PASS — fail closed |
| revision change during registration | PASS — fail closed |
| occupied/unknown/insufficient-clearance candidate | PASS — rejected |
| KEEP_OUT / SLOW_ZONE / WAIT_ZONE | PASS |
| motion during collection | PASS — fail closed |
| stale/reordered cloud | PASS — fail closed |
| publisher conflict | PASS — fail closed |
| insufficient points | PASS — fail closed |
| timeout/process crash/cancel | PASS — bounded cleanup |
| top-K and ambiguity | PASS |
| transform convention | PASS |
| preview limits and no raw path | PASS |
| no candidate apply route | PASS |
| no lease/ARM/deadman/goal dependency | PASS |

## Why live acceptance remains closed

The authorized work did not start a ROS observer or alter either Jetson. The
repository and prior C2 evidence establish `/velodyne_points` and `/Odometry`
at approximately 10 Hz, but do not yet prove the current
`/cloud_registered` frame, QoS, publisher cardinality or bounded scan
semantics. The D1 portable backend has also not been built or compared with
PCL NDT/GICP on aarch64.

The runtime therefore leaves `ApplicationRuntime.relocalization` unconfigured.
The new endpoints fail with 503 instead of borrowing the UI preview source or
claiming live readiness.

## Read-only live audit and aarch64 evidence — 2026-09-07

Repository and deployment identities were deliberately kept separate:

```text
repository/origin main at initial audit = 86304406d128c149493380189b01409448225a3a
external production release = 3d62e254decaafda9b793bb43901141fd237ae48
external development checkout = 72e39c3f9517e9ba445ee2b8ddbcf6779bfe699b (dirty; untouched)
robot-side release after Wi-Fi recovery = 10a7fa9cec2c329f2c50edc9ad98de13a22689da
```

The external dashboard remained active. Mapping, Localization, Navigation,
Mission, control lease and non-zero command ownership were not started. The
read-only graph audit found:

| Topic | Publishers | Advertised QoS | Payload result |
|---|---:|---|---|
| `/cloud_registered` | 1 advertised, unattributed | endpoint node identity `UNKNOWN` | no qualified live payload |
| `/Laser_map` | 1 advertised, unattributed | endpoint node identity `UNKNOWN` | not selected as a local observation |
| `/Odometry` | 1 advertised, unattributed | endpoint node identity `UNKNOWN` | no qualified live payload |
| `/velodyne_points` | 0 | n/a | unavailable |
| `/imu/body` | 0 | n/a | unavailable |

The initial fixed onboard management-address check failed with neighbour state
`INCOMPLETE`, ICMP host unreachable and TCP/22 unavailable. After Wi-Fi was
restored, SSH and bounded ICMP succeeded. The onboard Foxy graph nevertheless
contained none of the five candidate topics, and there was no sensor or
FAST-LIO process. The external `--no-daemon` graph still returned malformed
node discovery data and `UNKNOWN` publisher identity. The earlier CLI
deserialization result is therefore not evidence of a currently running
incompatible publisher; it is an unattributed/malformed DDS discovery result.

The existing dashboard preview owner then retried automatically without any
new lifecycle command from this audit. It started the fixed external Hesai
driver, but raw-cloud readiness repeatedly timed out. The onboard relay was
active and the XT16 (`192.168.123.20`) and Go2 body (`192.168.123.161`) were
reachable, yet relay counters showed `accepted=0` and `forwarded=0` while
`packet_type` and `ip_address` rejections continually increased. Thus the
required fixed XT16 tuple
`192.168.123.20:10000 -> 192.168.123.18:2368` was not present in the relay's
accepted input. A bounded privileged packet-header inspection must determine
the actual destination before any configuration change is proposed.

Frame, stamp progression, rate, bounded-cloud semantics, fresh odom transform
and independent IMU stationary evidence remain unverified. No dedicated D2
subscriber or provider was enabled, and no service was started, stopped or
restarted by this audit. Control remained lease-free, deadman false and exact
zero; Navigation, Localization and Mapping pipeline state remained idle.

The exact repository revision was built only in temporary external-Orin
staging. GCC 11.4/aarch64 build and CTest passed. The existing portable backend
produced:

```text
cases = 10
points/case = 2530
translation median/p95 = 0.005111 / 0.016583 m
yaw median/p95 = 0.173053 / 0.280628 deg
runtime p50/p95 = 937.776 / 982.801 ms
child peak RSS = 13,404 KiB
```

The production symlink remained on `3d62e254...`, the dashboard remained
active, and temporary build staging was removed. Although PCL 1.12.1 and Eigen
3.4 are installed, this repository has no PCL NDT/GICP executable to compare;
their benchmark status remains `NOT_RUN`.

## Exact next approval gate

Before any deployment, present and approve:

1. external-Orin target and exact release SHA;
2. read-only topic/type/frame/QoS/cardinality inspection plan;
3. dedicated observation-only provider and additional DDS endpoint count;
4. exact C++ backend build and same-corpus aarch64 benchmark plan;
5. estimated CPU/RAM/network load;
6. dashboard wiring and service restart order;
7. rollback release and final service state.

After that approval, perform stationary collection only. No candidate may be
applied, and no initial pose, goal or motion is permitted in D2.

Before that deployment gate can be presented, identify why the fixed XT16
input tuple is absent, restore the existing preview's raw cloud, then qualify
the current-scan and odometry sources. The next diagnostic is a bounded,
header-only capture on onboard `eth0`; it requires separate privileged
operator authorization and makes no network change. Do not wire
`ApplicationRuntime.relocalization`, start a persistent D2 observer, or deploy
the D2 release while this prerequisite is blocked.
