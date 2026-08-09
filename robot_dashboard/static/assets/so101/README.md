# Generic SO-101-class model

`generic-so101.urdf` is an original, primitive-only Robot Scope model for the
dashboard's `so-101` profile. It provides a recognizable articulated desktop
arm silhouette and a simple joint hierarchy for visualization.

It is **not** official SO-101 CAD/URDF and its geometry, link lengths, joint
limits, and kinematics are not dimensionally accurate. Do not use it for
collision checking, motion planning, simulation validation, control, or
fabrication.

`generic-so101-lite.json` is deterministically generated from the URDF by
`scripts/build_generic_robot_models.py`. Both files are original Robot Scope
work under the repository's MIT license; no third-party mesh or texture is
included.
