# C4 native-input continuation — 2026-10-30

## Verified boundary before native launch

Parent D3 `356d0a036eb62d546e159e12a0691d7f5ea278f6` was unchanged remotely.
The previous VM clone was absent; restored an ordinary clone of that exact remote
branch in its previous path. No reset, main integration, or user edits discarded.
Read ROUND2_RESULTS, ROUND2 and REPRODUCE and current repository AGENTS.

Exact owner snapshots inspected once (read-only Git objects, not copied into this
branch): C4 `7ac0d55b07abd20902d6d756c6b225733613fea7`; C1
`e0bc9cf8ba8bd22b406a287e1a9ef867a0cd367b`; D2
`7313f0a31c00ae87ae216b84ca41a23804e91917`.

**C4's requested new bridge is INPUT_REQUIRED at this pin.** Its FOLLOWUP.md
explicitly states the synchronous Runtime is not connected to its original
`offer_raw` worker. Actual `_Pipeline.process` invokes normalization and
`self.owner.d2.process`, validates identity, and emits an obstacle-only Result.
`RuntimeAdapter._result` sends a scene with `collision_assessment=None`.
Separate `expansion_runtime.Runtime.process` invokes actual D2 then D3 through
CanonicalCorePorts, but no submitted ROS/worker entrypoint invokes it.
This is a missing owner connection, not a D3 geometry or native environment error.
D3 does **not** insert a second worker or call synchronous perception from the ROS
callback to disguise that gap. No C4 code is changed or published here.

`c4_readiness.py` records the exact source-file hashes and inspected call sites;
its zero exit means **preparation succeeded**, never ROS/native integration PASS.
The existing workflow runs this before its unchanged five-case native baseline.
Latest C1/C4 are inspected dependencies only; existing actual core regression
continues using its explicit historical pins. No new-core execution claim is made.

## Minimal owner input contract / explicit fixture

Entry point: `experiments.expansion_20261029.d3_collision_sim.c4_input_fixture.measurement`.
It emits a bounded XYZ PointCloud2-shaped fixture with binary float32 records,
original immutable header/identity, nonempty measured wall returns, and raw-ray
references. It neither imports ROS nor publishes nor implements C4.
The identity is supplied by an owner-side bounded header lookup: ROS Header alone
cannot supply source restart epoch or sequence. Never invent identity on receipt.
The fixture's receipt clock and source simulation clock are intentionally distinct;
without an explicit epoch-bound mapping their difference is **not latency**.
Host nanoseconds may exceed `2**53`; persisted timestamp/latency strings are lossless.
No synthetic closed-volume coverage certificate is inferred from these planar rays.

C4 must supply a documented owner entrypoint composing its bounded worker with
`Runtime.process`, accepting original message/identity plus capture-time calibrated
TF, InputFramePacket, robot pose/joints, explicit mapping/context and diagnostic
command hypothesis. One executing + one latest pending, generation fencing and
nonblocking ROS callback remain owner responsibilities. It must expose original
source/receipt times, worker drops/age/errors, actual D2/D3 results and raw
observation output. Geometry processing must not be replaced with a D3 shim.
Rebind must clear old pending/results/track state; delayed old-epoch frames reject.

A further integration constraint: `ReviewRosPort.start` checks that domain 194 has
no existing DDS participants. Start it before the native graph in the private
container, or use a separately submitted C4-supported shared-context attachment;
do not disable that guard after native launch. Its current `review_profile`
requires a circle and changes costmap sizing/planner tolerance. **Do not use that
profile to replace the verified rectangular native footprint/settings.** Request
an observation-only attachment compatible with the unchanged native parameters.

## Required six cases once owner bridge is submitted

| Case | Required native evidence |
|---|---|
| Empty path | Actual input receipt/worker/D2/D3; plan retained within original criterion; real Twist/plant goal |
| Obstacle appears | Original input stamp; marked cell indices and first costmap stamp; first changed detour plan; actual actuator result |
| Obstacle removed | Previously marked cells become free along current valid original-origin measured rays; changed plan; no clearing inferred from empty object list/expiry |
| Input interrupted | Original last receipt ages without renewal; stale report, existing native safe wait/cancel; no new D3 command connection |
| Revision/epoch switch | New explicit map revision/generation/source epoch; no inherited objects/results/coverage across context |
| Old frame returns | Replay exact previous identity after switch; ingress rejects, no stale publication/marking/command authority |

For each record distinct ROS receipt, identity verification, worker, actual D2,
actual D3, observation publication, costmap consumption, plan and actuator result.
Retain input/costmap/first changed plan stamps and their clock domains/epochs;
compute latency only with proven comparable clocks. Record raw command counts,
independent contact and boundary counts, wall deadline misses, stale age and
terminal action. `audit_case` only rejects incomplete evidence envelopes; a unit
PASS for this audit is **not** a physics/native PASS. Existing independent oracle
and native validator must still pass unchanged. No publication-only pass.

## Preserved environment and execution scope

No URDF, scenarios, product controller, footprint, speed, tolerances, timeout,
workflow, main or other-role files changed. Existing `native_ci.py` adds only the
readiness record before its original runner. All five cases and gating are intact:
empty, diagnostic_single_obstacle, fully_blocked,
diagnostic_appearing_obstacle, sensor_stale. NavFn + **direct RPP**, not RotationShim.
`/robot_scope_review_x`, domain 194, localhost-only, network-none Docker, no devices
or robot secrets. Existing fake plant is driven by real Twist and sends feedback.
D3 URDF remains explicitly ADVISORY_ONLY and is never connected to commands.
The five-case baseline is separate from all six **NOT_RUN** new C4 chain cases.

## Commands and checks

```sh
git fetch --no-tags origin 7ac0d55b07abd20902d6d756c6b225733613fea7 e0bc9cf8ba8bd22b406a287e1a9ef867a0cd367b 7313f0a31c00ae87ae216b84ca41a23804e91917
python3 -m experiments.expansion_20261029.d3_collision_sim.c4_readiness --output /tmp/d3-c4-readiness.json
python3 -m unittest discover -s tests/expansion_d3 -v
python3 experiments/expansion_20261029/d3_collision_sim/native_ci.py --stage-only --output /tmp/d3-followup-stage
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
```

Pre-publication focused **34 PASS**, JavaScript **699 PASS**, syntax **112 PASS**.
Pure namespace-only staging succeeds; this is not a native launch. Previous local
socket denials are not retried. Unfiltered Python and Ruff run in the unchanged
hosted standard CI; local Python has no Ruff installed (NOT_RUN locally).
Exact source/final SHA, remote tree equality, native launch/results and terminal
final CI are recorded in C4_NATIVE_RESULTS.md after the actual hosted runs.

**Remaining one connection:** C4-owned bounded-worker→Runtime ROS adapter with the
above capture/context/raw-ray contract. Until submitted, only this new integration
is INPUT_REQUIRED/NOT_RUN; the existing five-case baseline stays independently
verified. No infinite owner polling or duplicate adapter implementation.
