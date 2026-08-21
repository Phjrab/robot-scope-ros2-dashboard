# Third-Party Notices

Robot Scope source code is distributed under the repository's
[MIT License](LICENSE). The following bundled robot model files remain under
their respective upstream licenses. The MIT license does not replace those
terms.

## Unitree Go2 model

- Upstream: `unitreerobotics/unitree_ros`, `robots/go2_description`
- Pinned commit: `f3772ce54c56ef2d34c6aee8100bc768896c7d19`
- Bundled material: a lightweight derivative of the upstream URDF/DAE visual
  model
- License: BSD 3-Clause
- [Full license](robot_dashboard/static/assets/go2/LICENSE.txt)
- [Provenance and modifications](robot_dashboard/static/assets/go2/README.md)

## ROBOTIS TurtleBot3 Burger model

- Upstream: `ROBOTIS-GIT/turtlebot3`, `turtlebot3_description`
- Pinned commit: `90a68bd2e3c61c12966779da89d8eeaec82730e9`
- Bundled material: upstream URDF/STL files and a lightweight visual derivative
- License: Apache License 2.0
- [Full license](robot_dashboard/static/assets/turtlebot/LICENSE.txt)
- [Pinned source manifest](robot_dashboard/static/assets/turtlebot/upstream-manifest.json)
- [Provenance and modifications](robot_dashboard/static/assets/turtlebot/README.md)

## External runtime components

Unitree ROS 2, Hesai drivers, FAST-LIO, Livox SDK2, Livox message packages and
Nav2 are not vendored by this repository. If they are bundled into an
installation image or redistributed with Robot Scope, the distributor must
inventory and comply with their licenses and NOTICE requirements separately. See
[`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

The pinned bootstrap manifest currently identifies Unitree ROS 2 and Hesai ROS
2 as BSD-3-Clause, Livox SDK2 and Livox ROS driver 2 as MIT, and FAST-LIO as
GPL-2.0-only. Those projects are downloaded and built only when the operator
requests it; they are not relicensed by Robot Scope's MIT license. Redistributors
of a full system image must review the exact pinned sources and satisfy all
applicable source, license and notice obligations.
