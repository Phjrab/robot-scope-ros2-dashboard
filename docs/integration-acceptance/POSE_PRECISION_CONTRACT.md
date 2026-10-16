# Independent pose accuracy and Go2 body extrinsics

Current real result: **BLOCKED — no independent truth or measured camera-to-Go2
body extrinsic**. The user confirmed that no additional measurement is available.
Preserved Oct13/14 CameraInfo and five camera static transforms provide a camera
chain reference. They do not locate the camera relative to the Go2 body. The
latest sampled camera SLAM estimates and operator stationary declaration also do
not supply independent truth. FAST-LIO, map alignment, initialpose, odometry, a
second rendering of the same SLAM pose and synthetic transforms are not truth.

The offline module and CLI below prepare numerical comparison of future supplied
measurements. A computed result is **software comparison of declared inputs**;
it does not certify metrology, physical independence or a calibrated operational
body pose. No operational TF, initialpose, motion goal, camera, service or ROS
operation is added. Current driving prohibition remains in force.

## What can be prepared while the robot stays stationary

Keep the mount unchanged and document its identity, rigid attachment, photographs
with visible axes, the camera serial and the body frame definition. `base_link`
must identify a documented origin and axes on the rigid body, rather than a point
chosen on a plastic cover. A photo and ruler are useful planning records; they
do not establish the optical center or a precision 6DoF calibration.

Prepare an external instrument/rigid target and its independent calibration:
for example, motion capture, a laser tracker with an orientation-capable rigid
target, or a calibrated external camera observing a surveyed rigid body target.
A single measured point constrains position but does not independently measure
orientation. Ordinary tape measurements alone do not qualify a camera optical
origin or a precision six-axis body transform. Any supplier/CAD/mount dimensions
need their actual origin definitions, tolerances and applicability to this mount.

| Measurement record | Required values and evidence |
| --- | --- |
| Body/mount definition | Body origin, x/y/z axes, mount ID, rigid target-to-body transform, dimensions and their uncertainty, method/instrument and date |
| Camera chain | Current left/right K/P/R/D, dimensions, binning/ROI, frame IDs and complete camera static chain; serial/config/source/runtime identities; compare with preserved reference |
| Camera-to-body extrinsic | `T_body_camera` for the exact camera frame used by the SLAM pose; independently measured translation and rotation, uncertainty bounds, method and original calibration artifacts |
| Independent truth | Timestamped `T_world_body` from the external system, reference/world definition, target-to-body calibration and per-axis coverage; raw/export bytes and hashes |
| Map/world relation | Fixed measured `T_world_map`, separately established before the evaluation rows, with uncertainty and calibration evidence; no fit to the evaluated trajectory |
| Timing | Both clock domains, independently measured offset direction/value, bound covering offset/drift across the run, predeclared pair-skew budget and timing evidence |
| Stationary series | Repeated simultaneous estimate/truth poses at the unchanged placement, both acquisition IDs/epochs, all source stamps and missing samples; do not replace the external truth with a constant inferred from SLAM |

For each transform record fill parent frame, child frame, translation in metres,
quaternion **[x,y,z,w]**, measurement method/date, instrument ID, original artifact
path/SHA256 and translation/angular uncertainty bounds in metres/radians. Unknown
uncertainty remains unknown; do not enter zero to satisfy the validator. Keep raw
source values and exact source/runtime/config identities. The example input is
intentionally incomplete and returns BLOCKED until actual data is supplied.

An externally tracked stationary repeated series can measure bias/noise at that
placement under the supplied uncertainty. It does not establish trajectory
accuracy, scale, turns, long-term drift or robustness. A future moving evaluation
needs a separately approved supervised trajectory, fixed external tracking of
the body, measured time synchronization, and a preregistered route/duration/error
criterion. Suggested future coverage includes translations and rotations with
independent observations, return to surveyed positions and held-out sequences;
this document does not authorize moving the robot or camera to obtain them.

## SE3 direction, axes and frame contract

Use right-handed column vectors: `p_A = T_A_B * p_B`. `T_A_B` describes the pose
of frame B in A; the translation is the B origin expressed in A. Translation is
metres, angles radians and rotations proper SE3. Matrices are 4×4 with last row
`[0,0,0,1]`; reflections, scale, shear and nonfinite values are rejected.

For this SLAM output, camera C is **vslam_lab_camera_link**, map M is
vslam_lab_map, body B is the documented Go2 base_link and W is an independent
survey_world. ROS link/body axes are x forward, y left, z up. Optical axes are
x right, y down, z forward. camera_link and optical frames are different origins
and bases. If an optical pose is supplied, declare the optical axes and use the
measured transform to that exact named optical frame; the tool does not infer a
link/optical rotation or silently reuse another frame's extrinsic. The roughly
0.0499m stereo baseline is a camera-to-camera separation, **not a body offset**.

Given measured `T_B_C` and fixed `T_W_M`, the body estimate is:

```
T_W_B_est = T_W_M * T_M_C_est * inverse(T_B_C)
E = inverse(T_W_B_truth) * T_W_B_est
position_error_m = norm(E.translation)
rotation_error_rad = acos(clamp((trace(E.rotation)-1)/2, -1, 1))
```

Multiplication order matters. Do not rename a camera pose as body pose, apply an
extrinsic twice or put `T_camera_body` into `T_body_camera`. The evaluator checks
the parent/child labels; it cannot detect a physically reversed measurement that
has been mislabeled. It never estimates an extrinsic, trajectory alignment, clock
offset or scale from evaluation samples.

## Input and offline execution

Copy [pose_precision_input.example.json](pose_precision_input.example.json) into
a private measurement directory and fill only values supported by measurement.
Provide six relative evidence paths and SHA256s for estimate, truth, extrinsic,
world alignment, timing and current camera calibration. The CLI verifies actual
bytes beneath the input directory (maximum32MiB each). The estimate/truth files
must each contain their complete JSON series object, semantically identical to
the corresponding manifest section; sample edits require a new matching source
artifact hash. Other references remain opaque measurement evidence requiring
human review. Large bags can stay in the
private archive with a bounded signed/recorded export receipt and pose extracts.
These hashes bind files; they do not prove their measurement method or independence.
The manifest itself is also bounded to32MiB and each series to100000 rows.

Each series declares its acquisition ID, parent/child frames and one epoch.
Every sample has `stamp_ns` as an exact decimal **string**, the same `epoch`, and
a `pose` object containing parent/child frames plus either `translation_m` and
`quaternion_xyzw`, or `T_parent_child`. Example shape, with measured values:

```json
{"stamp_ns":"1792149540723526656","epoch":"actual-epoch",
 "pose":{"parent_frame":"vslam_lab_map","child_frame":"vslam_lab_camera_link",
         "translation_m":[0.1,0.2,0.3],"quaternion_xyzw":[0,0,0,1]}}
```

Those numbers demonstrate syntax only. Do not use them as a robot measurement.
Input quaternions must have unit norm within1e-6; the math applies a numeric unit
correction within that tolerance and preserves source bytes. No unchecked
quaternion normalization or coordinate relabeling occurs.

The explicit time relation is `estimate_ns = truth_ns + offset_ns`. A positive
offset adds to the truth clock before pairing. The constant offset and its bound
must cover this run's drift; unsupported time synchronization blocks evaluation.
Matching is mutual unique nearest timestamps, one-to-one, without interpolation,
under `abs(timestamp_difference) + offset_uncertainty_ns <= max_pair_skew_ns`.
Equidistant pairs and unmatched rows are excluded and counted. No matching budget
is inferred from successful pairs or widened automatically. Zero skew is not
proof that two unsynchronized clocks refer to the same physical instant.

```sh
.venv/bin/python scripts/evaluate_pose_precision.py /private/path/input.json \
  --output /private/path/new-result.json
```

The output is a new0600 file; existing evidence is never overwritten. Missing,
unqualified or inconsistent inputs produce BLOCKED with null error metrics and
exit2. A computed result retains input/module/CLI hashes, declared provenance,
uncertainties, matched coverage and each matched pair. It reports position and
SO3 angular RMSE/p50/p95/max. It does not subtract uncertainty, propagate a
covariance, assert RPE or promote sparse coverage to whole-trajectory accuracy.
`accuracy_acceptance`, `independent_truth_verified_by_tool` and
`body_extrinsic_qualified_by_tool` remain false even for recorded-real inputs:
external provenance is self-report requiring independent human evidence review.

Focused regressions use synthetic transforms and fake evidence only, including
noncommuting transform order, known errors, quaternion sign/180° cases, invalid
SE3/frame/epoch/stamps, timing uncertainty, ambiguous pairing, source/reference
hash checks, private output and no-overwrite behavior. They establish software
arithmetic and rejection behavior, not a real accuracy or extrinsic result.
