# IN/OUT to central X: parallel-corridor geometry correction

LOCAL review revision, generated 2026-10-24 UTC. Base: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
Original `rulebook-20261015` assets and results are immutable and unchanged. No production viewer/wiring changed, no Git publication, no robot contact.

## Finding and correction

The right NE and SE diagonal outer edges and inner triangular keep-out edges were not parallel. This is an actual model error, not perspective. Transverse width at 1.0 m from the central axis origin was 0.925879 m and at 2.5 m was 0.703517 m (both arms). See the orthographic comparison in `previews/corridor_before_after.png`.

The correction derives both edges from the existing **provisional** 1 m-wide, 45-degree central platform axes. Both right diagonal corridors now have 1.000 m transverse width over the checked straight section (longitudinal station 0.50001 through 2.5 m), while preserving:

- Arena floor envelope 8 × 6 m.
- IN/OUT bays 2.4 × 1.018 m and their positions.
- Central platform and all ramp/stair dimensions and heights.
- Parking bay, right vertical corridor, all left-side floor polygons.

The diagonal outer edges meet the horizontal envelope at x=5.592893218 rather than x=5.6; a 7.106782 mm horizontal joining segment preserves the bay. The right inner triangle vertical endpoints become (5.482,1.525106781) and (5.482,4.474893219), instead of y=1.018/4.982. This is the minimal parallel-axis construction under the retained assumptions, not a newly measured official design. T-junction openings can be wider than the straight arm; no claim is made that all union cross-sections at the junction have exactly 1 m width.

Do not interpret the chosen 1 m as an official measured diagonal width. Rulebook cross-span baselines remain unresolved, and the old 6.5 m parking/bay/gap stack conflicts with the 6 m envelope. Left-side geometry may retain provisional narrowing and is deliberately out of this correction scope. Original assumptions remain applicable except right-side terrain overhang: right NE ramp/SE stair ground projections are now contained in the floor union. Physical walking, parking posture, map registration, route qualification and native ROS/Nav2 remain NOT_RUN. `map_transform` stays null.

## Reproduce

From repository root, in a project-local Python environment with numpy, matplotlib, shapely==2.2.0:

```sh
blender -b --threads 4 --python assets/competition-arena/revisions/corridor-parallel-20261024/build_arena.py
python assets/competition-arena/revisions/corridor-parallel-20261024/validate_arena.py
MPLCONFIGDIR=/tmp/corridor-mpl python assets/competition-arena/revisions/corridor-parallel-20261024/check_corridor.py
python assets/competition-arena/revisions/corridor-parallel-20261024/validate_glb_floor.py
blender -b assets/competition-arena/revisions/corridor-parallel-20261024/arena.blend --python assets/competition-arena/revisions/corridor-parallel-20261024/validate_blend_reopen.py
```

## Validation and integration

- Geometry audit: 402 connected cross-sections, floor-union versus boundary exact area equality, unchanged 8 other floors, bay/envelope dimensions and right terrain containment PASS.
- GLB 51 actual exported objects versus geometry bounding boxes PASS, max coordinate error 4.04e-7 m.
- Actual GLB top triangle union versus 10 semantic floor polygons PASS; maximum area discrepancy 6.34e-7 m² (float32 quantization).
- Blender reopen PASS.
- Full repository suite NOT_RUN for this isolated new asset revision; no runtime wiring changed.
- Independent review documented separately.

Consumer must select **all files from this same revision** together, never the new GLB with old semantic/fences. Two short outer joining segments increase wall count and change sequential wall IDs. `wall_id_changes.json` describes old/new edges; consumers must identify openings geometrically, not reuse numerical old wall IDs. Existing simulation results still refer to their old geometry and are not rerun or requalified by this correction. No live map transform or production asset checksum has been altered. C1 integration requires explicit review and revised asset selection/checksum, then separate regression against this revision.
