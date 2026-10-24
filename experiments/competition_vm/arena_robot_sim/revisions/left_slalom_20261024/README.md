# Left-corridor multi-cone slalom (2026-10-24)

**SYNTHETIC / HOLONOMIC PLANAR; no gait dynamics, native Nav2, SLAM or hardware qualification.**

This is the user's requested leftmost slalom experiment, not a replacement for D0's fixed-baseline regression. It uses `corridor-parallel-20261024-v1` as one coherent visual/semantic/fence bundle. The left corridor itself was unchanged by that correction. Original artifacts remain untouched.

## Layout and footprint

- Shared start `(0.50, 0.95, pi/2)`; goal `(0.50, 5.05)` in arena-design metres.
- Five non-overlapping cones, centres `(0.18,1.55), (0.18,1.83), (0.82,3.00), (0.82,3.28), (0.18,4.45)`.
- Every cone keeps a 0.26 m square base, 0.12 m radius, 0.32 m total height, 0.04 m base height. No scaling to obtain a pass.
- A low wall-side cone leaves a 0.69 m transverse gap. The conservative animated robot rectangle is 0.81 m long by **0.56 m wide**. This envelope was enlarged after preliminary FK showed limbs outside the earlier 0.42/0.49 m rectangles.
- Layout is a documented manually selected deterministic fixture; `seed=20261024` is its reproducibility identifier, not a claim that a random generator selected these coordinates.
- The 1 m middle-corridor width remains a provisional design interpretation, not measured registration.

## Navigation and evidence

Existing `avoidance/core.py` A* runs unchanged on observed virtual-LiDAR occupancy. Because body yaw is fixed at pi/2, configuration-space expansion uses the full axis-aligned rectangle, conservatively 43 by 31 raster cells at 0.02 m resolution, followed by A*'s existing cell-clearance margin. This is not a smaller circular replacement for the body. A full rectangular swept check gates every command. The plant permits lateral velocity, capped total speed 0.16 m/s, and does not rotate. This is an explicit holonomic quadruped kinematic assumption, not proof that the robot can execute these motions.

Four horizontal first-hit synthetic LiDAR rings are reused from the original arena simulator. Pose is SIM_GT. Controller receives only static map plus observed scans; hidden cone truth is used only for ray generation and evaluation. No live ROS, robot connection, GPU model or user weights.

Independent saved-trace audit checks all footprint vertices against left floor and exact cone polygons at eleven samples per 0.1 s transition (<=1.6 mm translational spacing). Full corrected floor/fence data are preserved and renderer uses the same revision. All current trajectories stay inside the convex middle left corridor, away from any terrain. The animation worker separately checks actual articulated meshes against this envelope; geometric trace PASS alone does not certify animated limbs.

## Results and reproduction

`results/audit.json`, `results/reproducibility.json` and `results/VALIDATION.json` contain actual results. Empty, three-cone and five-cone runs reach the goal; blocked-five stays SAFE_WAIT. Two runs match exactly after excluding wall-clock execution duration. Straight-reference collision counts demonstrate that the five-cone scene actually requires lateral weaving.

Commands from this directory (NumPy/SciPy installed in the VM):

    python3 simulate_slalom.py
    python3 audit.py
    python3 test_slalom.py -v
    python3 reproduce.py

Tests operate on generated traces; regenerate them first if raw traces are not distributed. No test silently skips absent traces. Raw traces, scene triangles and failed attempts are local-only unless separately delivered. No commit or push was performed for this new experiment.

## Preserved development failures

- attempt_01_point_candidate: point-inflated A* rounded corners before the long body cleared a cone. Swept guard correctly held; not counted as successful navigation.
- attempt_02_tight_spacing: original five-cone spacing had no full-envelope configuration-space route. SAFE_WAIT, no collision.
- attempt_03_base_overlap_rejected: draft pair spacing overlapped cone bases by 1 cm; rejected as invalid layout despite planar success.
- attempt_04_small_limb_envelope: preliminary narrower envelope was superseded by articulated FK evidence.
- attempt_05_blocked_base_overlap_rejected: invalid overlapping blocked row, replaced with three separated blockers plus two downstream cones.
- attempt_06_limb_envelope_exceeded: 0.49 m footprint passed chassis geometry, but animated limbs exceeded it; retained, not final. Final envelope expanded to 0.56 m and cones repositioned within the user's placement authorization, not shrunk.

No full-lap, terrain climbing, parking posture, physical stopping, balance, ground reaction force or competition readiness claim is made. A few centimetres of synthetic clearance are not safe real-robot tolerances.
