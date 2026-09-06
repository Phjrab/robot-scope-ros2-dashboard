# Track D2 stationary live candidate acceptance

Status: `D2_REPOSITORY_SOFTWARE_PASS`; live acceptance not run

```text
D2_REPOSITORY_SOFTWARE_PASS
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
