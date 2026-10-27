# D0 ROUND7 — independent review of C3 atomic snapshot reconciliation

## Decision: review complete and frozen; no checker change, navigation NOT_ADOPTED

The latest C3 result directly answers the new-run portion of D0 ROUND6's remaining
question. There is new atomic evidence, so a small independent review is warranted.
No existing audit, exporter, collision policy, planner, model or controller changed.

- D0 starting remote: `8664e3691188b47e2714d36f9d75ec6f9cf74b53`.
- C3 current report-only HEAD: `8aef2fb972af1358929774b85b642b6fc5f6c06b`.
- Actually executed C3 source: `cf7662123bf13c9c38d565c03a978a4b9ae357a2`.
- [C3 report](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/8aef2fb972af1358929774b85b642b6fc5f6c06b/docs/parallel-review/20261024/C3/ROUND7.md),
  [native run40296598053](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40296598053).
- Exact submitted/tested D0 SHA and terminal CI are in the delivery receipt. This
  report and review source belong to one commit, not a docs-only CI inheritance.

AGENTS and clean status were inspected. Old task clones were absent in this VM
snapshot; a clean same-role independent clone preserved current remote history.
Explicit D0 branch instruction overrides default main-only guidance. No reset,
clean, stash, force push, main/PR/other-role edits, robot/network discovery, camera,
services, deployment, commands, native rerun or automatic monitoring.

## OBSERVED retained evidence and provenance

Artifact12638597871 was downloaded privately and its ZIP hash independently verified:
`91a7d37428dc838e324de82152ff7f84082a0cd618546376e559dfb73fead404`.
Embedded source SHA matches cf766212. Checked diagnostic patch/header and retained
ROUND6 checker patch/helper hashes against build provenance. No original raw grid,
scan, path, map/PCD, model or build tree is committed. The new sparse JSON contains
derived review results and hashes only.

All **33** packet paths have one-to-one exact association with published paths:
header nanoseconds, every XYZ coordinate, every quaternion and map frame. Each
120,000-byte raw array has the declared dimensions, recorded unchanged-under-lock
flag, correct source, bounded footprint and null Costmap2D update stamp. This is
inspection of stored bytes/metadata, not a second capture or proof against recorder
tampering. The original archive hash and packet/raw hashes make substitutions visible.

**SOURCE_SUPPORTED_INFERENCE:** pinned upstream createPlan's existing Costmap2D
mutex encloses packet construction, search and supplemental checks. Diagnostic code
copies pre-search bytes and compares them with the array at finish; it does not
rewrite costs. Packet path is stored before optional upstream smoothing, so exact
published-path matches and this run's `smooth_path: false` are essential. Do not
generalize the recorder to post-smoothing paths. Capture/finish times are not sensor
or map-update timestamps. Disk/JSON work under lock can affect timing; warning counts
do not isolate controller computation or prove an overlay performance regression.

## INDEPENDENT_RECONSTRUCTION: two selected disputed intervals

[Review code](../../../../experiments/competition_vm/arena_robot_sim/revisions/atomic_snapshot_review_20261027/review.py)
reuses prior D0 polygon clipping, not C3 SAT or its expected verdict as an oracle.
The two reported indices select the question; actual poses, raw bytes and preceding
published maps determine the answer. Native parsed footprint, actual resolution
0.019999999552965164, map frame/origin/dimensions and shortest-angle interpolation
are preserved. Full polygon including interior cells is checked. A maximum2mm
corner-displacement/.005rad finite interval sampling bound is used, not continuous
sweep proof.

| Selected interval | Original raw map | Preceding published map | Independent result |
|---|---|---|---|
| invocation3 / path2 / segment49, cell(15,121) |253, nonlethal inflation |100, lethal |0 raw hits;3 of11 poses overlap published lethal cell |
| invocation7 / path6 / segment81, cell(15,130) |253, nonlethal inflation |100, lethal |0 raw hits;2 of16 poses overlap published lethal cell |

Both intervals avoid the unchanged original cone. Actual retained supplemental
checker verdicts are clear. Changing **only** the selected raw byte253→254 yields
collision at the same3/2 sample poses in independent reconstruction. This is a
synthetic diagnostic pair, not another native checker run or a policy relaxation.
Raw253 and published99 are inflation; raw254 and published100 are lethal. Ordinary
published bytes are not inverted into raw bytes. Unknown remains blocked.

Both next published maps have99 at the selected cell. They remain explicitly later
observations and are **not** substituted for the preceding-map validator. For
invocation3 the next map arrives about10.7ms after path receipt. Current source/frame
and receipt selection are retained in result.json. The old asynchronous discrepancy
is explained, not deleted or labeled an actual body collision.

Exact raw bytes for historical ROUND6 segment97 remain **INPUT_REQUIRED**. The new
path is not the old170-pose path. This review establishes the current pair's snapshot
difference; applying the same explanation to the historical packet remains inference.
No unchanged rerun is requested merely to recover unavailable historical bytes.

## Keep partial validation and navigation outcome separate

C3 reports all33 paths passing locked raw-grid/original truth sweeps (64,818 finite
samples), versus31/33 passing earlier published grids. D0 independently verifies
all33 identities, but recomputes geometry only for the two intervals above; do not
claim a second full33-path geometry run. C3's previous16 native cases were not rerun.

D0 directly inspected628 retained virtual-plant records: no recorded contact or
boundary-positive sample, final actuator[0,0,0]. These counters are not an independent
continuous body/foot collision proof or real Go2 evidence. C3's native receipt still
reports SAFE_WAIT/ABORTED, traveled.953508738m, remaining3.161727160m and104 missed20Hz
warnings. Goal failure remains; no navigation adoption follows from correct paths.
Actual physical gait/cargo envelope and stopping distance remain unqualified.

## Checks and one next task

New dedicated D0 tests: **8 PASS**, including exact archive reconstruction and
negative source/frame/path/byte-length/immutability guards. Synthetic tests retain
nonlethal inflation acceptance and lethal/unknown rejection. Mandatory repository
Python:2691 tests, existing manifest failure1, VM socket permission errors25, skip1.
JavaScript:660 PASS. New Python compilation and diff check PASS. These baseline
failures are not changed or relabeled as passes. No new native execution. Exact
remote CI outcome is finalized in the delivery receipt.

C3 source commonCI40296598034 failed at the documented GO2_JOINT_NAMES browser import;
native run40296598053 failed overall despite successful diagnostic capture. C3
report-only HEAD is NOT_RUN [skip ci], not a successful source CI. D0's exact-head CI
is separately checked at submission.

**One remaining task belongs to C3:** isolate controller progress/timing using the
retained atomic-valid paths and command/receipt records. This is a proposed bounded
offline diagnosis, not authorization here to tune, launch another native run or
deploy. No additional checker patch is supported by this evidence. D0 freezes after
this submission and does not wait for or monitor C3.
