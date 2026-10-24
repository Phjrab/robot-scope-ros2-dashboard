# Final independent articulated replay review

## Scope: OPEN DIAGNOSTIC, different from the original cone layout

This report qualifies only the two explicitly frozen synthetic open-layout traces
below. It does not convert the original narrow-layout candidate into a success.
The original candidate's independent checks remain under `attempt_01/` and are
marked NOT_ADOPTED because its separate planner-rectangle clearance target failed.
The earlier open diagnostic before terminal deceleration remains under
`candidate07_pre_terminal_stop/`; it is not the final rendering source.

Final sources:

- `final_regressions/open_normal.json`:
  `528b1705fc10c3bb1fef92f87f5b2a8f5c86a6d1852d535de6902ce01f8cbb72`
- `final_regressions/open_baseline.json`:
  `bc54b20f098ca832f7be738b4d60db96d65ed85473974bbdffe8f75d78f0db21`
- `gait.py`:
  `ce266eeffa23238aa00553b28f3a933f0848111335adc4f9a23b339ae34a670b`

The two final scenes have identical cones, footprint, start, goal, seed, allowed
floor, arena revision and sensor heights (checked directly). They use the corrected
arena's left corridor only. Body poses are synthetic holonomic planar outputs;
articulated joints are offline IK visualization, not joint telemetry or a controller.

## Independent checks actually run

For each final source, 8 artifact tests and 6 common synthetic unit-fixture tests
pass. The shared synthetic tests are not 12 distinct cases. Artifact tests check
input hashes, exact source-pose interpolation, variable-yaw versus fixed-yaw
contract, independent FK, all visual mesh vertices above ground and inside the
planner footprint, joint limits/sampled velocity, and stance XY anchors. Synthetic
fixtures exercise arcs, simultaneous sideways/forward motion, pause/resume and
turn-in-place; they are not mission scenarios. Logs are
`open_normal_FINAL_unittest.log` and `open_baseline_FINAL_unittest.log`.

Independent projected-mesh hull sweep:

| Metric | Final open normal | Same-layout baseline |
|---|---:|---:|
| Interpolated poses, terminal included | 7,741 | 3,981 |
| Wall/cone crossings | 0 | 0 |
| Floor-edge violations | 0 | 0 |
| Planner-envelope violations | 0 | 0 |
| Joint-limit violations | 0 | 0 |
| Minimum visual hull clearance | 0.102134m | 0.116168m |
| Minimum visual mesh ground gap | 0.000972m | 0.000906m |
| Maximum interpolated stance XY error | 0.0151mm | 0.0191mm |

The sweep uses ten substeps per animation interval, roughly 150Hz, and hull-edge
samples no farther than 5mm apart. Clearance distances are evaluated at roughly
15Hz. Full source/joint/fence/gait hashes are recorded in the two `*_FINAL_audit.json`
files. These are bounded sampled geometric checks, not formal continuous proofs.

The visual hull clearance decreased; do not claim a clearance improvement. This
metric also differs from the conservative planner-rectangle clearance. The source
owner's rectangle values of approximately 4.530cm/5.360cm are separate evidence.

## Motion and terminal evidence

Recorded world-XY command finite differences have maximum acceleration
0.200m/s² for the new version and 1.069m/s² for the same-layout baseline.
These are command derivatives, not measured physical acceleration. The new
version's final recorded v/vx/vy/w values are zero. The legacy baseline's final
GOAL_REACHED record still has nonzero XY command; no zero was silently appended.
Therefore the baseline is not evidence of explicit terminal stopping. Details are
in `final_command_characterization.json`.

Source timestamp `t` labels the sample's beginning and `pose_t` its propagated
pose. New version final values are t=51.6s, pose_t=51.7s, metric duration=51.7s;
baseline t=26.5s, pose_t=26.6s, duration=26.6s. The replay does not alter these fields.

## Reproduction

Set paths to the immutable trace and corresponding generated joints. The
`EXPECTED_YAW_MODE` is `variable` for open_normal and `fixed` for open_baseline.

    CURVED_TRACE_FILE=/absolute/path/open_normal.json CURVED_JOINT_FILE=/absolute/path/open_normal_joints.json EXPECTED_YAW_MODE=variable python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/articulated-curved-20261024/review -v

    python3 experiments/competition_vm/arena_robot_sim/revisions/articulated-curved-20261024/review/audit_trace.py --trace /absolute/path/open_normal.json --joints /absolute/path/open_normal_joints.json --fences /absolute/path/virtual_fences.json --output /absolute/path/audit.json

Missing inputs are errors, not silent skips. There was no robot connection,
production change, remote publication, commit or package installation in this review.

## What this does not prove

No dynamics, force/contact solver, balance, self-collision, actuator torque,
real sensor/model replay, terrain gait, full-course competition mission or physical
robot behavior was validated. Display-only short fences must remain disclosed and
must not replace sensor/collision fence geometry. The changed diagnostic cone layout
cannot be used as a same-input improvement comparison against the original layout.
