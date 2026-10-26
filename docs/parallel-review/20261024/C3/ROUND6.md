# C3 ROUND6 — native checker fixed on bounded cases; navigation candidate frozen

**CHECKER_REPRODUCED and CHECKER_FIXED are PASS. The navigation candidate is not adopted.**
The actual stock/fixed C++ comparison passes all16 fixed cases. The first planner-only
path is valid, but the one permitted closed-loop feasible1 run has one published-grid
path discrepancy and fails to reach the goal. No further checker candidate, retuning,
repeat or regression navigation case was executed after that outcome.

Actual tested code: **`d33d2efc3a9bc25e21f45889c18b13ce543b2850`**.
Native [run40276802563](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40276802563)
completed **FAILURE**. This final report is a docs-only submission over that tested
source; its SHA is supplied in the external receipt. [Native receipt](ROUND6_NATIVE.json),
[single remaining path discrepancy](ROUND6_FAILURE.json),
[earlier checker checkpoint](ROUND6_CHECKER.json), [initial stock packet](ROUND6_STOCK_INITIAL.json).

| Assessment | Actual result |
|---|---|
| CHECKER_REPRODUCED | PASS: calls to installed stock Smac/NodeLattice/CostCritic reproduce omissions |
| CHECKER_FIXED | PASS: same final16 raw-field cases; negative cases rejected, positive corridor/inflation/allowed-unknown cases accepted |
| PLANNER_PATH_VALID | **FAIL overall**: planner-only1/1 PASS; closed-loop33/33 original-truth checks PASS,32/33 published-grid checks PASS |
| CLOSED_LOOP_GOAL_REACHED | FAIL: accepted UUID, ABORTED6, SAFE_WAIT; .955098978m traveled,3.161866250m from goal |
| ACTUAL_SWEEP_SAFE | PASS for this simulated applied-twist bounded sweep; contact/boundary/HOLD-nonzero all0 |
| RUNTIME_BUDGET | FAIL: planner1Hz warning and121 controller missed20Hz warnings; periods/CPU/TTL unchanged |
| ROBOT_QUALIFIED | NOT_RUN |

PASS here refers to the stated finite tests and sampled virtual sweeps, never universal
continuous collision proof, hard realtime performance or physical robot qualification.

## Preserved baseline and exact scope

Starting/remote C3 HEAD was `86e73f8349581c26dc3af59505b55407b3d0412c`, clean existing
independent clone on `review/20261024-c3-nav2-benchmark`. Main remains
`104692fa0070ef085eee918913ea05fdb2d88c05`. ROUND5/FAILURE/NATIVE and read-only D0
`dc24b598e70dfd028a67b5bc5c11f3dcabb81ec3` ROUND5 were reviewed. B1 a70f22dd/run40260839144
remains rejected: .58 applied, .9611m movement, no actual contact,15/51 truth-invalid
and51/51 grid-invalid paths, no goal; later progress/Spin failure and377 missed20Hz
warnings are preserved. None of those old tests are counted as new ROUND6 passes.

Only C3 experiment/workflow/review paths changed. No other-role writes, common
integration, main merge/push, PR, robot/network discovery, camera acquisition,
service changes, deployment or physical motion. No past time contract, binding,
replay/fixture/installation work was reopened. Runtime stays in network-none
containers with virtual sensors/actuator, SIM_GT, ROS domain193 and localhost only.

All seven prior generated RPP/MPPI/SE2/B/B1 configurations equal the starting source.
New `omni_checked_overlay` YAML equals B1; **both actual runtime params.yaml and
fixture.json equal the retained B1 artifacts**. D0 source83f4ee8d and manifest
1e995e63 remain pinned. Raw body .81×.56m, once-padded .87×.62m, padding0,
resolution.02, inflation.58, primitives, weights, velocity/acceleration,65s goal
budget, tolerances, sensor period.2, TTL.25 and runtime4CPU/4GB are unchanged.

## Actual C++ reproduction and the one source correction

The small executable links the real Smac Lattice and MPPI critic libraries. Its
protected-member seam initializes deterministic CostCritic state while calling the
original `inCollision` and `score`; it also calls `NodeLattice::isNodeValid` and the
native perimeter checker. D0's actual published results/checker_cases.json and
coverage.json are copied read-only and hash-pinned for evaluation. Synthetic fields
assign raw bytes directly; there is no lossy OccupancyGrid inverse.

Final input SHA256: `569d23d9375ca1d960ac68fb7835ba415dd3255e9e145bfd0157a5c66633322d`.
Both stock and fixed classes use this same file. Observed stock behavior:

- Center0 and78<T82 skip full-body collision in Smac and in both CostCritic direct/score paths, despite native actual-pose perimeter254.
- Synthetic B1 point10 has actual center80 and stock lookup80; the collision is missed.
- Synthetic point16 has actual center93 but stock integer lookup0; actual-pose perimeter254 differs from cached-pose0. MPPI rejects, Smac accepts. This does **not** prove the historical B1 internal branch or a full-branch Smac execution for point16.
- Interior lethal/disallowed unknown cells evade perimeter-only checking. Allowed unknown cannot be permitted to mask a lethal cell.
- Lattice accepts a rotation whose endpoint poses are clear and native middle-pose check collides.
- The final D0-style .68m corridor has center216/perimeter253 and is accepted by both stock and fixed classes. The .62m rectangle fits; a circumcircle is not used as the body.

The initial corridor packet used uniform253 plus one center200, which exposed the
stock integer lookup reading a different cell; that input is retained separately
and is not called a physical corridor failure. The final positive control uses the
explicit wall-distance inflation recipe and records the actual stock center/cached
pose. Historical B1 sparse cells are labeled synthetic raw-field reconstructions,
not recovered raw snapshots. The old atomic checker packet alone is INPUT_REQUIRED.

The [patch](../../../../experiments/competition_nav2/overlay/nav2.patch) and
[helper](../../../../experiments/competition_nav2/overlay/c3_exact_footprint.hpp)
make Smac use fractional emitted XY and actual yaw, with complete convex polygon/
closed-cell overlap including interior cells. MPPI bypasses both its free-center
skip and conditional footprint gate when consider_footprint=true. Nonlethal costs
remain scores; unknown follows caller policy, exterior is blocked and unknown does
not mask lethal cells. Lattice checks emitted primitive points, starts/joins and
analytic transitions during search. A returned-path/start-connector check is
supplemental; the already-disabled smoother stays disabled. The planner actually
returns a valid path and the plant moves, so this is not an always-SAFE_WAIT guard.

Sweep bounds are <=resolution/10 corner displacement (2mm here), <=.005rad and
max4096 subdivisions, failing closed beyond the bound. This is bounded numerical
checking. MPPI's existing rollout point sampling stays unchanged; independent actual
plant sweep remains mandatory. CostCritic alone disables fast-math for reliable
finite geometry checks; no weights, frequencies or resource limits are adjusted.

## Separate source, image and loaded-library identity

Upstream tag1.1.20 resolves to **`a097086719c88f781aa59788eca29ac6ca5e56db`**.
[Source lock](../../../../experiments/competition_nav2/overlay/source-lock.json)
records every modified original file hash and D0 input hashes. The native receipt
records post-patch hashes. Only nav2_smac_planner and nav2_mppi_controller are built
under `/opt/c3-overlay`; `/opt/ros/humble` is preserved. Already locked GCC/CMake/
colcon are used, with **no apt additions/upgrades and an empty runtime package delta**.
Full package TSV SHA256 remains `45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de`.
Original base remains `ros@sha256:566b87e6dfc48392189a9c32e594e84060fa9948de93b04e536f39475a1f6963`.

- Patch SHA256: `1f099f26287ee13355783a21d69f46e113464dea3c79fa316c34f08283753c43`.
- Helper SHA256: `5207de4150b4c3326315a32410b3a87afb3390bf1bc942bd8a8520fefc06da05`.
- Actual overlay image: `sha256:2ac0f0d2475f1945fc22598ec2472d2f3a1c655d0596069bbff2555394b202e8`.
- Loaded overlay Smac Lattice: `29edd1a762e6db296f1274914d5188619d0917fa8ede7593e9f1e032c02e4193`.
- Loaded overlay MPPI critics: `483a7ee177bbee2aef1e57549ad16334605637c9171189215aaf8df8bd5865db`.
- Loaded overlay MPPI controller: `62b5da5fbba1c5eef5985afe3cd0c763995f3a5c7d5775225de91968be242d15`.

The first two overlay library hashes are identical in the successful earlier
checker checkpoint and final probe/runtime processes. Stock Lattice is2c4c5568…6679b,
stock MPPI critics570f0e69…e6f7b; changed binaries are never represented as stock.
The runtime collector explicitly requires the appropriate stock/overlay prefix.

## Actual planner-only and one closed-loop result

Planner-only ComputePathToPose accepted a real UUID and succeeded(status4), returning
177 poses. Its one published path passed2361 full-body truth/grid interval samples.
Actuator/raw-command counts and distance were0. ROS action planning duration was
1.449999999s; native planner warned that its1Hz loop ran at.6897Hz. This is total
reported action duration, not isolated A* compute time. Configured search budget1s
is unchanged. Both servers' overlay libraries and original inflation layer were
verified before this action.

Only then did the one original feasible1 NavigateToPose run execute. It recorded
33 paths and64847 interval samples: original truth0 invalid, published grid1 invalid.
Actual motion .955098978m, final pose(.517586727,1.888182660,1.838789150), remaining
goal distance3.161866250m. Action aborted6 after `Failed to make progress` at native
wall1792994449.453121894; Spin predicted collision at1792994451.217251599, and goal
failed at1792994451.256656792. No terminal gate fault was latched. Sim31.25s/wall31.3052s,
122 controller and15 behavior raw commands; final command[0,0,0], >=2s zero tail and
graceful cleanup with no remaining processes. Applied-twist sweep/contact/boundary/
HOLD checks passed; whole validation failed on the single path/grid discrepancy.

The controller has121 missed20Hz warnings. Its121 receipt gaps have mean.188014s,
median.188062s and max.243846s; these are receipt timings, not isolated compute
latency. Moving-output source/receipt ages remain below unchanged.25s:
command .231693/.231242s; sensor .159077/.144116s. Neither the periodic budget nor
goal success is claimed. Feasible1 repeat1, empty, blocked, dropout and feasible2
are all NOT_RUN. The candidate is frozen after this first actual outcome.

## One unresolved grid discrepancy and next task

[Exact packet](ROUND6_FAILURE.json): closed-loop path index2, source sim6.05,
receipt sim7.50 / monotonic1455.862305634,170 poses. Segment97 has an independently
sampled pose(.629962831,3.011891860,1.570796371) overlapping published lethal cell
(15,129). Original truth is clear. Both the preceding published map(source5.55,
receipt1453.897779657) and next map(source7.50, receipt1455.875382448) retain that
cell. Map selection requires both source and receipt precedence; no future receipt
is silently selected. These asynchronous maps are still **not an atomic raw
snapshot under the planner lock**.

The unchanged C++ helper rejects an offline synthetic raw254 cell(15,129) at that
sample. This is a local reconstruction, not an extra native run or proof of the
past internal costmap. Exact attribution remains INPUT_REQUIRED for an atomic
raw-grid/pose packet; the observed discrepancy remains FAIL rather than waived.

**One next task:** capture the planner-locked raw costmap and matching path segment,
and resolve this single sim6.05/segment97/cell(15,129) mismatch before treating all
emitted paths as valid. Goal/progress and runtime limitations remain recorded; no
additional tuning or candidate search is performed in this round.

## Checks, CI and evidence preservation

Latest source checks: C3 **79 PASS**(3.081s); repository Python2691 run,
**2689 PASS /2 SKIP**(83.503s); JS **70 file-level tests PASS**; Ruff, secret scan,
contract hashes and diff checks PASS. Prior successful suites are not added to these
counts. The actual16-case native checker comparison is separate. Common source
[CI40276802473](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40276802473)
failed on both Ubuntu jobs at the existing GO2_JOINT_NAMES CommonJS browser test
collection error. C3 does not edit C1's common integration files. Final docs-only
HEAD uses `[skip ci]`: its CI is NOT_RUN, not inherited PASS.

Artifact12630872211, `c3-native-d33d2efc3a9bc25e21f45889c18b13ce543b2850-1`, expires
2026-11-09T06:01:01Z. Downloaded ZIP SHA256 matches GitHub digest:
`68dc02a516bf4f98354e7f14d1930dfe4321a619ce72f25f16b7b4a865acf107`.
Raw virtual maps/scans/trace remain in artifacts/local evidence, never public Git.

Earlier attempts are preserved, not counted as navigation cases:40274348913 and
40274599835 were probe library-link discovery failures;40274895639 executed but
could not persist its packet under capability-free root;40275256434 captured the
initial actual stock failure;40275939298 passed fixed16/16 but its old /opt/ros-only
provenance filter aborted before any planner action. The final source fixes only
that collector connection, retaining the same checker candidate and input. The
first genuine planner-only action and one closed-loop run are the final run above.
C1 can inspect the C3 delta incrementally; there is no automatic integration,
production adoption, PR or authorization to replace the production controller.
