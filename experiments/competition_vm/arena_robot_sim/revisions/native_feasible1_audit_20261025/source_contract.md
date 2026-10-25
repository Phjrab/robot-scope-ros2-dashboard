# feasible1 native source and recording contract

## Pins and event

- Native source: `5eacacf42378ad91319a5de323df7844f34ea33b`; C3 report: `32914885d84b9bf98e799492366aeab0f908f547`. Their `experiments/competition_nav2` trees have no diff.
- Native run [40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349), artifact 12588085458; original ZIP SHA-256 `c2d20937c7e2d7d2d20527994e8eaa116d2fab1d556638562ce688972317d8cb` (see machine-readable record for authoritative full digest).
- First RPP exception: feasible1 `native.log` line 144, host wall epoch 1792904808.540106401. New path handed to controller at 1792904808.539209630.
- Wait recovery follows. Spin starts 1792904809.598600397 and reports collision 1792904810.449059220. Spin is later, not the first failure.

## Clock and available samples

The log timestamps are host wall time, not `/clock`. `raw_commands.jsonl` records DDS wall timestamps, callback monotonic time, source age, and callback simulation time. The nearest post-error zero command bridges wall and monotonic approximately; subtracting its callback source age improves the alignment over treating publication time as receipt time. This is not an atomic clock calibration.

The error falls between trace sim 6.40 and 6.45 seconds. Mission elapsed is sim minus 1.55 seconds, so the pre-error trace elapsed is 4.85 seconds. The pre-error published plant pose is (0.5167972571840633, 1.7462801514863986, 1.5282629698786039 rad). It is not a recording of RPP's internal TF lookup result.

The most recent recorded global path is source sim 6.349999999; global costmap is source sim 6.149999999, approximately 0.25 simulated seconds before the error. The prior nonzero published command is v=0.18 m/s, w=-0.01558637696076498 rad/s. The immediate post-exception command is zero. Neither identifies the rejected candidate command.

## What the recorder retains

[Native recorder](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/5eacacf42378ad91319a5de323df7844f34ea33b/experiments/competition_nav2/native_runner.py): lines 129–136 subscribe only to global OccupancyGrid and native plan; lines 181–215 record header times, grid metadata and XY path positions. There are 10 paths and 11 global costmap snapshots. Path orientations and per-pose timestamps are discarded. No local costmap, transformed/pruned plan, carrot, predicted arc, rejected twist or checker sample/cost is recorded.

Lines 295–323 integrate the previous actuator command, advance sim by 0.05, then publish pose/clock. Lines 468–513 record resulting pose, previous applied command and next actuator output. These columns cannot be interchanged. Map-to-odom is simulation-only identity (lines 338–345).

## Version-matched Nav2 semantics

Installed RPP package is `1.1.20-1jammy.20260915.232155`. These are upstream tag 1.1.20 semantics, not proof of a binary-identical source build.

[RPP source](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp#L260-L536): transformed path XY determines interpolated carrot and curvature; path alignment uses carrot bearing, not intermediate path yaw. Goal alignment uses terminal yaw. Collision checks current footprint then constant-candidate-velocity projected footprints; normal step is resolution/abs(v), pure-rotation step uses circumscribed radius only for timestep. Forward Euler updates XY then yaw, stopping before the time horizon or beyond carrot chord distance. Exception occurs before returning candidate twist. Raw costs below254, including253 inscribed inflation, do not alone reject; unknown255 is allowed when tracking unknown. A center outside costmap warns and returns false. Arc publication is absent if the initial current footprint already collides.

[Footprint checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/src/footprint_collision_checker.cpp#L44-L131): transformed polygon edges are rasterized, not a filled interior or circumscribed circle. Out-of-map vertices return254; otherwise edge maxima and early lethal exits determine cost.

[Costmap publisher](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/src/costmap_2d_publisher.cpp#L81-L93): raw0→0, raw253→99, raw254→100, raw255→-1. Raw1..252 are lossily mapped to1..98. Recorded compressed bytes encode signed unknown -1 as255. Therefore `occupancy >=99` is not RPP's lethal threshold; it conflates inscribed inflation with lethal obstacle.

[Navfn](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_navfn_planner/src/navfn_planner.cpp#L187-L251) plans on a 2D cost field, not a rectangular nonholonomic swept-body feasibility search. A path XY tangent reconstructed offline is not its recorded pose yaw and is not the executed RPP sweep.

## Fixture/config contract and minimal C3 follow-up

The artifact's effective params use raw body0.81×0.56m plus0.03m per side exactly once: footprint0.87×0.62m, padding0, grid0.02m. The generic rpp-contract top-level0.716×0.324m diagnostic footprint does not apply to this external D0 fixture. Actual params show lookahead0.4m, collision horizon1s, no reverse, rotate-to-heading enabled, desired speed0.18m/s and local costmap5×5m. Inflation radius0.4m is a cost field, not an extra geometric margin.

Minimum instrumentation for the same single failing cycle: controller input pose with TF stamp, full/pruned path with yaw, carrot, candidate rejected twist, raw local costmap with origin/resolution/time, and checker first failing sampled pose/raw cost. Carrot/arc topic recording alone is insufficient for current-pose failure and does not expose the rejected twist. Do not change footprint, padding, motion limits or controller tuning to collect this evidence. Parent geometry output can reject/confirm geometric hypotheses against recorded global data, but must label any last-command projection as counterfactual and exact rejected-arc attribution as NOT_RECORDED.
