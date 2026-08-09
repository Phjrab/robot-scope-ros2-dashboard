# Generic TurtleBot-class model

`generic-turtlebot.urdf` is an original, primitive-only Robot Scope model for
the dashboard's broad `turtlebot` profile. It depicts a compact differential
drive base, wheels, caster, mast, camera, and 2D-LiDAR housing.

It is **not** an official ROBOTIS asset, does not target a specific TurtleBot
variant, and is not dimensionally accurate. Do not use it for collision
checking, motion planning, simulation validation, control, or fabrication.

`generic-turtlebot-lite.json` is deterministically generated from the URDF by
`scripts/build_generic_robot_models.py`. Both files are original Robot Scope
work under the repository's MIT license; no third-party mesh or texture is
included.
