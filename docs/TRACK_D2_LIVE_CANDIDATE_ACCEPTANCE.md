# Track D2 stationary live candidate acceptance

Status: `D2_STATIONARY_ENVELOPE_DEPLOYED`; candidate not run

```text
D2_REPOSITORY_SOFTWARE_PASS
D2_RUNTIME_WIRING_SOFTWARE_PASS
D2_RUNTIME_DEPLOYED
D2_STATIONARY_ENVELOPE_SOFTWARE_PASS
D2_STATIONARY_ENVELOPE_DEPLOYED
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

## Lineage-aware map conversion and deployed observer check — 2026-09-07

Fresh operator approval authorized only the stationary FAST-LIO observation
owner and a new lineage-aware 2D conversion of the pinned PCD.  Initial pose,
Localization, Nav2, goal, lease, ARM, deadman and motion remained forbidden.

The server-side fixed conversion completed successfully without changing or
deleting any existing map:

```text
source PCD id = dabd3853721e237f99d15399
source PCD revision = 74bfe16b9576656d976d5d8d4caf118ee4bedf4ebbf184f83a12ba45f2ea26e5
source points = 46140
new occupancy name = map_20260902_161903_d2
new occupancy id = 85fa623a8a859c351ec47912
new occupancy revision = cbfc70e3c79ccc1fb365c68f4d0705bda0b822e9d063138eb19052995e81d219
family id = bff5cbc6eaf6e7ba2d9c62a7
family revision = b129314b331405e2b324cc64818de9117ec0f40d869377862754309267f1ca07
family status = linked
conversion parameters hash = 199419f60916ec1414b17f102209f3d1a42ef2b496e41d4fc189b1be4ba625c8
```

The fixed parameters were z `[-0.2, 0.8]` m, 0.05 m resolution, 0.10 m noise
radius, ten minimum neighbours and unknown background.  The conversion kept
21,038 points in the z slice, selected 19,940 points and produced a 297 x 156
map with 5,656 occupied cells.  The family endpoint pins the exact PCD ID and
revision and records the explicit `camera_init` to `map`
`planar_xy_identity` projection.  The legacy edited and original occupancy
maps remain present and unchanged.

The approved observation-only Mapping owner then ran from
`2026-09-07T03:11:53Z` until reverse cleanup at
`2026-09-07T03:16:30Z`.  The deployed D2 observer created its fixed
subscriptions after the publishers appeared:

| Topic | Publisher/cardinality | D2 subscription | Observed payload |
|---|---|---|---|
| `/cloud_registered` | one `laser_mapping` | present, reliable/volatile | `camera_init`, 354 points, final 9.975 Hz |
| `/Odometry` | one `laser_mapping` | present | `camera_init -> body`, final 9.986 Hz |
| `/imu/body` | one `robot_scope_wireless_imu_receiver` | present | `body_imu`, final 500.306 Hz |

The D2 evidence hub itself still owns no publisher.  The enclosing
`robot_scope_agent` retains its pre-existing `/initialpose`, parameter-event
and logging publishers, but no initial-pose message was sent.  This distinction
prevents the node-level publisher list from being misreported as D2 output.

Two diagnostic odometry samples approximately 20 seconds apart changed by
about 6.44 mm in the plane.  FAST-LIO linear twist was zero at both samples and
body IMU angular-rate magnitude remained approximately 0.0126--0.0129 rad/s.
The translation result is above the fixed 5 mm D2 collection limit for treating
that sampled interval as stationary evidence.  No limit was relaxed and no
candidate collection or registration was attempted.  A future candidate run
must obtain fresh bounded 2--5 second evidence through the manager and pass the
same 5 mm check; this longer diagnostic interval is not reused as a candidate
baseline.

Reverse cleanup stopped FAST-LIO, the external IMU receiver and the onboard
sender owned by the Mapping session.  Their source publisher counts returned
to zero.  The existing `/velodyne_points` preview remained running with one
publisher.  Control ended lease-free, deadman false and exact zero, with the
Bridge non-zero Move count still zero.  Navigation, Localization and goal
remained idle.  The relocalization manager is still unconfigured, so candidate
execution remains closed.

## Runtime wiring software acceptance — 2026-09-07

The repository now contains the missing fail-closed runtime construction, but
it remains disabled in every deployed environment. The manager requires the
exact competition FAST-LIO profile, the existing observer opt-in and the
additional explicit opt-in
`ROBOT_SCOPE_D2_STATIONARY_RELOCALIZATION=1`. The executable and private
runtime paths are server-owned; clients cannot select a process, topic, frame,
host, port or filesystem path.

Each candidate request now carries a strict, fresh
`physical_safety_confirmed=true` value. The value is consumed before the job
worker starts and is not retained in the public result. Runtime facts must
also prove: authenticated ready Bridge, no lease/deadman/action, exact-zero
command and fresh Sport velocity, no software-stop latch, idle Navigation,
goal and Dataset Capture, no conflicting Mapping action, a running fixed
observation pipeline, fresh motion evidence and one fresh QoS-valid
`/cloud_registered` publisher in `camera_init`.

The same gate is checked throughout collection and after its final polling
interval. Hardware-free regressions cover false/missing confirmation, wrong
profile, missing observer, pipeline or Bridge loss, software stop, lease and
source readiness changes. Existing `/api/v1/pose`, strict wireless odometry,
C2 controller odometry and all Control/Nav safety behavior are unchanged.

```text
RUNTIME_MANAGER_DEFAULT=DISABLED
DEPLOYMENT=NOT_RUN
LIVE_CANDIDATE=NOT_RUN
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

Deployment remains a separate approval gate. It must pin the exact clean
release, retain the current external release as rollback, enable only the new
external dashboard flag and restart only that dashboard while Control remains
disarmed and motion-free. A subsequent live candidate run requires another
fresh stationary safety confirmation with the exact linked family revisions.

## Runtime opt-in external deployment — 2026-09-07

The operator explicitly approved external-dashboard-only deployment of exact
release `ebbcf5a17e1973ccb9c2a76b99b79a6d88d8ac98`, activation of the D2
runtime opt-in and one dashboard restart. Candidate execution and every
Control, Localization, Nav2, goal and motion action remained prohibited.

```text
external target = 192.168.50.10
deployed release = ebbcf5a17e1973ccb9c2a76b99b79a6d88d8ac98
rollback release = b8fe0c5a749eafc9c507157b101ba289e393e60d
archive sha256 = 9ad99654283602967845ceb5ee51b7847547970791782818b35c28eef42a981e
runtime wiring sha256 = 4d22767ad6d3afd5d3e77679a29d03018055e573713d04c0d87b92ec7be828f5
registration executable sha256 = 2b5db260035b9c69c91ca29fc56775e2d939087db31249b59b98fdddd3e543b1
profile = go2-xt16-wireless-competition-fastlio
observer opt-in = ROBOT_SCOPE_D2_STATIONARY_OBSERVER=1
runtime opt-in = ROBOT_SCOPE_D2_STATIONARY_RELOCALIZATION=1
dashboard active = 2026-09-07T13:03:06+09:00
```

The archive hash was verified before extraction into a new release directory.
The aarch64 registration core rebuilt with GCC 11.4 and CTest passed 1/1.
The runtime-wiring Python import also passed. The private environment file and
the previous release symlink were retained as exact rollback artifacts before
the stable release link was atomically switched. Temporary local and remote
archives and the one-use transition script were removed after verification.

Only `robot-scope.service` was restarted through its existing fixed lifecycle
API. The new process cwd and stable symlink both resolved to the exact full
SHA; systemd reported `active (running)`, restart count zero and a clean new
application startup. The retiring process exceeded its graceful WebSocket
shutdown interval and logged cancelled WebSocket tasks. Those messages came
from the previous `b8fe0c5...` PID during the requested transition; no error or
restart loop was observed in the new process.

The live relocalization snapshot reported schema
`robot-scope.relocalization.v1`, `active=null`, `latest=null` and
`candidate_apply_supported=false`. No registration executable or
localization/Nav2 process was running. Navigation pipeline, localization
session and goal remained idle with zero command-topic publishers. The normal
preview recovered under the pre-existing dashboard policy; this did not start
FAST-LIO or a D2 candidate job.

Control remained authenticated and exact zero throughout the post-deployment
check: lease inactive, deadman false, no action guard, accepted velocity all
zero, fresh Sport velocity all zero, `move_count=0`,
`nonzero_move_count=0` and `action_count=0`. The robot-side Bridge release and
service were not changed or restarted by this deployment.

```text
D2_RUNTIME_DEPLOYED=PASS
STATIONARY_LIVE_CANDIDATE=NOT_RUN
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

The next action is not automatic. A live candidate collection requires a new
stationary safety confirmation and a preflight that pins the exact linked
family/map/PCD revisions, proves the fixed observation pipeline and fresh
sources, and rechecks every no-lease/no-motion gate.

## First candidate preflight block and stationary envelope — 2026-09-07

After a fresh stationary candidate approval, the pre-command read-only gate
stopped before starting the observation pipeline or submitting a job. Control
was lease-free, deadman false and exact zero, and Navigation, Localization and
goal were idle. The signed, fresh Sport state nevertheless reported
`[0.003695, -0.003542, -0.031734]` while the physically stationary robot had
no Robot Scope Move request. The deployed `ebbcf5a...` runtime required each
raw state-estimator velocity component to equal floating-point zero.

A subsequent fixed ten-second, 20-sample read-only observation contained no
exact-zero sample. Maximum observed planar velocity was approximately
`0.0208 m/s` and maximum absolute yaw rate was `0.0323 rad/s`. This is treated
as an observed stationary state-estimator noise envelope, not as evidence that
the robot moved and not as authority to relax any command or collection limit.

The repository fix remains specific to the opt-in D2 runtime:

- signed Sport state must remain fresh and all three values finite;
- planar Sport velocity must be at most `0.025 m/s`;
- absolute Sport yaw rate must be at most `0.04 rad/s`;
- missing, boolean, NaN, infinite or out-of-envelope values fail closed;
- `0.03 m/s`, the smallest C4C micro-probe command, remains outside the D2
  envelope and is rejected;
- Control command exact-zero, no lease/deadman/action, authenticated Bridge,
  no software stop and all existing idle-owner gates remain unchanged;
- the collector still rechecks the whole preflight on every poll and after the
  collection window;
- the independent collection limits remain 5 mm translation, 0.01 rad yaw,
  `0.01 m/s` FAST-LIO twist and `0.05 rad/s` IMU angular rate.

Hardware-free tests cover the accepted observed noise, both exact boundaries,
the rejected `0.03 m/s` linear value, excessive yaw and malformed/non-finite
values. No observation pipeline, candidate job, registration process, apply,
initial pose, Nav2 goal or motion was started during the blocked attempt or
this software correction. The deployed runtime remained `ebbcf5a...` until
the separately approved exact-release deployment recorded below.

## Stationary-envelope external deployment — 2026-09-07

The operator separately approved external-dashboard-only deployment of exact
release `9693ebd51ccd73decdba3eb3cd5030cd8e769629`. The existing D2 observer
and relocalization opt-ins were preserved; no robot-side release or service was
changed.

```text
external target = 192.168.50.10
deployed release = 9693ebd51ccd73decdba3eb3cd5030cd8e769629
rollback release = ebbcf5a17e1973ccb9c2a76b99b79a6d88d8ac98
archive sha256 = d63f72baf071643386ab5f55315fa884c0af2dff26e8b903810f072ce8b47f99
stationary manager sha256 = d6c1760125c91e58bb18b1a83bb3209488d3b28a76c5e238ba0c1df85873ec79
runtime wiring sha256 = 255ab2362f91a242ec9b4b88923de2ffa6a33d526d15f9585f76f590f8e1dbbb
registration executable sha256 = 89be25926a9bc1c66576d227473de520fde9b1cad9946e8ea060f8fca21b8ee5
dashboard active = 2026-09-07T14:04:44+09:00
```

The archive hash was verified before extraction into a new immutable release.
The aarch64 registration core rebuilt with GCC 11.4 and passed CTest 1/1.
The stable release symlink and the new service process cwd both resolved to the
exact full SHA. The dashboard restarted once through its existing fixed
lifecycle API and systemd reported `active`, a new PID and `NRestarts=0`.

One initial lifecycle request contained malformed shell-quoted JSON and was
rejected with HTTP 422 before an operation was scheduled. The corrected strict
body was then accepted once with HTTP 202. This did not cause an additional
service restart. As in the prior transition, the retiring dashboard exceeded
its graceful WebSocket shutdown interval and cancelled open stream tasks; the
new process completed startup without an error or restart loop.

Post-deployment evidence remained motion-free: Control lease inactive,
deadman false, accepted command exact zero, action guard inactive, and Bridge
`move_count=0`, `nonzero_move_count=0`, and `action_count=0`. Navigation,
Localization and goal remained idle with zero command-topic publishers. The
relocalization endpoint reported `active=null`, `latest=null`, and
`candidate_apply_supported=false`. No FAST-LIO, registration, candidate,
initial-pose, Nav2 or motion process was started. Temporary local and remote
deployment archives were removed; the previous release remains intact for
rollback.

```text
D2_STATIONARY_ENVELOPE_DEPLOYED=PASS
STATIONARY_LIVE_CANDIDATE=NOT_RUN
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

The earlier live-candidate approval was consumed by the fail-closed preflight
attempt and is not reused. Candidate collection requires a new stationary
safety confirmation against this exact deployed release.
