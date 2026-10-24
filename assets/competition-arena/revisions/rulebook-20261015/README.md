# Rulebook 2026-10-15 arena revision

Local design and test fixture, NOT a surveyed map, navigation map, collision-qualified simulator, or robot clearance certificate. The original arena stays unchanged.

## Reproduce
From this directory, with Python 3 + NumPy and Blender 4.3.2:

    python geometry.py
    blender --background --python build_arena.py
    python validate_arena.py
    blender --background arena.blend --python validate_blend_reopen.py
    blender --background --python build_arena.py -- --output /tmp/arena-independent --no-render

Optional signal/debug profile:

    blender --background --python build_arena.py -- --output /tmp/arena-profile --profile profiles/ambiguous.json

Profiles accept signal_01 / signal_02: RED, GREEN, OFF, AMBIGUOUS. Red/green materials emit light. AMBIGUOUS deliberately uses a white/unknown source, not a verified real lamp layout. Default scene red/green; default.json adds synthetic foot/footprint overlay; ambiguous.json adds synthetic green-background, display-monitor, and red-P distractors. Reflection/flicker/clipping camera validation NOT_RUN.

Use `geometry.feet_inside(zone, left_xy, right_xy)`, `polygon_inside(zone, full_footprint_xy)`, and `finish_crossed(previous_footprint, current_footprint)`. The latter requires the entire current footprint beyond x=8 AND inside the finite exit y interval. These are geometric predicates, not dwell-time, stopped-state, heading or mission qualification. Input poses must already be in arena_design; no ROS map transform exists.

## Outputs
- arena.blend: editable scene, metre Z-up
- arena.glb: glTF Y-up, already (x,z,-y); no extra -90° rotation
- arena.json: actual model object manifest; semantic JSON: draft zones/course graph
- collision/virtual_fences.json: explicitly zero-thickness fences, not wall solids
- collision/terrain_meshes.json: closed terrain mesh export, individual treads; physics load NOT_RUN
- scenario_*.json: seven deterministic fixture definitions, no obstacles baked into base map
- previews: top, isometric, terrain/signals and parking review images
- validation/reproducibility/reopen/legacy_validation JSON: evidence and exact limitations

Geometry is parameterized in geometry.py. Fixed-seed random_obstacles supports 0..10; reject 11. Static scene generation intentionally does not silently bake scenario objects into an alleged measured map. The declared 0.60×0.32m robot footprint is SIMULATION_ASSUMPTION, not measured Go2.

Blender GPL software is a build dependency; no Blender binary or font file is shipped. Python stdlib and NumPy are validation dependencies. Source license follows the repository; source PDF/legacy drawings remain evidence, not a newly granted redistribution license.
