# Latest follow-up

See [ROUND2.md](ROUND2.md) for the actual pinned D2/D3/C1 composition, canonical validity conversion, explicit advisory/active modes, and the recorded C1→C3 failure. The first-round evidence below is retained as historical evidence.

# C4 runtime ports — fixed offline candidate

Implemented and locally verified on 2026-10-29 KST. This is a new C4 expansion
submission, not a continuation of historical C1–C4 or competition work. It is a
default-OFF adapter candidate with fixture algorithms and a real memory-only
checked-command consumer. Product integration, deployment and physical driving
are not claimed.

## Commit identity and publication

| Identity | Value |
|---|---|
| Repository | `Phjrab/robot-scope-ros2-dashboard` |
| Branch | `review/20261029-x-c4-runtime` |
| BASE_SHA, fixed from initial latest remote main | `f469155c2b0c505f3e472e878f75029d7b8d39df` |
| TESTED_IMPLEMENTATION_SHA | `7919e84141ec5cebc6842f2891274b69f82bf0aa` |
| FINAL_DOCUMENT_HEAD | The documentation commit containing this HANDOFF, directly after TESTED_IMPLEMENTATION_SHA. Resolve with `git rev-parse HEAD` on the published branch; its exact SHA and immutable HANDOFF URL are reported in the chat's final response. |

The final commit only adds this handoff. Implementation/test/launch source at
FINAL_DOCUMENT_HEAD is identical to TESTED_IMPLEMENTATION_SHA. The containing
commit's own hash cannot be embedded literally in its contents; this explicit
resolution avoids a self-referential SHA editing loop.

[Branch source](https://github.com/Phjrab/robot-scope-ros2-dashboard/tree/review/20261029-x-c4-runtime),
[tested implementation](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/7919e84141ec5cebc6842f2891274b69f82bf0aa),
[integration points](INTEGRATION_POINTS.md),
[machine-readable validation](../../../../experiments/expansion_20261029/c4_runtime/results/validation.json).

Independent normal clone: `/home/desktop1/Documents/ChatGPT/robot/c4-runtime-20261029`.
The shared empty repository's branch/index/remote was not changed. The actual
AGENTS.md was read before editing; the user's explicit branch exception was
applied. No reset, merge, cherry-pick, force push, main update or other-role
source copy was used. Main was not followed repeatedly after fixing BASE_SHA.

## Changed ownership paths

- `robot_dashboard/obstacle_runtime_adapter/`: message layout readers, isolation,
  injected D2 worker, C1/C3 wire projections, Nav2 transport/profile/snapshot
  ports, D3 constraint projection, memory-only checked-command gate.
- `ros2/robot_scope_obstacle_adapter/`: opt-in Humble package/launch and plan-only
  BT. No controller/bridge or recovery motion is launched.
- `tests/expansion_c4/`: contract doubles and 46 focused tests.
- `experiments/expansion_20261029/c4_runtime/`: generated synthetic smoke,
  exact-C1 compatibility checker, profile generator, offline regression guard,
  validation summaries and logs.
- `docs/parallel-expansion-20261029/C4/`: handoff and precise future connections.

No root product config, common scene/navigation/heading code, camera owner,
SDK bridge, lease implementation or deployment file was modified. No PCD,
recording, private video, model weight, environment file, secret or ROS
build/install/log tree was committed. Fixtures generate message data at runtime.

## Implemented behavior

PointCloud2 decoding respects real fields/offsets, float32/float64, endianness,
point/row stride and padding; raw data and non-XYZ fields remain intact. Image
and CameraInfo readers retain encodings, units, intrinsics/distortion/profile
metadata; pose, TransformStamped and JointState readers preserve source identity.
Source stamp is a decimal string and is never replaced by now. Clock, receiver
clock ID, source/TF/map epoch, map generation and source sequence are fenced.
Shared unknown clocks remain UNKNOWN. Cross-device or unattested aligned
RGB/depth inputs and image-only detections have geometry_unavailable diagnostics;
C4 does no deprojection/fusion/registration/collision calculation.

Normalization and injected D2 processing run off the subscriber using the
existing TrafficWorker, one executing plus one latest pending. ROS-to-owner-loop
handoff is also bounded to one pending item/callback. Source registry is capped
at 16, output is bounded and oversize results are rejected without presenting a
truncated cloud as full geometry. Late, stale, superseded, reordered and changed
generation results cannot publish a scene. UI health includes source receipt
age/stale, latency counters, dropped/rejected/invalid counts and worker status.

Nav2 transport keeps complete obstacle points and each sensor origin. LiDAR's
original acquisition frame has marking/clearing; depth and aggregate geometry
are marking-only. No centroid LaserScan, artificial combined clearing origin,
YOLO miss, localization exclusion, track TTL or sensor dropout creates free
evidence. The opt-in profile retains a single inflation pass and a conservative
D3-provided circle radius/padding without shrinking the base envelope. NavFn
remains a circular baseline. Native clearing/occlusion outcomes are NOT_RUN.

Read-only global/local costmap and actual path callbacks feed a bounded snapshot
port; `scene_with_observations` connects those inputs to C1/C3 with a generation
fence. Publication, observed occupied-cell correlation, actual path geometry
change and controller consumption are distinct. UNIT tests exercise observer
branches using labelled doubles; they are not native Nav2 evidence.

The D3 assessment port invokes an injected validator and passes its severity to
the gate. STOP_REQUIRED writes actual ZERO/hold to MockCommandSink. UNKNOWN is
also fail closed; CAUTION can only reduce velocity. Existing STOP/estop/canceled
lease outrank clearance. A newer CLEAR alone cannot release a stop, and an
explicit resume must acknowledge the exact stop revision and fresh context;
resume still emits ZERO and requires a new command. Duplicate/order/TTL/future
time/command/goal/generation/lease/clock/source mismatch is rejected. A trusted
consumer tick expires nonzero output independently of the browser. There is no
retry/recovery loop or production nonzero publisher.

## Dependency pins and connection limits

One remote role-ref check found C1 bootstrap only. Its exact SHA was fetched as
objects and exported separately to `/tmp/c4-c1-2402c02c-readonly`, made read-only,
and imported in a separate compatibility process. It was not merged or copied
into C4 source.

| Counterpart | Pin / execution result |
|---|---|
| C1 contracts | `2402c02c6f91ba54064894b21735e01b98610acd`: actual ObstacleFrame, ScenePacket and CollisionAssessment parser/projection PASS |
| C1 scene service | NOT_RUN: bootstrap pin contained contracts but no service; documented ingest signature exercised with a fixture |
| D2 | No exact published SHA available at the single check; injected pure process fixture called, no perception algorithm copied |
| C3 | No exact published SHA available; C1 ScenePacket shape validated, actual consumer NOT_RUN |
| D3 | No exact published SHA available; assessment/command/envelope fields are fixture ports, native full harness NOT_RUN |

The C1 implemented wire uses schema_version `0.1`, including map generation and
host receipt fields; the design pack's v1 envelope is explicitly projected by
injected C1 constructors, not a second shared validator. D2's eventual concrete
process_lidar/lift_detections/Tracker shim and D3's binding/validity extension need
exact-SHA compatibility checks. This is not END_TO_END_IMPLEMENTED across roles.

## Executed verification

Environment: desktop Linux x86_64; Python 3.12.3 in private `/tmp/c4-runtime-venv`;
Node 24.22.1 from the bundled runtime. NumPy 2.5.4, PyYAML 6.0.3, FastAPI 0.162.0,
Pydantic 2.14.1, httpx 0.28.1, OpenCV headless 5.0.0.93 were used for the existing
repository suite. No robot, camera, inference model or ROS node was opened.

| Evidence | Result |
|---|---|
| UNIT — focused C4 | 46 tests, zero failures/errors, one native generated-type skip |
| UNIT — required Python full discovery | 2,987 tests, zero failures/errors, 17 skips; 83.896 seconds |
| UNIT — related/all JS test files | 77 passed, zero failed/skipped, bundled Node 24 |
| UNIT — compileall and git diff check | PASS |
| SYNTHETIC — 1,200 sensor inputs | latest sequence 1199, 1199 superseded, queue capacity 1, executing capacity 1, D2 fixture actually called |
| SYNTHETIC — final consumer | STOP_REQUIRED -> actual velocity [0,0,0] and hold=true in mock sink |
| UNIT — separate exact C1 export | actual three contract parsers and scene projection PASS |
| NATIVE_NAV2_SIM | NOT_RUN: ROS Humble/Nav2 plugin installation unavailable |
| REPLAY_REAL / UI_FIXTURE | NOT_RUN: no real recordings or exact C3 consumer used |
| DEVICE_NOT_RUN | all physical sensors/robot/TF/goal/velocity/deployment untested |

Full-suite skips: 11 historical competition integration/traffic modules lacked
optional jsonschema; three historical native cross-role classes lacked their own
pinned dependencies; C4 generated ROS types, optional SVG plotting and optional
rosbags backend were unavailable. Exact test names/reasons are preserved in
`results/python_full_summary.txt`. These are recorded as skips, not passes.

Initial default system Python lacked dependencies. Restricted-sandbox full runs
were interrupted/stopped after asyncio teardown stalled; a separate existing
coordinator test reproduced suppressed self-pipe wakeups. No pass is claimed for
those attempts. The successful final full discovery ran as a local process with
`offline_test_guard.py` installed as temporary sitecustomize: non-loopback
connect/bind/sendto and external DNS were rejected before access. C4 tests also
use the repository's documented test-only selector timer workaround. Initial
system Node 18 produced seven ESM loader failures; the unchanged tests passed
under bundled Node 24. No product changes were made to address environment issues.

Synthetic latency uses a virtual clock; zero timing values are not measured
hardware performance. Native plugin load, effective parameter readback, actual
costmap ingestion, actual plan change and controller enforcement remain NOT_RUN.
Actual run evidence flags are all false except mock command enforcement.

## Reproduction and review boundaries

From the independent checkout with the private venv on PATH:

```bash
python3 -m unittest discover -s tests/expansion_c4 -t tests -v
PYTHONPATH=.:tests python3 experiments/expansion_20261029/c4_runtime/smoke.py
PYTHONPATH=.:tests python3 experiments/expansion_20261029/c4_runtime/compat_c1.py --export /tmp/c4-c1-2402c02c-readonly
PYTHONPATH=/tmp/c4-network-guard:. python3 -m unittest discover -s tests -v
node --test tests/*.mjs
```

The guard export and exact dependency export procedure are described in the
experiment README. `results/validation.json` records commands, environment,
statuses and log fingerprints; focused/JS logs and synthetic/exact-SHA results
are published. The large Python log is summarized with every skip reason.

Future connection points, arguments, sensor provenance, single final consumer,
required profile readback and rollback are in INTEGRATION_POINTS.md. Default mode
is offline; ROS launch is disabled unless explicit. Real endpoints/LIVE mode are
rejected before startup. No device mounts, host-network container, robot subnet
probe, SSH/HTTP/DDS/graph/service query or product registration was used. Local
ROS socket-domain guard behavior was UNIT-tested only; native launch was not run.

## One next step

When D2/D3 and C1/C3 implementations publish exact SHAs, run one read-only
cross-role compatibility pass in a separate temporary export using this fixed C4
candidate. D3 owns the subsequent isolated Humble 1.1.20 native matrix. Do not
poll, merge, wire product files, deploy or test the robot without the user's
separate integration instruction after existing validations finish.
