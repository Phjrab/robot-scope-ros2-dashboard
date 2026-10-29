# D2 perception handoff — offline candidate, no runtime integration

## Pins / publication

- Branch: `review/20261029-x-d2-perception`
- Fresh ordinary clone, actual BASE: `f469155c2b0c505f3e472e878f75029d7b8d39df`
- Tested source commit: `ade52881f917ec63a73d443ca2f3ffa822077f42`
- Final publication SHA: resolve this document's containing Git commit / the
  branch head; the actual immutable GitHub SHA is recorded in the delivery
  message. A commit cannot literally contain its own hash. Git-data publication
  may have a different commit ID from the local tested source; tree equality and
  every changed remote blob are checked before reporting completion.
- C1 dependency: `2402c02c6f91ba54064894b21735e01b98610acd`, read-only export of
  `robot_dashboard/expansion_contracts/messages.py`, actual
  `ObstacleFrame.from_dict` PASS. No copied/merged C1 code or duplicate validator.
- D1 is not a code dependency. No D1 code copied; D3 owns collision/native tests.

Only four owned prefixes changed: `robot_dashboard/obstacle_fusion_core/`,
`tests/expansion_d2/`, `experiments/expansion_20261029/d2_perception/`,
`docs/parallel-expansion-20261029/D2/`. Existing work and latest base preserved.

## Implemented

Deterministic voxel-connected LiDAR geometry, slope-plane uncertainty-aware
filtering, stamped self geometry, observed extent/uncertainty and independent
novelty; calibrated depth-optical deprojection, Brown-Conrady inversion and
cross-camera reprojection; foreground distribution/background rejection; native
model input/hash/class adapter without model execution; unique geometry/time
association with conservative union; bounded local tracking with epoch/map
reset, retired-generation rejection, occlusion and no expiration-clearing;
separate validated fresh free-ray evidence; pure Python APIs and offline CLI.
No services, UI, ROS publishers, camera acquisition, or mission-policy duplication.

## Reproduce from repository root

```sh
python3 -m unittest discover -s tests/expansion_d2 -v
python3 -m experiments.expansion_20261029.d2_perception.reproduce \
  --output /tmp/d2-baseline.json --fixture /tmp/d2-fixture.json
python3 -m robot_dashboard.obstacle_fusion_core \
  /tmp/d2-fixture.json --output /tmp/d2-output.json
python3 -m experiments.expansion_20261029.d2_perception.check_c1
# Required unmodified aggregate command (known VM failures, see below):
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
# After the original known denials, do not retry those operations:
python3 -m experiments.expansion_20261029.d2_perception.regression_without_known_blocks
```

C1 checker needs the pinned Git object available (`git fetch origin` in a fresh
clone if necessary); it creates a temporary read-only dependency export and
never imports current remote HEAD. Synthetic data is generated in `/tmp`; no
original video, weights, PCD, rosbag, environment files, credentials or generated
point cloud is committed.

## Evidence / test results

- UNIT: **23/23 PASS** on final source. Covers 0/1/2 cones, wall, low 8 cm cone,
  slope, self geometry/staleness, invalid/range bounds, novelty and coverage,
  depth scale 0.001, optical-axis transform, intrinsics/distortion, invalid and
  background-only depth, wrong/unverified extrinsics and different cameras,
  image-only/LiDAR-only/depth-only/fused observations, ambiguous nearby objects,
  crossings, occlusion/movement/removal, stale/reordered frames, map jumps,
  retired epochs, independent clearing, deterministic replay, memory bounds,
  disconnected component overflow and model artifact/hash/class identity.
- SYNTHETIC: fixed 15-run baseline, 1,862–2,246 points; 0/1/2 cones plus wall
  produce 1/2/3 objects. 984 ground and 3 body points filtered per scene.
  Final recorded p50 **7.59 ms**, p95 **11.32 ms**, max RSS **26,096 KiB**;
  frame-budget drop rate 0 in this tiny fixture. Not a stress/load benchmark.
  See `baseline.json`; timing is VM-only, not Jetson.
- C1 exact-SHA wire validation: **PASS**, synthetic 2-cone frame.
- CLI / import compilation smoke: **PASS**, no ROS/model/process side effect.
- JS: **699/699 PASS**, no skips.
- Required unmodified full Python: **FAIL**, 2,995 tests in 101.535 s,
  **36 errors, 11 skips**: 25 VM socket `PermissionError: [Errno 1] Operation not
  permitted`; 11 unavailable `cv2`. Existing 11 skips: ten optional cv2 replay
  modules plus one optional rosbags test. Exact cases are retained in
  `original_regression_cases.txt`, known environment exclusions in JSON.
  No full-suite/baseline pass is claimed. This run preceded the final two focused
  additions (model identity and disconnected-component bound).
- A final filtered regression excludes only those exact 36 original cases; it
  is explicitly **not** an unmodified full-suite pass. An initial exclusion-ID
  typo was caught and the run interrupted; one socket case was inadvertently
  retried and remained denied. The exact ID inventory was then checked against
  discovered tests before execution. No permission escalation/bypass attempted.
  Final filtered result: **2,997 discovered, 2,950 PASS, 47 SKIP**,
  100.182 s. These skips are the 36 documented blocked cases plus the original
  11 optional-dependency skips. No new failures.

Environment: selected dot VM, Linux 6.18.55 x86_64, Python 3.12.14, NumPy;
sequential heavy execution after D1, no sweeps. No user Mac or robot access.

## Explicit remaining evaluations

- `SEMANTIC_MODEL_INPUT_REQUIRED`: real cone weight + class manifest + independent
  labeled test clips. Synthetic detection and hash checks do not prove accuracy.
- Real calibrated RGB-D/LiDAR replay: `INPUT_REQUIRED` for recordings, actual
  intrinsics/distortion/extrinsics and clock correspondence. Arrays test math,
  not actual calibration accuracy or real sensor latency.
- `REPLAY_REAL`: NOT_RUN; `NATIVE_NAV2_SIM`: D3 responsibility, not claimed here.
- `DEVICE_NOT_RUN`: robot geometry/joints, calibration, Jetson load, live novelty,
  sensor motion/deskew, costmap ingestion, planner/controller use and stopping
  distance all unverified. All output Nav2/ingestion/controller flags stay false.

See [INTEGRATION_POINTS.md](INTEGRATION_POINTS.md) for API inputs, conservative
failure policy, C1 size-limit caveat, C3 display fields, C4 future connection
points and D3 usage. No shared file modifications are proposed for this branch.

**Next one action:** C4 supplies one calibrated, timestamped recorded sensor
packet through this core in an isolated fixture, retaining observation-only mode.

## Publication / static-check follow-through

Initial remote publication `8b47a3fb05a983a9f22b738b959afcdd63980ea9` was fetched
back: all 14 changed blobs and complete tree matched local bytes. Push triggered
CI run 40829033258. The subsequent formatting-only follow-up removes E701/E702
violations; **AST equality was asserted for all three core Python files**, then
23 focused tests, CLI and pinned C1 validation passed again. Full repository
`ruff check robot_dashboard scripts` and tracked-source secret scan both PASS.
Ruff 0.11.13 was installed only under `/tmp/d2-quality`, not in repository or
shared dependencies. Earlier numerical/full-safe-regression results remain for
identical ASTs. Final CI outcome and immutable follow-up SHA are in the delivery
message; no workflow/shared-file changes were made to obtain a green result.
