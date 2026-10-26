# D0 ROUND5 — independent cost-field / footprint audit

## Decision and frozen scope

**The requested independent audit is complete and frozen.** B's effective-margin
boundary violation is reproduced. A free center does not certify the oriented
footprint. Inflation support alone is not a complete discrete-checker fix: a small
quantized-corner regression still bypasses the source-reconstructed threshold even
with 0.58 m support. This is **not** a new native failure or an adopted correction.

- D0 starting/remote HEAD: `da7230bb65722e4a1d3f4ab0c1d16e63fcd344e3`.
- Read-only C3 latest remote HEAD: `d253ee090a5f5c145c3842ed2cc0105d7d95fea3`.
  Its ROUND4, ROUND4_OMNI_FAILURE and ROUND4_NATIVE were read first.
- Read-only main: `104692fa0070ef085eee918913ea05fdb2d88c05`.
- Existing role branch: `review/20261024-d0-vm-offline`; exact final submission and
  tested commit are reported in the external handoff to avoid self-reference.
- Only new `footprint_costfield_audit_20261026/**` and this report changed. An old
  clone was absent, so a clean independent clone of the same role branch was used.
  No reset, shared-checkout change, merge, PR, other-role write or force-push.

No first-time contract/binding/integration/installation work was repeated. No native
Nav2 rerun, robot access, camera, service, deployment or motion. Original fixtures,
parking/forbidden polygons, cone, raw 0.81×0.56 m body, once-padded 0.87×0.62 m body,
margin 0.03 m and nominal 0.02 m grid remain fixed. No new image/video was necessary.

## OBSERVED — retained artifact, not new execution

[Run 40168963222](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168963222)
uses source `2a1b1f172f30d010fa33d9b7f247a9163f175e82`. Artifact `12590081484` was
available and downloaded privately. ZIP SHA256 exactly matches
`43580b9a3ced0b6bba00211a14a6398650fb7018c2794243f2af092cc5c34c29`.
The five consumed input-file SHA256s match the retained C3 receipt; environment
source matches, so no raw-input substitution was needed. Full raw data stays out of Git.

The trace contains one first boundary crossing at sim 3.35 s, then a stationary
violating footprint. **64 positive samples are one crossing, not 64 impacts.**
No nonzero actuator follows that first failure. This successful stop is not safety PASS.

## INDEPENDENT_RECONSTRUCTION — prior and first-failure poses

| Saved sample | Pose (x, y, yaw) | Raw floor clearance | Padded floor clearance |
|---|---|---:|---:|
| Prior, sim 3.30 | (0.4979798532, 0.9640031154, 1.4374741223) | +34.377460 mm | +0.655860 mm |
| First failure, sim 3.35 | (0.4980243678, 0.9643053338, 1.4308869105) | +33.215781 mm | **−0.674681 mm** |

Floor y=0.491 is unchanged. The first failing padded corner is
(0.7443330077, 0.4903253195). Raw body is still clear: this is the required-margin
violation, **not raw-body physical contact**.

The last received local map before both trace samples has source sim
3.049999999; the next has source sim 3.449999999. Both show center occupancy 0;
closed-cell edge reconstruction finds 4 lethal cells for the previous pose and 5
for the failing pose. The previous pose's continuous +0.656 mm floor margin but
raster overlap is expected conservative discretization, not an extra contact event.

Global map receipts matter: the sim-3.30 global publication arrived **after** the
sim-3.30 trace. Its prior global snapshot is source 2.299999999, next 3.299999999.
At failure, global before/after are 3.299999999 / 4.299999999. All selected sources,
receipts, resolutions, origins and sparse hit cells are retained in the audit JSON.
Do not choose a newer map merely because its source stamp is numerically close.

Frame alignment is SOURCE_SUPPORTED_INFERENCE: the pinned
[native publisher](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/2a1b1f172f30d010fa33d9b7f247a9163f175e82/experiments/competition_nav2/native_runner.py#L404-L425)
constructs identity map→odom and publishes plant pose odom→base_link. Runner
SHA256 `fdff344a0d10403195ab68121b18ba069ab1e3f02f525df740597ca75556f56f`.
No atomic TF-buffer or internal checker packet was recorded. The overlays are not
claimed to be the exact instantaneous native checker input.

## SOURCE_SUPPORTED_INFERENCE — cost coverage and gate conditions

Exact Humble Nav2 1.1.20 sources, not Rolling:
[Smac checker](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_smac_planner/src/collision_checker.cpp),
[MPPI CostCritic](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_mppi_controller/src/critics/cost_critic.cpp),
[inflation formula](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/include/nav2_costmap_2d/inflation_layer.hpp),
[inflation support](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/plugins/inflation_layer.cpp).
Smac and MPPI source hashes match C3's `2be59308…b939` / `0630dc3f…7fa4` references.

ri=0.31 m; Rc=sqrt(0.435²+0.31²)=0.5341582163 m.
For non-inscribed distance d, C(d)=floor(252 exp[-5(d−ri)]), hence T=C(Rc)=82.
This formula itself has no inflation-radius cutoff. The emitted inflation field
has support h×ceil(Rinf/h), with h=0.02 m. Rinf=0.4 gives only 20 cells, less than
Rc/h=26.7079. It can therefore leave collision-relevant centers free.

Let D* be the largest center-cell/source-cell distance among lethal footprint
boundary hits for the actual raster checker and evaluated pose set. Necessary
coverage checks (sufficient for invoking the full check in the stated cost model):

1. Actual emitted support h×ceil(Rinf/h) >= D*.
2. Smac positive-threshold shortcut: emitted center cost >= T > 0.
3. MPPI with consider_footprint=true: center cost >= 1 **and**
   (center cost >= T or T < 1).
4. Verify layer enabled/current, actual footprint/padding/resolution/unknown policy,
   actual readback and source costs, then exact oriented-footprint collision result.

MPPI's score loop skips center cost<1 **before** inCollision; setting a threshold
nonpositive alone would not bypass that skip. T is derived from footprint/layer
in these reviewed sources, not an invented user parameter. Merely enabling
consider_footprint is not an unconditional full check.

### Discrete counterexample: radius-only prescription is insufficient

A synthetic 2 cm raw grid with pose (1.019,1.019,0), padded body unchanged,
center cell (50,50) and one lethal source at padded-corner cell (72,66) has
center/source distance 0.5440588203 m. At Rinf=0.4 or Rc its emitted center is 0;
at Rinf=0.56 or 0.58 it is **78 < T82**. Both source-reconstructed shortcuts still
skip the full footprint. A separate cell-center pose (1.01,1.01,0) has the same
corner-cell counterexample for the Smac-style snapped case. Actual installed
checker result is null / NATIVE_NOT_RUN, not fabricated native confirmation.

The finite MPPI-style sweep covers 64 yaws ×16 subcell offsets ×4 vertices=4096
placements; expanded 0.58 support still yields 2000 below-T vertex cases. A
separate snapped-center sweep uses the original 16 cardinal/atan primitive
headings. These are finite source reconstructions, not a universal proof or planner run.
The vertex-only conservative bound Rc+sqrt(2)h=0.5624424875 suggests 0.58 support,
but does **not** by itself prove line-raster/heading/time collision coverage or
solve threshold eligibility. No arbitrary .4→.58 prescription is approved.

### Non-overblocking counterexample

A 0.68 m corridor x=[0.16,0.84], north-facing 0.62 m-wide padded rectangle, is
valid with 0.03 m lateral space; the 1.0683 m-diameter circumcircle does not fit.
Synthetic raw lethal wall columns 7/42 on a 2 cm grid, with an explicit inflation
recipe, invoke the footprint branch while its perimeter max is 253, not lethal254.
Source-reconstructed polygon Smac/MPPI accept this case. A wider second wall case
also passes. Native C3 must retain this acceptance, not declare all inflation or
circumcircle overlap a collision. This is a regression field, not modified arena geometry.

## Stored-cost semantics

[Publisher mapping](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/src/costmap_2d_publisher.cpp):
raw 253→OccupancyGrid99, raw254→100, raw255→−1, raw0→0. Ordinary raw1..252
maps to 1+floor(97(c−1)/251), which is lossy. The raw-byte transport value255 in
compressed int8 observations means occupancy−1, not an independently retained
raw cost255 array. No ordinary raw costs were inversely inferred.
[Costmap2D constructor](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_costmap_2d/src/costmap_2d.cpp)
scales an OccupancyGrid with round(254*p/100); 99 becomes251, not253. That is not
the publisher inverse. The synthetic counterexample constructs raw cost directly.

## Deliverables and verification

[Audit revision](../../../../experiments/competition_vm/arena_robot_sim/revisions/footprint_costfield_audit_20261026/README.md)
contains audit.py, coverage.py, dedicated tests and small audit/case/coverage/verification JSON files.
`checker_cases.json` and `coverage.json` are C3's bounded evaluation inputs; never
inject these as a runtime route/hidden obstacle prior. All installed-native expected
results remain null. The original tight5 witness is untouched.

- Dedicated offline tests: **17 PASS**, including verified private-artifact replay.
- Mandatory full Python: 2691 tests, **1 failure, 25 errors, 1 skip**. Existing
  immutable VM manifest expectation fails (UNAVAILABLE_OR_CHANGED vs SYNTHETIC_ONLY);
  25 socket/AF_UNIX permission errors are VM restrictions. These are not fixed or
  counted as passing; C1 owns common integration.
- Repository JavaScript: **660 PASS**; syntax checks **234 files PASS**; new Python compile PASS. Exact submission CI is reported externally
  after publication; do not inherit C3's CI or call the baseline CI green.
- Actual Nav2 checker/new native run/physical observations/motion: **NATIVE_NOT_RUN**.
- Atomic internal checker packet only: **INPUT_REQUIRED**. It does not block this
  bounded independent analysis, and no automatic follow-up monitoring is started.

## One remaining task for C3

Use the existing installed 1.1.20 checker to evaluate these small raw-field cases
and the retained feasible1 correction, in the already authorized C3 scope. Reject
any cost-field/readback/footprint-check candidate that still skips a corner collision
or blocks the valid rectangle corridor. If radius-only cannot meet the discrete
condition, a genuine full-footprint fallback must bypass **both** MPPI's zero-cost
skip and conditional footprint gate; this is a code-level, version-checked option,
not a nonexistent parameter and not implemented here. Keep geometry and margin fixed.
D0 stops here; C3 publication is not a dependency and is not automatically watched.
