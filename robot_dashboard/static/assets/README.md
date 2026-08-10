# Robot model assets

`robot-model-catalog.json` is the dashboard's allowlisted mapping from robot
type to local model asset. Every entry renders without a CDN or external
runtime dependency.

| Type | Pinned model source | Fidelity |
|---|---|---|
| `go2` | Unitree `unitree_ros` Go2 URDF/DAE | `official-derived` |
| `turtlebot` | ROBOTIS TurtleBot3 Burger URDF/STL | `official-derived` |
| `so-101` | TheRobotStudio SO-101 new-calibration URDF/STL | `official-derived` |

For TurtleBot3 and SO-101, the upstream URDF and all visual STL files it
references are stored unchanged below each model's `source/` directory. The
browser downloads a deterministic lightweight JSON derivative instead of the
multi-megabyte STL set. Upstream commit, file list, license path, and applied
mesh transformations are embedded in each JSON asset and documented in the
model-specific README.

Rebuild both lightweight assets with:

```bash
python3 scripts/build_official_robot_models.py
```

The builder uses only the Python standard library. It reads binary STL,
applies URDF mesh scale, simplifies by deterministic vertex clustering, and
quantizes positions to 0.01 mm. It preserves the official joint hierarchy,
axes, limits, visual origins, and material colors. The output uses the
`robot-scope.robot-model-lite` v1 schema shared by the dashboard renderer.

These lightweight derivatives are for dashboard visualization. Do not use
them for collision checking, motion planning, control, simulation validation,
or fabrication; use the unchanged source assets and the upstream project's
supported tooling for those purposes.
