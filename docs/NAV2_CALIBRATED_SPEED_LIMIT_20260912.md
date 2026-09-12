# Nav2 calibrated longitudinal speed ceiling

The operator selected a 1.0 m/s target after a passive stock-controller
measurement and subsequently approved the change, including reverse motion.
Repeated four-second fast segments indicated 1.04–1.05 m/s from onboard
position change, and 1.01–1.04 m/s from integrated planar velocity. This is
not independent ground truth or proof that a Bridge command of 1.0 m/s has
the same physical response. Isolated 2.54 m/s velocity peaks are not used.

## Change

- Go2 explicitly configures symmetric X limits of ±1.0 m/s, enforced by both
  the dashboard manager and robot-side Bridge. Profiles without an explicit
  X limit still default to ±0.3 m/s.
- Nav2's parameter editor and backend accept desired linear velocity from
  0.05 to 1.0 m/s. The existing preset remains 0.25 m/s, and persisted operator
  values are not automatically overwritten (the observed value was 0.1).
- Go2 sets `navigation_speed_scale=1.0`: physical Nav2 velocities no longer
  inherit the manual controller's 35% attenuation. Legacy profiles without
  this field retain their previous manual-default scaling.
- Manual default scale remains 35%. No keyboard implementation or UI was
  changed or deleted. The shared server/Bridge X cap necessarily also affects
  manual commands if that interface is used.
- Signed accepted-command and request-evidence validators recognize the same
  ±1.0 m/s ceiling; nonfinite and out-of-range status still fail closed.

Y remains ±0.2 m/s and yaw remains ±0.5 rad/s. Acceleration limits, lease,
deadman, source identity, E-stop, sensor interlocks, command age and startup
Stop acknowledgement are unchanged. Nav2 input age remains 300 ms; manual
input and robot Bridge watchdog remain 200 ms.

Unity Nav2 scaling applies to all axes, so existing yaw requests are no
longer attenuated to 35% either; the yaw ceiling and angular acceleration
limit are unchanged. Actual stopping distance and obstacle avoidance at the
new speed ceiling have not been established by stock-controller observation.

## Offline verification and deployment boundary

Tests cover positive/negative saturation at 1.0, unchanged lateral/yaw caps,
slew limits, 200 ms Bridge stopping, 300 ms Nav2 expiry with no automatic
rearm, legacy scaling, Go2 unity scaling, signed status acceptance, and
parameter editor/backend agreement at 1.0 and just above it.

Local verification: 1,426 Python tests OK (one skipped), 293 JavaScript tests
passed, application-source Ruff passed, and `git diff --check` passed.
An additional Ruff invocation including the existing transport test harness
reported its pre-existing E402/E731 patterns; they were not changed here.

Deploy both components with Nav2 idle, no lease, and exact-zero command.
Stage immutable releases and retain both old release targets; keep the
Bridge stopped during the dashboard release transition. Verify signed
readiness and zero Move/action requests before preparing another goal.
Do not equate a configured ceiling with a commanded cruise speed, and do not
send a new goal until localization and the onsite test setup are ready.
