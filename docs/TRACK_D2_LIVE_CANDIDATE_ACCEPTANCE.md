# Track D2 stationary live candidate acceptance

Status: `D2_LIVE_CANDIDATE_REJECTED_MAP_NOT_ELIGIBLE`; candidate not applied

```text
D2_REPOSITORY_SOFTWARE_PASS
D2_RUNTIME_WIRING_SOFTWARE_PASS
D2_RUNTIME_DEPLOYED
D2_STATIONARY_ENVELOPE_SOFTWARE_PASS
D2_STATIONARY_ENVELOPE_DEPLOYED
D2_LIVE_SOURCE_QUALIFIED
D2_DENSE_QUERY_COLLECTION_PASS
STATIONARY_LIVE_CANDIDATE_REJECTED
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

## Live candidate pre-collection lineage failure — 2026-09-07

The operator issued a fresh stationary-only approval for exact release
`9693ebd51ccd73decdba3eb3cd5030cd8e769629`, the exact linked D0 revisions
recorded above and REGION seed `(0, 0, 0)`, radius `3.0 m`, yaw half-range
`1.57 rad`. Candidate apply, initial pose, Nav2, goal and motion remained
forbidden.

Fresh preflight confirmed the exact deployed process cwd, authenticated Bridge,
inactive lease, false deadman, exact-zero accepted command, idle Navigation and
Localization, and zero Move/non-zero Move/action counts. The approved
observation-only Mapping owner then started once and reached ready with the
fixed wireless sensor and FAST-LIO sources.

One malformed shell-quoted candidate request was rejected with HTTP 422 during
JSON parsing and did not allocate a job. The corrected request was accepted
once as job `a20a721dd662c58f7af0188e`, generation 1. It failed before entering
collection: `family_id`, `family_revision`, collection and candidates all
remained null or empty. No registration process ran.

The failure was an exact-lineage availability failure, not a stationary-source
failure. The saved-map catalog no longer contained occupancy map
`85fa623a8a859c351ec47912`; the currently present historical edited map is the
different, deliberately unlinked map `f292601e2c8b269eb635cb0f`. The operator
event timeline records an accepted `map_delete` for the exact D2 occupancy ID
at `2026-09-07T06:21:03.790Z` (`15:21:03.790 KST`). The managed map directory
contains neither `map_20260902_161903_d2` nor a map-family sidecar. Deleting the
lineage-aware occupancy correctly retained its source PCD, so the PCD remains
present but cannot be paired with another occupancy map by filename.

The deployed runtime converted this expected `SavedMapNotFound` into the
generic public error `relocalization job failed`. A narrow repository
correction now maps catalog not-found and lineage-conflict failures at the D2
runtime boundary to bounded, path-free relocalization conflict reasons. It
does not loosen revision pinning, infer lineage, change the legacy map API or
make a missing family usable.

Reverse cleanup stopped only the approved Mapping owner at
`2026-09-07T07:48:54.000Z`; the existing preview remained. The final audit
showed the dashboard active from exact `9693ebd5...`, no FAST-LIO,
registration or Nav2 child, no active relocalization job, inactive lease,
false deadman, exact-zero command, and Bridge Move/non-zero Move/action counts
all zero.

```text
D2_LIVE_CANDIDATE=FAIL_PRECOLLECTION_EXACT_MAP_UNAVAILABLE
CANDIDATE_JOB_COUNT=1
CANDIDATE_OUTPUT=NONE
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=IDLE
```

No automatic retry is permitted. A future attempt must first create a new
lineage-aware occupancy from the still-pinned PCD, record its newly generated
map/family revisions, and obtain a new exact stationary candidate approval.

## Exact-lineage recovery and bounded external deployment — 2026-09-07

Before creating another map, the catalog was checked again. A later Mapping
save had already produced a complete, linked `robot-scope.map-family.v1`
family, so no duplicate conversion or map mutation was performed. The exact
family selected for the next separately approved D2 attempt is:

```text
name = map_20260907_175720
family_id = 23a29b9668a8a51e59a7f1b2
family_revision = befd68fa917f93f3731855b172b06e799a03f6e7f982e7d4361684ccd72fcd8e
pcd_map_id = e1252aeb1793d7bb78847e5e
pcd_revision = 86df7447267f0c1107e7fe7b8524a112a849ea3070dd4a8d292e2df8a00c0c80
pcd_frame = camera_init
occupancy_map_id = 5ba0ac7a28fcc1c7b81cc58e
occupancy_revision = 4ed9f19aec8cb338e2cdfa3e54946432e6231991ef87f8ea05e89dd242a4b979
occupancy_frame = map
conversion_parameters_hash = 199419f60916ec1414b17f102209f3d1a42ef2b496e41d4fc189b1be4ba625c8
```

The operator then separately approved external-dashboard-only deployment of
the narrow missing-lineage error correction at exact release
`6285408fb17edf59a03c89cbee29d94a91db1bd2`. The robot-side Bridge release,
services and configuration were not changed or restarted.

```text
external target = 192.168.50.10
deployed release = 6285408fb17edf59a03c89cbee29d94a91db1bd2
rollback release = 9693ebd51ccd73decdba3eb3cd5030cd8e769629
archive sha256 = e1b471f309b0b40b51e4a6a4dc75442e6597125664cb8db4b1e58679d24e6153
runtime wiring sha256 = 8cea0e8e1a2882201ba3abec5caa298697176484497946fdd5402cb28266d3d7
registration executable sha256 = 89be25926a9bc1c66576d227473de520fde9b1cad9946e8ea060f8fca21b8ee5
dashboard active = 2026-09-07T23:24:00+09:00
```

The archive hash was verified before extraction into a new mode-0700 release.
The registration source was unchanged from the rollback release, so its
previously verified aarch64 executable was copied with the same exact hash.
The changed Python module hash matched the repository and imported
successfully before the release transition. The stable symlink and the live
process cwd both resolved to the new full SHA after one dashboard-only restart.
Systemd reported `active/running`, PID 9039, invocation
`f37046ec9a394fb18a1c87daa71f9d2a` and `NRestarts=0`. The deployment archives
were removed from the local and remote temporary directories; the rollback
release remains intact.

Post-deployment Control remained authenticated and motion-free: lease
inactive, deadman false, accepted command exact zero, action guard inactive,
Bridge `move_count=0`, `nonzero_move_count=0`, and `action_count=0`. Battery and
joint telemetry were fresh. Navigation, Localization, goal and relocalization
candidate state remained idle. No FAST-LIO, registration or candidate process
was started. The existing XT16 relay remained active on the robot-side host;
the observation-only FAST-LIO/IMU pipeline remained stopped pending a new
candidate approval.

```text
D2_MISSING_LINEAGE_ERROR_DEPLOYED=PASS
D2_EXACT_LINKED_FAMILY_AVAILABLE=PASS
STATIONARY_LIVE_CANDIDATE=NOT_RUN
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

The next action remains a new, exact stationary candidate approval. Deployment
approval and every previous candidate approval are not reused.

## XT16 destination recovery and exact candidate attempt — 2026-09-07

The operator supplied a fresh combined approval for the fixed XT16 destination
repair and exactly one stationary candidate attempt. Read-only inspection first
showed that the XT16 was reachable and out of standby, but its configured UDP
destination was `192.168.123.99:2368`. The deployed wireless relay deliberately
accepts only the established stream addressed to the robot-side Jetson at
`192.168.123.18:2368`; its counters consequently remained at zero accepted and
zero forwarded packets while rejecting unrelated traffic.

The approved device setting was changed to `192.168.123.18:2368` while retaining
GPS port 10110. The device returned success and an immediate read-back matched
the requested values, so the rollback to `.99` was not required. The existing
robot-side relay was not restarted. Its counters advanced from zero to more than
one million accepted and forwarded packets, with zero sequence loss, duplicate
or reorder counts. The next existing preview attempt reached raw and preview
readiness and remained running.

The observation-only Mapping owner was then started once as job
`6cc5c5346e924389b8c68a156b4c318b`. Wireless IMU, FAST-LIO, odometry and
`/cloud_registered` readiness all passed. Immediately before this operation,
Control remained authenticated, lease-free, deadman false and exact zero, with
Bridge Move, non-zero Move and action counters all zero.

Exactly one candidate request was submitted as job
`b7a656e65836a0d72846d30e`, generation 1, with the following immutable inputs:

```text
map_id = 5ba0ac7a28fcc1c7b81cc58e
map_revision = 4ed9f19aec8cb338e2cdfa3e54946432e6231991ef87f8ea05e89dd242a4b979
source_pcd_id = e1252aeb1793d7bb78847e5e
source_pcd_revision = 86df7447267f0c1107e7fe7b8524a112a849ea3070dd4a8d292e2df8a00c0c80
seed = REGION x=0 y=0 yaw=0 radius=3.0m yaw_half_range=1.57rad
```

The server's stationary preflight passed, but collection then failed before the
registration executable ran with `collection filtered point count is invalid`.
There was no candidate output or preview layer and nothing was applied. The
preprocessor has a distinct overflow error above 100,000 voxels, so this error
path means the deterministic 0.15 m voxel result was below the fixed minimum of
500 points. The exact filtered count is not retained by the current failure
projection and remains unknown. The 500-point acceptance minimum and all
stationary limits were left unchanged; no automatic retry was attempted.

Reverse cleanup stopped the Mapping-owned FAST-LIO and external/robot-side IMU
processes. The persistent XT16 preview and relay remained active, and the
repaired XT16 destination remained `.18`. Navigation, Localization and goal
remained idle. Final Control evidence still showed no lease or deadman, exact
zero, and zero Move, non-zero Move and action requests.

```text
XT16_DESTINATION_RESTORED=PASS
XT16_WIRELESS_RELAY=PASS
D2_OBSERVATION_PIPELINE_READY=PASS
D2_LIVE_CANDIDATE=FAIL_PRE_REGISTRATION_FILTERED_POINTS_BELOW_MINIMUM
CANDIDATE_JOB_COUNT=1
CANDIDATE_OUTPUT=NONE
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=IDLE
FINAL_PREVIEW_STATE=RUNNING
```

## Wireless FAST-LIO DDS isolation correction — 2026-09-08

The continuity guard was deployed on the external Orin as exact release
`89e1de320782e062ee4aee190d45607af310235a`.  A stationary observation-only
pipeline was started after the operator's fresh safety confirmation.  Control
remained lease-free with deadman false and an exact-zero command; Navigation,
Localization, initial pose, candidate apply, goal and motion remained idle.

The runtime exposed a second, independent input-boundary defect.  The
dashboard-owned Hesai and XT16 cloud bridge processes retained the intended
wireless `ROS_LOCALHOST_ONLY=1` graph and continued converting exactly 50
clouds per five-second log interval.  The generic FAST-LIO runner, however,
cleared that inherited DDS setup and installed the direct-wired `eno1`
`CYCLONEDDS_URI`.  Inspection from the FAST-LIO DDS environment showed one
`/velodyne_points` subscription but zero publishers.  FAST-LIO consequently
published approximately 10 Hz odometry from continuing IMU input without a
continuing LiDAR publisher; no `/cloud_registered` samples were observed.
The IMU path itself remained healthy at approximately 490--499 Hz with no
authentication, clock or send failures.

This was not an XT16 relay outage: the onboard relay's accepted/forwarded
counters progressed continuously and its latest accepted/forwarded age stayed
near zero.  The defect was the wireless FAST-LIO child overwriting the local
DDS isolation selected by `setup_wireless_mapping_ros2_humble.sh`.  The
pipeline was stopped through the normal Mapping lifecycle with exit code 130;
the persistent preview remained running and no candidate request was made.

The wireless wrapper now explicitly re-sources the fixed wireless ROS setup
and selects an allowlisted `local` DDS mode.  The shared FAST-LIO runner keeps
its existing direct-wired behavior as the default, while the local mode
requires `ROS_LOCALHOST_ONLY=1` and rejects any inherited interface-specific
CycloneDDS URI.  Unknown modes fail closed.  No topic, timestamp, freshness,
publisher-cardinality, map-safety or Control threshold was changed.

```text
D2_CONTINUITY_RELEASE=89e1de320782e062ee4aee190d45607af310235a
D2_STATIONARY_PIPELINE_START=PASS
D2_WIRELESS_FASTLIO_INPUT=FAIL_DDS_GRAPH_SPLIT
D2_XT16_RELAY_CONTINUITY=PASS
D2_IMU_CONTINUITY=PASS
D2_CANDIDATE_REQUEST=NOT_RUN
D2_DDS_ROOT_CAUSE=FASTLIO_CHILD_OVERRODE_LOCAL_GRAPH
D2_DDS_FIX=SOFTWARE_IMPLEMENTED
DIRECT_WIRED_PROFILE_DEFAULT=UNCHANGED
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=STOPPED
FINAL_PREVIEW_STATE=RUNNING
```

The next step is hardware-free diagnosis of the live-query density and a
bounded failure projection that records raw and filtered counts without
weakening the fixed 500-point gate. Any later collection or candidate retry
requires a new explicit approval.

## Bounded count evidence and dense D2 query correction — 2026-09-08

Exact release `4d330116d4d1af519734697510455eaae3dd2748` added a
path-free, bounded collection diagnostic projection while retaining the
existing failed-job behavior. GitHub Actions run `34135991412` passed both
Ubuntu/Python matrices before deployment. The external dashboard was then
transitioned from `6285408fb17edf59a03c89cbee29d94a91db1bd2` to the exact
release with archive SHA-256
`97d529434f9199f0e77960160fee4063def47c3f0221d94e5e33bb04b38b27f7`.
The existing registration executable was retained at SHA-256
`89be25926a9bc1c66576d227473de520fde9b1cad9946e8ea060f8fca21b8ee5`.
Only the external dashboard restarted; the robot-side release and services
were unchanged.

With the robot stationary and Control lease-free, deadman false and exact
zero, the observation-only Mapping owner reached FAST-LIO readiness. Exactly
one candidate request was submitted as job `6d0f95d66ab629dde62ffaba` against
the same immutable map/PCD revisions and REGION seed as the preceding attempt.
It failed before registration with the following bounded evidence:

```text
frames = 26 (accepted range 20..50)
raw_points = 9307 (accepted maximum 1000000)
filtered_points = 455 (accepted range 500..100000)
query_voxel = 0.15 m
reason = filtered_points_below_minimum
```

This proves that the transport and collector received progressing frames. The
failure is specifically a 45-point shortfall after deterministic query
voxelization, not a missing XT16 stream, frame-count failure or registration
failure. The general competition FAST-LIO profile publishes a pre-thinned
registered scan (`dense_publish_en: false` with the unchanged 0.5 m FAST-LIO
surface/map filters). Applying the D1 0.15 m query filter to that already sparse
static output leaves insufficient unique geometry in this scene.

A narrow software correction adds a fixed D2-only FAST-LIO parameter file. It
is selected only when the existing exact D2 relocalization opt-in equals `1`.
It is semantically identical to `fastlio_xt16.yaml` except that
`dense_publish_en` is true. The base runner accepts only the two repository
filenames and rejects every other selection; an invalid D2 flag also fails
closed. There is no caller-supplied path and no runtime fallback. The normal
FAST-LIO profile, point filtering, frames, topics, odometry, IMU, clock and map
writer settings remain unchanged.

The correction does **not** lower or bypass the D1 contract: query voxel remains
0.15 m, minimum filtered query remains 500, maximum raw/filtered points remain
1,000,000/100,000, collection remains 20--50 frames, and all stationary,
cardinality, freshness and QoS checks remain active. It only prevents the D2
query source from being unnecessarily thinned before those checks.

Hardware-free verification on the focused tree:

```text
wireless mapping profile tests = 16 PASS
stationary relocalization tests = 26 PASS
mapping runtime artifact tests = 25 PASS
full Python suite = 1342 PASS
JavaScript unit suite = 278 PASS
Playwright = 34 PASS
Ruff = PASS
mypy = PASS (4 source files)
frontend syntax = PASS (55 modules)
secret scan = PASS
git diff --check = PASS
```

The first system-Python full-suite attempt was not an acceptance result because
that interpreter lacked repository dependencies (`fastapi` and `ruff`). The
complete result above used a fresh repository-only environment with both
requirements files installed. The browser suite was rerun outside the file
sandbox after its first local web-server bind was denied with `EPERM`.

After the live measurement, the operation-owned Mapping/FAST-LIO/IMU processes
were stopped in reverse order. Persistent preview and XT16 relay remained
running. Navigation, Localization, initial pose and goal stayed idle; candidate
apply remained unsupported. Final Control evidence retained inactive lease,
released deadman, exact-zero accepted command and zero Move/non-zero/action
requests.

```text
D2_BOUNDED_COUNT_EVIDENCE=PASS
D2_DENSE_QUERY_SOFTWARE=PASS
D2_DENSE_QUERY_DEPLOYMENT=NOT_RUN
D2_DENSE_QUERY_LIVE_CANDIDATE=NOT_RUN
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=IDLE
FINAL_PREVIEW_STATE=RUNNING
```

## Dense-query deployment and stationary candidate result — 2026-09-08

The dense-query correction was committed as exact release
`db4a9a9a81f49ed94915bd8d873c878ca6233f94`. GitHub Actions run
`34137638936` passed both Ubuntu/Python matrices before deployment. The exact
archive SHA-256 was
`7f8ce37654cdbb9bcc16307bc6913f150ea8e5194d80ed13f434aa67a4371c2e`.
Only the external dashboard was transitioned and restarted; the onboard
release remained `10a7fa9cec2c329f2c50edc9ad98de13a22689da` and its Bridge
was not restarted. The copied aarch64 registration executable retained
SHA-256
`89be25926a9bc1c66576d227473de520fde9b1cad9946e8ea060f8fca21b8ee5`.

The D2-only config, base runner and wireless runner hashes were respectively:

```text
776ed3e1ecba65629bbc47b422287a66f105dfcfdafcde1d2d6a1668397ad4df
0822b7826232ec44fe0956b06ef151ef975de27f2ffe31e26a34737c2babca37
4c756b550c8f8702e67286289443a48cf10b1e421fb1e5fa0124645f0803ede8
```

The dashboard process cwd resolved to the exact release, systemd reported
`NRestarts=0`, and Control preflight showed inactive lease, false deadman,
exact-zero accepted command and zero Move/non-zero Move/action requests.
Navigation, Localization and goal remained idle. The observation-only owner
then reached fixed XT16, IMU, FAST-LIO and D2 source readiness.

Exactly one candidate request was submitted as job
`fdf9613a575f47d54a025871` with the same pinned family and REGION seed. The
dense collection passed every fixed count and stationary gate:

```text
duration = 3.1798 s
frames = 25
raw_points = 366290
filtered_points = 1199
reference_points = 182949
source = /cloud_registered
frame = camera_init
local_origin = odom_at_collection_start
query_voxel = 0.15 m
```

The registration backend returned three bounded candidates, so the original
455-point problem is resolved. The top result had map-base pose approximately
`(-0.1225, -0.6186, 1.6001)`, fitness `0.08559`, overlap `0.97998` and
ambiguity margin `0.02258`. The next two results remained spatially distinct.
The result contract labeled all three `REJECTED`; because their point count,
overlap and fitness passed the rejection thresholds, the remaining exact
registration predicate is `converged=false`. This is not overridden by the
high overlap.

Every candidate also failed `footprint_not_known_free`. A byte-exact offline
inspection of the pinned 795 x 673 occupancy PGM using its trinary thresholds
found:

```text
total cells = 535035
known-free cells = 0
occupied cells = 8496
unknown cells = 526539
top candidate 0.35 m footprint = 0 free, 0 occupied, 183 unknown cells
seed (0,0) 0.35 m footprint = 0 free, 0 occupied, 183 unknown cells
```

This is consistent with the fixed PCD conversion's conservative unknown
background: it projects occupied returns but does not invent ray-traced free
space from a point cloud that contains no sensor trajectory. Consequently no
pose anywhere in this exact occupancy map can satisfy the known-free footprint
gate. The gate behaved correctly and was not weakened. Converting unknown
space to free is an explicit operator-reviewed map edit or a separate
`background=free` conversion; it is not safe to perform implicitly during
relocalization.

The operation-owned Mapping/FAST-LIO/IMU processes were stopped in reverse
order. Persistent preview and the onboard XT16 relay remained active. Final
Navigation and Localization state was idle, candidate apply remained false,
and Control remained lease-free, deadman false and exact zero with no Move or
action request.

A narrow follow-up now counts known-free cells in the immutable occupancy
snapshot before collecting sensors. A zero-free-cell map fails before the
collector and registration child run, and exposes only bounded map
diagnostics (`known_free_cells`, required 0.35 m clearance, eligibility and a
fixed reason). It does not mark unknown as free, change the legacy map API,
relax the footprint gate, apply a candidate or start navigation.

```text
D2_DENSE_QUERY_DEPLOYMENT=PASS
D2_DENSE_QUERY_COLLECTION=PASS
D2_REGISTRATION_CONVERGENCE=FAIL
D2_OCCUPANCY_KNOWN_FREE_ELIGIBILITY=FAIL_ZERO_FREE_CELLS
CANDIDATE_JOB_COUNT=1
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=IDLE
FINAL_PREVIEW_STATE=RUNNING
```

## Free-background review map and convergence isolation — 2026-09-08

After CI run `34139275304` passed both matrices, exact release
`fee0b39e307ec76818820e57940405847fff49a6` was installed on the
external Jetson only. Its archive SHA-256 was
`0fcaf1506e978f0ba1880e05169b47c0701b1f7194f1203fe68243549e09602f`.
The dashboard was restarted through the fixed lifecycle API and ran from the
exact release with PID 78743, invocation
`1807b56bf4cc4f8a86a1d9ef42f994c0`, and `NRestarts=0`. The onboard
Bridge release and services were not changed or restarted.

The original conservative occupancy map was retained. A separate, explicitly
named review artifact was generated from the same exact PCD with the existing
fixed conversion and `background=free` option:

```text
name = map_20260907_175720_d2_free_review
occupancy_map_id = 1d3919f3566bc6b06fd5ee2c
occupancy_revision = 047db8a83e823227d0e6dac465d258caa246ab16522846a3744daccf02007837
family_id = f302795bf3383bab2812e4ad
family_revision = e88c7036f78faac1a19bff5cf0dafe0a77193176fe5ad10bb394a6e16074a096
source_pcd_id = e1252aeb1793d7bb78847e5e
source_pcd_revision = 86df7447267f0c1107e7fe7b8524a112a849ea3070dd4a8d292e2df8a00c0c80
conversion_parameters_hash = d42e4f111b3f3c4a6382660dd1aeac4e1884b10ff051a2bdfa3a9445086b7d82
known_free_cells = 526539
occupied_cells = 8496
```

This artifact is a review candidate, not an active navigation map. The source
PCD and the earlier unknown-background family remain unchanged. No candidate,
initial pose or navigation state was applied from it.

With the robot still stationary, the observation-only owner was started and
reached readiness. Exactly one D2 candidate job,
`659d57cd7c7fa4231b8de54e`, used the new exact family and the unchanged
REGION seed. Map preflight reported `eligible` with 526,539 known-free cells.
Collection again passed without relaxing any limit:

```text
duration = 3.1242 s
frames = 26
raw_points = 380976
filtered_points = 1189
reference_points = 182949
```

The top result was approximately `(-0.1148, -0.6597, 1.5875)`, with fitness
`0.08396`, overlap `0.98402`, 1,189 query points, and ambiguity margin
`0.00956`. Its footprint was known-free, proving that the previous footprint
failure was solely the map's zero-free-cell condition. The result remained
`REJECTED` because the registration backend reported `converged=false`.
The second result was also footprint-valid but spatially distinct; the third
result remained footprint-invalid. Nothing was applied.

A path-free current preview was retained for offline diagnosis. Replaying the
same bounded query against the exact reference reproduced `converged=false`
for the original REGION search, an exact top-pose seed, and a tight local seed.
An independent iteration audit reproduced the backend's final pose exactly.
Across all 30 refinement iterations, the translation correction never fell
below the fixed 0.1 mm convergence threshold; after the initial correction it
continued at approximately 3.35--7.68 mm per iteration along the ambiguous
geometry. This is persistent nearest-neighbour drift, not a near-converged
result that should be rounded into acceptance. The low `0.00956` ambiguity
margin and separated alternatives independently support keeping the current
fail-closed outcome. No convergence threshold, confidence threshold, search
bound or footprint rule was changed.

Reverse cleanup stopped the operation-owned FAST-LIO and IMU processes. The
persistent preview and onboard XT16 relay remained running. The temporary
remote replay PCD was removed. Final state retained inactive lease, false
deadman, exact-zero command, zero Move/non-zero Move/action requests, idle
Navigation/Localization/goal, and no candidate apply.

```text
D2_ZERO_FREE_PREFLIGHT_DEPLOYED=PASS
D2_FREE_REVIEW_MAP_CREATED=PASS_NOT_ACTIVE
D2_MAP_ELIGIBILITY=PASS
D2_DENSE_COLLECTION=PASS
D2_REGISTRATION_CONVERGENCE=FAIL_AMBIGUOUS_DRIFT
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=IDLE
FINAL_PREVIEW_STATE=RUNNING
```

## Opt-in PCL backend isolation — 2026-09-08

The external Orin package audit found PCL 1.12.1 and Eigen 3.4.0 already
installed. No package, OS, firmware or service configuration was changed. The
retained query from job `659d57cd7c7fa4231b8de54e` and the exact immutable
source PCD were evaluated only as local offline files on that host.

Unconstrained PCL NDT and GICP converged from several seeds, but produced
materially different transforms. An integrated six-degree-of-freedom NDT
result was rejected by the unchanged out-of-plane correction bounds. The
follow-up implementation therefore provides PCL NDT2D as a separately built,
explicit opt-in x/y/yaw backend; PCL GICP remains an opt-in comparison backend
and must satisfy the same out-of-plane bounds. The portable
`bounded-se2-icp` executable remains the build and runtime default.

With the existing 30-iteration ceiling and the same bounded coarse seeds, the
temporary aarch64 NDT2D build returned three converged results. The top result
was approximately `(-0.2894, -0.7796, 1.6322)` with fitness `0.08915`, overlap
`0.98734`, and confidence `LOW`. The next result was spatially distinct and
the fitness margin was `0`; therefore the existing ambiguity gate would mark
the result `AMBIGUOUS`, never apply it. This was an offline replay, not a new
live candidate job.

The API job projection now preserves the exact requested seed, selected
backend, bounded stage timings and an explicit `converged` flag. Rejected
registration results retain the compatibility reason `registration_rejected`
and add either `registration_not_converged` or
`registration_quality_rejected`. This supplies D3 with exact diagnostic text
without changing acceptance policy.

```text
D2_PCL_DEPENDENCY_AUDIT=PASS
D2_PCL_NDT_GICP_OFFLINE_COMPARISON=PASS
D2_PCL_NDT2D_AARCH64_BUILD=PASS_TEMPORARY
D2_PCL_NDT2D_LIVE_JOB=NOT_RUN
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

## PCL qualification rejection — 2026-09-08

The opt-in implementation was published for review at `0f1fd15`, but it was
not activated. An exact inactive aarch64 staging build exposed an NDT2D
no-overlap failure in the deterministic corpus and an unsafe internal GICP
optimizer failure. Production remained on `fee0b39`; no environment setting,
stable release link or running service was changed.

Follow-up `bc3b7c9e0e137b7c385befe41aaa91d8b1bfdfac` converts catchable PCL
refinement failures and invalid out-of-plane transforms into explicitly
rejected bounded-seed diagnostics. It also adds strict benchmark accounting,
where all cases must converge, remain policy-accepted and meet the published
D1 median/p95 error limits. Its exact release archive SHA-256 was
`0a7ac2d19f8942a6c2813de861c5d41b460b3fb6b0dc23613ec24cc608e6bda0`.
The external Orin built both optional PCL executables and passed the C++ test.

The strict NDT2D result was:

```text
cases = 10
converged_cases = 0
accepted_cases = 0
acceptance_pass = false
translation median/p95 = 0.005111 / 0.016583 m
yaw median/p95 = 0.173053 / 0.280629 deg
runtime p50/p95 = 7319.814 / 7679.981 ms
```

The error numbers are the preserved bounded-seed diagnostics after NDT2D
failure, not successful PCL estimates. An identical-cloud check also produced
three no-overlap failures and no converged candidate. NDT2D therefore cannot
be selected for D2 live use. GICP was not rerun after its prior internal PCL
assertion because a process abort is already disqualifying evidence. The final
runtime allowlist contains only `bounded-se2-icp`; both PCL executables remain
offline diagnostic builds.

```text
D2_PCL_AARCH64_BUILD=PASS
D2_PCL_NDT2D_STRICT_CORPUS=FAIL
D2_PCL_GICP_RUNTIME_QUALIFICATION=FAIL_NOT_RERUN
D2_PCL_RUNTIME_ALLOWED=false
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
PRODUCTION_RELEASE_UNCHANGED=fee0b39e307ec76818820e57940405847fff49a6
```

## Fixed-grid NDT2D qualification — 2026-09-08

The no-overlap result was isolated to the NDT2D grid density. A 2.0 m fixed
grid remained fail-closed with zero converged cases. A 4.0 m fixed grid, with
the same 20 m extent, three bounded coarse seeds, 30-iteration ceiling,
15-second process timeout and unchanged confidence/error limits, passed the
same exact aarch64 corpus:

```text
cases = 10
converged_cases = 10
accepted_cases = 10
acceptance_pass = true
translation median/p95 = 0.001277 / 0.003105 m
yaw median/p95 = 0.028152 / 0.097858 deg
runtime p50/p95 = 7464.705 / 8297.440 ms
```

The source now compiles that exact grid value. `pcl-ndt2d` may be selected
only by the server-owned environment allowlist, while the default remains
`bounded-se2-icp`. GICP remains offline-only. This qualification authorizes a
new exact-release build and stationary candidate attempt; it does not apply a
pose, start localization/Nav2, acquire control authority or move the robot.

```text
D2_PCL_NDT2D_STRICT_CORPUS=PASS_FIXED_GRID
D2_PCL_GICP_RUNTIME_ALLOWED=false
D2_PCL_NDT2D_RUNTIME_ELIGIBLE=true
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

## New operator map and fail-closed estimator-continuity result — 2026-09-08

The operator created a new map while retaining every earlier map family.  The
edited occupancy map was selected because it contains reviewed known-free
space and the confirmed mapping start pose has the required fixed clearance:

```text
name = map_20260908_072712_edited
occupancy_map_id = 8050fff44b44ce106dc5a210
occupancy_revision = 9e72787f2443b714ed3045fda62c08c53e85294c7d02e26b8e74ce0cc30fc8ac
family_id = 9c0d4b61b0ae56f51fc58282
family_revision = 00ec2270739659dd6e25fd35885e77257df44adeffd25e0223b4d712cb822b50
source_pcd_id = a0c90ce578dced8ee5a6751f
source_pcd_revision = c39b41c367c93c4834acf864f78104ef853ec32f5a8d627306ef2a91e5374574
source_pcd_frame = camera_init
source_pcd_points = 501135
occupancy_size = 295 x 205
occupancy_resolution = 0.05 m
known_free_cells = 54936
occupied_cells = 5539
unknown_cells = 0
seed_clearance = PASS at x=0 y=0 radius=0.35 m
```

The external dashboard ran exact release
`0970f05a35a9f6620b2617289e74a3ae5973ec13`; the onboard signed Control
Bridge remained on `10a7fa9cec2c329f2c50edc9ad98de13a22689da` and was not
restarted.  The operator confirmed the standing robot was stationary at the
mapping start pose and direction with the physical remote/E-stop ready.  A
pre-existing observation-only Mapping pipeline was reused rather than starting
a second owner.  Exactly one D2 request was submitted as job
`32412e4611296d328affd47a` with REGION seed `(0, 0, 0)`, radius `3.0 m` and
yaw half-range `1.57 rad`.

Map and bounded collection gates passed through 26 frames, 391,685 raw points
and 1,503 filtered points.  Registration was not started because the unchanged
5 mm stationary translation gate rejected the collection as
`robot moved during stationary collection`.  No candidate or preview was
created and nothing was applied.

Read-only evidence proves this was estimator divergence rather than physical
motion.  Two `/Odometry` samples twelve seconds apart changed from
approximately `(472.58, 1591.42, -12768.73)` to
`(-340.74, 1335.81, -20438.32)`.  FAST-LIO logged repeated
`No Effective Points!` messages.  At the same time, the onboard authenticated
IMU sender stopped receiving its fixed `/lowstate` input for roughly 50
seconds: its received and sent counters both stopped, `input_ready` became
false, `send_errors` stayed zero, and the clock/authentication rejection
counters stayed zero.  The external receiver showed the same packet gap while
NetworkManager and kernel logs showed no Wi-Fi interface transition.

This localizes the observed interruption upstream of the onboard IMU sender,
at the `/lowstate` publisher/input boundary.  It does not yet identify why that
publisher disappeared.  It also does not establish a generic wireless UDP
failure.  Once input resumed, the old FAST-LIO process continued with a
corrupted estimate, which the D2 displacement gate correctly rejected.

The unstable operation-owned Mapping pipeline was stopped through its normal
lifecycle and reached `stopped` with exit code 130.  The saved map and PCD were
preserved.  Persistent XT16 preview and relay stayed active.  Final Control
state remained lease-free, deadman false and exact zero; signed Bridge evidence
showed zero Move, non-zero Move and action requests.  Navigation,
Localization, initial pose and goal remained idle.

The D2 evidence owner now records an explicit publisher generation for each of
the fixed cloud, odometry and IMU inputs.  A receipt gap over the existing
0.50-second freshness limit, a non-progressing source stamp, invalid source
sample or publisher-cardinality transition latches the evidence invalid.  New
packets cannot silently clear that latch.  Only a verified transition to a new
single-publisher generation resets it, which in this lifecycle requires a
fresh observation-pipeline generation.  The collector pins all three source
generations and rejects any change during its collection window.  The existing
5 mm, twist, IMU, source-age, QoS, cardinality and map-safety limits are
unchanged.

```text
D2_NEW_MAP_ELIGIBILITY=PASS
D2_NEW_MAP_LIVE_JOB=FAIL_PRE_REGISTRATION_ESTIMATOR_DIVERGENCE
D2_IMU_GAP_BOUNDARY=ONBOARD_LOWSTATE_INPUT
D2_IMU_GAP_ROOT_CAUSE=UNKNOWN
D2_EVIDENCE_CONTINUITY_GUARD=SOFTWARE_VALIDATED
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=STOPPED
FINAL_PREVIEW_STATE=RUNNING
```

## New-map local-DDS recovery and one-shot candidate result — 2026-09-08

Exact external release
`f1c9edb97b01bcea1da98482bc36f18b114611a1` preserved the wireless local
DDS graph for the FAST-LIO child.  A freshly confirmed stationary run then
showed exactly one publisher for each fixed input/output.  The measured rates
were approximately 10.00 Hz for `/velodyne_points`, 9.99 Hz for `/Odometry`,
9.95--10.00 Hz for `/cloud_registered`, and 493--500 Hz for `/imu/body`.
Observed maximum gaps were respectively 0.125 s, 0.169 s, 0.167 s and
0.009 s.  Frames remained `hesai_lidar`, `camera_init`, `camera_init` and
`body_imu`.  Control remained lease-free, deadman false and exact zero;
Navigation and Localization remained idle.

After an exact lineage preflight, job `2a1b88bd81dcc4b02baad4c6` was submitted
exactly once for `map_20260908_072712_edited`, REGION seed `(0, 0, 0)`, radius
3.0 m and yaw half-range 1.57 rad.  Collection and map eligibility passed:

```text
frames = 21
raw_points = 315049
filtered_points = 1392
known_free_cells = 54936
required_clearance = 0.35 m
```

The job failed closed before producing candidates because the opt-in PCL
NDT2D executable returned syntactically invalid JSON.  Code-path audit found
that its zero-correspondence diagnostic used positive infinity as `fitness`
and serialized the C++ stream token `inf`, which is not JSON.  The fixed result
contract already supports a non-converged, zero-overlap `REJECTED` candidate,
so the producer now uses the finite squared correspondence ceiling as that
diagnostic fitness.  This does not mark the candidate converged, increase
overlap, lower any confidence threshold, accept a pose, or change registration
bounds.  The strict consumer continues to reject all non-finite numbers and
malformed JSON.

No automatic retry was attempted.  Candidate apply, initial pose, Nav2, goal,
lease, ARM, deadman, non-zero command and robot motion were not executed.

```text
D2_LOCAL_DDS_GRAPH=PASS
D2_NEW_MAP_COLLECTION=PASS
D2_NEW_MAP_ELIGIBILITY=PASS
D2_CANDIDATE_JOB_COUNT=1
D2_CANDIDATE_RESULT=FAIL_INVALID_PCL_JSON
D2_PCL_ZERO_CORRESPONDENCE_JSON_FIX=SOFTWARE_IMPLEMENTED
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
```

## Exact finite-JSON release deployment — 2026-09-08

After both GitHub Actions matrices passed, the operator explicitly authorized
an external-dashboard-only deployment of exact release
`fccd003410c53065120340e4c14b52a6fe17b68d`.  The release archive SHA-256 was
`b8cd0772a8a5c2a1b3fc52faad729a5e938f5fefa13157e182e7a838f483dbb6`.
It was extracted to a new release directory without modifying the retained
rollback release `f1c9edb97b01bcea1da98482bc36f18b114611a1`.

On the external aarch64 Jetson, PCL NDT2D was rebuilt from the exact release.
CTest passed 1/1.  The strict fixed-grid benchmark parsed the executable output
as JSON and passed all ten cases:

```text
cases = 10
converged_cases = 10
accepted_cases = 10
acceptance_pass = true
translation median/p95 = 0.001277 / 0.003105 m
yaw median/p95 = 0.028152 / 0.097857 deg
runtime p50/p95 = 956.050 / 1001.532 ms
```

Only the external release symlink was switched and only
`robot-scope.service` was restarted.  The resulting process cwd and stable
symlink both resolved to the exact `fccd003...` release; the dashboard was
active with PID 403070 and `NRestarts=0`.  The external local Control Bridge
service remained inactive, and the onboard Jetson and signed robot-side
Bridge were not changed or restarted.

Post-switch checks showed no active or retained relocalization job.  The
persistent preview recovered to `running`, while the mapping pipeline and
mapping operation were `idle`.  Navigation, Localization and goal were idle.
Control retained no lease, deadman false and exact-zero x/y/yaw commands.  The
selected map remained `map_20260908_072712_edited` with revision
`9e72787f2443b714ed3045fda62c08c53e85294c7d02e26b8e74ce0cc30fc8ac`.
No candidate, initial pose, Nav2 goal or motion was executed by this
deployment.

```text
D2_EXACT_FCCD003_EXTERNAL_DEPLOYMENT=PASS
D2_EXACT_FCCD003_AARCH64_BUILD=PASS
D2_EXACT_FCCD003_CTEST=PASS_1_OF_1
D2_EXACT_FCCD003_STRICT_JSON_CORPUS=PASS_10_OF_10
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=IDLE
FINAL_PREVIEW_STATE=RUNNING
```
