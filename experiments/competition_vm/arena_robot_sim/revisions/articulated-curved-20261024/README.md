# Gradual-yaw articulated replay

This is a new revision. The previous fixed-yaw demonstration and its source outputs are preserved in `../articulated-20261024`.

## Scope

The source planner/follower produces stored planar poses. This revision visualizes those poses using offline 12-joint IK, fixed world stance anchors, swing targets based on future stored poses, and official-derived Go2 link meshes. It does not smooth, replace, or fabricate the recorded chassis path. Rendering is kinematic, not a physical locomotion simulation. It cannot qualify balance, contact forces, gait policy, actuator response, terrain climbing, or real hardware operation.

A rotating body changes its world collision footprint. Validation must inspect the full rotated planner envelope and the animated mesh, not only its centerline or the earlier fixed-yaw footprint. Candidate failures remain failures; gait is not reduced simply to fit a successful path.

## Primary references

- Official Go2 URDF and joint limits: https://github.com/unitreerobotics/unitree_ros/blob/f3772ce54c56ef2d34c6aee8100bc768896c7d19/robots/go2_description/urdf/go2_description.urdf
- Official Unitree MuJoCo project, reviewed as a possible future dynamics approach but not installed or executed: https://github.com/unitreerobotics/unitree_mujoco
- Asset license: `../../rendering/UNITREE_BSD_LICENSE.txt` (BSD-3-Clause). `official_urdf_check.json` records comparison with all 12 existing asset joint limits.

Gait timing and swing construction are visualization code, not an official Unitree controller.

## Validation categories

1. `test_gait.py`: original behavior regression.
2. `review/test_synthetic_curves.py`: synthetic fixtures for turning, combined lateral/forward motion, and stopped intervals. These fixtures are not new planner results.
3. Actual saved trace joint checks and independent mesh/hull audits must pass before a scenario is marked qualified for this visualization.
4. Render provenance validation checks source hashes, stored states, frame counts and timestamps.

Virtual fences are shortened in the display only to show feet; sensing and collision geometry remain unchanged. All video labels retain the synthetic-planar/kinematic limitation.

## Candidate comparison

Same five cones, same ±0.405 m longitudinal / ±0.280 m lateral planner half-extents. New heading spans 87.708°–92.292° (only ±2.292°); this is still combined holonomic lateral/forward motion, not a nonholonomic forward-only maneuver. Stored-pose peak yaw rate is 0.0613 rad/s, peak planar speed 0.1104 m/s, and peak finite-difference planar acceleration 0.2000 m/s². Prior stored-pose peak speed was 0.1600 m/s and peak acceleration 0.8242 m/s². These are simulated pose differences, not measured physical performance.

Source metrics include one additional final integration step compared with the stored frame span. Before: source metrics 29.7 s / 4.752 m; stored frames 29.6 s / 4.736 m. After: source metrics 52.1 s / 4.52854 m; stored frames 52.0 s / 4.52654 m. Videos reproduce only actual saved frames, without manufacturing a missing final step.

The first candidate (source SHA256 `40880f322c057c6f4bda6e972d8f1a0af031af134ceaaf4b1294a46c786236b3`) was NOT ADOPTED. Its animated mesh passes the sampled geometric audit, but the conservative planner rectangle clearance drops to approximately 1.63 cm. A visually collision-free mesh is not a substitute for retaining the full planning safety margin. The candidate is preserved under `attempts/candidate_01`; the initial comparison above is diagnostic, not the final selected result.

## Final selected diagnostic (not the original tight layout)

`open_normal.json` SHA256 `528b1705fc10c3bb1fef92f87f5b2a8f5c86a6d1852d535de6902ce01f8cbb72` is frozen for rendering. Its SAME open-layout baseline is `open_baseline.json` SHA256 `bc54b20f098ca832f7be738b4d60db96d65ed85473974bbdffe8f75d78f0db21`. Both are in the source owner's `curved_slalom_20261024/results/final_regressions/`.

The five cone positions differ from the original tight-layout experiment. The baseline/new comparison checks identical cone geometry and identical planner footprint before drawing any comparison. A successful open diagnostic does NOT mean that the original tight-layout curved planner was adopted.

Source metrics: baseline 26.6 s / 4.256 m, new 51.7 s / 4.24778 m. Conservative planner clearances are respectively 5.360 cm and 4.530 cm, both above 3 cm; clearance did NOT improve. Peak consecutive recorded-command acceleration falls from 1.069 to 0.20 m/s² (baseline 1.60 m/s² is a separate startup estimate assuming a prior zero command); speed and duration differ. The NEW trace ends with explicit zero velocity/yaw commands. The baseline ends at GOAL_REACHED with nonzero command, so it is not certified stopped. In the synchronized 1× comparison, its last frame is held and explicitly labeled after its trace ends. No invented braking trajectory or time normalization is used.

Reproduction: generate both joints using `gait.py --trace-path ... --case open_normal` / `open_baseline`; render 775 / 399 frames respectively with `render.py`; then `bash encode_comparison.sh /absolute/path/to/final_regressions`. `verify_render.py` verifies source hashes, states and frame counts. Scene inputs are the corrected `corridor-parallel-20261024/arena.blend`. Full independent audit results are under `review/`.
