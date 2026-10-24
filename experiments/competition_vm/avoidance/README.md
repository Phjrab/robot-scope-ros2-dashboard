# Competition avoidance VM prototype

**Synthetic closed-loop core, not Nav2 / RPP / MPPI and not real Go2 validation.**

Run from any cwd:

    python /path/to/avoidance/simulate.py --seeds 3
    python -m unittest discover -s /path/to/avoidance/tests -v

The virtual laser is raycast against hidden scene truth and returns only first-hit ranges. The controller receives these ranges, a known static map, pose and mission inputs, not truth geometry. It updates an independent dynamic layer, replans using an explicitly named fallback grid A*, follows with a differential kinematic plant, and gates commands. Truth is used again only for contact evaluation. Goals never skip to another mission. Motion and footprint are SIMULATION_ASSUMPTION, not measured robot dynamics.

Static known-free map cells are prior free, not proof that a future object is absent. Occupied dynamic cells must receive an actual visible clear ray to become free. Dropout/occlusion cannot clear them. At expiry they become UNKNOWN, which blocks planning. Static/keepout masks are immutable. Freshness uses receiver-local receipt time; source clock is explicitly VM_SIM. Native ROS sensor transport is not validated.

Design initial parameters: 0.1m fallback grid, 0.25m/s cap,0.8rad/s max yaw,10Hz plant/sensor,2Hz replanning,0.3s receipt freshness,2s dynamic occupied expiry,0.5s swept collision horizon. None are a field braking certificate. Polygon is 0.50×0.36m and circumscribed-radius planning is conservative, so some physically traversable passages could be rejected. Native candidate grids use0.05m, separately labeled; they were not benchmarked.

Ground classifier uses an externally supplied gravity-aligned plane and separates ambiguous near-ground points. It preserves ring fields and includes deterministic per-ring sampling. It is not Patchwork++; Patchwork++ and real XT16 comparison remain NOT_RUN. Terrain segments deliberately require a terrain executor. No claim of stair/ramp traversal is made.

Prepared candidate native YAMLs use actual Humble plugin IDs but parameter acceptance is NOT_RUN. Do not install them on a robot. See INTEGRATION_DIFF.md and VM_TO_CODEX_HANDOFF.md.

Final evidence: `VALIDATION_RESULTS.json`, `results/RESULTS.md`, `results/final-run.log`, `results/map-misalignment-run.log`, and `results/unit-tests.txt`. 48 synthetic runs and30 unit tests pass. Purple trajectory, START/GOAL markers and terminal status are shown in final PNG/GIF, regenerated from saved traces. Historical output is quarantined under `results/development/` and is not final evidence.

Sibling `../integration/` now supplies a tested pure-core traffic MotionConstraint receiver adapter. This is separate synthetic integration evidence, not live ROS wiring. Its output is not automatically connected by this simulator or candidate launch.
