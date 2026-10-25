# D0 ROUND3 — shared native-input contract and original tight-layout feasibility

Branch: `review/20261024-d0-vm-offline`. Work started from verified remote
`b1561bfc23c7935dcd61cb08605fde4e4b4f0a91`. The user's explicit role-branch instruction
is the exception to AGENTS.md's default main-only workflow; AGENTS.md is unchanged.
Prior restored collision checkpoint `69789d3cadded006dfc303e65e57f61941753214` and
finished bounded acceleration/replay `924345a0f4b46f1d2f3f467142cad069124a17ad` are preserved.
ROUND3 functional input/feasibility commit: `83f4ee8d6971d00ab31b2de0eeebf329542dd5d6`.
This document is a later report commit; its own final SHA is given in the submission,
not pursued through self-referential commits.

## Primary result and remaining actual connection

**Original tight five-cone geometry has a certified holonomic SE(2) witness, without
shrinking the body, cones, forbidden areas, or 3 cm clearance.** The independent
review-only verifier checks 9,974 samples at <=0.5 mm vertex displacement and a
continuous interval reserve: minimum lower bound **0.03475 m**. The search author's
separate <=1 mm sweep certifies 0.0345 m. Existing controller SAFE_WAIT is preserved
as an actual failure to finish, not retroactively promoted to success.

The witness includes 30 lateral translation edges at fixed yaw. It is geometric
feasibility for a holonomic quadruped body, **not RPP/unicycle feasibility, a smooth
dynamic trajectory, native Nav2 execution, gait or physical stopping proof**. It
must never be supplied as NavFn/RPP/MPPI's answer path or simulated velocity script.

Pinned C3 `16c63e08be5a7c10887e9e05cae94e94788e990f` was read only. Its current CLI
cannot accept external D0 fixtures; `World` uses a different global body and a 2D
ray-marched sensor. Therefore native consumption here remains
**ADAPTER_REQUIRED / NOT_RUN**, not a claimed integration success. The missing
connection is identified precisely rather than hidden behind another D0 harness.

## Fixed inputs and direct paths

Root: `experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/`.

- `fixtures/geometry.json`: full original and approved corrected geometry, source
  and fence hashes, floors/holes/terrain/parking keepouts, body versus visual envelope.
- `fixtures/SCENARIO.truth.json`: actual cone base polygons, dimensions, spawn times,
  poses, source seed/stamp, sensor contract and expected results; hidden truth.
- `fixtures/SCENARIO.observations.json`: separate fixed-pose sensor conformance stream,
  source/receipt time, epoch, 360 ranges and explicit absent dropout observations.
- `fixtures/manifest.json`: canonical value hashes. Seven scenes / 16 small JSON
  inputs total 192,454 bytes; no map grids, bags, videos, weights or copied meshes.
- `CONSUMPTION.md`: exact read-only C3 inspection and narrowly owned adapter request.
- `FEASIBILITY.md`, `feasibility_results.json`, `witnesses/`: A/B/C/D comparison,
  bounds and audit-only witnesses. `review/REVIEW.md` is independent review.

Canonical manifest SHA-256:
`1e995e63e9e601433399f052d6a9630b4d5fb53081cfd1b00003aae2b16ef84e`.
Hash encoding: sorted-key compact JSON, UTF-8, no NaN. The file has a trailing
newline, so this canonical digest is intentionally distinct from byte SHA.
Each truth wrapper exposes a separate stable `scene_sha256` matching feasibility
input hashes; expectation/provenance changes remain protected by full truth hashes.

| Scenario | Canonical scene SHA-256 | Bounded result | Continuous lower bound (m) |
|---|---|---|---|
| empty | `bc8a9e3a728d6ce96d078a2d9e2ab167f90e17e5172069e28d79e72c4e262bdd` | CERTIFIED_FEASIBLE_WITNESS | 0.05350000000000028 |
| feasible1 | `339a754ab4dd636092aa9b3aceb777ea43684c47519f661576e161f822a0affc` | CERTIFIED_FEASIBLE_WITNESS | 0.03449999999999992 |
| feasible2 | `4c39f22b058538de7b6626d024d353bb6327892fdb03c74ffb339b1d274dacc7` | CERTIFIED_FEASIBLE_WITNESS | 0.03449999999999992 |
| original_tight5 | `4485bc958ed0894f4a8a33767cf6fbe55ae4c3f42382b010f0ff7cd18bbab605` | CERTIFIED_FEASIBLE_WITNESS | 0.03449999999999992 |
| blocked | `f2861ed1ba6ce252c5fc019fe9ef62f2de6342602b798881affcde1f1c59d3a0` | NO_WITNESS_WITHIN_BOUNDS | — |
| sensor_dropout | `3f2bf3000a84ee5795aeb4e77acd13ada0c09262dcbe0ecb0af86d1a05f80e34` | CERTIFIED_FEASIBLE_WITNESS | 0.05350000000000028 |
| open_diagnostic | `834a0b584fe96ac096f1bae35a3e8ba891cdea99df588ae878e381b31f730697` | CERTIFIED_FEASIBLE_WITNESS | 0.03449999999999992 |

The sensor-dropout witness concerns geometry only; no commands may continue after
freshness expires. Blocked has both a goal violating the 3 cm clearance and an
independent transverse barrier with at most 9 cm gaps. Its zero search expansions
are not exhaustive reachability evidence. OPEN changes longitudinal cone spacing,
not the physical floor boundary; it is never substituted for original tight5.

## Frames, envelope, clearance and visibility

All navigation inputs are metres/radians, right-handed Z-up, lower-left arena
design origin. `arena_design -> d0_sim_map` is identity **within this simulation**.
GLTF `(x,y,z)->(x,z,-y)` is viewer-only; transform roundtrips are tested. Real-map
`map_transform=null` remains unchanged: measured map registration is INPUT_REQUIRED.
Original rulebook geometry is retained. The corridor-parallel right-side correction
is preserved as approved design geometry, not an official field survey. Both share
the same left-straight floor used by these seven cases.

Collision body is .81 x .56 m, distinct from smaller standing FK visual bounds.
The planar sweep requires .03 m once. Search uses the conservative .87 x .62 m
padded rectangle plus a disclosed 1 mm numerical reserve; independent certification
uses the unpadded body and checks actual distance. Circumscribed raw-body radius
plus margin is .522366733 m (diameter 1.044733466 m), already wider than the 1 m
corridor. This circle rejection is not rectangular-body impossibility. The .534158216 m
circumscribed radius of an axis-padded rectangle is a different approximation.
The old .225 candidate constant is not the active curved planner's robot radius.
Do not duplicate robot radius inflation/full-body sweeping or apply .03 padding twice.

Four ground-relative scan heights .025/.10/.20/.35 m, 360-degree horizontal FOV,
1-degree spacing, valid range (.02,8)m and first-hit occlusion are explicit. Native
live sampling must use actual plant poses, not these conformance-probe poses. Truth
cones must not enter a static map prior. Semantic keepouts remain restrictions,
not fake laser returns. Dropout at 4 s removes observations; no old range restamp,
clear-scan substitution, or old nonzero command replay is permitted.

## Bounded original-layout diagnosis

Lattice A* is an offline feasibility analysis, not another runtime planner:
.025 m x/y, 36 yaw bins/10 degrees, x 0..1.375 m, y .5..5.5 m, 405,216 states,
90 s guard between expansions (not hard interruption during initialization).
The original witness preserves exact cone centers (.18,1.55),(.18,1.83),(.82,3),
(.82,3.28),(.18,4.45), .26 m square bases and full body. Opposing cones leave
only .04 m longitudinal center-transition slack after padding; the witness uses
lateral translation there. Observed unknown cells, closed-cell raster conservatism,
87x61 expansion/EDT reserve, smoothing and current-pose guards can prevent the old
controller from using it. This round does not overassign one unproven cause.
No witness within finite resolution/time bounds would prove continuous impossibility.

## Slow planning versus fresh commands

The already-started collision follow-on was bounded and finished, not made a
prerequisite for C3's native NavFn/RPP. Preserved fresh evidence: 34 focused tests,
15 watchdog tests, 12,900 generic and 21,240 accelerated oracle cases, five independent
replays. Final paired planner medians 2.047/8.204/.693 s compare old-buggy/generic-
corrected/accelerated-corrected on the same observed snapshot. Shared-VM load included
repository checks; no real-time claim. .693 s still exceeds experimental .1/.25 s
budgets. Generic and accelerated executed traces match exactly. No further tuning,
RRT, RL, Isaac installation, gait simulator or long rendering was started.

`profile_observations.py` is a three-probe small profile only: pinned static geometry
and fence preparation separated from current active-cone assembly and pose raycast;
all 360 ranges match the exporter. `observation_profile.json` records hashes and times.
Geometry/epoch change must rebuild any static cache. Dynamic observations/source
stamps remain current, and watchdog/TTL/path validity stay independent. The frozen
sensor wrapper mutates a temporary module geometry binding; C3 must isolate or
serialize each sensor instance rather than share that mutable global across scenes.

## Actual checks and reproduction

From the repository root:

```sh
D0=experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025
python3 "$D0/export_fixtures.py" --check
python3 "$D0/test_export_fixtures.py"
python3 "$D0/test_feasibility.py"
python3 "$D0/review/test_independent_audit.py"
python3 "$D0/review/audit_saved_witnesses.py"
python3 "$D0/profile_observations.py"
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 scripts/check_repository_secrets.py
```

- Exporter contract: 15 PASS; feasibility: 7 PASS; independent adversarial controls: 5 PASS.
- Six saved witnesses independently certified; original cone/body/forbidden checks,
  hash links, transform roundtrip, occlusion, spawning and dropout verified.
- Existing frozen simulator emits ResourceWarning for an unclosed fence-file read;
  tests pass and frozen source is not changed for that warning.
- Full Python/JS results and exact log hashes: `validation/submission_checks.json`.
  D0's pre-existing public manifest mismatch stays separate from C1's evidence registry
  integration. No common manifest, signal core, lifecycle, C4 or production UI is edited.
- Exact final remote CI run/result is reported with the submission; report-only final
  SHA is not recursively embedded here. Nested experiments are tested explicitly,
  not inferred to run from the generic repository CI badge.

## Cross-role preservation and next one task

C1 pinned/current integration `765622ecbe20dd29b40296dd2ad24fa508ac9443` was read only;
its explicit evidence registry selects prior D0 and resolves shared manifest selection
there. This D0 branch does not cherry-pick or duplicate that fix. Current L1 branch
exists at `5339e3b5c9906991e08766b61bd27d92e725aa6f`; main was
`104692fa0070ef085eee918913ea05fdb2d88c05` at read-only check. L1 is one commit ahead
of that main and diverges from C1 (3 ahead/3 behind); no claim of full integration.
L1 LiDAR STALE work and main localization/initial-pose work are untouched.

**Next one task:** C3 owner adds the narrow external-fixture/body/sensor adapter
specified in CONSUMPTION.md, then runs its actual native planner/controller against
these unchanged hashes, including the original tight case. Witnesses remain audit-
only; C3 must report its own path/commands and independent full-body sweep. No new
D0 harness or performance work is needed first.

No main merge, PR, robot/SSH/HTTP probe, sensor/camera ownership, service change,
deployment, ARM or physical goal/velocity/posture command occurred. No standing
future monitoring or unattended robot work is promised.
