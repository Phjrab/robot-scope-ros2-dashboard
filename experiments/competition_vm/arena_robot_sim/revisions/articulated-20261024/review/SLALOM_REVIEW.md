# Independent final five-cone articulated replay review

2026-10-24 UTC. Reviewed `gait.py` SHA256
`ce266eeffa23238aa00553b28f3a933f0848111335adc4f9a23b339ae34a670b`.

## Final sources

- `left_slalom_20261024/results/slalom_5.json` SHA256
  `e0754856cecc8747b09cfb3f35de7a22482bfb9de9177db67da26bcdf99fca11`
- `left_slalom_20261024/results/blocked_5.json` SHA256
  `5bb828969be6f82da2ed35abff262e467a3c31eadd948788590ba18b3529ee49`
- Corrected `corridor-parallel-20261024` revision fences; the trace itself supplies
  only its strict left-corridor allowed floor polygon.
- The final planner envelope is longitudinal +/-0.405m and transverse +/-0.280m.
  Default animation stride remains 0.16m. No robot or cone scaling was used.

## Failure preserved and repair checked

The first articulated five-cone replay exceeded the original proposed +/-0.245m
transverse planner envelope: the visual mesh reached 0.263434m, with 33 interpolated
poses outside the envelope. Although that finite geometric sweep happened not to
hit obstacles, it did not establish that the planning envelope contained the model.
See `slalom_stride016_envelope_failure.json` and
`slalom_initial_0245_projected_hull_audit.json`. The simulation owner widened the
planning envelope and reran the planner; this audit uses the new immutable hashes
above, not relabeled old results. The short-stride experiment is not the final run.

## Final checks

16 independent unit/artifact tests PASS across original and new cases. Checks cover
joint limits, independently composed FK, mesh-ground clearance, foot-target IK,
source-pose interpolation, source hash identity, stationary stance, zero consecutive
stance XY slip, sampled joint velocity and all mesh vertices inside the final
planning envelope. `final_unittest.log` records the actual command result.

4,892 densely interpolated poses (4,441 slalom + 451 blocked) were checked using the
convex hull of all articulated visual mesh vertices. At ten substeps per animation
interval, wall/cone crossings, floor-edge samples outside strict permitted floor,
cone containment, joint-limit violations and planning-envelope violations are all
zero. Maximum local absolute extents are 0.396248m longitudinal and 0.262760m lateral.
Minimum mesh-ground distance is 0.884878mm. Boundary clearance sampled at roughly
15Hz is 0.084101m (slalom) and 0.100645m (blocked). The collision audit runs at roughly
150Hz and samples hull edges no more than 5mm apart. Exact final timings come from
record timestamps; frame times are evenly spread over the recorded duration.

These are projected geometric checks, not dynamics, contact forces, self-collision,
balance or physically feasible locomotion. The replay uses HOLONOMIC PLANAR root
motion and synthesized IK joints. The physical robot, terrain traversal, full-course
mission, original camera/model or calibrated sensors were not tested.

## Reproduction and dependency

The source traces and corrected arena must be available. In the reviewer's separated
clone they reside in a different local checkout; no source files were altered there.

    ARENA_SLALOM_SOURCE_ROOT=/absolute/path/to/slalom-checkout python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/articulated-20261024/review -v
    python3 experiments/competition_vm/arena_robot_sim/revisions/articulated-20261024/review/audit_slalom_projected_hull.py --source-root /absolute/path/to/slalom-checkout

When both revisions exist in the same repository, the default source root is the
current repository. Missing sources intentionally raise an error, not a silent skip.
An initial unconfigured invocation in the animation-only clone produced eight
missing-source errors; an imported TestCase also duplicated old tests. The loader
import was corrected and the explicit source-root invocation passed all sixteen
unique tests. No failing substantive checks were deleted to obtain this result.
