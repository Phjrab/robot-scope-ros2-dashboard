# D0 ROUND6 — independent review of the retained C3 checker comparison

## Decision: review complete; D0 frozen, navigation NOT ADOPTED

A new actual C3 stock/overlay comparison and source patch exist, so the request's
new-result branch applies rather than AWAITING_C3_RESULT. This is a small independent
review, not a second native run. Existing D0 ROUND5 input/export needs no correction.

- D0 base/remote: `dc24b598e70dfd028a67b5bc5c11f3dcabb81ec3`.
- C3 report HEAD inspected once: `d4bbee6b88277239cb1355b9b7037c3db935186b`.
- C3 actual tested code: `d33d2efc3a9bc25e21f45889c18b13ce543b2850`.
- C3 native run: [40276802563](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40276802563), FAILURE overall.
- Exact D0 final tested/submitted SHA and its terminal CI are in the delivery receipt;
  this report and the small review source share one commit, not a docs-only add-on.

AGENTS/status were checked. The earlier independent clone was not present in this
VM snapshot; a clean same-role clone was created without resetting or touching any
existing checkout. No main/PR/other-role writes, C3 source edits, native execution,
robot/network discovery, camera, service, deployment or motion. No new planner,
framework, render, configuration tuning or future C3 monitoring.

## Evidence and actual native versus reconstruction

C3's final [report](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/d4bbee6b88277239cb1355b9b7037c3db935186b/docs/parallel-review/20261024/C3/ROUND6.md)
and ROUND6_NATIVE/FAILURE JSON, source lock, C++ probe and patch were inspected.
Artifact 12630872211 was downloaded privately. ZIP SHA256 independently matched
`68dc02a516bf4f98354e7f14d1930dfe4321a619ce72f25f16b7b4a865acf107`.
Raw maps/trace/build artifacts are not committed. `result.json` retains only sparse
non-sensitive computed results and consumed-file hashes.

**OBSERVED retained evidence:** the probe directly calls installed C++ Smac
GridCollisionChecker, NodeLattice and MPPI CostCritic direct/score methods. A
protected-member setup supplies deterministic state, threshold82 and72 checker bins.
It is controlled synthetic class invocation, not arbitrary live planner state. The
stock and fixed executions use the same cases; loaded library and source provenance
are retained separately. Upstream 1.1.20 is pinned at a0970867. Runtime software
package delta is empty. This is stronger than a Python-only reconstruction but does
not recover the historical B1 atomic raw packet.

D0 checker_cases/coverage files are present in C3, hash-pinned to D0 dc24b598; the
local originals independently match both declared hashes. Raw ordinary center costs
in B1 point10/point16 tests are assigned synthetic bytes, not an inverse of published
OccupancyGrid. The initial invalid uniform253 corridor packet is not reused as the
final positive control.

## INDEPENDENT_RECONSTRUCTION: 16 fixed cases

[Small review](../../../../experiments/competition_vm/arena_robot_sim/revisions/native_checker_review_20261026/review.py)
reuses D0's original corner transform and applies Sutherland–Hodgman closed-cell
polygon clipping, independently of C3's SAT/helper. Verdicts are derived from raw
cells, geometry and unknown policy. The C3 `expected_collision` field is **not read
as an oracle**. Float32 pose conversion mirrors the input precision; this does not
claim bit-identical Smac fractional coordinate arithmetic.

All16 fixed static verdicts agree with independent geometry. The retained stock
results expose missed free-center/below-threshold corners, interior cells and the
point16 sparse cached-pose/center-lookup combination. `fractional_pose_full_branch`
also passes stock; it is not falsely counted as a reproduced fractional miss.
Point10 and point16 causes remain distinguished. Rotation primitive endpoint poses
are clear, middle pose collides; stock accepts the primitive and overlay rejects.

The positive .68m rectangle corridor remains accepted: fixed padded width .62m,
explicit walls at columns7/42, center216/perimeter253 in the native packet. The
circumscribed diameter is1.0683m, so a hard-circle gate would wrongly reject it.
Nonlethal inflation and allowed unknown remain accepted; allowed unknown does not
mask lethal. Actual footprint .87×.62m, raw .81×.56m and once-only margin .03m remain
unchanged, as do scene, original cone/forbidden geometry and .02m grid.

**SOURCE_SUPPORTED_INFERENCE:** isolated patch removes MPPI's zero-cost early skip
and conditional footprint gate, checks full polygon/interior cells, exact fractional
XY/yaw and lattice/analytic intervals. It does not merely increase inflation or
block all motion. Sweep is bounded sampled <=2mm corner displacement/.005rad, not
continuous-time proof. MPPI rollout point sampling is unchanged. Passing these16
cases is not unrestricted safety/performance acceptance.

## INDEPENDENT_RECONSTRUCTION: actual returned path segment

The actual archived observations, not C3's expected verdict, supply closed-loop
path index2 (170 poses), source sim6.049999999, received monotonic1455.862305634.
Segment97 endpoints are (0.6300741055,3.0100029845) and
(0.6284049847,3.0383361137), with common quaternion-derived yaw1.5707963705.
We independently divide this interval into15 subdivisions (16 poses, <=2mm XY).

- Both endpoints avoid published cell(15,129).
- **13 interior sample poses intersect the cell.** First u=1/15 has positive clipped
  area **7.428727453e-7 m²**, so this is not merely a floating-point zero-area touch.
- The unchanged original cone box x=[.05,.31], y=[2.37,2.63] does not intersect any
  of these16 poses. This narrow reconstruction is not a rerun of all33 paths.
- Both selected preceding and following published maps contain occupancy100 there.
  Before: source5.549999999/receipt1453.897779657; after:
  source7.499999999/receipt1455.875382448. Selection respects both source and receipt;
  the later map is explicitly an after-observation, not smuggled into prior evidence.
- All compared records use map frame. Published resolution .019999999552965164 is
  used, not silently rounded to .02 for this observed segment.

The observed path/grid discrepancy is preserved as FAIL. Published occupancy100
establishes its published lethal classification; it does not establish the exact
internal raw array at planner-lock time. Neither asynchronous agreement nor this
positive overlap proves the patch's historical execution branch. Atomic internal
raw grid plus path/pose association remains **INPUT_REQUIRED only for attribution**.

## Keep outcomes separate

C3's retained full-run receipt reports planner-only valid1/1; closed-loop truth
valid33/33 but published-grid valid32/33. Simulated actual applied-twist sweep has
no recorded contact/boundary violation, travels .955098978m, and ends SAFE_WAIT,
3.161866250m from goal. Those are C3 observations, not new D0 native passes.
The candidate is not adopted: path discrepancy, goal failure and121 missed20Hz
warnings remain. A zero tail does not turn an invalid path or failed goal into PASS.

C3 source CI40276802473 failed at the existing GO2_JOINT_NAMES CommonJS collection
error; C3 report-only HEAD uses skip-ci. Do not relabel that report as a tested CI
head or equate checker-stage PASS to whole native-run PASS.

## D0 verification and one remaining task

Dedicated independent review tests: **10 PASS**, including archive replay; no ROS
or native library run. Mandatory repository Python and relevant JS were run on the
unchanged baseline plus this small review: Python2691 tests, existing manifest failure1, VM socket errors25 and skip1; JS660 PASS; new Python compile PASS. Unrelated baseline failures are not fixed or counted as passes. Exact remote CI is finalized in delivery.
Old ROUND5 tests and C3's16 native cases are not added to D0's10-test count.

**One remaining task belongs to C3:** obtain the planner-locked raw costmap and
matching segment97/path packet to resolve this one published-grid discrepancy.
This does not authorize another run here. D0 review is frozen after publication;
no waiting for C3, new tuning or automatic follow-up.
