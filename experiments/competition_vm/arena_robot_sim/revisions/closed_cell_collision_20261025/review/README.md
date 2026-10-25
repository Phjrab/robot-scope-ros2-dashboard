# Independent collision geometry review

Run from the repository root:

```sh
python3 experiments/competition_vm/arena_robot_sim/revisions/closed_cell_collision_20261025/review/independent_geometry_review.py
```

## Result

The independently rerun candidate passed 12,900 comparisons with **zero false-clears**. The exhaustive oracle visits every occupied cell, uses normalized SAT axes and long-double, relative-coordinate arithmetic, and imports no candidate geometry helper or broadphase. Closed lower and upper map boundaries are treated as occupied.

- 12,000 seeded random convex polygons (triangles, rectangles, pentagons and octagons), varied angles, grid densities, resolutions and negative-world origins: exact Boolean agreement.
- 900 deterministic boundary/gap cases: occupied-cell edge and corner contacts, both map boundaries, rotated footprints, signed gaps, and origins up to 1e8 m.
- 237 conservative differences against the zero-tolerance oracle; all within the documented coordinate-scaled tolerance. Largest sampled positive gap was approximately 1.071e-7 m, in a large-coordinate case.
- Six malformed footprint checks fail closed, including a self-intersecting pentagram, nonnumeric/ragged input, degenerate/duplicate edges, and NaN.
- Source-array mutation does not change an existing snapshot. New snapshots and borrowed-mask guard queries see added and removed obstacles.

`geometry_review.json` records the tested candidate SHA-256, per-group counts, lifecycle results, and the largest conservative examples. `geometry_review.log` is the corresponding run output.

## Findings resolved during review

The first candidate had two robustness defects: a same-turn-sign check accepted self-crossing stars, and global-coordinate polygon-area arithmetic caused conservative collisions with centimeter-size gaps at an origin of 1e8 m. Nonnumeric and ragged footprints also raised conversion exceptions rather than failing closed. The author fixed these; the final independent rerun includes regression coverage.

## Cache lifecycle review

Source inspection of `simulate_curved.py` confirms `build_path` creates a new owned snapshot and a new closure-local `lru_cache` for each invocation. The cache key is the exact point tuple, not a rounded key; its yaw and footprint are fixed within that invocation. It is not a global or map-identity cache. The standalone collision guard retains no mask or cache across calls. Dynamic source age and TTL remain the caller's responsibility, not a property established by snapshot immutability.

## Scope and limitations

This is finite sampled validation, not a formal geometric proof, continuous-time swept-volume certification, perception validation, hardware validation, or a real-time guarantee. The oracle operates on represented floating-point inputs with long-double trigonometry; mathematical contacts may shift very slightly due to input and trigonometric rounding. Such conservative differences are reported, not silently counted as exact agreement. Planner cache lifetime was inspected in source; this review does not claim an independent full planner or course replay. No frozen core, robot, service, UI, deployment, branch, commit, or publication was changed by this review.
