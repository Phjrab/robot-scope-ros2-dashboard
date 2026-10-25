# C3 ROUND4 — feasible1 narrow Nav2 review

Baseline: `32914885d84b9bf98e799492366aeab0f908f547` on `review/20261024-c3-nav2-benchmark`. Local and remote match; worktree was clean. Read-only remote check on 2026-10-25 matched all supplied ROUND4 snapshots (main `104692fa`, C1 `85c5b6b8`, C2 `8a58370b`, C4 `9e9ebcc0`, D0 `8ba7affe`, L1 `5339e3b5`). Only C3 files are changed. No main/other-role write, PR, robot access, service change, deployment or physical motion.

## Baseline evidence before any new native execution

Preserved run [40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349), source `5eacacf42378ad91319a5de323df7844f34ea33b`, original artifact `12588085458`. See `ROUND4_BASELINE.json` for exact original file hashes and readback.

First RPP error: wall timestamp `1792904808.540106401`, immediately followed by its zero command with DDS source timestamp `1792904808540151104`. Trace sim 6.40 / goal elapsed 4.85 s is `(0.516797, 1.746280, 1.528263 rad)`. No TTL, gate fault, contact or goal deadline caused this abort. Spin subsequently rotates at the stopped xy and aborts; its final yaw is 1.868475 rad. Its failure is separate from the initial forward prediction.

Original native global path at sim 6.35 s has **zero lethal/unknown center samples** against the latest retained global costmap (sim 6.15 s). Independent body placement on the same points gives **80 collisions with segment-tangent yaw** and **59 with fixed north yaw**. First north-yaw overlap is at `(0.517448, 1.944714)` while center occupancy is 0. Cone base is x `[0.05,0.31]`, y `[2.37,2.63]`; a north-facing 0.87 m long body reaches it before its center begins the late detour. These yaw hypotheses are explicitly independent analysis: original NavFn path orientation/local map/carrot/arc were not recorded. They do not claim the exact local collision cell.

Actual global/local readback: raw body 0.81×0.56 m, once-padded footprint 0.87×0.62 m, native padding 0, resolution 0.02 m, inflation radius 0.4 m/cost factor 5. No evidence of duplicate padding. Inflation cost is not itself a lethal cell. Exact native local cell and predicted arc require one bounded feasible1 baseline diagnostic; original evidence stays intact.

## Fixed first candidate and supported version

`se2_rpp`: replace only NavFn with installed **Humble Nav2 1.1.20 SmacPlannerHybrid**. Keep RPP/controller parameters, DiffDrive axes (vx,wz; vy=0), full padded body, costmaps/inflation, original D0 inputs/sensor, limits, TTL, goal, timeout and recovery unchanged. Native DUBIN forward search uses 72 yaw bins, 0.8 m minimum turning radius, original 0.02 m grid without downsampling, no path smoothing, unknown forbidden, zero goal tolerance. Radius implies <=0.225 rad/s at 0.18 m/s, within existing 0.6 bound; no physical steering claim. Planner time is bounded to 1 s and 500000 iterations. This is a single explicit candidate, not a parameter sweep.

Version evidence: preserved complete package lock contains `ros-humble-nav2-smac-planner 1.1.20-1jammy.20260915.232226`. No package delta or lock replacement requested. Exact official 1.1.20 sources checked before selection:

- [RPP implementation](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp), SHA256 `8012c94afb3ebb3d98dde4a0f255b9596ba80b10dbdd9527b417ddc85fcb0756`.
- [Hybrid implementation / parameter declarations](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/smac_planner_hybrid.cpp), SHA256 `ff51b5a9df603c6524f27545390ba7d3b3e74cfc6cd20a405fef39f9bbe98184`.
- [Humble plugin export](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/smac_plugin_hybrid.xml), SHA256 `3eace0d6320306040941349172b94ffaa3fefcee637ba4d6417a457a7635b6b6`: slash-form `nav2_smac_planner/SmacPlannerHybrid`, C++ type `nav2_smac_planner::SmacPlannerHybrid`, library `nav2_smac_planner`.
- [Smac footprint checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/collision_checker.cpp), SHA256 `2be59308f6b216130abc6247aed60709137bac8b9bcd888d1afcb59a13f3b939`.

Read-only observations now retain local costmap, native RPP carrot/collision arc, and path quaternions. Humble's arc quaternion is zero; it must not be interpreted as measured yaw. Planner parameters are read back and its actual loaded shared library is hashed. Existing RPP contract remains baseline-only with unchanged generated baseline config; its configure source hash is refreshed.

## Bounded validation protocol

Use existing isolated executor and locked image. One baseline feasible1 diagnostic, then candidate feasible1. Only if candidate feasible1 has native goal completion plus independent validation PASS, continue same candidate on empty, blocked, sensor_dropout, feasible1 repeat 1, feasible2. No generic diagnostic 7-run repetition, tight5 run, MPPI matrix or extra tuning. At most two candidates are allowed. Safety/evidence PASS and goal completion are separate claims.

Native results pending initial candidate run; no new result claimed by this source commit. Physical braking, gait, Jetson performance and physical motion: **NOT_RUN**.

## C1 reproduction

Read/apply C3-owned changes in the existing integration branch. Materialize pinned D0 inputs before C3 tests (the prior ROUND3 common-CI handoff remains necessary). Existing `rpp_contract.py` stays baseline-only; `se2_rpp` is opt-in through the existing isolated executor.

```sh
git fetch --no-tags --depth=1 origin 83f4ee8d6971d00ab31b2de0eeebf329542dd5d6
python3 experiments/competition_nav2/prepare_d0.py
python3 -m unittest discover -s experiments/competition_nav2/tests -v
cp experiments/competition_nav2/repro/image-lock.json /tmp/c3-round4-image-lock.json
python3 experiments/competition_nav2/container/manage.py build --lock /tmp/c3-round4-image-lock.json
python3 experiments/competition_nav2/run_narrow.py --lock /tmp/c3-round4-image-lock.json --output /tmp/c3-round4-new-run
```

`--baseline-debug` is an explicit additional one-case diagnostic, used once in this review. All native execution uses `--network none`, ROS domain 193, namespace `/c3_nav2`, SIM_GT; production consumer=null and live import disabled. Reproduction requires a fresh output directory and the original exact lock. Package mismatch fails instead of silently accepting a new image.
