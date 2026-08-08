# Unitree Go2 official-derived web model

`go2-official-lite.json` is a lightweight, browser-ready derivative of the
official Unitree Go2 URDF and DAE meshes. It is used by Robot Scope's
dependency-free Canvas renderer; no CDN or WebGL library is required.

## Provenance

- Upstream project: [unitreerobotics/go2_urdf](https://github.com/unitreerobotics/go2_urdf)
- Upstream commit: `f3772ce54c56ef2d34c6aee8100bc768896c7d19`
- ROS package: `go2_description`
- Source files: `urdf/go2_description.urdf` and the seven files under `dae/`
- License: BSD-3-Clause; see [LICENSE.txt](LICENSE.txt)
- Local source location used for this build:
  `/home/jetson_orin_nano/ws/unitree_ros/robots/go2_description`

The source DAE files are not copied into the dashboard. The generated asset
retains the official mesh surfaces, per-material colors, URDF visual origins,
joint hierarchy, axes, and limits. The build applies the DAE scene transforms,
clusters nearby vertices, removes collapsed/duplicate triangles, quantizes
positions to 0.01 mm, and omits textures (the upstream files have no image
textures). These are modifications under the upstream BSD-3-Clause license.

## Size and fidelity

| Measure | Upstream unique meshes | Lightweight asset | Assembled robot |
|---|---:|---:|---:|
| Triangles | 196,836 | 3,845 | 7,033 |
| Download | approximately 26 MB DAE | approximately 74 KB JSON | same asset, instanced |

“Unique meshes” counts each of the seven source DAE files once. “Assembled
robot” counts reused hip, leg, and foot meshes at all four URDF links. The
dashboard model is intended for telemetry/map visualization, not precision
simulation or collision checking.

## Rebuild

Use a checkout or installed copy of the upstream package containing `dae/` and
`urdf/`:

```bash
python3 scripts/build_go2_official_model.py \
  /path/to/go2_description \
  robot_dashboard/static/assets/go2/go2-official-lite.json
```

The builder uses only the Python standard library and produces deterministic
compact JSON from the same inputs.

## Renderer integration

Load `go2_official_model.js` after `scene3d.js` and before the dashboard app:

```html
<script src="/static/scene3d.js" defer></script>
<script src="/static/go2_official_model.js" defer></script>
<script src="/static/app.js" defer></script>
```

The module automatically installs itself on `RobotScene3D`. Until the JSON is
ready (or if it cannot be loaded), the existing procedural model remains as a
fallback.

```js
const scene = new RobotScene3D(canvas);
await scene.loadOfficialRobotModel();

// Unitree motor order: FR, FL, RR, RL; hip, thigh, calf for each leg.
scene.setRobotJointPositions(lowState.motor_state);

// Named joint values are also accepted.
scene.setRobotJointPositions({
  FL_hip_joint: 0.0,
  FL_thigh_joint: 0.75,
  FL_calf_joint: -1.5,
});

scene.configureOfficialRobot({
  enabled: true,
  poseOrigin: 'ground', // use 'base' if odometry z is the base-link origin
  adaptiveScale: true,
  scale: 1,
});

console.log(scene.getOfficialRobotModelStatus());
```
