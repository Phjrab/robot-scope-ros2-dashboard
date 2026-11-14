# Current hardware cloud preservation and comparison

## Outcome

Current hardware messages were preserved before analysis. The active FAST-LIO
configuration really publishes a heavily reduced world-frame cloud. A same-stamp
comparison shows that denser input helps local fitting, but **does not by itself
fix global candidate search**. Dense local fitting finds a substantially lower
residual than either global result, while remaining inconsistent with the prior
and outside existing adoption limits. Production behavior is unchanged.

This is current-cloud **offline diagnostic evidence**, not an accepted live
navigation proposal, step ② application, verified physical location or motion
test. No zero height/tilt, synthetic TF, relaxed bounds, or extended freshness was
used. Old Z/roll/pitch is explicitly an unverified diagnostic seed hypothesis.

## Reboot and operations

On 2026-11-14 the user reported power/network ready, resuming the already
authorized stationary investigation. Boot ID was
`46ef6005-cb47-4d3e-b84c-70c697216290`. The actual dashboard `robot-scope.service`
and control bridge ran release `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c` with
restart counts zero. The initial query used the wrong dashboard unit name
`robot-scope-dashboard.service`; its inactive result was corrected by checking
the actual `robot-scope.service` PID 995/cwd. HTTP was working throughout.

Initial observation was STOPPED/inactive/not busy; STOP=true, lease=false,
bridge Move=0. The agent started one STOP-held observation through its normal API:
session `59e167547ae34c25979f71939dcad64a`, which reached READY/guard HELD.
The first operational state had no selected pair. A later read showed pair
generation `740dcf3f09a145579791a2f286b5f326`, with the same map assets/calibration;
the agent did not write that selection.

### Investigation-path mistake and handling

The agent submitted one independent raw-global diagnostic job through
`/api/v1/observations/global-jobs`, job `60cc318f8757dddfd40d4f87`. This was an
incorrect concurrent investigation path: active FAST-LIO observation permits
global work owned by its navigation proposal, not arbitrary raw-global jobs.
The observation became INVALIDATED/OBSERVATION_OWNER_CHANGED_OR_UNKNOWN. The
recorded sample at monotonic 402.019092345 was unknown global_observation with
OWNER_LOCK_BUSY. Lock contention was observed, but the raw job would also conflict
with the allowed-owner policy independently of that contention. This is not
proof that the normal navigation-proposal path has the same defect.

The helper's READY assertion then stopped its copy watcher before it captured
the temporary input. That job nevertheless finished (365 points), and its output
was saved. **Those exact 365 input XYZ were not preserved**, and the later capture
must not be represented as that job's input. No raw-global retry was made and no
safety ownership check was removed.

The agent instead read existing ROS messages without publishing or changing
parameters. Observation was still active but invalidated, with inhibit HELD;
the data can support offline analysis, not a fresh valid-session proposal proof.
After capture, one exact-session stop was sent. Initial STOPPED/busy/RELEASED
readback was retained as incomplete cleanup; subsequent monitor cleanup was
verified as STOPPED/inactive/not busy/guard null. No duplicate stop was sent.

## Preserved current input and actual parameters

Read-only subscriptions preserved CDR messages for `/velodyne_points`,
`/cloud_registered`, `/cloud_registered_body`, and exact-stamp `/Odometry`.
Three registered-cloud/odometry pairs were saved with original bytes and decoded
XYZ. Raw LiDAR packets were not recorded; `/velodyne_points` is already converted
PointCloud2, and the registered clouds are processed/deskewed estimator output.

The comparison pair has exact sensor stamp **1794633990863503694**:

| Input | Population | SHA256 of float64 XYZ |
| --- | --- | --- |
| World registered cloud rebased to IMU using exact-stamp odometry | 361 | `28fa1a044faa672bdc9a770c69d8cd38abc0e75e208fe2b56fe1f2e865c726f7` |
| Same-stamp registered IMU/body cloud | 15,358 rows, 7,973 unique XYZ | `187c8b77d1a196cc85bbe32ff1f7e457e57f38dd1815a2bf8c2e6145217af502` |
| Full unchanged map | 32,387 | `5faf3f82b91150b2e4bd0b2ff8ab726ded8d0eba3c3ed056981d2b02a1f904dd` |

Other captured registered frames had 362/365 points. Converted LiDAR messages
had 16,000 points. Effective ROS GetParameters returned:
`publish.dense_publish_en=false`, `filter_size_surf=0.5`,
`filter_size_map=0.5`, `point_filter_num=1`, `preprocess.blind=0.5`, and
`mapping.extrinsic_est_en=true`. The process command used `config/fastlio_xt16.yaml`.
No parameters were set.

Installed `laserMapping.cpp` was read and its hash/excerpts preserved: world
publication selects `feats_down_body` when dense=false; body publication always
uses `feats_undistort` and applies the same current LiDAR-to-IMU extrinsic.
World publication additionally applies the current IMU rotation/translation.
Thus inverse exact-stamp odometry puts the sparse world cloud in the same IMU
coordinate convention as the dense body cloud, without applying extrinsics twice.
This checks the implementation/convention, not independent physical calibration.

Dense data contains 7,385 exact XYZ pairs and 588 singletons. Converted LiDAR
already contains many paired duplicates (about 8,070 unique XYZ/16,000 rows), so
the repetition is not introduced solely by the registered-cloud stage. Its
underlying return/packet cause is not established. All rows were retained for
scoring; point count is not a count of independent observations.

## Same frozen input comparison

Both global reruns used the exact pinned backend source, unchanged map, six
attempts, feature scales 0.15/0.30 m, seed 41, same worker implementation, and
single native threads. Original arrays were not edited. The worker wrote only
separate offline outputs; no API proposal or source freshness proof was generated.

| Route | Inlier RMSE | Full-cloud RMSE | Overlap at 0.75 m | Points within 0.10 m |
| --- | --- | --- | --- | --- |
| Sparse global, selected #1 | 0.233155 m | 0.662555 m | 85.87% | 31.30% |
| Dense global, selected #5 | 0.223072 m | 0.276038 m | 97.07% | 29.85% |
| Dense local sensitivity, robust refinement | 0.058414 m | 0.058414 m | 100% | 93.39% |

Global candidates retained unresolved ambiguity. The selected sparse and dense
IMU positions were respectively (-1.882, -0.309), yaw 7.85 degrees and
(-3.772, -0.507), yaw 6.62 degrees. Neither global pool found the region/direction
indicated by the user's last draft. Similar opposite-facing wall layouts are
consistent with a false correspondence basin, not proof of a featureless map.

The user confirmed the physical position/direction was unchanged from the
previous evening. Local sensitivity used that evening's last draft
(4.670812002, 3.429015474, -3.066965148 rad) and candidate #4's **old, unverified**
Z/roll/pitch. It is not an exact new prior-anchor admission, current measured
height/tilt, or automatically restored UI draft. The source-to-map frame
convention was checked; a historical seed assumption remains.

With that same seed, sparse local fitting remained poor (coarse RMSE 0.276004 m,
full 0.502752 m). Dense coarse/robust/plane paths converged near X=3.93, Y=4.63,
yaw=-174.5 degrees with full RMSE 0.0584–0.0587 m. These are three numerical paths
on the same data/seed, not independent physical tests. The chosen dense local
transform was independently rescored against the entire map; two neighboring
frozen dense frames, without refitting, yielded full RMSE 0.058535/0.058536 m.

The dense local position is **1.409103 m from the draft**. This exceeds the
0.25 m navigation prior-selection limit, and 0.058414 m exceeds the existing
seeded-local 0.05 m residual limit. This sensitivity experiment did not execute
the full live acceptance path. No accepted proposal or location is claimed.
Do not declare the draft wrong or the numerical position physically correct.
Prior placement, an alternative matching location, and map/sensor relation remain
possible explanations of that discrepancy.

Independent analysis reproduced all ten sparse and ten dense candidate residuals
within 5.6e-17 m. Sparse/dense covariance ratios 0.03240/0.03174 do not trigger
the 0.002 global degeneracy gate, but do not prove unique localization features.
Fixed-origin 0.15 m occupied voxels increased from 357 to 1,145; these are not
the exact Open3D feature-downsample counts. Density and initial candidate search
both affect this example. Density alone did not solve it; a flat/featureless map
has not been established as the sole cause.

## Artifacts, validation and final state

Preserved outside Git:

- `../nav2-current-cloud-20261114/`: device readbacks, current original CDR/XYZ,
  exact-stamp contexts, paired sparse/dense inputs and pinned worker outputs.
- Its `derived/` folder: local sensitivity, independent scoring, installed-source
  evidence, final readback and `paired-offline/current-cloud-comparison.png`.
- `../nav2-live-analysis-20261114/`: reproduction/analysis helpers and test logs.
- Remote: `/home/unitree/robot-scope-diagnostics/current-cloud-20261114/`.

The downloaded derived archive SHA256 matched
`6cf72c533d7d875197cc66b09f04c4fd3515cfde512f17759fa793a376b71bd2`.
No raw maps, clouds, images of map data, environment files or credentials are
committed. No executable production change or deployment was made.

JS event-safety/preparation tests: **29 passed**. Required full Windows unittest:
1,798 tests, **24 failures, 422 errors, 22 skips**, 32.878 s; not a pass. Unix API
availability remains among the platform failures; complete log retained.
Existing main `b410bc8` CI/I0 both passed and deployed `8234fcd` Linux CI had passed;
those remain separate software evidence, not hardware localization acceptance.

At **14:37:36 KST**, final readback: STOP=true, lease=false, bridge Move=0;
observation STOPPED, active=false, busy=false, session=null, guard=null;
seed_geometry=null and initialization_handoff=null. The historical owner_failure
sample remains recorded. Actual execution SHA is still `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`.

Agent requests this resumed turn: observation start 1, independent raw-global
diagnostic start 1, exact-session observation stop 1. Separate offline computations:
two frozen global reruns, one local-sensitivity batch for both populations, and
independent rescoring. Navigation proposal/confirmation, INITIAL POSE, operational
registration, Nav2, goals, STOP release and Move requests: **0**.

Next one task: independently verify the robot's map position against the dense
local candidate near (3.93, 4.63) using current physical landmarks and a newly
confirmed draft, before considering any production source/search change. Retain
existing ownership, freshness and admission checks.
