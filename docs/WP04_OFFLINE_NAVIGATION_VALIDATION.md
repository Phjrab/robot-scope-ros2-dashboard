# WP04 offline navigation validation (2026-09-29)

## Scope and provenance

The MacBook has no `ros2` executable, so an isolated Nav2 planner server was
not run: **ACTUAL_NAV2_NOT_RUN**.  The new connectivity probe is explicitly
`OFFLINE_GRID_CONNECTIVITY_NOT_NAV2`; it is a bounded four-neighbor occupancy
search, not a replacement planner or an executable route.  It emits no goal,
pose, velocity, lease, or control transport.  The data in the new tests is a
hand-built 12 × 12 synthetic grid (0.5 m/cell), not a recorded sensor run or
an independently measured robot map.  No hardware behavior or position error
is inferred from these results.

The probe requires an exact D0 family ID/revision, PCD ID/revision, and
occupancy ID/revision match.  It reuses `NavigationMapSnapshot.known_free` for
footprint clearance, leaving unknown cells blocked.  It also requires the E1
annotation map revision and checks the candidate cell-center trace through
`validate_route`, including KEEP_OUT.  If that trace is rejected, the probe
reports rejection rather than treating connectivity as an executable path.
The trace omits the exact start/goal connector and Nav2's costmaps, inflation,
kinematics, and TF lookup; it is diagnostic only.  The caller supplies pose age,
maximum age, robot radius, and simulated TF authority counts.  Those are
experiment inputs, not runtime safety parameter changes or observed TF data.

## Reproduce

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_offline_plan_probe.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_navigation_command_timing.py -v
```

The tests cover a connected goal, occupied/unknown/out-of-map goals, a fully
blocked corridor, exact map and annotation revision mismatch, missing/stale
pose, missing/duplicate TF authority, and an E1 KEEP_OUT barrier.  A successful
probe returns `reachable=true` and `actual_nav2_run=false`; no Nav2 path is
produced.

The timing replay drives the real `NavigationRosGateway` and `ControlManager`
with a virtual monotonic clock, ROS-shaped inputs, and an in-memory output
list.  The test fixture has no ROS node or publisher and patches socket
creation to fail during added fault cases.  New cases inject a stale `/Odometry`
receipt, stale runtime-health receipt, loss of localization readiness, and
nonzero command reentry while a goal is canceling.  They check stop before
cancel, goal/lease cleanup, original failure reason, and no automatic restart.
Existing cases retain irregular 10 Hz arrivals, 20 Hz ticks, lock wait,
processing delay, 299.999/301 ms boundaries, and watchdog-before-callback
ordering.  These are injected delays, not measured live DDS arrival times.

## Distinct clocks and limits

- C4 odometry callback-arrival gap has a separate 0.25 s readiness gate in
  `localization_health.py`; no rosbag receive time is substituted for field
  DDS time.
- Navigation input receipt age is 0.75 s for scan and odometry, 1.0 s for
  localization pose, and runtime-health freshness is 0.75 s in
  `navigation_gateway.py`.  Fast-LIO odometry stamp bounds are 1.5 s old and
  0.5 s future.  These values were not changed.
- Nav2 command timeout is 0.30 s, while manual input timeout and the
  independent robot-side Bridge watchdog are each 0.20 s.  The synthetic
  replay does not exercise the robot-side watchdog.

## Deferred evidence

An actual planner-only Nav2 run remains unverified until a safely isolated
ROS/Nav2 environment is available.  `TF_MISSING_OR_CONFLICTING` in the probe
uses injected authority counts; it is not a live ROS graph measurement.  A
localization-health failure does not by itself identify a TF, LiDAR, DDS, or
scheduler root cause.  A real controller, bridge, initial pose, goal, robot,
or Jetson service was not started.  WP05 may consume these read-only results;
live verification remains separate and requires the robot to be powered and
an explicitly approved procedure.

## Local checks

On this MacBook, the focused probe suite passed 5 tests and the timing suite
passed 23 tests.  The complete Python suite using an existing dependency
environment passed 1,483 tests (one Linux-only skip); JavaScript unit tests
passed 329.  The required plain system-Python discovery ran 1,441 tests but
ended with five import errors because its environment lacks FastAPI/Pydantic;
those are environment dependency failures, not assertion failures.  No
dependency was installed or globally changed.
