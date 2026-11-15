# Go2 approach stall and repeated recovery (2026-11-15)

The supervised onboard/Fast-LIO goal reached about 0.28 m from its target,
then made only 0.009 m of net progress over 55.7 seconds. The median command
was 0.093 m/s; reported forward velocity was about 0.006 m/s. The controller
reported failure to make progress seven times and the action reported eleven
recoveries. These are measurements of this run, not a universal gait model.

Bounded supervised comparisons at 0.09 and 0.16 m/s produced swaying/stepping
in place according to the operator. A 0.20 m/s comparison reached its 0.15 m
displacement stop bound and the operator confirmed clear forward translation.
The last probe's continuous sample export failed on a numpy float32 after its
STOP request; its end reason and independent STOP readback were retained. One
earlier 0.20 m/s attempt lost its diagnostic control lease before movement and
is excluded from the speed comparison. The native obstacle avoidance switch
remained enabled. No gait switch or remote-control override was performed.

Humble RPP defaults to a 0.6 m approach scaling distance and 0.05 m/s minimum
approach velocity. That scaling explains the approximately 0.093 m/s command
at 0.28 m with desired speed 0.20 m/s. In this operating state the resulting
command did not sustain translation. The `fastlio_body` profile now sets
`min_approach_linear_velocity = min(0.20, desired_linear_vel)`. A deliberately
lower selected speed remains lower; this setting does not assert it can move
the robot. Strict onboard and competition profiles retain their existing policy.

The [upstream Humble RPP implementation](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp)
takes the minimum of the approach velocity and the preceding constrained
velocity, then clamps to the current desired velocity. This patch changes no
collision checks, cost/curvature regulation parameters, external speed caps,
bridge watchdog, tilt limits, progress thresholds or goal tolerances. The
existing goal-heading controller still commands zero translation during rotation.

The launcher isolates recovery velocities from the signed bridge, but Humble's
default recovery tree still clears costmaps and retries FollowPath. This could
reset the progress checker repeatedly without providing an effective recovery
move. The onboard tree now continuously replans at 1 Hz while following the
path and propagates planner/controller failure immediately to NavigateToPose.
It contains no retry, costmap-clearing, spin or backup recovery. A new goal
requires a new operator action after the failure is investigated.

Validation includes generated-profile/cap/guard regression tests and native
Humble BehaviorTree execution confirming that controller failure propagates and
planner failure does not start FollowPath. Physical goal completion with the
changed approach policy still requires a fresh initial pose and a supervised
goal trial; the successful straight-line probe alone does not prove arrival.
