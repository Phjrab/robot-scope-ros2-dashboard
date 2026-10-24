# Version-specific reference audit

Inspected Nav2 Humble branch commit:
`3c3db59d6969d8ecee8e68468693d006397f4a0c` (read on 2026-10-24 KST).
This is reference-source provenance, **not an installed binary version**. Native
package versions/image digest are NOT_RUN until the container is actually built.

1. [Humble optimizer source](https://github.com/ros-navigation/navigation2/blob/3c3db59d6969d8ecee8e68468693d006397f4a0c/nav2_mppi_controller/src/optimizer.cpp):
   `getParams` and `setOffset` establish velocity constraints and reject controller
   periods longer than model_dt. The old VM 10 Hz / .05 s candidate would hit this
   incompatibility. New candidates use 20 Hz / .05 s. The inspected implementation
   does not declare newer `ax_max`/`az_max` limits; the shared final gate enforces slew.
2. [Humble RPP source](https://github.com/ros-navigation/navigation2/blob/3c3db59d6969d8ecee8e68468693d006397f4a0c/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp):
   RPP regulates path tracking with lookahead and collision checks. Candidate settings
   use declared lookahead, rotation, collision horizon and minimum-speed options.
   RPP tracking and MPPI trajectory optimization have different roles; no winner is presumed.
3. [Humble behavior server](https://github.com/ros-navigation/navigation2/blob/3c3db59d6969d8ecee8e68468693d006397f4a0c/nav2_behaviors/src/behavior_server.cpp):
   Humble declares `global_frame`; set it to odom for the local costmap. The inherited
   candidate's extra `local_frame` is removed. Only native Spin/Wait behaviors are used.
4. [Humble noise generator](https://github.com/ros-navigation/navigation2/blob/3c3db59d6969d8ecee8e68468693d006397f4a0c/nav2_mppi_controller/src/noise_generator.cpp):
   noise generation uses xtensor random sampling; no configurable RNG seed is exposed
   here. Fixture seeds therefore do not imply deterministic MPPI optimization.
5. [Humble bringup parameters](https://github.com/ros-navigation/navigation2/blob/3c3db59d6969d8ecee8e68468693d006397f4a0c/nav2_bringup/params/nav2_params.yaml)
   provide reference plugin identifiers, costmap observations and behavior settings.
6. [Official Humble MPPI guide](https://api.nav2.org/nav2-humble/html/md_nav2_mppi_controller_README.html)
   supplies model/critic context. Installed package readback and real run receipts are
   still mandatory. Newer Rolling/Jazzy parameter pages are not used as a Humble contract.

No native Collision Monitor is added, so no behavior from a newer Collision Monitor
release is silently assumed. Existing production configuration is unchanged.
