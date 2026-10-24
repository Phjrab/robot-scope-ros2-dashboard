# Articulated Go2 recorded-path visualization (2026-10-24)

This is **KINEMATIC ANIMATION / SYNTHETIC PLANAR**, not contact dynamics, a trained gait policy, Nav2, VSLAM, or a real robot test. No devices were contacted. The existing stored chassis trajectory and timestamps are interpolated without replanning; joint positions are a separate offline animation layer. Do not transfer previous static-envelope collision claims to the animated body.

## Implementation
- `gait.py`: 12 revolute joints from the existing official-derived Unitree asset. Analytic three-joint inverse kinematics, diagonal swing timing, horizontal world-anchored stance feet, 45 mm synthetic swing lift, and iterative visual-mesh sole-height correction.
- Each contiguous moving interval ends at an integer gait cycle, so middle and terminal stationary intervals have four grounded stance feet and frozen joints. Pure turning counts as motion. The planned offline foothold target looks ahead in the recorded trajectory; this is not an online robot controller.
- `render.py`: all 17 link meshes receive their own FK transform each frame. Camera follows the recorded chassis pose. Virtual fence **display height only** is reduced from 0.6 to 0.048 m so legs are visible; saved collision/sensor geometry is unchanged. Cyan points are held from the latest recorded sensor frame, not newly simulated from animated joints. The robot is not rendered climbing stairs or ramps.
- `label_frames.py`: provenance, source time, exact source outcome, and limitations remain visible throughout videos.

## Sources checked
1. Unitree official Go2 URDF, fixed asset provenance commit:
   https://github.com/unitreerobotics/unitree_ros/blob/f3772ce54c56ef2d34c6aee8100bc768896c7d19/robots/go2_description/urdf/go2_description.urdf
   Its 12 angular limits were fetched as data and independently compared to the bundled skeleton (`official_urdf_check.json`). Hip/thigh/calf axes and 0.213 m segment lengths come from this asset. Existing BSD-3-Clause license remains in `../../rendering/UNITREE_BSD_LICENSE.txt`. The already-simplified meshes are reused, no new third-party gait code copied.
2. Unitree official dynamics simulation repository:
   https://github.com/unitreerobotics/unitree_mujoco
   Reviewed as the future native dynamics route. It is not installed or run for this deliverable; no SDK/DDS/network interface was started.

The particular diagonal timing and foothold interpolation are our visualization design, not an official Unitree gait or an experimentally identified controller.

## Reproduce
From this directory (Python with NumPy/Pillow, Blender 4.3.2, ffmpeg):

    python3 gait.py
    python3 -m unittest test_gait -v
    python3 -m unittest discover -s review -v
    blender -b -t 6 --python render.py -- --trace cone_detour --frames 280
    python3 label_frames.py cone_detour
    ffmpeg -y -framerate 15 -i output/cone_detour/labeled/%04d.png -c:v libx264 -crf 22 -pix_fmt yuv420p -movflags +faststart output/go2_articulated_cone_detour.mp4

External recorded planar trace:

    python3 gait.py --trace-path /absolute/recorded.json --case slalom
    blender -b -t 6 --python render.py -- --trace slalom --trace-path /absolute/recorded.json --arena-path /absolute/coherent/arena.blend --frames <records_count>

The terrain revision must match the trace. Do not mix numeric wall IDs or meshes between old and corrected revisions.

## Validation and limits
`output/VALIDATION.json` records source SHA256, unmodified original metrics, new articulated bounds, IK error and visual-mesh ground clearance. Unit tests cover pose fidelity, all-joint motion, stops, limits, ground, reproducibility and upstream joint-limit matching. Independent review uses a separately implemented FK and stop regression.

On the original cone replay the dynamic local mesh extent reaches approximately x=[-0.400,0.331] m, y=[-0.201,0.203] m, wider than the original standing footprint. The slalom planner must account for this and the actual final animated trace must be checked anew. A conservative initial planning envelope is ±0.405 m by ±0.210 m, but future traces are not guaranteed to fit it; audit each trace. The original cone experiment also allowed parking-bay edge usage and is not strict no-parking-area certification.

No claims about torques, friction, stability, contact forces, stance load distribution, realistic actuator dynamics, terrain traversability, exact sitting posture or real-world navigation are made. Physics support is NOT_RUN, not PASS. MuJoCo/PyBullet are absent in this VM; no global packages or OS configuration were changed. No source publication is performed by this visualization worker.

### Independent audit result (original two traces only)
Original suite: 8 author tests + 8 independent tests PASS (subsequently expanded to 10 author tests). 3,692 poses at ten interpolation subdivisions between 15 Hz joint samples: zero modeled wall/cone intersections, zero sampled floor-edge violations, zero cone containment. Minimum visual mesh ground clearance 0.899 mm. Projected hull clearance sampled at 15 Hz is 0.15666 m (cone) and 0.28932 m (blocked), not the former static rectangle/grid proxy metric. See `review/projected_hull_audit.json`. Finite sampling is not certified continuous collision proof.

## Final five-cone left corridor replay
Uses the separate `left_slalom_20261024` revision's recorded traces and coherent `corridor-parallel-20261024` arena. Fixed heading, holonomic lateral translation is explicit, not a heading-following/dynamic gait claim. The IK layer anchors stance feet in world XY and therefore includes lateral foot motion rather than sliding forward-only legs sideways.

The initial 0.405×0.245 m half-extents were **rejected**: 33 interpolated poses exceeded the transverse planner envelope even though a separate hull test found no wall/cone contacts. That failure remains in `review/slalom_stride016_envelope_failure.json` and `slalom_initial_0245_projected_hull_audit.json`. The planner owner reran with ±0.405/±0.280 m, unchanged robot/cone dimensions and unchanged 0.16 m animation cycle length. Cones were repositioned within the user's scenario-selection scope. No gait amplitude or body size was reduced to force a pass.

Final source hashes:
- slalom_5.json: e0754856cecc8747b09cfb3f35de7a22482bfb9de9177db67da26bcdf99fca11
- blocked_5.json: 5bb828969be6f82da2ed35abff262e467a3c31eadd948788590ba18b3529ee49

Final animation bounds x=[−0.396248,0.330680], y=[−0.226424,0.262760] m fit the revised planning rectangle. 4,892 interpolated poses passed independent projected-hull wall/cone/strict left-floor checks, joint limits and the planning envelope. Ground minimum about 0.885 mm; sampled hull clearance 0.08410 m for slalom and 0.10065 m for blocked. Finite sampling, not certified continuous/contact dynamics. Full details and limitations: `review/SLALOM_REVIEW.md`.

10 author tests PASS. 16 independent tests (8 original +8 final slalom) PASS with the explicit source checkout available:

    ARENA_SLALOM_SOURCE_ROOT=/absolute/slalom/repo python3 -m unittest discover -s review -v

The full slalom source trace files are a dependency owned by that revision; they are not silently copied or replaced. The first run without that dependency failed with 8 missing-source errors and this is recorded, not reported as a pass. `gait.py` accepts `--stride-m` for experimentation, but the final videos use the unchanged 0.16 value; preliminary shorter-step outputs are not final deliverables.

For final videos use `gait.py --trace-path <source> --case slalom_5` (and blocked_5), then `render.py` with the same source and corrected arena, then `label_frames.py slalom_5 --trace-path <source>`. The top-down inset is generated from recorded cone geometry, floor polygons, executed trajectory and planning footprint. It is not a second simulation. Combined video transitions directly from GOAL_REACHED replay to the separate SAFE_WAIT case; no fabricated connecting motion is added.
