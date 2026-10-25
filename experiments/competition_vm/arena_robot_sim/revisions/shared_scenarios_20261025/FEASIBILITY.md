# D0 ROUND3 bounded geometric feasibility

## Decision

A, the unchanged original tight five-cone layout, **has a certified planar holonomic geometric witness**. This is not native Nav2 execution, gait feasibility, or real-robot validation. The existing controller's `SAFE_WAIT` is not proof of geometric impossibility. C3 should consume this original fixture first, without supplying the witness as a planner/controller answer path.

The witness uses the actual defined 0.81 × 0.56 m body, square 0.26 m cone bases, original rulebook left floor, strict parking/terrain forbidden polygons, and at least 0.03 m clearance. No cones, forbidden areas, or body were shrunk or moved. The left floor is identical in the preserved rulebook and user-approved corridor-parallel revisions; that correction remains non-measured design geometry, `map_transform=null`.

## A/B/C/D results

- **A original_tight5:** 984 states expanded; 5.74 s search in the final run; 5,124 independent sweep samples; continuous body-to-geometry clearance lower bound **0.0345 m**. Witness stays at yaw π/2, centers x=0.375…0.625. Turning was available to the search, not necessary for this witness.
- **B circumscribed-circle diagnostic:** radius sqrt(0.405²+0.28²)=0.492366733 m, then one 0.03 m margin gives radius 0.522366733 m. Its diameter 1.044733466 m exceeds the 1 m corridor width even without cones. The start's clearance to the bottom floor is 0.459 m, below that radius. Circle rejection is conservative-model rejection, not physical rectangular-body impossibility. The diagnostic raster uses a conservative 64-sided circle envelope and can overreject; its zero valid-node count is not asserted to be an exact continuous-space count.
- **C feasible1 / feasible2:** independent certified original-geometry witnesses, each clearance lower bound **0.0345 m**, respectively 1,372 / 1,018 search expansions. One cone at (0.18,2.5); two at (0.18,2.0),(0.18,3.5). These are separately named diagnostic layouts, not changes to A.
- **D open_diagnostic:** independent certified witness, **0.0345 m** lower bound. Existing OPEN widens longitudinal maneuvering space by changing cone spacing, not the original floor envelope. This is not evidence substituted for A.
- Empty: **0.0535 m** lower bound.
- Sensor-dropout scene: the empty static geometry is feasible; its witness says nothing about commanding motion after sensor dropout. Runtime freshness must still stop motion.
- Blocked: no bounded witness; goal violates the clearance margin (body's 0.015 m gap to the last cone is below 0.03 m). Separately, the row at y=2.5 leaves horizontal gaps of at most 0.09 m, below the body's minimum 0.56 m central cross-section. This barrier blocks the required center crossing inside the 1 m left corridor. The report does not infer impossibility merely from search failure.

## Why tight can wait despite a geometric path

At yaw π/2, left cone right edge x=0.31 leaves a 0.69 m aisle; the padded robot is 0.62 m wide, leaving 0.07 m of center-placement slack. Between the opposing pair, the free longitudinal gap is 0.91 m; the padded body's length is 0.87 m, leaving only **0.04 m** for the lateral transition. The witness makes holonomic lateral moves through that small interval; it is not a smooth dynamically certified trajectory.

This isolates true geometry from downstream constraints. Observed first-hit grids, unknown-space treatment, closed-cell rasterization, rectangular grid expansion, EDT cell reserve, near-fixed-yaw smooth-path construction, finite controller lookahead and the current-pose padded collision guard can conservatively reject or stop a usable geometric route. This experiment does not assign the current controller failure to one particular module without its trace; it establishes that continuous planar geometry is not the absolute obstruction.

The existing curved candidate uses 87×61 grid expansion at 0.01 m, full padded rectangle validation and EDT >0.0071 m. Its `.225` left-slalom constant is not the body circumscribed radius and is not the active curved planner radius (that call passes zero). Full polygon validation after configuration-space candidate generation is not automatically a second inflation. Applying robot-radius inflation and then sweeping a padded full body would double-count the robot extent; adding 0.03 m to both obstacle inflation and an already padded body would double-count clearance. Padded rectangle circumscribed radius is 0.534158216 m, distinct from raw-body circumscribed radius plus a Euclidean 0.03 m margin. Keep these alternatives separate.

## Bounds and independent certification

Run from this directory:

    python feasibility.py
    python -m unittest test_feasibility -v

Search is bounded offline lattice A*: x/y spacing **0.025 m**, **36 yaw bins / 10 degrees**, x=0…1.375 m, y=0.5…5.5 m, yaw=[0,2π). The lattice has 405,216 states. Six neighbors translate one x/y cell or rotate one yaw bin. A 90 s wall-time guard is checked between expansions (not hard preemption during vectorized initialization). No RRT/RL or new runtime planner is introduced. The padded search body includes 0.001 m numerical reserve above the requested margin. Grid-node and yaw-midpoint checks produce candidates only; every published witness must pass continuous verification. No witness within these bounds is not proof of continuous impossibility.

Search uses SAT against base/forbidden polygons and boundary segments. The independent verifier does not import `collision.py`, `fast_snapshot.py`, occupancy grids or SAT: it uses unpadded body vertices, edge intersection/distances and polygon containment. It subdivides each linear SE(2) edge until translation plus corner-radius × yaw change is ≤0.001 m per interval. Sampled clearance minus half that bound certifies every continuous interpolated point against the original floor, cone bases, and forbidden polygons. Contact and tunneling negative controls are tested. This is a separate algorithm, not merely denser calls to the candidate collision function.

`feasibility_results.json` records exact canonical scene SHA-256 values and per-case bounds/timings. Witness files repeat their scene hash and mark `FEASIBILITY_ONLY_NEVER_NATIVE_PLANNER_ANSWER_PATH`. The canonical hash is sorted-key compact JSON with no NaN values, covering full scene geometry, dimensions, cones, poses and clearance. It is distinct from the export manifest's individual file-byte hashes.

Original A scene SHA-256: `4485bc958ed0894f4a8a33767cf6fbe55ae4c3f42382b010f0ff7cd18bbab605`.

Seven focused tests passed in 8.766 s after final regeneration (also passed in the initial run). No production configuration, native Nav2, hardware, UI, services or deployment changed. Remaining step: C3 consumes the exact original tight fixture with its own native planner/controller and reports the independent outcome, without using this geometric witness as an answer path.
