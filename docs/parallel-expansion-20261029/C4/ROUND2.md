# C4 round 2 — actual core ports and binding

**Latest continuation:** [ROS_ADAPTER.md](ROS_ADAPTER.md) records async ROS/core/
HTTP/current-C3 composition and actual hosted native evidence. [FOLLOWUP.md](FOLLOWUP.md)
retains the previous synchronous 0.2 profile and its older C3 rejection.
The evidence below is the preserved earlier fixed-SHA 0.1 execution.

Branch: `review/20261029-x-c4-runtime`. Started clean at
`b9d700d754f0d3d43b9afdcffcb86e9deb7b1020`. Existing independent clone retained.
No merge/cherry-pick/reset, no PR, no edits to another role, product entrypoint,
main, ROS distribution, operating configuration or CI workflow. No robot/device
connection, production DDS, deployment or physical motion. C2 remains frozen;
its branch SHA is unchanged, and it is not a C4 code dependency. No Dots work was
started or reordered; this wrapper calls D2 before D3.

## Actual API findings and resolved defects

The supplied follow-up document differs from the actual pinned sources in three
places. Source inspection, not an invented alias, determines the wrapper:

1. D2 at `c0d266e...` exports **obstacle_fusion_core**, not
   `obstacle_perception_core`; the latter path does not exist at this SHA.
2. C1 at `54629c7...` requires
   `{host_clock_id, start_monotonic_ns, end_monotonic_ns}`. It does not accept a
   `clock_domain` key inside this interval. D3 returns
   `{clock_domain, from_ns, until_ns}` with decimal strings. The old C4
   `clock_id/valid_from_ns/valid_until_ns` proposal is historical and rejected by
   the new explicit-profile converter.
3. This D3 pin has no `coverage.complete_for_motion` object. Its actual API is
   `coverage="SPARSE"` or synthetic-only `"COMPLETE_SYNTHETIC"`. C4 confines the
   latter to an explicit finite fixture attestation with exact motion hash,
   context, observation sequence and expiry. It is never attached to replay or
   real observations. Real scoped coverage remains an owner input requirement.

New files are confined to `robot_dashboard/expansion_runtime/`,
`tests/expansion_runtime/`, the dedicated `c4_runtime/round2` scripts/results and
C4 docs. Existing first-round source and tests are preserved.

- `ports.py`: real D2 process_lidar/lift_detections/associate/Tracker and real D3
  assess factories. No copied owner code, fake fusion or replacement collision
  algorithm. D2 extent already includes uncertainty; D3 receives
  `uncertainty_in_extent=True` exactly once.
- `binding.py`: exact profile conversion with explicit unit-rate clock mapping,
  clock/source epoch, finite mapping window, offset and uncertainty evidence.
  Conservative start moves later and expiry moves earlier. No receipt-based TTL
  restart. Original D3 interval/clock and full reference are retained in freshness.
  C1 host integer values beyond JS safe range fail explicitly; large source
  nanoseconds and mapping offsets/windows remain decimal strings.
- `composition.py`: runtime-owned goal/authority/lease/command/map/family/
  footprint/geometry/TF/clock context, duplicate/reorder/late fences and explicit
  serialized rebind generation. State and packets are copied before core calls.
  Original observation receipt, D2 start/end, D3 start/end and C4 receipt/conversion
  times are separate. Synthetic scope can shorten both C1 snapshot validity and
  enforcement expiry, never extend the original D3 interval. C4 output sequence
  is separate from retained original D3 sequence.
- `sensor.py`: normalized raw PointCloud2 plus verified stamped transform → local
  InputFramePacket. Keeps raw frame/layout/reference/origin/range/FOV, rejects
  unknown transforms, creates no clearing rays. Free-ray evidence is separately
  supplied with original measurement provenance; empty detections, missing source
  and tracker expiry never become free rays. Camera failures retain raw LiDAR.
- `intent.py`: default **ADVISORY_ONLY** is diagnostic and writes no commands.
  Explicit **ACTIVE_CONSTRAINT** retains HOLD/rejection for UNKNOWN, stale,
  missing authority, wrong scope/context, unsupported CAUTION or expiry. No
  automatic downgrade. Only intents and a memory-only mock final sink exist.
  Existing CommandGate latches STOP/UNKNOWN; UI state cannot release it. The
  trusted consumer must schedule its watchdog and own STOP/estop/lease/resume.
- Actual C1 reference matching required `{source_epoch, sequence}` rather than
  D3's expanded reference. The converter narrows the matching reference and
  preserves the complete original separately. `ingest_scene` checks actual
  service ingest results; it does not claim success on rejected packets.

## Exact read-only dependencies

| Role | Used SHA | Actual use |
|---|---|---|
| C1 | `54629c793ad4ae0ea88127f00ed1b7f8805fc4e2` | Contracts, SceneSnapshotService, actual DI HTTP router |
| D2 | `c0d266e290a2d29c173d3b83520f8c96efea9447` | Real perception/fusion/tracker |
| D3 | `09b68b692fa4b7ccdea39b1a16e3ff150794e12d` | Real URDF geometry and assessment |
| C3 | `92658bccc253f31552415f9c9d667bbd28957a06` | Real JS consumer against actual C1 snapshot — FAIL |
| C2 | `5eed1a9959ca25a4f30bd5b5712806a5ad660c51` | Latest ref check only; unchanged, no code use |
| D1 | `cbedd05ba6f97dad5506e8003302f689ed8fcb4c` | Latest ref check only; no code use |

Each peer export lives in `/tmp/c4-round2-deps/<role>-<full-sha>`, chmod read-only.
The loader checks every imported owner-package Git blob and verifies common
relocalization/PCD sources match owner SHA. No foreign package is published in C4.
Source manifest and exact canonical snapshot hash are in
[composition.json](../../../experiments/expansion_20261029/c4_runtime/round2/composition.json).
Contract is **C1 schema 0.1 at the SHA above**, not a newly invented v1.
The example snapshot SHA256 is
`936f34912b2433864ee665e710397dd9f7d3bebb86579688ad9d63a88fa9d05f`.

## Execution evidence

Commands and setup: [round2 README](../../../experiments/expansion_20261029/c4_runtime/round2/README.md).
Machine-readable counts: [validation.json](../../../experiments/expansion_20261029/c4_runtime/round2/validation.json).

| Check | Result and boundary |
|---|---|
| Actual D2→D3→C4→C1 focused checks | **20 PASS**, no skips, included in unfiltered full run |
| Scoped synthetic CLEAR | CLEAR, mock velocity `(0.1,0,0)`; not an all-HOLD success claim |
| Modeled geometry overlap | STOP_REQUIRED, mock ZERO/HOLD; physical contact **unconfirmed** |
| Sparse positive clearance / empty observations | UNKNOWN / HOLD, never relabeled CLEAR |
| Out-of-motion scope, replay synthetic-coverage claim | UNKNOWN; actual D3 SPARSE path remains diagnostic |
| Generation/goal/family/footprint/TF changes, duplicate/reorder/late | Old limits/CLEAR rejected |
| Source interruption / processing delay | Watchdog ZERO at expiry; no reception TTL extension |
| No camera detections / invalid depth | LiDAR obstacles retained by actual D2 |
| Raw valid free ray vs source loss | Separate core clearing evidence vs none; native removal **NOT_RUN** |
| Actual C1 snapshot + actual HTTP route | PASS; in-process ASGI request/auth/response, no TCP server/product mount |
| Actual C1→C3 consumer | **FAIL**, `C1_DISPLAY_PROFILE_REQUIRED`, script exit **2** |
| Full Python | **3149 run, OK, 6 skipped**, 106.400 s, no exclusions |
| Existing C4 tests | 46 included; one native-generated-message skip |
| JavaScript | **77 PASS**, syntax 112 modules PASS, Node 24.22.1 |
| Static checks | Ruff entire robot_dashboard/scripts, tracked secret scan, diff check PASS |
| ROS subscribe/convert/publish lifecycle | **NOT_RUN**, rclpy/sensor_msgs/tf2_ros/nav2_msgs absent |
| Native costmap mark/clear and controller | **NOT_RUN**; adapter publication and ingestion flags remain false |
| Real replay, YOLO inference, physical contact, robot | **INPUT_REQUIRED / NOT_RUN**, no claims from synthetic tests |

Six skips are three historical exact-SHA comparison classes, native ROS generated
message, optional SVG plotting and optional rosbags. Newly installed temporary
jsonschema enabled previously skipped legacy checks, hence a higher full count
than round 1. Synthetic timestamps are deterministic, not throughput evidence.
The D3 robot model in these tests is a declared synthetic standing box, not a
calibrated physical Go2 or independently observed contact. Sensor data, TF,
calibration, detections, finite complete scene and authority inputs are generated
fixtures. Core math, contracts, service and router are actual owner code.

## Unresolved boundaries and CI

C3 requires `sources.display`, which the real C1 service does not emit at this
pin. C3 also reads legacy `valid_until_ns`. This is a concrete cross-owner
contract failure; C4 does not fabricate display data or modify either owner.
No claim of full C3 display integration is made. The current D3 SPARSE coverage
cannot justify active URDF CLEAR for real observations; advisory is the default.
Native ROS evidence is absent. Existing opt-in launch and review port remain
unchanged; the exact synchronous harness entrypoint and the first-round worker
interface distinction are documented in [INTEGRATION_POINTS.md](INTEGRATION_POINTS.md).

Prior C4 HEAD `b9d700d...` remote CI passed:
[40828844706](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40828844706).
Review main `d8d15e5...` CI passed. Latest inspected main
`5c1ffe3ba3c070e67e143d39b65650cc8dba5f2e` failed
[40832553004](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40832553004)
in `tests/e2e/slam_presentation.spec.mjs:87`, 390px light layout top difference:
expected `<1`, received `25.5` (Ubuntu 22.04 / Python 3.10). CI workflow bytes are
unchanged between inspected main and C4. This baseline failure is recorded, not
waived or attributed to C4 without evidence. No criterion or test was relaxed.
Tested source/test-code SHA: **`ba60767ee6f90f20c911bcf3ea033118a820f31e`**.
After commit, the 20 actual-core/HTTP focused checks passed again in 0.731 s.
The full run above used exactly the same source/test bytes; its new-source
manifest was checked against this commit. See
[source_validation.json](../../../experiments/expansion_20261029/c4_runtime/round2/source_validation.json)
for exact Python/package versions and verification.

Remote full CI for this tested code is
[40838588432](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40838588432).
At preparation of this documentation follow-up, static checks, offline
integration, Python and JavaScript had passed in both matrix environments;
browser E2E was still running. **No full CI pass is inferred from those partial
results.** The delivery message reports the latest observed run outcome. The
previous C4 full run took approximately 19–22 minutes, so elapsed time alone is
not interpreted as failure or success. CI is unmodified and no rerun/waiver was
used. Required local owner composition is separate: the normal remote workflow
does not fetch the new C1/D2/D3 pins, and visibly skips those 16 real-composition
tests (the four local binding tests still run).

Final submission HEAD is the commit containing this documentation follow-up;
its exact immutable SHA and remote-head equality are given in the delivery
message. This follow-up changes only C4 docs and the small verification record,
not the tested source or tests. The previous HANDOFF result link was corrected.
Source SHA and final documentation HEAD are deliberately distinguished.

**Next one connection:** C1/C3 owners agree and publish the real scene display +
canonical validity consumer contract, then replay this exact C4-produced C1
snapshot into that consumer. C4's part remains observation-only by default.
