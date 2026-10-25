# C3 ROUND4 — frozen feasible1 native comparison

**No successful candidate.** The bounded comparison is complete and frozen after two candidates. A (`se2_rpp`) produces no path and stops safely; B (`omni_lattice`) produces native paths and three-axis commands but violates the once-padded footprint boundary at its initial rotation. **B fails independent safety as well as goal completion. Neither candidate is recommended for adoption.** No third candidate, parameter sweep or additional native run is requested by this submission.

Base: `32914885d84b9bf98e799492366aeab0f908f547`. Native A/diagnostic source: `20d7f56f24cff768e716a56813250ebbd3c2c234`. Frozen B and final locally tested code: `2a1b1f172f30d010fa33d9b7f247a9163f175e82`. The final documentation commit is reported in the external submission receipt, avoiding a self-referential commit. Branch: [`review/20261024-c3-nav2-benchmark`](https://github.com/Phjrab/robot-scope-ros2-dashboard/tree/review/20261024-c3-nav2-benchmark).

The original checkout was clean and matched the remote base. Only `experiments/competition_nav2/**`, `.github/workflows/competition-nav2-review.yml`, and this C3 review directory changed. Existing evidence, DiffDrive core/time contracts, D0 source and user changes were preserved. No main/other-role write, PR, robot access, service change, deployment or physical motion. All native evidence below is **actual Nav2 with virtual original D0 sensors, SIM_GT, x86_64 isolated container**, not physical robot evidence.

## Actual outcomes

| Execution | Native run / source | Path length | Independent safety | Native terminal / goal |
|---|---|---:|---|---|
| Unchanged baseline, one diagnostic | [40167720216](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40167720216) / `20d7f56` | 0.805500 m | PASS, zero contacts/boundary violations | ABORTED (6), SAFE_WAIT; no goal, expected diagnostic outcome |
| A: Smac Hybrid + RPP | Same run / `20d7f56` | 0 m | PASS, zero contacts/boundary violations | ABORTED (6), SAFE_WAIT; **goal FAIL** |
| B: Smac Lattice + MPPI Omni | [40168963222](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168963222) / `2a1b1f1` | 0.015466 m | **FAIL**, effective footprint boundary crossing | CANCELED (5), acknowledged after harness fault; **goal FAIL** |

Both native workflow runs concluded **FAILURE**. Each candidate stopped at the first feasible1 failure. Empty, blocked, sensor_dropout, feasible1 repeat 1 and feasible2 for these candidates are **NOT_RUN**, not inherited successes from ROUND3. No new tight5, generic diagnostic seven-case repeat or 144-run MPPI matrix. The baseline diagnostic was run exactly once and was not repeated for B.

Machine-readable provenance and results: [ROUND4_NATIVE.json](ROUND4_NATIVE.json). It records all three actual cases, controller/planner/costmap readbacks, loaded library hashes, action UUID/status, metrics, cleanup, original-sensor conformance, source/image/config hashes and artifact file hashes. [ROUND4_BASELINE.json](ROUND4_BASELINE.json), [ROUND4_DIAGNOSTIC.json](ROUND4_DIAGNOSTIC.json) and [ROUND4_OMNI_FAILURE.json](ROUND4_OMNI_FAILURE.json) preserve the separate analyses.

## Original RPP first failure

Before new native execution, preserved ROUND3 run [40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349), source `5eacacf42378ad91319a5de323df7844f34ea33b`, was inspected. Its first RPP warning at wall `1792904808.540106401` is followed by native zero command source timestamp `1792904808540151104`. Immediately preceding trace: sim 6.40 / goal elapsed 4.85 s, pose `(0.5167972572, 1.7462801515, 1.5282629699)`. No stale-command, sensor-TTL, gate fault, actual contact or 65 s goal deadline caused that warning.

The retained NavFn path center samples are all free of lethal/unknown cells. Independent full-body placement gives 80 colliding samples using segment-tangent yaw and 59 using fixed north yaw. The first north-yaw collision is at `(0.517448,1.944714)`, center cost 0. Those are explicitly hypothetical orientations: the original artifact did not retain the path quaternion or native collision arc. A free centerline does not establish full-body feasibility.

The single diagnostic reproduced the same configuration hash and exactly 0.8054999813 m travel. Actual readback confirms raw body 0.81×0.56 m, once-padded 0.87×0.62 m, native padding 0, grid 0.02 m, inflation radius 0.4 m, cost scaling 5. There is no duplicate margin. Original cone base is x `[0.05,0.31]`, y `[2.37,2.63]`.

The retained native carrot in base_link is `(0.39983529,-0.01147774)`. Its eight-point collision arc reconstructs initial yaw 1.52826297 and final projected yaw 1.50530749. The front-left padded corner `(0.24433723,2.36041016)` overlaps a lethal local cell with world bounds x `[0.24,0.26]`, y `[2.36,2.38]`, occupancy 100. The published maps bracketing the arc (sim 6.30 and 6.70) both retain that same world cell; rolling-grid indices are `(111,157)` and `(111,155)`. It is a cone lethal cell, not unknown or merely an inflation cost. The continuous cone starts at y=2.37; conservative rasterization rejects the predicted corner approximately 9.6 mm before continuous contact.

**Precision limit:** the native arc and published maps are asynchronous, not an atomic snapshot of the internal collision checker. This is a reconstruction supported by both bracketing maps, not a claim that the internal failing cell was instrumented. Recorded arc quaternions are default `[0,0,0,1]`, not projected headings; yaw is reconstructed from consecutive arc segments and the source's Euler update. The earlier code comment describing a “zero quaternion” is imprecise and is not used in any calculation. The rejected candidate velocity is not substituted with the last accepted twist.

Spin later rotates at the stopped xy and predicts overlap with the right wall (world cells near x=0.98–1.02, y=1.54–1.60). It does not fix the late cone detour. This separate Spin explanation reconstructs actual pose and the [1.1.20 implementation](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_behaviors/plugins/spin.cpp); it is not an emitted Spin arc. The [exact RPP source](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp) hash is `8012c94afb3ebb3d98dde4a0f255b9596ba80b10dbdd9527b417ddc85fcb0756`.

## A: bounded SE2 planner with unchanged RPP

A replaces only NavFn with installed Humble **Nav2 1.1.20 SmacPlannerHybrid**, export `nav2_smac_planner/SmacPlannerHybrid`. DUBIN forward search, 72 yaw bins, minimum radius 0.8 m, original 0.02 m grid, no smoothing/downsampling, unknown forbidden and zero planner tolerance. Planning is limited to 1 s/500000 iterations. RPP, body/margin, sensors, inflation, limits, TTL, goal, recovery and timeout are unchanged.

Actual planner readbacks and loaded library are verified. Config SHA256 `68b04225ff3510bdb98f5052b10ca575388b4de094e0e1b515544c817787f549`; library SHA256 `74828b79ec7e98af15058e7af99579e9252106123c2ff1b3c6b3da934006ce40`. Native planning returns no valid path about 3.6 ms after the goal starts, before FollowPath. No planner path or translational motion is claimed. Increasing the goal timeout would not resolve this initial failure. This rejects this candidate; it does not establish that all DiffDrive configurations are infeasible.

## B: explicit Omni contract and observed safety failure

B uses native SmacPlannerLattice and MPPI `motion_model=Omni`. The separate `repro/omni-contract.json` declares body-frame vx/vy/wz, yaw-aware world integration, three-axis gate/trace/validator, command source and receipt clocks, sequence/epoch, sensor TTL .25 s, HOLD/latch and exact three-zero stop. Limits are vx≤.16, |vy|≤.08, |wz|≤.6, linear norm≤.18, vector acceleration≤.3 and angular acceleration≤1.2. These are simulation bounds. Existing two-axis schema, `core.py` and baseline-only RPP contract remain in place; only the RPP contract's configure source hash changes. Production consumer=null and live import=false.

Generic primitives use the official 1.1.20 generator, 2cm resolution, 16 native headings, 0.06 m primitive turning-radius parameter and one-cell cardinal/lateral translations. No arena, witness or solution path enters generation. Endpoint/yaw/grid and lateral reachability tests pass. Primitive SHA256 `bffe262d759b8866fa1b305d0d1529d6e2cbd7f9df389deedee30d5318f3b17c`. The offline generator used an exact inclusive bounding-box intersection fallback because Rtree was unavailable; full fallback source and upstream hashes are recorded in `repro/omni-primitives-provenance.json`. No runtime generator or installed package change. The primitive radius does not increase command limits or claim physical steering capability.

Before execution, exact Humble source verification rejected the unsupported newer `PathAngleCritic.mode` parameter. The supported [PathAlignCritic](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_mppi_controller/src/critics/path_align_critic.cpp) instead follows native path orientations. MPPI uses 56×.05 s horizon, batch 1000, one iteration; CostCritic footprint consideration remains enabled. No collision threshold was relaxed. Config SHA256 `51dc10e7b659cde570cda07a9b9cc25f40ebfda1d1a8fbef488349af6ca95246`.

Actual native result:

- Five lifecycle nodes active; native goal accepted; three native global paths. First path has 187 poses and 14 full-padded-body collisions under independent geometry checks. Its initial in-place rotation is already infeasible at the floor boundary.
- 33 raw native commands, 32 with nonzero vy. Maximum applied |vy|=.013936 m/s and linear norm=.027255 m/s. The plant integrates native gated twists, not a witness path.
- First crossing: sim 3.35 / goal elapsed 1.65 s, pose `(0.498024368,0.964305334,1.430886911)`. Previous applied `(vx,vy,wz)=(.00610931,-.00005881,-.13174424)`. The padded corner y=.490325319 is below floor y=.491 by .000674681 m. Raw-body clearance remains .033215781 m; the required margin has nevertheless been breached.
- `FOOTPRINT_CONTACT` latches all three commands to zero; no post-fault nonzero command, one cancel acknowledgment, terminal CANCELED (5), graceful cleanup. This is successful fault stopping **after a safety violation**, not safety PASS.
- Contact/boundary counters are 64 samples of the first crossing plus the stationary footprint remaining outside the effective boundary, not 64 distinct impacts. Validator rejects contact count, boundary count, failed outcome and independently interpolated footprint contact. Goal remains 4.085695 m away.

### Narrowed cause and its limit

The unchanged inflation radius is **0.4 m**, smaller than the once-padded body's circumscribed radius **0.534158216 m**. At the first bad native path pose the retained global map gives center occupancy 0; at actual crossing the retained local map also gives center occupancy 0 while padded edges intersect lethal floor cells.

The exact [1.1.20 Smac checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/collision_checker.cpp) returns collision-free before footprint evaluation when center cost is below a positive possibly-inscribed threshold. The exact [MPPI CostCritic](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_mppi_controller/src/critics/cost_critic.cpp) skips a pose with center cost <1 and otherwise conditionally invokes the full footprint checker. The threshold calculation at this body's circumradius gives cost 82, while the truncated .4 m inflation field leaves the center at zero. Thus enabling footprint consideration alone does not guarantee evaluation of that footprint under this inconsistent cost-field coverage.

This explains a specific safety-check prerequisite mismatch and is consistent with both observed invalid paths and motion. **The executed internal branch was not atomically traced, and a corrected configuration has not been validated.** No claim of a completed fix or universal MPPI failure is made. The supported inference and exact evidence/source hashes are retained in `ROUND4_OMNI_FAILURE.json`.

## Immutable inputs, image and artifacts

D0 source remains `83f4ee8d6971d00ab31b2de0eeebf329542dd5d6`, manifest `1e995e63e9e601433399f052d6a9630b4d5fb53081cfd1b00003aae2b16ef84e`. Every actual case passes original sensor conformance: 3 probes ×360 beams, maximum range difference 0.0. Body, margin, cone, parking/corridor, observation ownership and unknown policy were not relaxed.

All cases use the existing base `ros@sha256:566b87e6dfc48392189a9c32e594e84060fa9948de93b04e536f39475a1f6963`. Exact package TSV SHA256 `45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de` matches the original image lock; **package delta is empty**. Nav2 1.1.20/rclpy 3.3.22. A image `sha256:7efd98f806f896c80bbae38d14b15a46b9a28758b467e03be706122725a9e882`; B image `sha256:7dc5872beec07b9d070b0e85258236db2163d78f8f15ec2c0c9cf31c3272f1f0`. B's loaded MPPI and Lattice libraries are hashed in the receipt. Fresh builds are allowed only with that existing exact lock; no reinstall/upgrade or silent lock replacement occurred.

| Native run | Artifact | Digest | Expiry UTC |
|---|---|---|---|
| 40167720216 | 12588834390 | `sha256:0179247167fda857c98a04837664d51ea26beb6bb4dad6ccbbc64d3ae3609fa4` | 2026-11-08T06:05:27Z |
| 40168963222 | 12590081484 | `sha256:43580b9a3ced0b6bba00211a14a6398650fb7018c2794243f2af092cc5c34c29` | 2026-11-08T06:26:42Z |

Native containers have `--network none`, only loopback, ROS domain 193, namespace `/c3_nav2`. No production consumer or live import. Physical braking, gait, Jetson performance, real RGB replay, real robot observations and physical motion: **NOT_RUN**.

## Checks and current integration state

Frozen source `2a1b1f172f30d010fa33d9b7f247a9163f175e82`:

| Check | Actual result |
|---|---|
| C3 focused offline unit tests | 71 PASS, 2.954 s |
| Repository Python suite | 2691 run: 2689 PASS, 2 SKIP, 82.595 s |
| Related JavaScript tests | 70 PASS |
| Ruff / repository secret scan / git diff check | PASS |
| Final validator replay on retained baseline and A native artifacts | Both PASS; no native rerun |
| Native B validation | FAIL with the four errors above |
| Common CI [40167720163](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40167720163), source `20d7f56` | completed / FAILURE |
| Common CI [40168963218](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168963218), source `2a1b1f1` | completed / FAILURE |

Both common-CI OS jobs fail browser E2E collection at the existing CommonJS named export `GO2_JOINT_NAMES` in `observed_joints.js`. Python, related JS, syntax and audits pass there; no browser suite PASS is claimed. This C3 branch does not modify common CI. The docs-only submission's exact CI status is reported externally with its final SHA; code tests are not rerun solely for prose edits. Local test-log hashes are in the receipt.

Read-only follow-up checks used actual C1 `50ad48849ad0862aeeba034d009ac34e42fddd8e` and D0 `da7230bb65722e4a1d3f4ab0c1d16e63fcd344e3`. C1's `ROUND4_EVIDENCE.json` already adopts C3 ROUND3 `32914885`; its actual common CI already fetches the pinned D0 source and runs `prepare_d0.py`. **The old ROUND3 adoption/prepare blocker is resolved.** Only this ROUND4 delta needs C1's incremental review. D0's independent original-artifact audit agrees that free centerline samples do not prove body clearance; its proposed atomic checker packet was not executed. Our bounded diagnostic adds arc/carrot and bracketing published maps but does not claim that atomic packet. Neither role's checkout or files were changed.

## C1 reproduction and remaining one task

C1 may review `32914885..2a1b1f1` plus this report-only commit in the existing integration branch. Treat both variants as rejected isolated experiments, not a successful production navigation candidate. `rpp_contract.py` remains baseline-only; Omni uses a separate explicit contract. The source changes comprise optional variant configuration/planner readbacks, bounded driver, three-axis gate/plant/validator and dedicated tests; unchanged prior RPP artifacts remain interpretable.

For later **manual reproduction of the rejected B result** using a fresh output directory and the existing exact lock (not an instruction to run a third candidate now):

```sh
git fetch --no-tags --depth=1 origin 83f4ee8d6971d00ab31b2de0eeebf329542dd5d6
python3 experiments/competition_nav2/prepare_d0.py
python3 -m unittest discover -s experiments/competition_nav2/tests -v
cp experiments/competition_nav2/repro/image-lock.json /tmp/c3-round4-image-lock.json
python3 experiments/competition_nav2/container/manage.py build --lock /tmp/c3-round4-image-lock.json
python3 experiments/competition_nav2/run_narrow.py --variant omni_lattice --lock /tmp/c3-round4-image-lock.json --output /tmp/c3-round4-new-run
```

The existing bounded driver expects feasible1 goal+validation PASS before empty/blocked/dropout/repeat/feasible2. `--baseline-debug` was used once for the retained first-run diagnostic; it is not needed to reproduce B. An image package mismatch fails instead of accepting an upgrade.

**Remaining one task:** in a future bounded review, correct cost-field coverage for the unchanged padded footprint (circumradius .534158 m plus grid allowance), then revalidate this same Omni feasible1. Keep body/margin and all original scene/sensor/stop requirements. The correction is unimplemented and its goal/safety outcome unproven; ROUND4 stops at the two-candidate limit.
