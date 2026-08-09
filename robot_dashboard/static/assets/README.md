# Robot model assets

`robot-model-catalog.json` is the dashboard's allowlisted mapping from a robot
type to its local model asset. All entries render without a CDN or external
runtime dependency.

| Type | Model source | Fidelity |
|---|---|---|
| `go2` | Lightweight derivative of Unitree's official URDF/DAE | `official-derived` |
| `turtlebot` | Robot Scope primitive-only URDF | `generic-approximation` |
| `so-101` | Robot Scope primitive-only URDF | `generic-approximation` |

The TurtleBot-class and SO-101-class assets are intentionally generic. They
are useful for identifying a selected robot and viewing its approximate pose
in the dashboard, but they are **not** variant-specific or dimensionally
accurate. They must not be used for collision checking, motion planning,
simulation validation, control, or fabrication.

The generic source URDFs and generated JSON assets are original Robot Scope
work under the repository's MIT license; see [LICENSE.txt](LICENSE.txt). They
use only URDF `box`, `cylinder`, and `sphere` primitives and include no
downloaded meshes, textures, or
third-party CAD data. TurtleBot is used only as a robot-family selection label;
the generic model is not an official ROBOTIS TurtleBot model. Likewise, the
SO-101-class model is not an official SO-101 CAD or kinematic description.

Rebuild the generated assets deterministically with:

```bash
python3 scripts/build_generic_robot_models.py
```

The resulting JSON uses the `robot-scope.robot-model-lite` v1 schema. Its
`meshes` and `skeleton` fields intentionally match the lightweight Go2
renderer data layout, while `source.fidelity` and `model.fidelity` ensure the
UI can disclose when a model is only a generic approximation.
