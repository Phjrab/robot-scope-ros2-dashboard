# Nav2 1.1.20 goal-heading overlay

This is a version-pinned patch to the existing RotationShim, not a new
controller. It is **inactive by default**. See the
[reproduction and deployment report](../../docs/operational-3d-navigation/GOAL_HEADING_FIX_20261029.md).

`upstream.json` pins the official source inputs by SHA256. `prepare.py` verifies
those inputs before applying the patches with zero fuzz. The original upstream
copyright notices stay in the patched files. [UPSTREAM-LICENSE](UPSTREAM-LICENSE)
preserves the repository license notice; the Shim package declares Apache 2.0.
[LICENSE](LICENSE) contains its full terms. New helper/test code is also Apache 2.0.

## Time contract

`same-time-goal.patch` and `common_time.hpp` first try the controller pose's
timestamp. Both the fixed map goal and robot chain must support that time.
Otherwise they discover the latest common chain time and reconstruct **both**
poses at that explicit time, bounded by the input timestamp and the existing
costmap transform tolerance. `TimePointZero` is used only to discover a time,
never to mix two latest transformations. Sensor/TF source timestamps and input
messages are unchanged. Missing, stale, future, or clock-reset inputs reject
through the existing ControllerServer exception/zero-command path instead of
silently falling through to the primary controller. A clock rewind requires a
new plan. Valid approach still calls the configured primary controller.

`final-rotation-collision.patch` is separate so the TF-only outcome is measurable.
It prevents the initial-heading handoff threshold from skipping footprint checks
for a short final yaw rotation. The initial-heading sweep is unchanged. This
additional defect was found in the native test; it is not asserted to explain
the historical second trial, which had no controller collision errors.

## Build and reproduce without a robot command

On a ROS 2 Humble host with the installed Nav2 1.1.20 packages, populate a private
source cache using the URLs in `upstream.json`, preserving their relative paths.
Use a new output directory outside the repository:

```sh
bash scripts/build_nav2_goal_heading_fix.sh /absolute/source-cache /absolute/new-output
```

This builds only the Shim package and executes original, TF-only, final, installed
original, and production-library tests. It uses an isolated localhost ROS domain,
no navigation action goals, no command publisher, and no bridge connection. The
fixture uses real C++ Shim/TF/goal/progress checkers and a spy primary to observe
fallback, not a closed-loop RPP/ControllerServer simulation. The production test
checks `/proc/self/maps` to prove which library was loaded. A receipt is emitted
only after all native tests pass. No `/opt/ros` files are overwritten.

## Explicit selection and rollback

Only an approved host deployment may set the trusted service environment variable
`ROBOT_SCOPE_NAV2_HEADING_OVERLAY` to the candidate `install` directory. The
navigation launcher validates source, library, installed base and package hashes
before sourcing `share/nav2_rotation_shim_controller/local_setup.bash` inside it.
Standalone CMake installs provide this package-level file, not colcon's root
`local_setup.bash`. The builder probes ament discovery and the loaded library
without starting a ROS node. HTTP users cannot select
an arbitrary plugin or overlay path. Existing controller and navigation parameter
values remain unchanged. Validate the actual controller process's loaded library
and generated/live parameters in the new session before a supervised goal.

To revert, cancel the **current** goal through the existing goal-ID API, confirm
the existing measured-stop condition, stop the session, clear the overlay
selection, and restart the dashboard/session from the prior release. Use a
fresh parameter revision if restoring a saved preset. Do not unlock SOFTWARE
STOP, reuse old goals, or replace later user edits with an old snapshot.

The installed PoseProgressChecker was compared but is not selected by this
change: it accepts large oscillation and endless rotation as progress. A finite
supervised trial and convergence evidence remain necessary.
