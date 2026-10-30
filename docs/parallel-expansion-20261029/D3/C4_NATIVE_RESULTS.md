# C4 input preparation and native preservation — actual results

Source/test SHA **`56cb4ab63ae42aa208573c68d17c3da688c58976`**; equivalent local
commit `406122e`, tree `014dbd942afdbd2e785c02cad35eaa8f7e529664`.
This final results-only commit changes no source, tests, workflow or parameters.
Final HEAD and its terminal standard CI are reported with delivery, not a
self-referential commit hash. All changed blobs/full tree are checked remotely.

## Actual baseline native execution

[Native run 41028203752](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41028203752)
**SUCCESS**, actual five-case native execution, not only image build/publication.
[Evidence artifact](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41028203752/artifacts/12964397847)
includes original command/actuator/feedback/costmap/plan/action traces, independent
validation, immutable image/package lock and unchanged namespace adaptation hashes.
Artifact SHA256 `c4489e7ef8d5cdb04e032dc0ea1eda6b3277feeeba75a675a0b11dd683d21953`.
Selected non-sensitive actual results are in [summary](c4-native-baseline-summary.json).
No raw logs, build/install trees, maps, clouds or private capture are committed.

| Existing case | Result/action | Controller commands | Path m | Contact / boundary / hold-nonzero |
|---|---|---:|---:|---|
| empty | GOAL_REACHED / SUCCEEDED | 348 | 2.583042 | 0 / 0 / 0 |
| diagnostic_single_obstacle | GOAL_REACHED / SUCCEEDED | 560 | 4.269372 | 0 / 0 / 0 |
| fully_blocked | SAFE_WAIT / ABORTED | 0 (45 behavior commands) | 0 | 0 / 0 / 0 |
| diagnostic_appearing_obstacle | GOAL_REACHED / SUCCEEDED | 603 | 4.372671 | 0 / 0 / 0 |
| sensor_stale | SAFE_WAIT / CANCELED, one cancel acknowledgement | 45 | .328500 | 0 / 0 / 0 |

Actual appearance/first hit scan: 3.05 s after baseline start, 27 hit beams;
first native costmap marking 3.40 s, **16 lethal cells**; first changed detour plan
3.70 s, 191 points vs original 197. These are comparable simulation-elapsed
stamps from the existing native evidence validator, not mixed host/source latency.
The source PointCloud2/C4 worker chain is **not** the source of this baseline scan.
Obstacle **removal/clearing via C4 is NOT_RUN**, not inferred from baseline marking.
Stale terminal is SENSOR_STALE; no collision/contact or cancel/infrastructure
outcome is relabeled goal success. Each run records one >75 ms plant deadline
miss; worst wall gap .092930941 s. VM timings are not physical stopping evidence.
Raw minimum conservative clearances remain 0/.279551825/0/.268833247/0 m;
zeros are not rewritten positive or presented as independently confirmed contact.

Actual Humble Nav2 **1.1.20**, rclpy **3.3.22**, NavFn + **direct RPP**.
- Image `sha256:b5f9046e2f76e4da065a1a4d40f8be7ec1bc549765a149825d0704077835485b`.
- Base `ros@sha256:d9bcf2e6f72df127fdee07048c2e87b1b4b9a59a74af0592f4489fc2844aa855`.
- Resolved config `03e662b688603f63dfdc3d90a0008ce4342b5939dcf1b948d6aad9552c5c940a`.
- RPP library `d63cca14c5cd1f5d85b61d2d37e40f70c1cba0133fe2dcd574595386b969f497`.
Config and plugin hashes match ROUND2. Footprint .716×.324 m, .18 m/s/.6 rad/s,
goal tolerance/timeouts/scenarios unchanged. No RotationShim claim. Domain194,
`/robot_scope_review_x`, localhost-only/network-none container and fake plant;
new D3 URDF constraints remain ADVISORY_ONLY, no new command connection.

## Exact dependencies and distinct execution levels

Inspected C4 `7ac0d55b07abd20902d6d756c6b225733613fea7`, C1
`e0bc9cf8ba8bd22b406a287e1a9ef867a0cd367b`, D2
`7313f0a31c00ae87ae216b84ca41a23804e91917`.
Final one-time C4 recheck at 08:47 UTC returned the same SHA: no new bridge submitted.
`c4_readiness.json` in the native artifact preserves all inspected source hashes.
Only an exact read-only export was used; no foreign code published.

Actual current C4 `messages.pointcloud2` accepted the fixture's 33 records,
preserved bytes/header/identity and >2^53 receipt integer: **PASS**. Raw fixture
SHA256 `0b08b13eecd6b22036dc0b45e669d2871217f6584c991bb9a44eb89947fbf384`.
This is a Python layout reader test, **not** ROS subscription, worker, D2 or D3.
Reproduce after archiving C4's `robot_dashboard/obstacle_runtime_adapter` to a
read-only `/tmp/c4` and adding `/tmp/c4/robot_dashboard` to Python search path:

```python
from obstacle_runtime_adapter.messages import Identity, pointcloud2
from experiments.expansion_20261029.d3_collision_sim.c4_input_fixture import measurement
f = measurement()
s = pointcloud2(f['message'], Identity(**f['identity']), origin_m=(0, 0, 0))
assert s.payload['raw_data'] == f['message']['data']
assert s.identity.received_ns == 2**53 + 12345
assert len(s.payload['xyz_m']) == 33
```

Existing hosted actual-core regression remains separately pinned to C1
`cb8ccc68be8d96a44b0d38adcff8186893ba2b08`, C4
`b9d700d754f0d3d43b9afdcffcb86e9deb7b1020`, D2 current above and old
`c0d266e290a2d29c173d3b83520f8c96efea9447`: **PASS both combinations**.
These are not advertised as execution of latest C1/C4 Runtime.

- Local focused 34 PASS; JS 699 PASS; syntax 112 PASS; staged-source secret scan
  and diff checks PASS. Pure native export preparation PASS (before actual run).
- Local full Python socket-denied cases not repeated; local Ruff unavailable.
  Hosted full Python 3.10 and 3.12, Ruff, secret scan, JS and syntax **PASS** at
  08:46:56 UTC. Source [standard CI](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41028203811)
  was then in browser E2E, so this is a timestamped snapshot, not terminal claim.
  Final delivery checks exact final-HEAD CI to completion.
- C4 new actual ROS subscriber→worker→D2→D3→Nav2 chain, six required cases:
  **INPUT_REQUIRED / NOT_RUN**, including marking/clearing, rebind/old-frame rejection.
  Standalone fixture and envelope audit tests do not make those cases PASS.
- Physical device, Go2 SDK, deployment, main/product integration: **NOT_RUN**.

**Remaining one item:** obtain C4's bounded-worker/Runtime ROS entrypoint satisfying
[C4_NATIVE_FOLLOWUP.md](C4_NATIVE_FOLLOWUP.md), then run the six new-chain cases
against the already preserved isolated native baseline. Do not bypass its guards,
change the footprint/profile, duplicate the adapter or enable D3 command protection.
