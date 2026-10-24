# Actual arena + Go2 + virtual LiDAR closed-loop experiment

## Evidence level
VM-only planar kinematic differential chassis simulation. This is **not** validated walking/contact dynamics, SLAM, VSLAM, Nav2, real-robot operation, or proof of the complete competition route. The actual repository Go2 simplified articulated mesh is used for rendering and standing-body bounds. Default joints stay fixed: this deliberately does not fake a physically validated gait.

The immutable rulebook-20261015 arena geometry is used at its original metre/Z-up scale. This geometry itself has documented provisional dimensions and unresolved connections. All ramp, stair, and central platform cells are blocked for planar navigation. No wall is widened or removed. Visible boundary walls are zero-thickness virtual fences, not newly certified physical walls.

## Model and clearance
Source: robot_dashboard/static/assets/go2/go2-official-lite.json; Unitree BSD-3-Clause provenance is embedded there. Default standing FK mesh bounds are x[-0.35777714,0.33068], y[-0.16138,0.16142], z[-0.33407456,0.08883] m. Grounding root is 0.33407456 m. See rendering/standing_bounds.json. Collision envelope is symmetric outward-rounded ±0.358 x ±0.162 m, NOT the earlier arbitrary 0.8 x0.4 m proxy. This is a mesh bounding box, not measured live foot/body clearance. A* uses its circumscribed radius plus grid diagonal margin. Evaluation uses the complete oriented rectangular footprint against conservative occupied grid cells. Minimum reported clearance is center EDT minus circumscribed radius, a discretized proxy that can overestimate clearance, not certified continuous physical clearance.

## Scene and sensor
Start (5.99,1.65,pi/2), same goal (5.99,4.35), actual right straight and adjacent parking extension. Allowing this local detour (the center stays within the right straight but rotated footprint reaches x6.57782, protruding 7.8cm into the parking bay) is a provisional experiment, NOT approval to shortcut the required competition route. Empty case, off-center cone case, fully blocked cone row share this start/goal. The 32-sided cones are 0.32 m tall, base radius0.12 m, sitting on 0.26 m square x0.04 m high bases. Sensor and rendering use these same surfaces. Exact scene triangle arrays are saved per case.

Four idealized horizontal LiDAR rings are mounted at z=.025/.10/.20/.35 m,360 azimuth rays each,8m range,5Hz; this is a synthetic stacked-height sensor, NOT a model of the actual Go2 LiDAR scan pattern. Two-sided Moller-Trumbore first-hit intersection handles occlusion on cone triangles/base and boundary surfaces. Min horizontal range across rings is the projected obstacle observation. No ground returns are generated because all rays are horizontal; the support plane is known and ground filtering is not tested. Saved world-frame point samples have ring index and scan_pose/scan_t. Robot pose is simulation ground truth, explicitly NOT SLAM.

Scene truth is passed only to raycasting and the independent contact evaluator. The planner receives the known static arena mask plus Occupancy-updated measured ranges; it never receives cone centers or sizes. Known-free static prior is allowed. Control runs10Hz, replan2Hz, A* with rotate-follow, v<=.18m/s,w<=.6rad/s. Collision sweep horizon.5s, observed occupancy TTL2s→UNKNOWN. Missing data are not fabricated as free space.

## Reproduce
From repository root:

    python3 experiments/competition_vm/arena_robot_sim/simulate.py
    python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim -p test_simulate.py -v

Dependencies: existing NumPy/SciPy; immutable sibling avoidance/core.py and arena geometry.py. Rendering reproduction is documented in rendering/. No ROS, robot, network control, live device or deployment is needed.

results/{empty,cone_detour,blocked}.json include scenes, actual commanded trace, scan observations and metrics. Each terminal frame has terminal_outcome. t denotes control tick time, pose_t=t+0.1 denotes the resulting pose time; scan_t and scan_pose identify measurement time separately. min_sampled_planar_envelope_edge_clearance_m is exact 2D segment distance at saved 5Hz poses on these nonintersecting paths, not a dynamic/continuous physical certificate. Mesh JSONs make scene construction inspectable; static_grid.npy is regenerated locally by simulate.py and deliberately excluded from Git under repository policy. Run all three cases together to regenerate the complete metrics.json.

## Development failures, not hidden successes
- Initial oversized ±.40/.20 proxy: empty succeeded14.3s; centered cone at(5.99,3) had no safe circumscribed path and timed out89.9s without movement/contact. Barrier initially at y2.0 overlapped starting footprint and failed CONTACT at t0. These were configuration/debugging failures, not real-world collisions.
- Actual mesh bounds substituted, blocked row moved to y2.4 before final runs; start remained unchanged.
- Cone at x5.75 had an initial feasible grid path but updated observation/short-carrot tracking produced a safe no-path wait,0contacts, timeout89.9s (0.895m with .20m carrot,0.651m with .08m carrot).
- Final cone at x5.70 permits a measurable conservative detour; final .08m carrot. No claim is made that the centered cone is passable. Placing the obstacle off-center is disclosed, not changing arena dimensions or shrinking the robot.
- An intermediate metadata edit had a syntax typo; repaired before final run.

No git commit/push, physical robot action, service restart or deployment performed by this experiment.
