# ADR: stationary 3D relocalization candidate job

Status: accepted for hardware-free D2 implementation; live source qualification blocked

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

This selection is provisional until a read-only graph/frame/QoS audit and an
external-Orin build prove:

- exactly one publisher and fresh increasing stamps;
- the actual `/cloud_registered` frame is `camera_init`;
- the cloud is a bounded current scan rather than an ever-growing map;
- `/Odometry` supplies a fresh `camera_init -> body` pose;
- controller odometry, FAST-LIO twist and body IMU provide independent
  stationary evidence.

The existing operator-selected point-cloud preview is not an acceptable data
owner. A dedicated profile-fixed provider must feed
`FixedCloudRegisteredCollector`; the repository does not silently enable or
construct that provider in D2 software acceptance.

## 2026-09-07 external-Orin audit

The read-only graph audit used the ROS environment of the running external
dashboard. It found one RELIABLE/VOLATILE publisher with depth 20 for each of
`/cloud_registered`, `/Laser_map`, and `/Odometry`; `/velodyne_points` and
`/imu/body` had no publisher. Both `/cloud_registered` and `/Odometry` failed
to deserialize in the external Humble CLI with CycloneDDS reporting
`string data is not null-terminated` followed by `invalid data size`.

The onboard Jetson at the fixed management address was not reachable from the
external Orin: its neighbour entry remained incomplete, ICMP returned host
unreachable, and TCP/22 failed. Therefore the graph endpoints cannot be
qualified as current live producers, their frame and stamps could not be
validated, and the provisional `/cloud_registered` choice remains closed.
Publisher cardinality by itself is not live-source evidence.

The exact `86304406d128c149493380189b01409448225a3a` portable reference backend
was separately staged under a temporary external-Orin directory, built with
GCC 11.4 on aarch64, and passed its CTest. The ten-case 2,530-point synthetic
benchmark measured translation median/p95 0.005111/0.016583 m, yaw median/p95
0.173053/0.280628 degrees, runtime p50/p95 937.776/982.801 ms, and child peak
RSS 13,404 KiB. The temporary staging was removed and the production release
and service were unchanged. PCL 1.12.1 was installed, but no PCL NDT/GICP
backend exists in the repository, so no PCL comparison is claimed.

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
