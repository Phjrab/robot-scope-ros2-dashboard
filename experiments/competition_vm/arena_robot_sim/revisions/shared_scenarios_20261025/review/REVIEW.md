# Independent D0 shared-fixture review

Reviewed 2026-10-25; read the complete D0 ROUND3 role attachment. Repository HEAD at review start: `d3981786e51f58e87fc62e6c7607b432d2c87434`. Read-only remote branch check returned `69789d3cadded006dfc303e65e57f61941753214`. These identify context, not the eventual submission commit. Only this `review/` directory was written by the reviewer.

## Result

**PASS for geometric witnesses, not native execution.** All six saved paths were checked by `audit_saved_witnesses.py`, which imports no exporter, search, SAT, or project collision helper. Its complex-plane winding test and edge geometry operate directly on saved truth polygons. Sampling bounds each body's vertex displacement by 0.5 mm; subtracting half the actual interval's translation-plus-radius-times-yaw motion bounds continuous clearance between samples.

- Original tight5: 9,974 samples; minimum sampled distance 0.035 m; continuous lower bound **0.03475 m**, greater than the required 0.03 m. This independently supports the separate 1 mm sweep's 0.0345 m bound.
- Feasible1, feasible2, OPEN diagnostic: continuous lower bound 0.03475 m each.
- Empty and dropout's geometric route: continuous lower bound 0.05375 m each. The dropout route is not evidence the controller continues driving safely through missing observations.
- Canonical input manifest: `1e995e63e9e601433399f052d6a9630b4d5fb53081cfd1b00003aae2b16ef84e`. Per-truth and witness hashes are in `independent_results.json`.

## Preserved geometry and distinctions

Read original `rulebook-20261015/geometry.py`, earlier left-slalom source, exporter, saved truth/observation streams, and C3 `16c63e08be5a7c10887e9e05cae94e94788e990f` fixture generator, native runner, and FOLLOWUP using read-only Git object access.

The original five centers remain (.18,1.55), (.18,1.83), (.82,3.00), (.82,3.28), (.18,4.45). Every square base remains 0.26 m; cone radius/height remain 0.12/0.32 m. The collision body remains 0.81 by 0.56 m, separate from the standing visual envelope. No cone shrinking, moving, body shrinking, parking permission, or terrain clearance was used to certify original tight5.

The left-straight floor is identical in original and approved corridor-parallel revisions; their full outer boundaries differ. All scene paths are constrained to the original left floor. Original holes, parking bay, center platform and ramp/stair zones are retained as forbidden polygons. This is planar, not terrain traversal or parking execution.

Feasible1 and feasible2 have one and two full-size cones respectively and different scene hashes. Their similar clearance and lateral motion counts do not imply identical inputs. OPEN changes cone spacing only and cannot be substituted for original tight5. Real `map_transform` stays null. Identity simulation transform and viewer `(x,y,z)->(x,z,-y)` round-trip tests pass without claiming measured-map registration.

## Meaningful qualifications and corrected findings

1. Original tight5 witness has **30 lateral translation edges at fixed yaw**. It proves holonomic configuration-space geometric feasibility, not differential/nonholonomic RPP feasibility, dynamics, gait, tracking, or physical stopping. C3 must generate its own native path and commands, never consume this witness as an answer trajectory.
2. The blocked case has an invalid goal as well as a transverse three-cone barrier; its recorded search expands zero states because the goal fails validity. Do not describe that as exhaustive reachability exploration. Separately, at y=2.5 the raw edge gaps are 0.02/0.09/0.09/0.02 m versus the body's minimum projected width 0.56 m. No impossibility claim is inferred merely from bounded search failure.
3. The circumscribed circle plus 0.03 margin has diameter about 1.0447 m, already larger than the 1 m middle corridor. That approximation's failure does not imply failure for the full rectangle. The search also adds a disclosed 1 mm numerical reserve; the independent checker uses the actual unpadded body and requires 0.03 m separation exactly once.
4. The initial raycast provenance omitted the actual `virtual_fences.json` dependency; exporter author added fence source path/hash for both revisions. Initial ambiguous original-tight5 expectation was changed to `GEOMETRIC_WITNESS_NATIVE_NOT_RUN`, retaining prior `NOT_ADOPTED_SAFE_WAIT` separately. Both corrections were checked in the final exported inputs.
5. Truth and observation streams are separate and hash-linked. First-hit aligned-cone occlusion, full square-base return, scheduled appearance, origin, four heights, FOV/range, source/receipt stamps, and absent observations at dropout t>=4 s are tested. These are ideal raycast probes at prescribed poses, not a live native rollout. An existing ResourceWarning from the frozen simulator's unclosed fence-file read remains; it did not fail checks.
6. C3's existing `World(fixture)` and runner use a different fixture schema, sensor timing, footprint and right-corridor/parking assumptions. This manifest honestly says **ADAPTER_REQUIRED**. C3 native execution for these D0 inputs is **NOT_RUN**. The remaining connection is a C3-owned adapter preserving these scene hashes, full-body clearance and strict keepouts while sampling observations at actual native simulated poses.

## Actually executed

From repository root:

- `python experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/test_export_fixtures.py`: **15 PASS**.
- `python experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/test_feasibility.py`: **7 PASS**.
- `python experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/review/test_independent_audit.py`: **5 PASS**, including edge crossing without vertex inclusion, collinear contact, containment, a deliberately colliding witness rejection, and all scene-hash links.
- `python experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/review/audit_saved_witnesses.py`: **6/6 PASS**, reproduces `independent_results.json` in about 2.5 s.

No new planner/framework, long simulation, rendering, Robot/SSH/service access, C3 source edit, main edit, PR, commit or push was performed by this review worker. Parent owns full-suite checks and authorized D0 publication.
