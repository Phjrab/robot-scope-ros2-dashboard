# D0 ROUND4: first feasible1 RPP collision-ahead audit

## Decision and frozen scope

The minimum offline diagnosis is complete. Current physical contact is excluded
at the **saved pre-warning pose**, not at an invented synchronous controller pose.
The native path's free center cell does not certify the full oriented body.
Exact RPP rejection cause remains **NOT_RUN_MISSING_SIGNALS**. Do not tune away
this failure, shrink the body, relax clearance, or claim geometric impossibility.
No feasible2/tight5 expansion, native rerun, hardware access or deployment occurred.

D0 input HEAD: `8ba7affe1023fc0791136aa47ca1cd8884b54685`.
C3 source: `5eacacf42378ad91319a5de323df7844f34ea33b`.
C3 latest report checked: `32914885d84b9bf98e799492366aeab0f908f547`;
its competition_nav2 tree equals the native source. The shared-input adapter and
native execution are **already complete**, not ADAPTER_REQUIRED.
[Native run 40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349)
artifact12588085458 was privately downloaded and SHA256 verified as
`c2d20937c7e2d7d2d20527994e8eaa116d2fab1d556638562ce688972317d8cb`.
The archive and raw logs remain outside the repository. Per-input hashes are in
the [judgment JSON](../../../../experiments/competition_vm/arena_robot_sim/revisions/native_feasible1_audit_20261025/results/judgment.json).

## First actual failure, separate from recovery

Native log line144: `RegulatedPurePursuitController detected collision ahead!`,
wall epoch1792904808.540106401. A new path was delivered immediately before it.
Using the recorded DDS source timestamp/age and monotonic receipt bridge brackets
this between saved sim6.40 and6.45 samples. This clock bridge is not atomic TF capture.

Latest pre-warning sample: `(x,y,yaw) = (0.5167972571840633,
1.7462801514863986,1.5282629698786039)`, elapsed4.85s.
Raw0.81×0.56m minimum geometric clearance is **0.186235160608m**;
effective0.87×0.62m clearance is **0.154986676804m**. Both are boundary minima.
The recorded body has no physical contact there. Margin0.03m is applied once,
native padding0 and grid0.02m in both captured costmaps: no double footprint
padding. Inflation0.4m is a separate cost field, not another body margin.
Later Spin collision at1792904810.449059220 is recovery, not this primary event.

## One bounded geometric counterexample, with sensitivity

The newest global path (source sim6.35) point21 has XY
`(0.5158475760553571,1.9545850698370089)`. Its center cell in the newest **global**
map (source sim6.15, about0.25s older) is free0. The outgoing-segment heading
1.401993995443007rad puts both raw and padded body through the true cone base.
However, native yaw was not recorded. Central-chord heading1.5667803695454525rad
leaves raw clearance0.009293731054m while the padded body still overlaps.
This is a heading-dependent geometric counterexample, **not an actual rejected
RPP pose or proof that RPP follows path yaw**. RPP computes curvature from carrot XY.

Holding the last accepted command v0.18m/s,w−0.01558637696076498rad/s for1s
from the saved pose yields raw minimum23.369mm and padded first sampled contact
at0.955s (independent continuous root0.954799167946s). This is explicitly
counterfactual, not the unpublished rejected twist or native Euler arc.
The original witness remains holonomic only, not a native solution.

[Diagnostic topdown image](../../../../experiments/competition_vm/arena_robot_sim/revisions/native_feasible1_audit_20261025/results/first_failure_topdown.png)
shows the recorded path/global grid, original cone/boundary, saved body and labelled
derived/counterfactual footprints. It was visually inspected. No new map is exported.
Independent SAT/segment implementation reproduces the values and heading sensitivity.

## Missing signals and one next action for C3

The recorder keeps global OccupancyGrid and path XY only. Exact local costmap,
controller input TF pose, rejected v/w, carrot and failed projected sample are absent.
Occupancy99 represents raw253 inscribed cost, which alone is below RPP's lethal254
threshold. Treating every inflation cell as collision would fabricate a cause.
Raw unknown255 has separate semantics. The older global grid cannot substitute
for the actual local checker input.

**Next one task:** instrument one first-warning packet and repeat feasible1 with
unchanged fixture/config. Suggested precise changes (C3 owner only):

1. `experiments/competition_nav2/native_runner.py` subscriptions129–136:
   add local raw costmap and time metadata; callback211–215: preserve Path
   quaternion and per-pose stamps instead of XY only. Record receipt and source
   times independently; preserve the established age/epoch contract.
2. In version-matched RPP `computeVelocityCommands`, immediately before the
   `isCollisionImminent` call/throw, retain input TF pose+stamp, candidate v/w,
   transformed path and carrot. In `isCollisionImminent`/`inCollision`
   (upstream1.1.20 lines440–536), retain the first failing footprint pose,
   raw max cost/cell and whether current-pose or projected sample failed.
   Arc topic alone cannot cover initial-current-pose rejection. Capture a
   consistent local grid snapshot/footprint under its normal lock, not a
   later asynchronous grid. One bounded packet, no tuning or safety changes.
3. Reuse the existing isolated native runner. With the reviewed diagnostic
   image lock available, the single-case command is:

```sh
python3 experiments/competition_nav2/rpp_contract.py run --mode isolated-sim \
  --fixture experiments/competition_nav2/d0_input/experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/fixtures/feasible1.truth.json \
  --lock /path/to/reviewed-image-lock.json --output /tmp/c3-round4-feasible1
python3 experiments/competition_nav2/validate.py /tmp/c3-round4-feasible1/run
```

This is a proposed C3 follow-up, **not executed by D0**. Do not invoke the six-case
run_d0 suite. Exact upstream source references and recording gaps are in the
[source contract](../../../../experiments/competition_vm/arena_robot_sim/revisions/native_feasible1_audit_20261025/source_contract.md).

## Reproduction and verification

[Reproduction commands and private input contract](../../../../experiments/competition_vm/arena_robot_sim/revisions/native_feasible1_audit_20261025/README.md).
Dedicated audit tests:7/7 passed, including the actual verified archive. Independent
geometry review:10 assertions passed. Original fixtures, witnesses, models and
checksums are unchanged. Only the new analysis revision and this report are owned
changes. Full regression results are recorded below before publication.

Final local full suite: `python3 -B -m unittest discover -s tests -v` ran2691
checks:1 failure,25 errors,1 skip. The failure is the existing immutable VM manifest
expectation (`UNAVAILABLE_OR_CHANGED` versus `SYNTHETIC_ONLY`); all25 errors are
AF_UNIX/socket `PermissionError: [Errno 1] Operation not permitted` in this VM.
These are not counted as passing or fixed here. C1 owns common manifest integration.
`node --test tests/*.mjs`:660 passed. JavaScript syntax checks cover104 files.
The exact published HEAD's terminal CI outcome is reported with its verified SHA
in the handoff, rather than creating self-referential report-only commits.
