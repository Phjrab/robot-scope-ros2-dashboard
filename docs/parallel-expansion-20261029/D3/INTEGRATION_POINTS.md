> ROUND1 historical reference. ROUND2 supersedes time/coverage/native status: see [ROUND2.md](ROUND2.md) and [ROUND2_RESULTS.md](ROUND2_RESULTS.md).

# D3 integration points — proposals only

No common files, services, UI, ROS adapter, controller, bridge or operational
parameters were changed. No main merge, PR, deployment or robot access.

## Pure call boundary

`robot_dashboard.collision_geometry_core.assess(geometry, state, obstacle_frame,
path_or_command, now_stamp_ns=..., now_clock_domain=..., padding=.03,
uncertainty_in_extent=True, coverage='SPARSE', support_surfaces=...)` returns the
C1 `CollisionAssessment` v0.1 dictionary. C1 owns the wire validator: validate
incoming objects there and validate output using `CollisionAssessment.from_dict`.
D3 performs only numerical/safety precondition checks, not a second C1 schema.
No module import starts processes, loads models or imports ROS.

`state` carries C1 observation metadata plus `pose` (4×4 row-major metric SE3),
`joints` (joint-name to rad/metres), decimal `joint_stamp_ns`,
`calibration_known`, `pose_uncertainty_m`, `joint_uncertainty_m`.
The latter two are positional bounds in metres, not angular covariance. They
must conservatively include joint/FK and calibration effects. Null is UNKNOWN.
`now_stamp_ns` MUST be mapped into the named source clock; unrelated host clocks
must never be subtracted. Gate: age 0–250 ms; pose-to-obstacle AND pose-to-joint
skew <=50 ms. A fresh receipt cannot make an old source sample fresh.

`path_or_command`: null for current pose; or `{ref, poses:[{time_s, pose}]}` starting
at current root pose and time zero; or `{ref, command:{linear_x_mps,
angular_z_radps,horizon_s}}`. Constant twist is a hypothetical prediction, NOT
a controller/plant/braking model. C4 must provide the actual stamped local
controller command/trajectory, not a global `/plan` masquerading as it. Supply
intermediate waypoints for rotations >pi. C3 must display these assumptions.

## C1/C3 consumers

- `geometry_hash` covers actual runtime links/joints/origins/mounts/gait margin,
  as well as source hash and provenance; changing model data changes identity.
- `unpadded_envelope.min_clearance`: signed conservative primitive separation.
- `padded_envelope`: clearance after ONE robot padding, pose/joint uncertainty
  and declared gait margin. D2 extent already includes its measurement bound;
  `uncertainty_in_extent=True` avoids inflating it again.
- `min_clearance` is the sampled padded value; the explicitly named continuous
  lower bound additionally subtracts maximum point travel per sample and command
  arc approximation bound. Box SAT is a lower bound, NOT exact Euclidean distance
  or penetration depth. Cylinder-to-capsule conversion is conservative.
- `modeled_ttc` is first conservative sampled risk time under held joints and
  held obstacles. It is not measured impact time, braking distance or contact.
- `MODEL_OVERLAP`, `PREDICTED_COLLISION`, `CONTACT_UNCONFIRMED` recommendation are
  not `CONTACT_CONFIRMED`. Real contact requires separate real evidence.
- `CLEAR` is possible only for explicitly complete SYNTHETIC fixture geometry
  with no declared unmodeled mounts. Sparse/replay clouds without risk remain
  UNKNOWN, and positive distances are not observed-free space. A measured risk
  still takes STOP_REQUIRED precedence over sparse coverage.

## C4 future port and simulated command boundary

The sole future publisher/ROS port remains C4's responsibility. Proposed flow:
C4 stamped `PointCloud2` -> D2 `process_lidar`/`Tracker.step()['obstacle_frame']`
-> D3 `assess` -> C1 storage/C3 display and existing final arbitration input.
D3 never publishes `/cmd_vel`, contacts a robot, clears a costmap, or changes stop
policy. Review namespace is `/robot_scope_review_x`, domain 194, localhost only,
network-none container, no physical devices/host network or bridge/SDK.

Fixture `Observer.step` is a mock final command gate: non-CLEAR latches zero and
permits only bounded observation. Contact, explicit cancel and infrastructure
failure terminate separately; no automatic recovery restart or goal resend.
This mock boundary does NOT claim native command/costmap ingestion.

## Exact dependencies checked, not integrated

- C1 `2402c02c6f91ba54064894b21735e01b98610acd`: real validator called read-only.
- D2 `c0d266e290a2d29c173d3b83520f8c96efea9447`: raw noisy/occluded sensor
  fixture -> real D2 core/tracker -> D3 geometry -> real C1 validator.
- Existing `experiments/competition_nav2` and D0 fixtures were read-only references.
  Their historical narrow-route/yaw failures and controller settings are not
  changed or superseded by these tests. No Omni overlay is adopted.

## Geometry qualification still required

Pinned official URDF collisions are not measured full robot geometry. Unknown:
actual camera/brackets, external LiDAR mount, Jetson enclosure/cables, loaded
accessories, real walking envelope, gait sweep, braking distance, pose/joint
uncertainty and terrain support tolerances. Explicit mounts can be supplied as
root-frame `Primitive` objects. Mesh collision backend and self-collision are not
implemented/tested; unsupported URDF meshes/mimic joints fail closed. Do not use
visual `go2-official-lite.json` or viewer adaptive scale for safety.
