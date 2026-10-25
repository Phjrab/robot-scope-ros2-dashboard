# Closed-cell collision rebuild, 2026-10-25

VM-only experimental follow-on to frozen `curved_progress_20261024`. Rebuilt from
remote b1561bfc23c7935dcd61cb08605fde4e4b4f0a91 because the earlier unpublished
candidate was unavailable. No old PASS counts or timings are treated as new runs.
No hardware, deployment, native Nav2 configuration, gait dynamics, or real-time
qualification. Original revisions and `avoidance/core.py` remain unchanged.

## Correctness change

The old grid query can omit a contacting cell immediately below a footprint's
minimum cell index, or above its maximum through floating-point division. Its
strict floating-point SAT may also classify rotated exact contact as clear.
`collision.py` includes both neighboring cells, expands the broadphase by its
explicit tolerance, and checks occupied closed cells with normalized convex SAT.
World boundary contact is conservatively occupied at both lower and upper bounds.
The tolerance is 1e-12 metres plus 64 floating-point epsilons times the maximum
coordinate scale (at least 1 metre). Sub-tolerance positive gaps can be classified
as collision; this never claims reduced safety clearance. This is numeric hygiene,
not a sensor-error model. Convex finite nondegenerate footprints are required;
invalid footprints fail closed; invalid grid construction raises ValueError.

## Acceleration and lifecycle

A fresh immutable occupancy snapshot is constructed per `build_path` call. Exact
point memoization is closure-local to that call, with fixed yaw/body parameters.
No cache persists across maps, epochs, scans, or planning calls. Every swept guard
queries its current grid directly and keeps no cache. The full swept footprint,
source age, receiver age, occupancy TTL, and watchdog output gate are not removed.
All cones/layouts and .81 x .56 m body plus .03 m clearance remain unchanged.

`benchmark.py` pairs five alternating runs on the SAME published initial observed
OPEN snapshot: old buggy planner, corrected nonmemoized planner, corrected
snapshot/memoized planner. It asserts exact path equality between the two corrected
versions. Old-vs-corrected paths need not match. Timing is shared VM evidence only,
not hardware timing or proof of the experimental .1 s / .25 s budgets.

## Reproduction

From this revision directory, first restore the baseline lossless fixtures:

    python -c "import sys;sys.path.insert(0,'../curved_progress_20261024');import publication_checks;print(publication_checks.verify_and_restore())"
    python -B -m unittest test_collision test_progress -v
    python -B review/independent_geometry_review.py
    python -B run_candidate.py open_normal tight_normal open_dropout open_delay blocked_5
    python -B benchmark.py

Fresh scenario traces are synthetic VM output, not real robot measurements.
Full-course or articulated rendering is not repeated in this bounded collision
rebuild. Tight SAFE_WAIT is a preserved limitation, not proof of impossibility.

## Summed-area refinement

The first generic vector SAT rebuild was geometrically correct but slower than
the original buggy predicate. Its fresh paired timings are retained separately
in validation/benchmark_generic.json. `fast_snapshot.py` adds a per-snapshot
summed-area table ONLY for verified axis-aligned rectangles at exact quarter-turn
headings. All other convex geometry and every swept command guard still use the
reviewed closed-cell SAT. Both boundaries of the rectangle query include the same
metric tolerance. Immutable mask ownership and cache lifetime are unchanged.

## Fresh finalized results

- 34 focused tests + 15 unchanged watchdog tests freshly rerun pass.
- Generic oracle: 12,900 cases, zero false-clears; final accelerated oracle:
  21,240 cases, zero generic differences and zero physical false-clears.
- Five final replays independently pass. OPEN reaches goal stopped at 57.4 s;
  tight remains SAFE_WAIT at 24.1 s; delay/dropout at 7.2 s; blocked at 3.1 s.
- Full actual poses/commands/states and deterministic metrics exactly match
  frozen baseline. Corrected tight XY planned paths differ only in 20 frames.
  Final acceleration exactly matches the generic-corrected traces including paths.
- Independent continuous interpolation clearance bound is at least 35.507 mm
  across these cases; not dynamics, articulated envelope, or hardware validation.
- Paired five-run medians: original buggy 2.046928 s; corrected uncached
  generic 8.203918 s; corrected accelerated 0.693391 s. Some runs overlapped
  repository checks on the shared VM. These are not real-time or hardware claims.
  0.693 s still exceeds both experimental .1 s tick and .25 s freshness budgets.
- Bulk synthetic point/mesh traces remain local. The small lossless
  validation/execution_samples.json.gz retains every execution sample plus path
  hashes; execution_manifest.json records full local raw trace hashes.
  Re-run run_candidate.py to generate full replay inputs, then run
  review/independent_review_scenarios.py (generic comparison requires the earlier
  generic run in results/generic_candidate02; documented in that review).
- User ROUND3 shifts priority to shared native-C3 inputs and feasibility, not
  further planner tuning. No installation, full-course rendering, or RL performed.

To regenerate the optional generic reference without editing any source, run
`python -B replay_generic.py` before the independent scenario reviewer. This is
slow and is not a prerequisite for C3 consuming ROUND3 shared inputs. The default
CI currently does not discover these nested experiment tests automatically; the
explicit commands/reports, not the repository CI badge, establish their result.
