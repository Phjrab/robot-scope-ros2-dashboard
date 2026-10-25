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
