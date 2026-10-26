# C3 ROUND5 — one footprint coverage correction B1

Base and remote C3 HEAD checked on 2026-10-26 KST: `d253ee090a5f5c145c3842ed2cc0105d7d95fea3`; clean independent clone on `review/20261024-c3-nav2-benchmark`. Main remains `104692fa0070ef085eee918913ea05fdb2d88c05`. No other-role changes, PR, robot/camera access, service changes, deployment or physical motion. Production is not adopted; real robot qualification is NOT_RUN.

This round authorizes **one B1 configuration**, not reopening the ROUND4 search. A (Smac Hybrid/RPP, native run40167720216) remains no-path/SAFE_WAIT and goal FAIL. B (Lattice/MPPI Omni, native run40168963222, source `2a1b1f172f30d010fa33d9b7f247a9163f175e82`) remains footprint-boundary/goal FAIL. Original reports, artifacts, image/package lock, D0 pin, primitives and old variants are preserved. B1 is the separate opt-in revision `omni_coverage`.

## Exactly two configuration values change

Only `global_costmap.global_costmap.ros__parameters.inflation_layer.inflation_radius` and the corresponding local value change from .4 to **.58 m**. A structural regression compares the entire generated B/B1 configuration after restoring these two values and requires equality. The independent geometry validator still uses the original rectangle, not an inflated circle.

Effective body is .87×.62 m (raw .81×.56 + .03 once, native padding0). Inscribed radius=.3100000000 m; circumradius=.5341582162618114 m. Pose-to-cell and touched-obstacle-to-cell quantization each allow half a cell diagonal: combined allowance `sqrt(2)*.02=.0282842712474619 m`. Required field support is .5624424875092733 m. Rounding upward to whole 2cm cells gives **29 cells, .58 m**, the smallest grid-aligned support satisfying this stated bound. Native `cellDistance` uses ceil; inflation enqueue truncates at that cell radius. Cost scaling remains5 and native `computeCost(circumradius/resolution)` threshold remains **82**. No threshold, critic weight, body, margin, unknown policy or controller limit changes.

This corrects the field support prerequisite; it is **not** proof against every grid/angle-bin aliasing case. The existing native center-cost shortcut still exists. Independent whole-body path and actual-motion checks remain necessary; zero after a boundary violation is still safety FAIL.

Exact official 1.1.20 sources inspected, with SHA256 in [ROUND5_PREFLIGHT.json](ROUND5_PREFLIGHT.json):

- [Inflation computeCost](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/include/nav2_costmap_2d/inflation_layer.hpp), [field enqueue/cache](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/plugins/inflation_layer.cpp), [cellDistance](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/src/costmap_2d.cpp).
- [Smac checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/collision_checker.cpp), [Lattice layer/threshold setup](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/smac_planner_lattice.cpp), [MPPI CostCritic](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_mppi_controller/src/critics/cost_critic.cpp).

B's actual native log shows both costmaps initializing `inflation_layer` and MPPI footprint CostCritic; its recorded parameter readback is .4/5/.02 with the full body. B1 additionally reads actual plugin lists/type/enabled/unknown defaults and critic layer selector, and hashes the loaded InflationLayer library in both controller and planner processes. With exactly one inflation plugin per map, empty CostCritic layer selector resolves that same inflation layer. Installed binaries are never patched.

## Small comparison before native execution

Retained B evidence is from run40168963222. Reconstructing inflation from its recorded lethal cells, using the exact cost formula and original geometry, gives:

| Retained pose | Nearest lethal center distance | B center cost | B1 reconstructed cost | Independent full-body result |
|---|---:|---:|---:|---|
| First unsafe native path pose (.510,.950,1.416247) | .46 m | 0 | 119 >=82 | Grid and original truth collision |
| First actual boundary crossing (.498024,.964305,1.430887) | .48 m | 0 | 107 >=82 | Grid and original truth collision |
| Same starting pose (.5,.95,pi/2) | .46 m | 0 | 119 | No grid/truth collision |
| Normal narrow north corridor (.5,1.5,pi/2) | .486621 m | 0 | 104 | No grid/truth collision |

The first two counterexamples no longer take the reconstructed free-center shortcut. Positive nonlethal inflation cost does not itself turn the last two poses into collisions. This comparison is **independent reconstruction**, not direct native checker/critic execution. Published grids are asynchronous. OccupancyGrid float32 resolution is normalized to the actual .02 double parameter for radius-cell arithmetic. The original B's three native paths also fail the new XY/yaw interval audit; no fabricated Z or native rerun is used for that historical check.

Focused synthetic tests include a rotation whose endpoints are body-free but whose intermediate orientations collide, preservation of a narrow rectangle corridor that a circumscribed hard circle would reject, invalid/missing native Z rejection and exact B/B1 parameter difference. No source/witness path is supplied to Nav2.

## B1 execution and evidence contract

Reuse the locked executor, original D0 source `83f4ee8d6971d00ab31b2de0eeebf329542dd5d6`, canonical manifest `1e995e63e9e601433399f052d6a9630b4d5fb53081cfd1b00003aae2b16ef84e`, original geometry and sensors. No local reinstallation or common fixture reimplementation. Existing body-frame vx/vy/wz gate, source/receipt clocks, sensor period/TTL, acceleration, goal/time budget and generic primitives stay fixed. Separate `repro/omni-coverage-contract.json` declares B1 and its provenance; RPP/B source hash pins are refreshed without changing their generated configurations or motion contract.

Existing observations now retain path XYZ/quaternion and actual delivered simulation TF transform/source stamp/receipt. Read-only post-run validation checks every native path's padded-body poses and interpolated XY/shortest-yaw intervals (<=2mm corner displacement, <=.005rad) against original truth and closed lethal/unknown cells in the preceding published global map. This bounded numerical interpolation is not exact continuous collision proof or a hard realtime safety guarantee. Original truth is never a runtime planner prior. Existing independent actuator-twist sweep, TTL, latch and exact three-zero final-command checks remain.

Native plan: one original feasible1. Only native goal + safety + evidence PASS permits the fixed remaining cases (empty, blocked, dropout, feasible1 repeat1, feasible2), maximum six total. Failure stops at feasible1; no same-configuration retry, new optimizer/critic sweep, old A/B rerun or general seven-case repetition.

**Native B1 result is pending this source commit.** The post-execution report will identify exact tested source/config/image/library hashes, source/receipt timing, distance, contact and goal outcomes. No native PASS is claimed from the preflight.

## Read-only cross-role state and reproduction

Latest observed C1 `c052db127f2952b693971642f0a33c8efcb43098` records successful integrated source CI40168592604 and already includes ROUND3 C3/D0 preparation. Its common browser collection fix is not reimplemented here. Latest D0 `da7230bb65722e4a1d3f4ab0c1d16e63fcd344e3` has its ROUND4 original-RPP audit; a ROUND5 B audit was not yet published at the initial check, so existing B artifacts are sufficient for this bounded correction. No waiting dependency is introduced.

```sh
python3 -m unittest discover -s experiments/competition_nav2/tests -v
# Existing prepared pinned D0 inputs and exact image lock; no hardware access.
cp experiments/competition_nav2/repro/image-lock.json /tmp/c3-round5-lock.json
python3 experiments/competition_nav2/container/manage.py build --lock /tmp/c3-round5-lock.json
python3 experiments/competition_nav2/run_narrow.py --variant omni_coverage --lock /tmp/c3-round5-lock.json --output /tmp/c3-round5-new-run
```

The hosted workflow uses network-none native containers, ROS domain193/localhost-only, namespace `/c3_nav2`, SIM_GT and fixed resource/artifact limits. Public Git contains source and small non-sensitive results only. Production consumer=null/live import=false. Physical stopping, gait, stairs, sensor fusion, Jetson performance and real robot motion are NOT_RUN.

## Local checks before source publication

C3 focused: 77 PASS (3.103 s); full repository Python: 2691 run, 2689 PASS / 2 SKIP (87.341 s); JavaScript `node --test tests/*.mjs`: 70 PASS; Ruff, secret scan, diff check and contract source pins PASS. All six previous generated candidate configurations equal the pre-ROUND5 source. The base command/Omni core, D0 adapter/pin, primitives and image lock have zero diff. Full-suite scope is unchanged common code; added path/coverage checks run in the C3 suite. Native B1 is still pending, separately from these synthetic/offline results.
