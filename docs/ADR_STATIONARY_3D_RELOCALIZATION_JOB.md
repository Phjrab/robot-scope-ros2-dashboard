# ADR: stationary 3D relocalization candidate job

Status: accepted; live source qualified; runtime wiring software complete but not deployed

## Decision

Robot Scope models stationary 3D relocalization as one generation-fenced,
server-owned job. The job pins one D0 map family, collects one bounded local
submap, invokes the D1 fixed registration process and returns at most three
review-only map-frame candidates. It never publishes `/initialpose`, starts
Nav2, acquires a lease, arms control, asserts deadman or sends motion.

The HTTP surface is deliberately limited to start, status, one job, cancel and
three bounded preview layers. It has no apply endpoint.

## Live source decision

The code-owned candidate source is `/cloud_registered` in `camera_init` for the
`go2-xt16-wireless-competition-fastlio` profile. This avoids using `/Laser_map`
as a current observation and avoids accumulating raw `/velodyne_points`
without a separately qualified transform owner. Each registered cloud is
expected to already use the fixed FAST-LIO local frame.

This selection was provisional until a read-only graph/frame/QoS audit and an
external-Orin build proved:

- exactly one publisher and fresh increasing stamps;
- the actual `/cloud_registered` frame is `camera_init`;
- the cloud is a bounded current scan rather than an ever-growing map;
- `/Odometry` supplies a fresh `camera_init -> body` pose;
- controller odometry, FAST-LIO twist and body IMU provide independent
  stationary evidence.

The 2026-09-07 stationary audit below qualifies the source contract. The
existing operator-selected point-cloud preview is still not an acceptable data
owner. A dedicated profile-fixed provider must feed
`FixedCloudRegisteredCollector`; the repository does not silently enable or
construct that provider in D2 software acceptance.

## 2026-09-07 external-Orin audit

The first read-only graph audit used the ROS environment of the running
external dashboard. It found one advertised publisher for each of
`/cloud_registered`, `/Laser_map`, and `/Odometry`; `/velodyne_points` and
`/imu/body` had no publisher. Both `/cloud_registered` and `/Odometry` failed
to deserialize in the external Humble CLI with CycloneDDS reporting
`string data is not null-terminated` followed by `invalid data size`.

After the onboard Jetson rejoined Wi-Fi, a fresh `--no-daemon` audit still saw
the three publisher endpoints, but their node names and namespaces were
`UNKNOWN`, node enumeration itself failed in the RMW layer, and the same
CycloneDDS decoding errors occurred. The onboard Foxy graph had none of the
five topics and no sensor or FAST-LIO process; only the fixed XT16 relay and
Control Bridge were active. The external dashboard's existing preview owner
was repeatedly starting its Hesai process, but no raw cloud became ready.
Consequently the advertised endpoints are discovery-corruption or otherwise
unattributed endpoint evidence, not proof of a live compatible publisher. The
earlier error must not be described as a proven live-wire serialization
incompatibility.

The onboard host was reachable at `192.168.50.30` over Wi-Fi and both the XT16
at `192.168.123.20` and Go2 body at `192.168.123.161` answered bounded ICMP.
However, the fixed relay captured hundreds of thousands of packets while
accepting and forwarding zero. Its counters increased only in `packet_type`
and `ip_address` rejections; the required
`192.168.123.20:10000 -> 192.168.123.18:2368` stream was not observed. A
bounded privileged header capture is still required to identify the actual
XT16 destination without changing it. Frame, stamp progression, rate and
bounded-current-cloud semantics therefore remain unverified, and the
provisional `/cloud_registered` choice remains closed. Publisher cardinality
by itself is not live-source evidence.

The exact `86304406d128c149493380189b01409448225a3a` portable reference backend
was separately staged under a temporary external-Orin directory, built with
GCC 11.4 on aarch64, and passed its CTest. The ten-case 2,530-point synthetic
benchmark measured translation median/p95 0.005111/0.016583 m, yaw median/p95
0.173053/0.280628 degrees, runtime p50/p95 937.776/982.801 ms, and child peak
RSS 13,404 KiB. The temporary staging was removed and the production release
and service were unchanged. PCL 1.12.1 was installed, but no PCL NDT/GICP
backend exists in the repository, so no PCL comparison is claimed.

## 2026-09-07 stationary source qualification

After the fixed XT16 wireless path and its cold-boot recovery had been
accepted, the operator gave a fresh stationary-only hardware approval. The
external dashboard was still running release
`6ce4b1dad5b2fdd75710022264683dd65fa6e9d4`; the onboard release symlink was
`10a7fa9cec2c329f2c50edc9ad98de13a22689da`. The repository under assessment
was `2adb329c674d166fe06d59f4c1b8d1998cbaf672`.

The existing fixed Mapping launcher was used only as an observation owner. It
reused the already-running Hesai preview driver and XT16 conversion process,
then started the remote wireless IMU sender, external IMU receiver and
FAST-LIO. No map save, initial pose, Nav2 session, goal, lease, ARM, deadman or
non-zero command was issued.

The qualified graph was:

| Topic | Publisher | Frame / child | Offered QoS | Observed rate |
|---|---|---|---|---:|
| `/cloud_registered` | one `laser_mapping` | `camera_init` | reliable, keep-last 20, volatile | 9.993 Hz final |
| `/Laser_map` | one `laser_mapping` | `camera_init` | reliable, keep-last 20, volatile | growing map; not selected |
| `/Odometry` | one `laser_mapping` | `camera_init` / `body` | reliable, keep-last 20, volatile | 9.994 Hz final |
| `/imu/body` | one `robot_scope_wireless_imu_receiver` | body IMU source | reliable, keep-last 5, volatile | approximately 499 Hz |

Five `/cloud_registered` payloads contained 350--359 source points. Three
`/Laser_map` payloads grew from 19,607 to 21,028 points. This distinguishes the
selected topic as the bounded current registered scan and the rejected topic
as the accumulated map. Source stamps progressed and the final cloud/odometry
period measurements were bounded (cloud 0.084--0.119 s, odometry
0.083--0.117 s).

Two stationary odometry samples taken 15 seconds apart had a planar delta of
approximately 3.75 mm. Sampled FAST-LIO twist was exactly zero and body IMU
angular-rate magnitudes were approximately 0.0137 and 0.0114 rad/s. These are
inside the existing 5 mm, 0.01 m/s and 0.05 rad/s D2 limits for this bounded
qualification interval. This evidence qualifies the live input; it does not
constitute a registration candidate run or prove a dynamic localization
result.

During the audit, process use was approximately 34% CPU/49.8 MiB RSS for the
IMU receiver, 30%/140 MiB for FAST-LIO, 28%/111.5 MiB for the Hesai driver and
10.6%/15 MiB for the XT16 bridge. System memory remained about
2.2--2.6 GiB of 7.6 GiB with no swap use; GPU use was zero and temperature was
approximately 39--41 C. The diagnostic CLI sampling itself caused a temporary
CPU burst, so those peak per-core values are not attributed to the steady
pipeline.

Cleanup stopped only the audit-owned Mapping pipeline. FAST-LIO, the external
IMU receiver and onboard wireless IMU sender were absent afterward;
`/cloud_registered`, `/Laser_map`, `/Odometry` and `/imu/body` had no live
publisher. The browser preview remained healthy on `/velodyne_points` with its
single publisher. Control remained disarmed, lease-free, deadman false and
exact zero throughout, with zero non-zero Move requests.

The source decision is therefore closed as `/cloud_registered` in
`camera_init` for the exact competition FAST-LIO profile. Runtime candidate
generation remains disabled. A dedicated profile-fixed evidence owner now
exists behind the exact server opt-in
`ROBOT_SCOPE_D2_STATIONARY_OBSERVER=1`; the wrong profile or a missing opt-in
creates no D2 subscription. It validates the three fixed live sources without
publishing anything and never follows the UI-selected preview source. The
manager still requires an explicit non-persistent physical-safety confirmation
boundary and fixed registration binary before it may be constructed and
deployed.

The observer-only `b8fe0c5a749eafc9c507157b101ba289e393e60d`
release was subsequently installed on the external Orin with the exact
competition profile and opt-in.  Its aarch64 registration core passed CTest,
but the manager stayed unconfigured.  Because the stationary FAST-LIO source
path was not started, no D2 source publisher was present and the observer
remained waiting rather than manufacturing readiness.  The selected edited
occupancy map and similarly named PCD were also confirmed to be legacy
`unlinked` artifacts.  They cannot be paired by name; a new explicit
lineage-aware conversion is required before candidate execution.

The approved follow-up conversion created
`map_20260902_161903_d2` (`85fa623a8a859c351ec47912`, revision
`cbfc70e3c79ccc1fb365c68f4d0705bda0b822e9d063138eb19052995e81d219`)
from the exact pinned PCD ID and revision.  Its family status is `linked`; the
family metadata preserves the explicit planar projection and conversion
parameters.  Existing map artifacts were retained.

The same follow-up started the fixed FAST-LIO Mapping owner while stationary
and proved that the deployed opt-in observer attaches to
`/cloud_registered`, `/Odometry` and `/imu/body` only after their fixed
publishers exist.  Each source had exactly one publisher and the observed
rates were approximately 10/10/500 Hz with the expected frames.  The observer
does not publish; the normal RosAgent's unrelated publishers do not change
that contract.  A longer diagnostic pair showed about 6.44 mm planar FAST-LIO
position change over approximately 20 seconds, so it was not accepted as a D2
stationary collection.  The 5 mm limit remains unchanged, the candidate
manager remains unconfigured, and no registration or apply operation ran.
Reverse cleanup removed only the Mapping-owned FAST-LIO and IMU processes and
kept the existing point-cloud preview active.

## Runtime construction boundary

The runtime manager is now constructed only when both fixed opt-ins are
present. `ROBOT_SCOPE_D2_STATIONARY_OBSERVER=1` enables the fixed evidence
owner, and `ROBOT_SCOPE_D2_STATIONARY_RELOCALIZATION=1` enables the candidate
manager. The second flag is false by default, requires the exact
`go2-xt16-wireless-competition-fastlio` profile and refuses startup if the
observer is absent. The registration executable path is server-owned and
fixed beneath the exact release; its existing adapter rejects symlinks and
paths outside the private relocalization runtime root.

The backend is also fixed before construction. The optional
`ROBOT_SCOPE_D2_REGISTRATION_BACKEND` value is accepted only from the
environment-owned allowlist (`bounded-se2-icp`, `pcl-ndt2d`). It
selects a distinct fixed executable beneath the release and is never accepted
from an HTTP request. The default remains `bounded-se2-icp`; PCL executables
exist only in builds that explicitly enable them.

Every start request must contain the strict boolean
`physical_safety_confirmed=true`. It is checked before the worker starts and
is deliberately removed from the stored/public job result, so it cannot be
reused as persistent authority. The runtime gate additionally requires an
authenticated ready Control Bridge, no control or navigation lease, deadman
released, exact-zero command and fresh Sport velocity, no action guard, no
software stop latch, idle Navigation/goal and Dataset Capture, and the fixed
Mapping observation pipeline running without a conflicting mapping action.

The collector re-evaluates that runtime gate before every source poll and once
more after the bounded collection window. A lease, goal, pipeline loss,
publisher change, stale source or non-zero velocity therefore fails the job
closed rather than being hidden by a cached cloud. The manager still has no
candidate-apply route and does not publish an initial pose or mutate Mapping,
Navigation, Mission or Control state.

This construction has passed hardware-free tests only. The manager opt-in has
not been added to either deployed Jetson environment, no service has been
restarted for it and no live candidate has been generated.

## Ownership and state

One `StationaryRelocalizationManager` owns one worker, cancellation token and
private job directory. States are `preflighting`, `collecting`,
`preprocessing`, `coarse_search`, `refining`, `candidate_ready`, `ambiguous`,
`rejected`, `canceling` and `failed`. Every mutation checks the job ID and
generation. Cancel propagates into the D1 child, which performs bounded
TERM-to-KILL process-group cleanup.

Only the most recent eight immutable public results are retained in memory.
Private PCD and occupancy snapshots are removed after settlement. Public
responses are deep copies and never expose paths.

## Fixed limits

| Contract | Limit |
|---|---:|
| collection duration | 2.5 s default; 5 s maximum |
| accepted evidence duration | 2–5 s |
| source frames | 20–50 |
| raw points | 1,000,000 maximum |
| filtered points | 500–100,000 |
| top candidates | 3 |
| reference/current/aligned previews | 50k / 30k / 30k |
| controller translation delta | 5 mm maximum |
| controller yaw delta | 0.01 rad maximum |
| FAST-LIO twist | 0.01 m/s maximum |
| body IMU angular rate | 0.05 rad/s maximum |
| footprint clearance | 0.35 m |

Every accepted source stamp is strictly increasing. The fixed source identity,
publisher cardinality, freshness and QoS must remain valid. Unknown evidence
fails closed.

## Transform convention and candidate validation

Registration estimates `T_map_odom`, mapping a current `camera_init` point into
the stored PCD map frame. The candidate base pose is:

```text
T_map_base = T_map_odom × T_odom_base
```

The candidate base must be inside the exact derived occupancy map and its
0.35 m footprint must be entirely known-free. KEEP_OUT rejects the candidate;
SLOW_ZONE and WAIT_ZONE are labels only. A spatially distinct runner-up with
insufficient score margin marks the top candidate `AMBIGUOUS`.

The D1 engine is 3DoF. It does not estimate z, roll or pitch, and the response
marks those corrections unavailable rather than fabricating zeros. Live use
therefore remains gated until that limitation is explicitly accepted or a
qualified production backend supplies bounded out-of-plane evidence.

## Compatibility

Track A/B/C behavior, strict wireless odometry guards, C2 FAST-LIO/controller
odometry, C3 localization ownership, navigation lease semantics, control
watchdogs and D0 map-family rules are unchanged. D2 API availability alone
does not enable the manager or add a ROS subscription.
