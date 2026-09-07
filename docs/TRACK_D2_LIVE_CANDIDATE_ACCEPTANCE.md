# Track D2 stationary live candidate acceptance

Status: `D2_REPOSITORY_SOFTWARE_PASS`; live source qualified; candidate not run

```text
D2_REPOSITORY_SOFTWARE_PASS
D2_LIVE_SOURCE_QUALIFIED
STATIONARY_LIVE_CANDIDATE_NOT_RUN
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
- opt-in, exact-profile D2 evidence owner for fixed `/cloud_registered`,
  `/Odometry` and `/imu/body` subscriptions, with no publisher;
- source cardinality, reliable/volatile QoS, frame, finite payload, original
  timestamp, progression and 500 ms past/100 ms future validation;
- collection-time readiness checks even while the last source sequence is
  unchanged, preventing a stale cached sample from surviving a graph fault.

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

## Why candidate acceptance remains closed

The original hardware-free acceptance did not start a ROS observer or alter
either Jetson. The later stationary audit below now proves the current
`/cloud_registered` frame, QoS, publisher cardinality and bounded current-scan
semantics, and the D1 portable backend has been built and benchmarked on
aarch64. The repository still has no PCL NDT/GICP backend, so no comparison is
claimed.

The runtime continues to leave `ApplicationRuntime.relocalization`
unconfigured. The endpoints fail with 503 instead of borrowing the UI preview
source or bypassing the explicit physical-safety boundary. The new dedicated
observer is disabled by default and requires both the exact competition
FAST-LIO profile and `ROBOT_SCOPE_D2_STATIONARY_OBSERVER=1`. A fixed
registration process and non-persistent physical-safety confirmation boundary
must still be wired before a candidate job can run.

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

The prerequisite described above is historical. Commits after this audit
restored and accepted the fixed wireless XT16 path, including cold-boot
recovery. It must not be used as the current D2 status.

## Stationary live-input acceptance — 2026-09-07

Fresh operator approval authorized a stationary sensor-input test only. The
robot was reported completely stopped with remote/E-stop ready. Map save,
initial pose, Nav2, goal and motion remained forbidden.

```text
repository = 2adb329c674d166fe06d59f4c1b8d1998cbaf672
external dashboard release = 6ce4b1dad5b2fdd75710022264683dd65fa6e9d4
onboard release = 10a7fa9cec2c329f2c50edc9ad98de13a22689da
pipeline ready = 2026-09-07T02:18:49.836867Z
pipeline stopped = 2026-09-07T02:21:28.782288Z
```

| Check | Result |
|---|---|
| `/cloud_registered` identity | PASS — exactly one `laser_mapping` publisher |
| frame | PASS — `camera_init` |
| source semantics | PASS — 350--359-point bounded current scans |
| stamp progression and rate | PASS — increasing; final 9.993 Hz |
| offered QoS | PASS — reliable, keep-last 20, volatile |
| `/Odometry` | PASS — one publisher, `camera_init -> body`, final 9.994 Hz |
| `/imu/body` | PASS — one receiver publisher, approximately 499 Hz |
| accumulated `/Laser_map` excluded | PASS — grew 19,607 -> 21,028 points |
| stationary translation | PASS — approximately 3.75 mm over 15 s |
| FAST-LIO twist | PASS — sampled exact zero |
| body IMU angular rate | PASS — approximately 0.0137/0.0114 rad/s |
| control isolation | PASS — disarmed, no lease/deadman, exact zero, non-zero Move count 0 |
| prohibited operations | PASS — no save, initial pose, Nav2, goal or motion |
| reverse cleanup | PASS — audit-owned pipeline stopped; preview retained |

The source decision is now accepted as `/cloud_registered` in `camera_init`
under `go2-xt16-wireless-competition-fastlio`. This is
`D2_LIVE_SOURCE_QUALIFIED`, not `STATIONARY_LIVE_CANDIDATE_PASS`: no D2
dedicated subscriber collected a submap, no registration process ran and no
candidate was generated.

## Revised next approval gate

Before candidate execution, present and approve:

1. a clean exact release containing the dedicated profile-fixed D2 observer;
2. explicit observer opt-in and proof of its three subscriptions/zero publishers;
3. an explicit, non-persistent physical-safety confirmation boundary;
4. the fixed aarch64 registration executable and allowed staging roots;
5. expected steady load and the temporary diagnostic overhead distinction;
6. external dashboard restart order and rollback SHA;
7. exact D0 family, occupancy map and source PCD revisions for the run.

Candidate execution remains a separate stationary-only deployment action.
`CANDIDATE_APPLIED=false`, and initial pose, Nav2, goal and motion remain
forbidden in D2.

## Observer-only external deployment — 2026-09-07

The exact repository release below was deployed to the external Orin after the
live-source qualification.  The previous production release remains available
as the rollback target and the dirty development checkout was not modified.

```text
external target = 192.168.50.10
deployed release = b8fe0c5a749eafc9c507157b101ba289e393e60d
rollback release = 6ce4b1dad5b2fdd75710022264683dd65fa6e9d4
archive sha256 = 303af41e81f45f0b7de09bbf368a6761204fcf8db225d1200580f829d32c9ce9
registration executable sha256 = 89be25926a9bc1c66576d227473de520fde9b1cad9946e8ea060f8fca21b8ee5
profile = go2-xt16-wireless-competition-fastlio
observer opt-in = ROBOT_SCOPE_D2_STATIONARY_OBSERVER=1
```

The aarch64 registration core rebuilt with GCC 11.4 and its CTest passed
1/1.  The dashboard restarted from the exact release and remained healthy.
Control was lease-free, deadman false and exact zero; the authenticated Bridge
reported zero non-zero Move requests.  Navigation, Localization and goal
state remained idle.  The relocalization manager remains deliberately
unconfigured and its status endpoint returns 503.

The normal preview recovered and remained the only sensor process owner.
FAST-LIO and the wireless IMU receiver were not started, so the three D2
sources had no active producer and the graph-dependent observer did not create
its fixed subscriptions.  No candidate collection or registration was run.
Starting the stationary FAST-LIO source path requires a fresh physical-safety
confirmation.

The requested map cannot yet be used by D2:

```text
occupancy map = map_20260902_161903_edited
occupancy id = f292601e2c8b269eb635cb0f
occupancy revision = 7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93
source PCD candidate = map_20260902_161903.pcd
source PCD id = dabd3853721e237f99d15399
source PCD revision = 74bfe16b9576656d976d5d8d4caf118ee4bedf4ebbf184f83a12ba45f2ea26e5
lineage status = unlinked
```

Both the original occupancy map and the similarly named PCD are historical
unlinked artifacts.  D0 expressly prohibits inferring their relationship from
filenames, so D2 remains fail-closed.  A new explicit PCD-to-2D conversion must
create a lineage-aware map, followed by a lineage-preserving edited copy if
the unknown-to-free edit is still required.  Existing maps remain untouched.
