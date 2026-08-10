# ROBOTIS TurtleBot3 Burger official-derived web model

`turtlebot3-burger-official-lite.json` is a lightweight browser derivative of
the official ROBOTIS TurtleBot3 Burger description. The dashboard's broad
`turtlebot` profile uses Burger as its concrete, recognizable default variant.

## Provenance

- Upstream project: [ROBOTIS-GIT/turtlebot3](https://github.com/ROBOTIS-GIT/turtlebot3)
- Upstream branch: `humble`
- Upstream commit: `90a68bd2e3c61c12966779da89d8eeaec82730e9`
- Package path: `turtlebot3_description`
- Source URDF: `source/turtlebot3_description/urdf/turtlebot3_burger.urdf`
- Visual meshes: Burger base, left/right tires, and LDS under
  `source/turtlebot3_description/meshes/`
- License: Apache-2.0; see [LICENSE.txt](LICENSE.txt)

The URDF and four visual STL files are byte-for-byte copies from the pinned
commit. Their upstream `package://turtlebot3_description/...` references are
intentionally preserved in the source URDF.

## Dashboard derivative

The browser asset preserves the official visual origins, mesh scale, material
colors, wheel/LDS hierarchy, joint axes, and joint types. The STL surfaces are
simplified and quantized for low-latency Canvas rendering. It is a visual
derivative, not a replacement description for ROS, Gazebo, Nav2, collision
checking, or manufacturing.

Rebuild deterministically from the committed sources:

```bash
python3 scripts/build_official_robot_models.py turtlebot
```
