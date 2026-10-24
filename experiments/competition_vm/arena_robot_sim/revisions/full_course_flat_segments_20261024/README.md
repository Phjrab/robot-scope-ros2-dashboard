# Partial closed-loop course demo

This extends (and preserves) the earlier mostly schematic whole-course storyboard with actual simulated flat IN, P and OUT segments. It is still **not an end-to-end full-course result**. Terrain transitions are unexecuted gaps, visibly marked. The left slalom uses the prior validated fixed-yaw baseline; the new curved controller on that same tight layout was not adopted and is not silently substituted.

## Actual execution and assumptions

`simulate_flat.py` reuses the repository's VM grid A* (`avoidance/core.py`) and the bounded holonomic follower/smoothing approach used in the slalom experiment. It is not Nav2 or gait/contact dynamics. These simple flat transfers use a known static floor map, not virtual LiDAR perception or SLAM. The reference XY trajectory is computed by A*, not inserted by hand; start/goal boundary conditions are specified per segment. Heading is fixed per segment, velocity limit 0.16 m/s, vector acceleration limit 0.20 m/s², control period 0.10s, lookahead 0.10m. No dashboard/runtime setting is changed.

| Segment | Start | Goal | Outcome |
|---|---|---|---|
| IN | (7.4,5.49,pi) | (6.1,5.49) | GOAL_REACHED, 9.8s, 1.252m |
| P | (5.99,2.0,pi/2) | (7.25,3.0) | POSITION_AND_HOLD_COMPLETE, 21.0s including 5.0s hold, 1.903m |
| OUT | exact final P pose | (8.6,0.509) | GOAL_REACHED,45.5s,5.752m |
| OUT closed | exact final P pose | same outside goal | SAFE_WAIT,3.1s,0m |

P uses a 0.81×0.56m rectangular envelope, not an actual seated pose. It decelerates to zero before counting 5.0 seconds of zero commands and stationary simulated state. This proves only kinematic state holding, not an observed physical stop or competition parking success.

OUT assumes a scene-only opening at x=8,y=0..1.018 and an exterior rectangle to x=9.2. This is **not a confirmed official opening**. No original wall mesh or asset was edited. The final body rear is x=8.28077, beyond the proposed plane. Without the added apron/opening the same outside goal remains SAFE_WAIT. This comparison does not authorize changing a real arena boundary.

The 0.81×0.56m envelope came from the previous articulated slalom audit. This extension checks that rectangle, not every joint vertex for these new transfers. Full FK, native physics and real Go2 tracking remain untested here.

## Validation

- Seven regression tests pass, including an independent exact rectangle-union coverage test across >10,000 swept samples, separate from the simulator's polygon clipping and occupied-grid checks.
- No floor/boundary violations in all four cases; maximum numerical uncovered area ~8.88e-16m².
- All moving cases obey 0.16m/s and 0.20m/s². Initial candidate with abrupt goal stopping was not adopted; its results remain in `output/attempt01`.
- First IN target (5.95,5.49) was outside the permitted full-footprint placement in the restricted rectangular bay; the corrected boundary condition stops at x=6.1 before the unexecuted ramp transition. The old failure is preserved and not relabeled a pass.
- Prior baseline source SHA256 is `e0754856cecc8747b09cfb3f35de7a22482bfb9de9177db67da26bcdf99fca11`.
- Renderer uses actual recorded poses and explicit segment resets at the terrain gaps. P→OUT is continuous in state. No manual robot motion is inserted through a gap.
- Full repository tests, ROS, physical terrain, live sensor/Go2 tests: NOT_RUN. No commit, push, deployment or robot access.

## Reproduce

Run `python3 simulate_flat.py` for all four cases, including the closed-exit comparison. Run `python3 -m unittest -v test_flat`. `python3 render_segments.py` renders the video using the baseline trace at its documented local path. Python NumPy/SciPy/Pillow and ffmpeg are required. Source/scene/trace hashes and precise replay timing are recorded under `output`.

For a future complete autonomous demonstration, implement and validate the ramp/stair locomotion transitions, actual signal observation/state, the seating posture and real stop evidence, and official gate/map registration. The partial video is a design/testing reference, not authorization or evidence to execute an untested full-course robot run.

Two complete runs produced byte-identical JSON for all four cases (`output/REPRODUCIBILITY.json`).
