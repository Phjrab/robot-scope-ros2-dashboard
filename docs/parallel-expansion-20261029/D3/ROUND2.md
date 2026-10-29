# D3 ROUND2 — canonical time, explicit coverage, actual native execution

This continues the existing clone/branch; no main, product common files, deploy,
robot access, new controller, or another role's published code is changed.
Initial ROUND2 parent: `09b68b692fa4b7ccdea39b1a16e3ff150794e12d`.

## Fixed boundaries

- `assess` now emits v0.2 decimal-string receipt times, including nested source
  references. An unbound host validity interval is empty: it cannot authorize a
  command. The original source interval is retained under
  `freshness.source_validity_interval`; its start comes from original input
  stamps and its end from the oldest input expiry, NOT adapter invocation time.
- `canonical_assessment` delegates clock conversion to the actual C1
  `normalize_collision_assessment` and explicit epoch-bound `ClockBinding`.
  Source domain/epoch/receipt/expiry are preserved; mapping uncertainty shrinks
  the window. Re-evaluation 100 ms later does not restart TTL. Above-2^53 ns
  values remain exact decimal strings at the canonical JSON boundary.
- Actual C4 `constraint_from_d3` still expects legacy `clock_id/valid_from_ns/
  valid_until_ns`. Direct canonical input rejects (confirmed). D3's explicit
  `c4_constraint` first invokes real C1 validation, then projects exact same
  bounds to C4's Python integers; its injected C4 validator revalidates the
  canonical original AND exact projection. No permissive fake validator or
  competing wire schema is substituted. Real C4 consumer and gate are invoked.
- `ADVISORY_ONLY` is explicit up-front configuration and creates no command
  constraint. It is NOT a protective layer. `ACTIVE` preserves UNKNOWN and the
  real C4 gate latches HOLD. Any conversion/context error raises; there is no
  exception-triggered advisory downgrade or auto-resume.
- A magic `COMPLETE_SYNTHETIC` string and empty objects no longer produce CLEAR.
  Coverage must bind finite observation volume, horizon, source references,
  validity, clock, frame/epoch and map generation. The entire padded swept
  conservative volume must be inside it. Only a generated closed SYNTHETIC scene
  is currently qualified. Real sparse/replay/blind coverage remains
  `MOTION_COVERAGE_NOT_QUALIFIED`, not relabeled synthetic.

## Exact read-only dependencies

- C1 latest inspected once: `cb8ccc68be8d96a44b0d38adcff8186893ba2b08` (v0.2
  and sole source-to-host normalization boundary; newer than review's 54629c7).
- C4: `b9d700d754f0d3d43b9afdcffcb86e9deb7b1020`.
- D2 latest: `7313f0a31c00ae87ae216b84ca41a23804e91917`.
- D2 retained regression: `c0d266e290a2d29c173d3b83520f8c96efea9447`.
- Historical bootstrap C1 `2402c02c6f91ba54064894b21735e01b98610acd` numerical
  regression retained via explicitly labeled legacy envelope projection only.

The actual-D2 test uses uncompressed Tracker output; geometry is not truncated
for C1's 16 KiB service/128 KiB wire limits. D2 UI/service payload budget behavior
is independently documented by D2, not claimed as a D3 HTTP test.

## Native execution boundary

New authorized workflow `.github/workflows/expansion-native-offline.yml` is
push-triggered ONLY on this D3 branch and owned code/test/experiment paths.
GitHub-hosted Ubuntu 22.04 only; no self-hosted runner, secret, host network,
physical-device mount, deployment or workflow_dispatch assumption.

`native_ci.py` reuses the existing `experiments/competition_nav2` executor in a
transient tracked-source export. Namespace/domain literals alone are replaced
with `/robot_scope_review_x` / 194; source and adapted hashes are recorded.
Actual parameters, Nav2 package versions, plugin library hashes, immutable image
ID/base digest, raw Twist, plant pose, odometry, scan, costmap, plan, lifecycle,
action result and independent collision scoring come from the existing runner.
No pose path follower is introduced. The reference feasibility waypoints are
NEVER fed to planner or plant.

**Baseline is stock NavFn + direct RPP, not RotationShim.** No heading patch is
mixed in and this is not RotationShim validation. Original .716×.324 m footprint,
0.18 m/s / 0.6 rad/s limits, goal tolerances and controller settings are unchanged.
The existing spacious-room single-obstacle diagnostic uses a conservative 0.6 m
square proxy, not a measured cone mesh; it is not a claim of real cone geometry.
The original narrow competition failures remain separate and unchanged.

Minimum order: empty, diagnostic single obstacle, fully blocked. A failure stops
expansion immediately and records the first actual blocker. ONLY if all three
pass: one appearing-obstacle case then one stale-input case. No parameter sweep.
Additional D3 URDF constraints are explicitly ADVISORY_ONLY in this native
baseline; existing native RPP collision detection and stale/STOP command boundary
remain ACTIVE. Do not claim the new 3D protection drove native safety.

## Reproduction

```sh
python3 -m unittest discover -s tests/expansion_d3 -v
python3 -m experiments.expansion_20261029.d3_collision_sim.reproduce --output /tmp/d3-round2.json
# Use git archive of each exact SHA above into /tmp/c1, /tmp/c4, /tmp/d2:
python3 -m experiments.expansion_20261029.d3_collision_sim.round2_compatibility \
  --c1-root /tmp/c1 --c4-root /tmp/c4 --d2-root /tmp/d2 --output /tmp/d3-compat.json
# For old D2, use its exact archive and --d2-sha c0d266e290a2d29c173d3b83520f8c96efea9447.
# Namespace-only preflight; no ROS/docker access:
python3 experiments/expansion_20261029/d3_collision_sim/native_ci.py --stage-only --output /tmp/d3-stage
```

Execution levels: actual D2/C1/C4 Python core PASS; final command sink MEMORY_ONLY;
HTTP NOT_RUN; C4 live ROS port NOT_RUN. Native execution has its own workflow,
source SHA and evidence; it cannot be inferred from those core tests.

Native trigger/execution/result and final source/example hashes are recorded in
`ROUND2_RESULTS.md` after the real CI run reaches its terminal state. Missing
physical calibration/mount/real replay remain INPUT_REQUIRED, not native success.
