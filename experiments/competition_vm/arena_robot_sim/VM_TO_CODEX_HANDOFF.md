# VM handoff: arena/Go2/virtual-LiDAR experiment

Only this new directory was changed by the simulation author. No git publication, physical device connection, ROS launch, actuation or production change occurred.

## Reproduce and inspect
Run simulate.py then unittest as README shows. Full repository root layout required: immutable assets/competition-arena/revisions/rulebook-20261015/geometry.py and collision/virtual_fences.json, sibling avoidance/core.py, and actual robot_dashboard/static/assets/go2/go2-official-lite.json plus its BSD license for rendering. Do not mistake renderer output for a validated gait controller.

Final cases: empty GOAL_REACHED14.4s/2.58619m; cone_detour GOAL_REACHED18.6s/2.78586m; blocked SAFE_WAIT6s/0m. All have0recorded footprint contacts. Same goal identity and start geometry are retained. Deliberately driving straight through the final scene gives76/200 collision samples, demonstrating that the detour is avoiding an actual envelope obstruction, not only a decorative cone. This metric uses conservative grid collision, not exact mesh penetration.

7unit tests cover actual model bounds, ray/base dimensions, occlusion, actual arena/terrain masks, all final record outcomes and obstructed straight reference. Independent reviewer densely interpolated recorded poses (~50Hz), checked cone SAT overlaps and floor exits, found0. Exact planar polygon-edge clearance at5Hz minimum: empty0.314252m, detour0.126966m, blocked0.262m. These are sampled geometric distances, not minimum continuous dynamic clearance certificates. Grid circumscribed EDTproxy is stored separately.

The car-like pose plant uses saved synthetic raycast sensor feedback, not an authored successful path. Synthetic four-height LiDAR is not physically calibrated Go2 LiDAR, and pose is known SIM_GT. Static default joint angles visualize actual Go2 morphology only. Terminal state derives from real goal/blocked condition, no synthetic final pose. Recorded control t and resulting pose_t differ .1s; scan_pose/scan_t preserve observation coordinates.

## Restrictions carried forward
- Actual arena has provisional geometry and unknown map transform; do not deploy it as qualified map.
- Plane-only navigation excludes ramps/stairs/platform. No full course completion claim.
- The final envelope enters parking opening7.8cm; center remains in straight. Route permission is provisional experiment only.
- Centered cone and x5.75cone configurations failed safe due conservatism/tracking; failures retained in README. Final x5.70 configuration is specifically disclosed.
- Require physical footprint/kinematics, localization uncertainty, sensor pattern/noise, real controller, slope/step executor, stop-sign integration and competition route qualification before robot testing.
- Preserve other workers' files. Parent owns packaging/publication. Re-run relevant verification before any integration; no authority to enable live motion is granted here.

## Git publication (2026-10-24)
This source snapshot is prepared for publication on main. Earlier no-publication statements describe the authoring stage. See experiments/competition_vm/PUBLICATION.md for included artifacts, exclusions and final test status. Module checksums describe the Git publication subset, not the separately delivered immutable ZIP. No real robot measurements are included.
