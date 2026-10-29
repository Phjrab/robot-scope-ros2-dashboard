# C4 continuation — current C1 0.2 and real owner ports

Tested source/test-code SHA: **`183dcde9f41504310019ad1a7bc1da3311e5e68d`**.
The containing follow-up commit adds documentation and validation only; source
hashes are checked against this exact commit in [validation.json](../../../experiments/expansion_20261029/c4_runtime/followup/validation.json).
Final HEAD and remote equality are recorded in the delivery message, avoiding
a self-referential commit hash. Branch remains `review/20261029-x-c4-runtime`.

This continuation started from clean `073d05b24c73b4de08c754833d4c05e537a23727`.
Both its [final CI 40840171897](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840171897)
and the prior tested implementation's [CI 40838588432](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40838588432)
completed **SUCCESS**. The earlier ROUND2 document's in-progress CI status is
historical. Those passes do not validate the new source in this continuation.

## Actual changes and scope

Only C4-owned expansion_runtime, its tests, dedicated scripts and C4 docs changed.
The independent clone and existing implementation are preserved. Other-role
packages are exact-SHA, read-only dependencies, not merged, cherry-picked or
published in this branch. D2 is called before D3; no Dots work is launched or
reordered. C2 remains frozen after the short unchanged-ref compatibility check.
No robot/device connection, production DDS, main integration, product hook,
deployment, controller command or physical motion was performed.

- New explicit `CanonicalCorePorts` calls the actual current D2, D3 and C1 APIs.
  The previous `CorePorts` remains available for its prior fixed 0.1 owners.
  No silent version detection or fallback is used.
- C1's actual clock normalizer produces 0.2 decimal-string host nanoseconds;
  control uses exact Python integers. C4 validates clock epoch and mapping
  lifetime, preserves full D3 references and source validity, and only shortens
  expiry. Receipt is never reset. Host times above `2**53` pass losslessly in
  0.2 and are explicitly rejected by the optional 0.1 projection.
- New D3 requires a synthetic closed-scene volume certificate, not the prior
  `COMPLETE_SYNTHETIC` label. C4 passes the harness's actual horizon, volume,
  clock/map/source references and time bounds. Missing, small, short, replay or
  wrong-command evidence remains UNKNOWN/HOLD. No live/replay free-space
  certificate is manufactured.
- A D2 object-budget drop rejects the assessment instead of accepting partial
  geometry as complete. Its actual provenance-only compactor retains objects
  and timestamps, and rejects oversized C1 delivery at the unchanged budget.
  No geometry truncation or larger service limit is used.
- Runtime publishes separate geometric severity and effective intent status,
  including missing authority and `product_enforcement_connected=false`.
  Default ADVISORY_ONLY is unchanged; active failure never downgrades the mode.

Exact host entrypoint and reproduction: [followup README](../../../experiments/expansion_20261029/c4_runtime/followup/README.md).
The C1 service version must be selected explicitly before `ports.ingest_scene`.
The reviewed ROS worker still uses its original `offer_raw` interface; this
synchronous Runtime is not claimed to be automatically wired into that worker.

## Exact inspected and executed dependencies

| Role | SHA | Evidence |
|---|---|---|
| C1 | `4e1dd519a707169da5f88cf2a92a20ed3e701cc7` | Actual 0.2/0.1 validators, time normalizer, SceneSnapshotService and ASGI HTTP router |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` | Actual perception, tracker, provenance compactor |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` | Actual geometry/assessment, volume coverage and C1 normalizer bridge |
| C3 | `a2b6d37f61ac426ac8a21e941750099b28318fd8` | Actual byte parser, adapter and JS consumer on exact C1 HTTP response |
| C2 | `5eed1a9959ca25a4f30bd5b5712806a5ad660c51` | Unchanged latest ref only; no source changes or code use |
| D1 | `cbedd05ba6f97dad5506e8003302f689ed8fcb4c` | Latest ref only; no code use |

The four previous owner SHAs in [ROUND2](ROUND2.md) also execute unchanged in
their historical regression profile. Each current owner package blob is checked
against its Git object and non-writable mode under `/tmp/c4-followup-deps`.
Current and historical owners run in separate interpreters. Common PCD-editing
and relocalization code is checked for equality, not replaced. Peer branches
were sampled once for this continuation, not automatically monitored.

## Results and honest limits

| Check | Result |
|---|---|
| Current actual-core + actual C1 HTTP checks | **15 PASS**, no skips, nested in full suite |
| Prior owner focused checks | **20 PASS**, included in full suite |
| Unfiltered Python suite | **3150 run, OK, 6 skips**, 110.549 s; 15 current checks run inside one subprocess test |
| JavaScript and syntax | **77 PASS**, **112 modules PASS** |
| Ruff / tracked-source secret scan / diff | **PASS** |
| Scoped synthetic CLEAR | Actual core CLEAR; mock final velocity `(0.1,0,0)` |
| Modeled overlap | Actual STOP_REQUIRED; mock HOLD, physical contact unconfirmed |
| Sparse/empty, scope/clock/generation failure, loss/expiry | UNKNOWN/HOLD, no TTL restart |
| Actual C1 0.2 HTTP snapshot | **PASS**, decimal strings/full refs; auth enforced in synthetic host |
| Canonical C1 0.2 → actual C3 | **FAIL: C1_VERSION_UNSUPPORTED**, report exit **2** |
| Explicit safe 0.1 → actual C3 | Objects/expiry **PASS**; command collision **UNAVAILABLE**, not a full display pass |
| ROS lifecycle / native costmap marking-clearing | **NOT_RUN**, rclpy/sensor_msgs/tf2_ros/nav2_msgs absent |
| Browser rendering of this composition | **NOT_RUN**; actual JS consumer execution only |
| Real capture, calibrated Go2, YOLO weights | **INPUT_REQUIRED**; synthetic box/cloud/TF/calibration/detections only |

Exact HTTP byte hashes, source hashes and outcomes are in
[composition.json](../../../experiments/expansion_20261029/c4_runtime/followup/composition.json).
0.2 response SHA256: `cff9a0fcc11663a95eaf46606bff2b5142eec8dadef93661f859729d6a7e31e7`.
0.1 response SHA256: `d149132477455fbe03ea66ca166400b5bb519382fa725785f8cb21f5bafb78e0`.

C3 now consumes real C1 sources, so the old `sources.display` failure is resolved
at the new C3 pin. Its adapter still accepts only top-level 0.1. The optional
explicit 0.1 projection does not hide that default 0.2 failure. It preserves
references and never fabricates robot pose, twelve joint observations or a
global path for C4's command hypothesis. Therefore collision visualization
correctly remains unavailable. Scalar D3 envelopes are not drawable geometry.
An assertion of this known rejection passing is **not** an end-to-end pass.

Final command sink is memory-only mock; sensor processing, adapter publication,
native costmap ingestion and controller consumption remain separately reported.
D3's separately reported native CI is not adopted as C4 ROS lifecycle evidence.
The local full suite uses the existing external-network-blocking audit guard.

The ordinary remote workflow does not fetch either new owner set: its visible
16 historical composition skips plus one current-suite wrapper skip must not
be called real-owner integration coverage. It still runs local binding tests,
the rest of the full Python suite and both browser matrices without changing
the workflow or test criteria. New final-HEAD CI is queried after push and its
actual run URL/outcome is reported in the delivery message. At documentation
preparation it has not run; no success is inferred from previous CI.

The previously inspected main browser failure is retained in ROUND2 with exact
run and first error. It was not waived or modified here.

**Next one connection:** C3's owner must consume the canonical C1 **0.2 command
assessment** with explicit command/pose/joint reference semantics, then replay
these exact C4-produced HTTP bytes. This is a cross-owner contract boundary;
the default C4 path remains advisory until independently qualified.
