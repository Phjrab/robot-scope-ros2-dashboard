> Updated by [ROUND2.md](ROUND2.md): actual C4 shim and C1 default-service budget are now exercised. Original integration notes below remain historical where superseded.

# D2 runtime-independent integration points

No shared product code changed. C1 wire validator is pinned read-only at
`2402c02c6f91ba54064894b21735e01b98610acd`; schema_version is `0.1` (not the
proposal prose's message-type string). C1 is the sole wire-schema owner.

## Calls and responsibility

- `process_lidar(points_Nx3, meta, ground=None, self_boxes=(), reference=None, limits=Limits())`
  returns local geometry, diagnostics and drop counts. C4 must decode original
  PointCloud2 using existing `robot_dashboard/ros/pointcloud.py` and preserve raw
  field layout, original source stamp/epoch, host receipt ID/time. Do **not** feed
  viewport-decimated points as if full raw observations. Source array is unchanged.
- Ground is a unit normal, plane offset d in metres, unit gravity_up and bounded
  uncertainty. It is an explicit trusted local support-plane input (not inferred
  gravity or a globally flat floor). Optional `ground.meta` must match exact time.
  Without ground, points remain occupied and `GROUND_UNKNOWN` is reported. The
  baseline does not automatically fit multiple ground surfaces. Suppression band
  is 25 mm minus uncertainty; 80 mm low cone remains. Highly uncertain planes do
  not erase returns. Ground/static-plane validity is the caller's responsibility.
- Self boxes are **current stamped** min/max AABBs in the same local frame, from
  current body/joint geometry. Unknown/stale pose means no suppression. C4 owns FK
  sourcing; D3 owns collision geometry, not D2. AABBs are explicitly approximate;
  future oriented body-link masks require an integration review.
- `lift_detections(detections, depth, meta, calibration=..., model_manifest=...)`:
  detector records retain native bbox, original `[height,width]`, class_id/name,
  confidence. Manifest includes hash, class_names and preprocess. The optional `detector_adapter` hashes a trusted local artifact in bounded
  chunks and verifies class/native-shape declarations without deserialization.
  This is an **input adapter**, no model is loaded or downloaded. Existing traffic class 2
  is not reinterpreted as cone. Actual cone weights/data are missing.
- Calibration includes `depth_intrinsics`, `color_intrinsics` (fx/fy/ppx/ppy,
  width/height/model/coeffs), depth_scale_m, `T_color_depth`, `T_local_depth`, id,
  uncertainty_m, verified, clock_correspondence_verified, and capture-time meta.
  Transform matrices are 4x4 row-major, column-vector SE3, metres. Existing
  `relocalization.experimental_se3.validate_transform` is reused. RealSense
  metadata's column-major extrinsics must be explicitly converted by C4.
  No `aligned=true` shortcut exists: every depth pixel is deprojected and
  reprojected through actual extrinsics to color, then transformed at capture time.
  None/Brown-Conrady supported; other distortion models are rejected. Optical Z
  is not Euclidean range. Different cameras need actual calibration, never equal
  pixel coordinates. Rigid-but-incorrect real calibration cannot be proven from
  arrays; caller must verify it. No motion compensation is claimed.
- Foreground selection requires coherent near-depth support in eroded bbox and
  nearer depth than its surrounding ring. Invalid, flat-background, or ambiguous
  depth stays image-only. This intentionally has false negatives for objects
  without background contrast, tiny/edge objects, or heavy occlusion. Never use
  image-only labels as exact 3D geometry. LiDAR remains independent.
- `associate(lidar, rgbd)` performs unique bidirectional geometry/time/frame gates,
  bounds size ratio and centre separation, and unions observed volumes. Ambiguity
  retains separate observations; no semantic-name shortcut. Different clocks
  without a verified common-domain mapping cannot fuse. RGB-D-only geometry in a
  matching frame remains valid with explicit support; mismatched frames are
  diagnostic-only and never silently transformed with latest TF.
- `Tracker.step(observation, clearing_rays=())` returns `obstacle_frame`,
  **separate** `clearing_evidence`, `expiry_policy`. Continuous local frame only;
  no map transform applied. Source epoch, map generation/revision, local frame or
  clock change resets IDs; retired generations are rejected. Duplicate/reordered
  stamps/sequences are rejected. Ambiguous crossings get new IDs, not asserted
  identity/velocity. It is an association baseline, not a velocity predictor.
- `source_age_ns` is optional caller-verified source-to-host mapped age. Unknown
  age stays UNKNOWN; monotonic timestamps from different hosts are never
  subtracted. Known age >150 ms is rejected by Tracker. C4 must gate actual
  runtime use on freshness; null age is **not** clearance permission.
- Clearing rays require source metadata, origin and observed-free endpoint before
  an occupied hit. C4 must obtain genuine free-ray evidence and retain calibration
  provenance. D2 filters by frame/clock/epoch/age/range; cannot independently prove
  sensor truth. Occlusion, missed detections and track expiry never create rays.
  Display TTL is 1 s; costmap lifetime is unspecified (`null`) for C4 policy. No
  clearing is inferred from point absence, and no permanent occupancy is imposed.

## C1 / C3 / C4 / D3

C1: validate `obstacle_frame` using its existing `ObstacleFrame.from_dict` before
publication. Core calls belong in a bounded worker, not HTTP loop. Enforce C1's
128 KiB wire limit; heavy provenance/64-object frames can exceed it and require a
C1-owned compact provenance-reference policy, not silent truncation or new schema.
Do not set observation_only false or Nav2/ingestion/controller flags true here.

C3: consume center/extent/orientation, sensor_support, uncertainty, state, novelty,
source time/age/epoch, unmatched reasons and dropped counts through C1 ScenePacket.
No renderer or service is implemented here. All extents are observed conservative
AABBs, **not** complete hidden-object reconstruction. Unknown coverage remains
unknown even if no obstacle object is emitted.

C4: future integration beside original source capture / depth metadata handling,
not camera ownership or traffic mission policy. No changes to
`navigation_runtime.py`, existing scan height policy, original topics, ROS ports,
or `/cmd_vel`. Source callback's existing raw capture identity should remain the
origin of metadata. A model worker must not block geometry or emergency pathways.

D3: use `Tracker.step(...)["obstacle_frame"]` as observations, not scene oracle.
Generate independent true geometry and sample occlusion/noise. Reject stale,
unknown frame/age, dropped-budget and PARTIAL coverage as proof of a clear path.
Consume clearing evidence independently; never interpret ID expiration as FREE.

## Bounds / limitations

30,000 LiDAR points, 64 objects/self boxes, 307,200 depth pixels, 64 detections,
64 active tracks and 64 retired generations. No queues. Oversized point/depth
input rejects before heavy geometry; component overflow is counted, never
represented as complete coverage. Voxel connectivity can split sparse surfaces or
join touching objects. Configured uncertainty is a bound, not learned covariance.
After 64 retired generations recreate the caller-owned tracker explicitly. No
object is a certified safety observation; no robot/native Nav2 claims are made.

Next one action: C4 supplies one timestamped, calibrated recorded sensor packet
through these functions in an isolated fixture; keep all runtime publishing gated.
