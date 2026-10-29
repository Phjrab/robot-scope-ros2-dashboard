# Reproduce D3 without robot access

Run from this branch's repository root with project NumPy/SciPy dependencies
(the repository's `requirements-competition-offline.txt` includes SciPy).
No ROS graph, sockets, physical devices, controller installation or robot route
is needed for these checks. Generated sensor points/results go only to `/tmp`.

```sh
python3 -m unittest discover -s tests/expansion_d3 -v
python3 -m experiments.expansion_20261029.d3_collision_sim.reproduce --output /tmp/d3-results.json
python3 -m experiments.expansion_20261029.d3_collision_sim.preflight
```

Actual source SHA exports (never merge/copy these into D3):

```sh
git fetch --no-tags origin 2402c02c6f91ba54064894b21735e01b98610acd c0d266e290a2d29c173d3b83520f8c96efea9447
mkdir -p /tmp/d3-c1-pin /tmp/d3-d2-pin
git archive 2402c02c6f91ba54064894b21735e01b98610acd robot_dashboard/expansion_contracts | tar -x -C /tmp/d3-c1-pin
git archive c0d266e290a2d29c173d3b83520f8c96efea9447 robot_dashboard/obstacle_fusion_core | tar -x -C /tmp/d3-d2-pin
python3 -m experiments.expansion_20261029.d3_collision_sim.compatibility --c1-root /tmp/d3-c1-pin --d2-root /tmp/d3-d2-pin
```

Required regression (run sequentially, one heavy worker):

```sh
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 -m ruff check robot_dashboard scripts
python3 scripts/check_repository_secrets.py
```

## Native status and bounded next step

`preflight` is READ-ONLY; it neither installs nor launches anything. This VM is
Debian 13, Python 3.12. No `ros2`, Docker, Podman, nerdctl, rclpy, `/opt/ros` setup
or container socket was found. A bounded search of existing workspace locations
found only the committed historical image-lock, not an executable local runtime.
The old C3 README distinguishes prior GitHub-hosted native execution from the
unavailable authoring host. That historical success is not a D3 native run.
No completed installation was repeated; no host setup/network permission sought.

All six native cases remain **NATIVE_NAV2_SIM NOT_RUN**: empty lane, feasible cone,
cone added in motion, cone moved/removed, full blockage, input interruption.
`fixtures.scenarios()` emits their evidence requirements, not fabricated results.
Once a safely isolated Humble/Nav2 1.1.20 environment and C4 adapter are provided,
D3 may own the single native run. Reuse NavFn + RotationShim/RPP and existing
limits; do not replace controllers or claim path-scripted motion as native.
Actual native commands must drive the fake plant; raw publication, costmap
consumption, plan change, controller command and action terminal must be recorded
separately. Preserve predictive command stop, bounded observer continuation and
separate actual contact/cancel/infrastructure outcomes. No broad tuning sweep.

## Model and numerical conventions

`go2_collision_source.urdf` is the actual source file from
`unitreerobotics/unitree_ros@f3772ce54c56ef2d34c6aee8100bc768896c7d19`,
`robots/go2_description/urdf/go2_description.urdf` (upstream Git blob
`70bce96b3e96a1c4cf5eeb1753bbd4351c9122e4`). BSD-3-Clause notice is retained as
`UNITREE_LICENSE.txt`. Runtime uses only `<collision>` and joints, never visuals.
Cylinders are enclosed by capsules; boxes and spheres use their metric geometry.
SE3 disallows scale/shear/reflection. No implicit mesh loading or scale repair.
Support requires named feet, a finite world-axis patch fully containing the
primitive, a unit plane normal and <=1 cm explicit contact/penetration tolerance.
Body/low obstacles are never erased as blanket ground. Out-of-patch support is
conservatively treated as obstacle plane, not certified support.

Sweeps hold joints/obstacles fixed; linear translation + SO3 shortest-arc
interpolation has <=5 mm default primitive point travel between samples. This
bound is subtracted to avoid claiming continuity from endpoints. Constant-twist
translation uses short arc chords and subtracts an additional v*w*dt²/8 bound.
Inputs are capped at 128 path knots, 4096 samples, 512 objects and 1,000,000 pair
evaluations. Exceeding budgets is UNKNOWN, not a shortened unchecked trajectory.
The independent analytic circle-vs-rotated-box oracle never calls core clearance.
The raw ray fixture models FOV/noise/nearest-return occlusion and never returns
hidden truth IDs to D2. Timing is VM-only, not Jetson or physical latency.
