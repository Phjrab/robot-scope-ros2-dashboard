# C3 ROUND7 — atomic planner snapshot explains the reproduced grid mismatch

**The current mismatch is a confirmed difference between the planner's locked raw
costmap and an earlier asynchronously published grid. No further checker correction
is justified. The navigation candidate remains NOT_ADOPTED because goal/progress
and runtime tests fail.** One instrumented feasible1 run is complete and frozen.

Branch: `review/20261024-c3-nav2-benchmark`. Starting local/remote HEAD:
`d4bbee6b88277239cb1355b9b7037c3db935186b`, clean. Actually executed source:
**`cf7662123bf13c9c38d565c03a978a4b9ae357a2`**. Final submission adds only this report
and [native receipt](ROUND7_NATIVE.json)/[map and model evidence](ROUND7_INPUTS.json).
Final submitted SHA is provided in the external submission receipt.

## Atomic raw grid versus published grid

All **33 returned paths** matched exactly to their respective planning invocation:
path header nanoseconds, all XYZ coordinates and all quaternions. All 33 raw arrays
were unchanged from capture before search to completion under the same Costmap2D
mutex. Independent validation examined **64,818 interval samples** with the original
once-padded body. These are finite numerical checks, not continuous collision proof.

| Evidence | Raw grid used by planner | Published grid | Finding |
|---|---|---|---|
| Invocation3, path index2, source sim6.049999999, segment49, cell(15,121) | raw **253**, native supplemental checker **clear**, independent raw-grid sweep clear | preceding sim5.55 grid has **100**; next sim7.55 grid has99 | **CONFIRMED snapshot difference**;253 is nonlethal inflation, not254 |
| Invocation7, path index6, source sim10.7, segment81, cell(15,130) | raw **253**, checker/independent sweep clear | preceding sim10.2 grid has100 | **CONFIRMED snapshot difference** |
| All current33 paths | **33/33 PASS** against captured raw grid; **33/33 PASS** against original D0 truth | **31/33 PASS**,2 discrepancies | Previous asynchronous validator still reports FAIL; not silently waived |
| ROUND6 source6.05, original segment97, cell(15,129) | Exact historical raw bytes **UNAVAILABLE** | Historical before/after maps both100 | Same mechanism **INFERRED**, historical exact-byte attribution **UNRESOLVED** |

Invocation3 capture/finish ROS times are6.05/7.55s. Its raw file SHA256 is
`ff1a97f642263682cb8b70d020570d2475f78db6df85e1279de44283665a498b`.
Its published path receipt is552.283266056s monotonic; the selected preceding map
receipt is550.301802428 and the next map receipt552.293983140, about10.7ms later.
The next map is not substituted for the preceding-map validator.

The new index2 path has172 poses versus ROUND6's170. Its bounded sampled geometry
does **not** intersect old cell(15,129). That cell is253 in the new atomic snapshot,
100 in the preceding grid and99 in the next grid. This is not the missing historical
segment97 packet and is not represented as proof of ROUND6's internal byte.
Only exact historical attribution remains `INPUT_REQUIRED`; it does not require
another unchanged rerun, nor invalidate this new confirmed snapshot comparison.

Current raw/published frames are both`map`, origins both(0,0), resolution both
0.019999999552965164m. Native footprint coordinates differ from configured values
by at most2.384185738e-9m due to upstream float parsing; this does not explain a
raw253 versus published lethal100 difference. No frame transform, grid stamp or
sensor drop was rewritten. Costmap2D has no own update stamp: packets explicitly
store null there and separately retain ROS capture/path time, steady process epoch,
start/goal, footprint, each checked segment/heading and actual checker verdict.

A local replay of the **unchanged C++ helper** at invocation3/segment49 accepts the
captured raw253 field. Changing only cell(15,121) to synthetic raw254 makes both
pose and segment sweep reject. This is one diagnostic positive/negative pair,
not a new native Nav2 execution or a repeat of the16 ROUND6 cases. The actual native
verdict comes from the instrumented planner itself. No unknown/lethal policy,
normal .68m rectangular corridor, inflation, body size or safety bound was relaxed.

## Small implementation and preservation

[atomic-diagnostic.patch](../../../../experiments/competition_nav2/overlay/atomic-diagnostic.patch)
is applied **after** the unchanged ROUND6 `nav2.patch` only with `build.py --diagnostic`.
[c3_atomic_packet.hpp](../../../../experiments/competition_nav2/overlay/c3_atomic_packet.hpp)
records an opt-in bounded packet under `createPlan`'s existing map lock. It does
not publish or modify costmaps/checker results. Raw files stay in execution artifacts,
not Git. Maximum64 invocations/1MiB per grid; actual33/120,000bytes each.
The runner enables capture only for a lock carrying the explicit diagnostic pin.
One recorder C++ regression verifies opt-in, exact bytes, source/time identity and
mutation detection. Source contract and build provenance include the diagnostic hashes.

ROUND6 helper, checker patch,16 cases, D0 inputs, original .81×.56m body,
.03m single margin/.87×.62m effective body, primitive, source/dependency pins,
runner/validator, TTLs, velocities and resource limits remain unchanged.
**Actual params.yaml and fixture.json equal ROUND6 byte for byte.** Original RPP,
B/B1 and other-role files are untouched. No completed time/config/replay/fixture
or16-case work was restarted. The hosted runner materialized the same pinned runtime
for this isolated build; no host/robot Nav2 installation was changed.

The workflow runs exactly **one closed-loop feasible1**, with no planner-only,
repeat, alternate fixture, new arena, controller search or broad tuning. It omits
the already completed stock/fixed16-case runs. Existing run_checked.py remains intact.

## Separate navigation, runtime and safety results

Native [run40296598053](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40296598053)
completed **FAILURE**; diagnostic acquisition succeeded. NavigateToPose accepted an
actual UUID and returned ABORTED6/SAFE_WAIT. Traveled **.953508738m**; goal remains
**3.161727160m** away, yaw error.269800785rad. No terminal gate fault was latched.
Original simulated contact/boundary/HOLD-nonzero counts are all0; minimum conservative
clearance.054m. Sim31.4s/wall31.4433s, one plant deadline miss, max gap.0920654s.
Final twist[0,0,0],3.1s final zero tail; graceful cleanup, return codes[0,0], no processes.
This is virtual applied-twist evidence, not physical gait/braking qualification.

Native logs report `Failed to make progress`, then `Collision Ahead - Exiting Spin`
and `Goal failed`. There are **104 missed20Hz controller warnings** and3 planner1Hz
warnings. Controller receipt gaps:103, mean.223248s, max.258713s; these include
transitions and instrumentation, not isolated compute latency or a performance
comparison. Configured planning/goal/CPU limits were unchanged. Moving applied outputs
have maximum command source/receipt ages.245358/.245028s and sensor ages
.165802/.144175s, below unchanged.25s. Drops/gaps are retained in the artifact.

Omni `vy` is actually emitted and applied:103 nonzero controller samples, maximum
absolute.022350905m/s versus configured.08m/s. The channel is not absent; this does
not establish useful lateral progress or identify a causal controller bottleneck.
**One next offline task:** isolate the remaining controller progress/20Hz failure
using these retained atomic-valid paths and timing records. No tuning or further
native navigation execution is performed in this submission.

## Latest similar map and physical Go2 information

Saved device records and current origin/main identify `map_20261023_135003.pcd`,
ID`b9087113da92a1f2b477e932`, revision
`58991300bd1aac8c872fd45cafdda6f3eaf2026e4e578d411a4cdba439d31f6a`,
saved2026-10-23T13:50:05.605707+09:00,41,073 points, `camera_init`/m. Original SHA256
`628653237cc7fb146793a6b970a5636f6562b5b3b73b57cf64fcf9badaead97a`.
PCD encoding beyond the recorded format was not re-read. The latest original bytes
were absent from checked local repositories/private work areas:
**MAP_INPUT_NOT_AVAILABLE** for using that latest map offline. No device connection.

The already available October18 PCD was read in place: full25,666 finite XYZ points,
binary XYZI, original hash`c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8`.
It was used only for format/count/bounds inspection. No raw map was copied into new
Git content. Neither map is the competition truth; `camera_init → arena_design`
remains unverified and is never assumed identity or injected into the D0 fixture.

Existing official-model asset provenance pins Unitree source`f3772ce5…`.
At its illustrative fixed joints(hip0,thigh.75,calf−1.5), the simplified visual meshes
have static XYZ extents approximately **.68846×.32280×.42290m**, relative to model base.
These are calculated model extents, not measured dimensions or full gait envelope.
The retained local URDF base collision box is.3762×.0935×.114m and excludes head/legs
when considered alone. Cargo-plate verification explicitly describes generic,
provisional mounting geometry, not the installed equipment envelope. No value
replaces or shrinks the VM footprint. Model/hash/collision details are in
[ROUND7_INPUTS.json](ROUND7_INPUTS.json).

Stored control acceleration limits(.8/.6m/s²) and command timeouts are software
settings, not measured physical deceleration. **PHYSICAL_FOOTPRINT_UNQUALIFIED** and
**STOPPING_DISTANCE_UNMEASURED** remain. Height, slope/step capability and foot
collisions are also not qualified by this planar simulation.

## Submission checks and C1 handoff

- Source checks: C3 **80 PASS**; Python **2689 PASS/2 SKIP**(2691 run); JavaScript
  **70 file-level PASS**. Ruff, secret/diff checks, both sequential patch applications,
  preservation/hash contracts and actual config/fixture equality PASS.
- Common [CI40296598034](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40296598034)
  failed on both Ubuntu browser jobs: `GO2_JOINT_NAMES` named export/CommonJS error.
  Other-role integration files were not changed. Final docs-only HEAD is
  **NOT_RUN [skip ci]**, not inherited PASS.
- Nav2 upstream1.1.20 commit`a097086719c88f781aa59788eca29ac6ca5e56db`;
  separate overlay image`sha256:ba5f1995bcfe688850e7ae04444d878113a8cf46e7c79b728bfc1cfce0ee6c00`.
  Actual loaded Smac hash`4d00498a14fb68c1c2a6c6575a8209c8ad5ea84779a005abe4dc93d4417f5bc1`;
  MPPI critics/controller remain ROUND6 hashes. Package TSV hash remains
  `45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de`, apt delta empty.
- Artifact12638597871 expires2026-11-09T09:09:12Z. Downloaded ZIP matches GitHub digest
  `91a7d37428dc838e324de82152ff7f84082a0cd618546376e559dfb73fead404`.
  Raw simulation packets/scans remain artifact/local evidence, not public Git.

C1 can review this diagnostic/evidence incrementally. **C3 does not block dashboard,
LiDAR or VSLAM observation integration**, and adds no shared dependency/gate.
Keep operating Nav2/RPP and control-bridge settings; never install this experimental
overlay into Jetson `/opt/ros`. No main/PR/other-role changes, device SSH/HTTP,
map→odom/initialpose changes, ARM/goals/cmd_vel, services or deployment were performed.

Device applicability requires separate C1 authorization: stationary read-only
map/state verification first; supervised low-speed movement separately, only after
onsite gait/mount envelope, measured stopping distance, accurate map/keepout,
actual actuator ZERO and physical stop means are confirmed. The user is not asked
to supply guessed dimensions. Current results do not approve autonomous operation.
