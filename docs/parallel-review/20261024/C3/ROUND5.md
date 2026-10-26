# C3 ROUND5 — B1 coverage applied, native path rejected and frozen

**B1 was executed once and is rejected.** The .58m inflation setting applied correctly and the actual plant had no contact, but the first native path still contains invalid full-body poses; the run later stopped with progress failure and did not reach the goal. No repeated B1, additional candidate, optimizer/critic tuning or upstream patch was performed. This is not a successful navigation candidate.

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

**Actual tested code:** `a70f22dd703502b6c6779946f34bd9c7261696c5`. Native [run40260839144](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40260839144): completed / **FAILURE**, exactly one attempted feasible1, `STOPPED_AT_FEASIBLE1`. Full native receipt: [ROUND5_NATIVE.json](ROUND5_NATIVE.json); first-failure correlation: [ROUND5_FAILURE.json](ROUND5_FAILURE.json). Final submission is a docs-only commit over this tested source and is reported externally; no self-referential commit loop.

### B / B1 actual comparison

| Property | Preserved B | B1, one actual run |
|---|---|---|
| Inflation global/local | .4/.4 m | .58/.58 m; actual config delta contains only these two keys |
| Native status / terminal | FAILED / CANCELED5 after footprint fault | SAFE_WAIT / ABORTED6, accepted actual UUID |
| Actual plant distance | .015466 m | **.961103133 m** |
| Actual padded contact / boundary samples | 64/64, one crossing plus stopped samples | **0/0**, independent actuator sweep has no collision error |
| Native path validation | Previously rejected | **FAIL**: 15/51 paths collide with original continuous truth; 51/51 touch lethal/unknown grid cells |
| Goal | Not reached | **Not reached**, 3.158701651 m remaining |
| Final command / cleanup | Three zero / graceful | **[0,0,0]**, >2 s zero tail, graceful, no processes left |

The invalid path existed before the first applied movement, so the first failure class is **native path collision after support coverage was applied**, not an unapplied parameter or simple timeout. Actual movement staying clear does not turn the rejected paths into safety PASS. Later native `Failed to make progress` at wall1792982986.117803990 corresponds near sim28.80, pose(.523082453,1.891351196,1.581394399). Spin then predicts collision and aborts; native goal terminal is6. Total sim33.80 s / wall33.847914 s, before the unchanged65 s budget. Startup COMMAND_TTL before any raw command is a transient zero gate, not the terminal cause; native terminal_fault=null.

### First path evidence and narrowed remaining defect

First native path: source sim1.95, local receipt monotonic195.451124384,185 XYZ/yaw poses. Its preceding global map: source sim1.35, receipt194.830971385. Two concrete points:

- Native point10: (.549999988,1.029999977,.999898553). Padded corner y=.496463767 is still above continuous floor. Its edge overlaps lethal cell(28,24), y[.48,.50]. Center occupancy31 corresponds to possible raw costs79–81, all below native threshold82. The lossy OccupancyGrid mapping is not inverted to an invented exact raw byte. The source-supported shortcut can still bypass this grid-corner collision even though the field now has support.
- Native point16: (.622709985,1.107580008,1.104412913). Its padded corner(1.095203716,1.356727905) crosses the original sloped right boundary, and four lethal cells overlap. This is an actual emitted native pose with an **original-truth collision**, not only conservative grid contact. It matches the first pose of unchanged generic primitive21 (start path index15, end index18).

Exact [1.1.20 Lattice node checking](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/node_lattice.cpp) uses XY separation to select intermediate checks; [Lattice setup](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/smac_planner_lattice.cpp) fixes72 checking orientations, and the checker places a cached oriented footprint at an integer cell. This can differ from an emitted intermediate continuous pose/yaw. These source/geometry observations narrow the next check; **the precise internal branch was not instrumented**, and point16 is not claimed to have the same below-threshold cause as point10. Relevant source hashes and primitive correspondence are retained in ROUND5_FAILURE.

Path intervals were also checked at <=2mm corner / .005rad spacing. Receipt ordering was independently rechecked: the original validator's source-time choice used one map arriving11ms after path source14.85. Requiring both source and receipt precedence changes that one snapshot but leaves **15 truth-colliding and51 grid-colliding paths**. The first path is unaffected. The original artifact/validator result is preserved, and this asynchronous-map limitation is not hidden.

### Applied native layer, timing and immutable provenance

Both global/local readbacks show exactly one enabled `nav2_costmap_2d::InflationLayer`, radius.58, scaling5, native padding0 and the full footprint; unknown defaults unchanged. MPPI's declared `inflation_layer_name` is empty, selecting the sole layer. Nav2 costmap package1.1.20 and the same `/opt/ros/humble/lib/liblayers.so` SHA256 `8c54b99629fe99031c058c5eb5e16a9b0602a9e258d0cd4c0b89920a2dabd9f2` are proven in both native processes. MPPI/Lattice library hashes exactly match B. The formerly free counterexample centers now have native OccupancyGrid46/41 (not raw cost bytes). Thus the .4m truncation was actually corrected, but it was insufficient for full native path validity.

- Config SHA256: `6d0c91060727d17f0bea77005dfe62a7d8130c3425f290346e00777c03bb36f0`.
- Image: `sha256:b55b3d7258cc3e91208c15236063e1545b83226a41b59349e616e6b4aa7d28eb`; original base `ros@sha256:566b87e6dfc48392189a9c32e594e84060fa9948de93b04e536f39475a1f6963`.
- Complete package TSV exactly equals the previous lock, delta empty, SHA256 `45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de`. No upgrade or silent lock rewrite.
- Original geometry canonical SHA256 `163af586ff5429cec348bc68b87b337e857dc63408e24c64d356677cd07da76d`; scene `339a754ab4dd636092aa9b3aceb777ea43684c47519f661576e161f822a0affc`; fixture `9dc29e53fd7ab721f0d6617493ac33b7a2d042113024985e2d27bbba14464d05`, unchanged from B.
- Original-sensor conformance:3 probes×360 beams PASS, max range difference0.0. Native observations:33 global maps,91 local maps,51 paths,676 delivered odom→base_link TF transforms.

For a concrete source/receipt example, first accepted nonzero native command source timestamp is1792982959436549867ns, DDS receive1792982959436604486ns, harness receipt monotonic195.551399133, sim2.10, source age.000262723s. First applied movement is sim2.15. Moving-output maxima: command source age.120675455s / receipt age.118640701s; sensor source age.161286441s / receipt age.139453153s, all below unchanged.25s. The source clocks are labeled separately; wall/DDS and monotonic values are not subtracted as if they were one clock. TF example source sim.05, receipt monotonic193.506237968, translation(.5,.95,0), yawpi/2. Complete samples are in the native receipt/artifact.

There are377 native controller missed-20Hz warnings; plant maximum wall gap=.094944501s and one startup deadline miss. These are retained performance limitations, not physical timing qualification. They do not explain away the first invalid path emitted before motion.

Artifact12624488425, name `c3-native-a70f22dd703502b6c6779946f34bd9c7261696c5-1`, expires2026-11-09T02:49:58Z. Downloaded ZIP SHA256 verified equal to GitHub digest `1786adfa172da15871d116c6dda966241537c174ea1fd2e4f17b2518f49bde4b`. Raw simulated maps/trace/scans remain in the artifact/local evidence, not Git.

B1 repeat1, empty, blocked, sensor_dropout and feasible2 are **NOT_RUN** because first feasible1 did not satisfy goal/path validation. Direct installed-checker calls on D0's synthetic raw-field cases are NOT_RUN; no fake native result is inferred from Python calculations. An atomic internal checker/TF-buffer/raw-grid packet is **INPUT_REQUIRED** for that exact branch-tracing claim only. These do not prevent rejection based on the observed emitted path and original geometry.

## Read-only cross-role state and reproduction

Latest observed C1 `c052db127f2952b693971642f0a33c8efcb43098` records successful integrated source CI40168592604 and already includes ROUND3 C3/D0 preparation. Its common browser collection fix is not reimplemented here. D0 ROUND5 was not published at the initial check. While this fixed B1 ran, new D0 `dc24b598e70dfd028a67b5bc5c11f3dcabb81ec3` appeared and its [ROUND5 audit](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/dc24b598e70dfd028a67b5bc5c11f3dcabb81ec3/docs/parallel-review/20261024/D0/ROUND5.md) was read. Its independent quantized-corner case has distance.54405882m and reconstructed cost78<T82 despite.58m support; C3 independently obtains78. This agrees that support correction alone is insufficient. D0's raw-field results are source reconstructions with native results null, not additional native runs. No D0 file was imported or modified and no waiting dependency was introduced.

```sh
python3 -m unittest discover -s experiments/competition_nav2/tests -v
# Existing prepared pinned D0 inputs and exact image lock; no hardware access.
cp experiments/competition_nav2/repro/image-lock.json /tmp/c3-round5-lock.json
python3 experiments/competition_nav2/container/manage.py build --lock /tmp/c3-round5-lock.json
python3 experiments/competition_nav2/run_narrow.py --variant omni_coverage --lock /tmp/c3-round5-lock.json --output /tmp/c3-round5-new-run
```

The hosted workflow uses network-none native containers, ROS domain193/localhost-only, namespace `/c3_nav2`, SIM_GT and fixed resource/artifact limits. Public Git contains source and small non-sensitive results only. Production consumer=null/live import=false. Physical stopping, gait, stairs, sensor fusion, Jetson performance and real robot motion are NOT_RUN.

## Local checks before source publication

C3 focused: 77 PASS (3.103 s); full repository Python: 2691 run, 2689 PASS / 2 SKIP (87.341 s); JavaScript `node --test tests/*.mjs`: 70 PASS; Ruff, secret scan, diff check and contract source pins PASS. All six previous generated candidate configurations equal the pre-ROUND5 source. The base command/Omni core, D0 adapter/pin, primitives and image lock have zero diff. Full-suite scope is unchanged common code; added path/coverage checks run in the C3 suite. Native B1 result is separately rejected above. Source common CI [40260839136](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40260839136), exact `a70f22d`, completed / FAILURE: both OS jobs fail existing browser E2E collection (`GO2_JOINT_NAMES` named export from CommonJS observed_joints.js). C1 already fixed this on its integration branch; C3 does not copy common files or claim branch CI green. The final report-only commit uses `[skip ci]`; its own CI is NOT_RUN, not inherited PASS. Source native CI40260839144 is also FAILURE for the actual B1 result. No identical full suite or native case is rerun for prose edits.

## Frozen handoff and one next task

C1 may review this C3-owned delta incrementally; **B1 is production-unadopted and rejected**, and real robot qualification remains NOT_RUN. Prior RPP general-scene success and ROUND4 A/B failures stay separate.

**One next task:** separately version and evaluate a native exact-pose full-footprint fallback for Smac lattice primitive poses/intervals, covering center-cost shortcut and coarse XY/yaw omission, with the retained first-path failures and valid rectangle corridor as regression inputs. Do not invent a parameter or silently patch installed upstream. This code-level candidate is proposed only; it was not implemented or executed in ROUND5. Current B1 is frozen.
