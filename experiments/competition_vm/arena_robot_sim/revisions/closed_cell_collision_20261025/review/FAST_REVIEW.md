# Independent summed-area fast-path review

Final result: **21,240 cases passed, zero false-clears against exhaustive long-double SAT, and zero Boolean differences against the corrected generic collision implementation.**

Run `python3 experiments/competition_vm/arena_robot_sim/revisions/closed_cell_collision_20261025/review/independent_fast_review.py` from the repository root. Results and tested file hashes are in `fast_geometry_review.json`; console output is in `fast_geometry_review.log`. Earlier generic review files were preserved unchanged.

Coverage:

- 1,944 deterministic occupied-cell edge/gap cases, clockwise/counterclockwise rectangles and unequal side lengths; exact 0, positive/negative quarter turn and half turn, plus non-eligible near-quarter-turn and arbitrary angles.
- 504 map boundary cases, including both exact closed boundaries, positive gaps, negative origins and large coordinates.
- 504 ULP-neighbor probes at the numerical tolerance boundary.
- 18,000 seeded random rectangular fast-path and nonrectangular fallback queries across occupancy densities, resolutions, poses and orientations.
- 288 tiny-resolution and interior-overlap probes, including 1e-11, 1e-9 and 1e-7 m grids.
- Immutable snapshot ownership, observation additions/removals, independent per-instance integral/template caches and malformed-input fallback.

## Issue found and resolved

The initial fast implementation disagreed with generic SAT on 28 tolerance-boundary probes. Some gaps classified as collision by generic SAT were clear in the fast implementation, although the exhaustive zero-tolerance oracle found no physical overlap. Floor/division rounding at the tolerance-expanded index boundary caused the difference. The revised fast implementation falls back to generic SAT near ambiguous occupied-cell boundaries. All 28 examples and the full expanded suite pass on the revised implementation.

## Cache review and limits

The summed-area table derives solely from the snapshot-owned immutable mask. Rectangle templates contain immutable coordinate tuples and are stored per snapshot; no global or cross-observation cache was found. The planner constructs a fresh snapshot for each planning call, and standalone guards remain generic uncached queries. The cache's lifetime does not enforce sensor freshness or TTL; callers still own those checks.

This is finite sampled geometry and cache validation, not formal proof, full-route validation, continuous-motion certification, hardware testing or a real-time guarantee. The fast and generic implementations intentionally differ from a zero-tolerance geometric oracle on conservative near-contact cases; their Boolean classifications agree in all reviewed cases.
