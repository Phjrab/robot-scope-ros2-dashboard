# ROUND2 — actual C4 → D2 → C1 ports, preserved observation evidence

## Pins and corrected inspection facts

- Starting published D2: `c0d266e290a2d29c173d3b83520f8c96efea9447`.
- Tested numerical/port source: `b7495a7c57ee3845113e04da83e7f9256f68f36c`.
  Subsequent report/example-generator changes do not alter core implementation.
- C1 pinned once: `54629c793ad4ae0ea88127f00ed1b7f8805fc4e2`.
- C4 pinned once: `b9d700d754f0d3d43b9afdcffcb86e9deb7b1020`.
- Contract is the actual C1 `schema_version="0.1"`; no independent validator.
- Final published HEAD is the containing commit/branch and immutable delivery
  link. Git-data publication preserves the remote parent and verifies complete
  tree + every changed blob against the tested local tree; local and remote
  commit metadata can differ. No self-referential commit hash is fabricated.

The prompt's `obstacle_perception_core/` and `obstacle_replay_bench/` do not exist
in this D2 branch. Existing `obstacle_fusion_core/`, `tests/expansion_d2/`,
`experiments/expansion_20261029/d2_perception/`, and D2 docs were retained.
No rewrite or package rename. Own remote/local histories were reconciled with a
merge of **the same D2 branch**, preserving all commits and identical prior tree;
no other role/main code was merged or copied into the submission.

Actual limits differ by boundary:

| Boundary | Actual limit |
|---|---:|
| C1 `messages.canonical` / ObstacleFrame wire | 128 KiB |
| C1 `SceneSnapshotService.ingest`, default per sample | 16 KiB |
| C1 latest slots aggregate | 80 KiB |
| C4 `_Pipeline` frame envelope | 512 KiB |

Passing a wire validator alone never proved the default service could ingest it.
This round executes both actual boundaries, including C4's actual sink wrapper.

## Narrow changes

1. Tracker generation now includes calibration ID and TF epoch. Switching
   calibration cannot reuse old tracks. Same source epoch's backwards stamps or
   duplicate sequence are rejected **before** reset; a config change no longer
   bypasses monotonic fencing. A changed map binding must advance map generation.
2. Added D2-owned `consumer_port.C4CorePort`, implementing C4's existing injected
   `d2.process(Sample)` protocol by calling the actual numerical functions. This
   is not a new C4 runtime/ROS adapter. The exact numerical API stays
   `process_lidar(points, meta, *, ground=None, self_boxes=(), reference=None,
   limits=Limits())`, `lift_detections(...)`, `associate(...)`, `Tracker.step(...)`.
3. Added `compact_frame`: only repeated per-object source provenance becomes an
   index into `input_sources`. All original timestamps/domains/epoch/sequence,
   receipts, calibration, field layout and sensor origins remain in those records.
   Every object's complete geometry, observed bounds, uncertainty, first/last
   observation times and state remain unchanged. Distinct RGB-D and LiDAR origins
   remain distinct, including in fused observations and old occluded objects.
4. Added bounded default-service delivery: 2 KiB reserved for C4 diagnostic
   wrapping. Over-budget delivery raises `FRAME_BUDGET_EXCEEDED` and retains
   **all** core geometry in `port.last_result`; no UI-based collision truncation.
   Original algorithm component overflow also rejects delivery rather than
   presenting a partial component set as complete. No new bulk schema is invented.
5. Postprocess completion has its own host clock ID and time, explicitly
   `renews_observation:false`. It does not replace receipt or source time.

### Exact C4 hook / source requirements

```python
from robot_dashboard.obstacle_fusion_core.consumer_port import C4CorePort
# C1 classes below come from the pinned read-only dependency, not copied code.
port = C4CorePort(canonical=C1.canonical,
                  validate_frame=C1.ObstacleFrame.from_dict,
                  geometry_context=lambda sample: {},
                  processing_clock_id="my-processing-clock")
# Inject port as d2=port into actual C4 RuntimeAdapter(...).
# RuntimeAdapter calls port.process(sample), NOT process(an arbitrary packet).
```

One instance binds one source ID. The supported C4 Sample kind is `PointCloud2`:
`payload.xyz_m`, `fields`, `invalid_points`, optional
`payload.metadata.calibration_id`, original `identity`, and `origin_m` are used.
Geometry remains in the declared source/local frame; no latest-TF substitution.
Missing origin/calibration stays null/unknown. This shim does not manufacture a
synchronized RGB-D sample from independent image events. Those still call the
existing `lift_detections` with explicit capture-time calibration, then
`associate`; this round tested those real functions for multi-origin fusion,
invalid/unaligned depth, and missing YOLO without suppressing LiDAR obstacles.
Other Sample kinds reject with `PAIRED_RGBD_INPUT_REQUIRED` rather than silently
creating geometry. Owner source/map rebind and C1 map/source reset remain explicit
host operations; this shim does not reset services on its own.

C4 geometry marking transport is tested with original source Sample metadata,
not bbox centers. Bbox centers are **never** ray origins or free measurements.
Separate fresh rays preserve each original origin. Occlusion, missed detection,
empty sample or TTL expiry creates no free evidence. Actual C4 `nav2.observation`
rejects a stale source even when postprocessing completed much later.

## Actual tests and payload evidence

`round2_results.json` records exact dependency pins and canonical example hashes.
`round2_obstacle_example.json` is an actual C1-validated, synthetic core result,
not a mock expected-output hand-crafted fixture. Its canonical SHA-256 is
`26f7924e2b3a423779eb6be73bb5324d88b5f3ffe0dd8d198b55fe80c0b14e9b`.

| Objects | D2 compact bytes | Actual C4 projection bytes | Default C1 service |
|---:|---:|---:|---|
| 1 | 2,525 | 2,642 | ACCEPTED |
| 8 | 7,012 | 7,129 | ACCEPTED |
| 16 | 12,147 | 12,264 | ACCEPTED |
| 32 | 22,419 | not sent | REJECTED, all 32 retained |
| 64 | 42,963 | not sent | REJECTED, all 64 retained |

The actual async C4 worker → actual C1SceneSink → actual SceneSnapshotService
also accepted **16** objects with runtime diagnostics. The table is representative
of these exact records, not a universal object-count guarantee. Large user
metadata can exhaust the budget earlier; C1 remains the final byte-limit owner.
The uncompressed 64-object actual frame passes 128 KiB C1 validation but fails
16 KiB service ingestion, demonstrating the real boundary difference.

- ACTUAL_CORE + ACTUAL_C1_VALIDATOR + ACTUAL_C1_SERVICE_PYTHON +
  ACTUAL_C4_PYTHON_PORTS: **7/7 PASS**, zero skips or mocks. Includes actual C4
  PointCloud2 normalizer, async TrafficWorker, C4 projection/sink, and C1 snapshot.
- All D2 focused tests with pinned exports: **30/30 PASS**.
- Source-fence negatives: invalid C1 map ID, malformed stamp/schema/authority,
  nonfinite input, duplicate sequence, backwards time across calibration switch,
  retired epoch/calibration, clock change, map revision without new generation.
- Full local safe regression: **3,004 discovered, 2,957 PASS, 47 SKIP**, 103.553 s.
  The same exact 36 previously established environment blocks are excluded
  before bodies execute; original 11 optional-dependency skips remain. This is
  **not an unmodified full-suite pass**. No denied socket action was retried in
  this round. See original HANDOFF and known_environment_blocks.json for errors.
- JS **699/699 PASS**; repository-wide ruff, secret scan, compile/CLI smoke PASS.
- Default discovery without pinned exports explicitly skips the seven external
  integration tests. The explicit pinned command below ran all seven locally.
- HTTP: NOT_RUN. ROS/DDS/native costmap: NOT_RUN. Python transport policy tests
  are not native publication/ingestion evidence; all ingestion/controller flags
  remain false. No fake generated sensor_msgs classes are counted as ROS tests.
- `REAL_YOLO_EVALUATION=INPUT_REQUIRED`: actual cone weights + independent labeled
  recordings absent. Synthetic detection math is not real model accuracy.

## Reproduction (existing clone, repository root)

```sh
# Only if pinned objects are absent; these are repository downloads, not devices.
git fetch origin 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 \
  b9d700d754f0d3d43b9afdcffcb86e9deb7b1020
python3 -m experiments.expansion_20261029.d2_perception.round2_check \
  --output /tmp/d2-round2.json --example-output /tmp/d2-obstacle-example.json
python3 -m unittest discover -s tests/expansion_d2 -v
# Existing exact-block inventory prevents repeating known VM permission denials.
python3 -m experiments.expansion_20261029.d2_perception.regression_without_known_blocks
node --test tests/*.mjs
python3 -m ruff check robot_dashboard scripts
python3 scripts/check_repository_secrets.py
```

`round2_check` exports only the pinned foreign packages to a temporary directory,
executes actual foreign code there, and removes the export. No C1/C4 source is
published here. Repository CI remains unmodified; final remote CI and source tree
verification are reported with the final immutable delivery SHA.

## Remaining one integration action

**C1-owned bulk/provenance-reference transport agreement for over-16KiB frames.**
Until that versioned interface exists, this D2 port rejects oversized delivery
and retains full geometry for its caller; it does not raise C1's limits or drop
collision objects. Current 16-object representative integration is complete.
Do not automatically watch other roles or wait for their future implementation.

No product app, shared source, main, PR, robot, camera, deployment or motion was
changed. D3 should pin this ROUND2 delivery SHA; its existing numerical call
signatures are unchanged, while optional C4CorePort and provenance compaction are
explicit additions. D3 can continue consuming uncompressed `Tracker.step`
geometry without adopting the C1 display/transport budget.
