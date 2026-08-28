# Hardware validation — 2026-08-28

## Scope and safety boundary

This session exercised the deployed Jetson dashboard, Go2 observation path,
XT16 preview path, and the fixed Control Bridge service lifecycle. The robot
remained DISARMED with no control lease, released deadman, and zero linear and
angular commands. No motion action, navigation goal, initial pose, mapping
launch, map mutation, map deletion, or dataset capture was performed.

The repository and Jetson were aligned to commit
`1cce222d40d3c12ab129c676a650411c8705bbfd`. Runtime acceptance reports remain
private and Git-ignored on the Jetson.

## Control Bridge lifecycle result

- The root-owned sudoers rule was installed from the repository example and
  validated with `visudo`. It permits only fixed `systemctl --no-block start`
  and `stop` commands for `robot-scope-control-bridge.service`.
- The independent `ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED=1` opt-in was
  added to the private deployment environment after preserving a private
  rollback copy.
- The dashboard reported the Bridge service as configured and startable while
  the unit remained disabled and inactive by default.
- A same-origin request mismatch was rejected with HTTP 403 before dispatch,
  confirming the mutation origin guard.
- Dashboard-mediated start reached `ACTIVE/RUNNING`, and the signed bridge
  reported authenticated, connected, ready, and idle.
- The observed graph cardinality was one sport subscriber, one owned sport
  publisher, zero foreign named sport publishers, nine expected bare Unitree
  publishers, ten total sport publishers, and one LowState publisher.
- The Controls UI showed `AVAILABLE`, `DISARMED`, `BRIDGE IDLE`, released
  deadman, and zero commands. The STOP button remained disabled until the local
  safety acknowledgement was checked.
- Dashboard-mediated stop reached `INACTIVE/DEAD` and completed successfully.
  The Bridge was left stopped at the end of the session.

## Acceptance results

An initial run after enabling the lifecycle produced:

```text
PASS=48 FAIL=2 BLOCKED=4 NOT_RUN=12
```

The signed bridge was healthy, but the public API omitted the internal total
publisher count. Commit `1cce222` now projects the validated internal
`sport_publishers` value to the public `total_sport_publishers` field without
exposing the internal field. After deployment, the next run produced:

```text
PASS=49 FAIL=1 BLOCKED=4 NOT_RUN=12
```

The `control.signed_bridge` row changed to PASS. The remaining FAIL was
`lidar.xt16_converted`. The four BLOCKED rows were the raw LiDAR dashboard
observation, idle FAST-LIO odometry, idle navigation timestamp/TF validation,
and idle localization health. These were not converted into false passes.

## XT16 performance finding

The Hesai driver continued producing complete 64,000-point raw frames at its
expected cadence, but the Python conversion bridge intermittently rejected
clouds when callback delay exceeded the fixed 250 ms clock residual boundary.
The observed converted topic fell below 4 Hz and became stale during those
windows. The bridge correctly rejected stale input instead of rebasing the
clock or publishing an unsafe timestamp.

The session also identified unrelated host contention: a separate
`cluster-discovery` process targeting an LLM benchmark worker repeatedly
created a temporary Python virtual environment and ran `ensurepip`. During
these probes it consumed a large share of one CPU core while the dashboard,
XT16 bridge, and Control Bridge were already active. Converted-cloud backlog
and rejection bursts increased during this contention. Robot Scope timing and
freshness thresholds were not weakened to hide the failure.

### Quiet-host rerun and rejected tuning

The unrelated discovery load was stopped and its temporary Python processes
were confirmed absent before a second session. With the Control Bridge stopped,
the converted cloud recovered to 6.49–7.37 Hz, 0.031–0.050 s age, and
68–126 ms jitter. This confirmed that the external probe materially worsened
the first run, but did not prove it was the only cause.

With the signed Control Bridge active, no lease, released deadman, and zero
commands, the acceptance result remained:

```text
PASS=49 FAIL=1 BLOCKED=4 NOT_RUN=12
```

The converted-cloud rate and jitter could remain within bounds while a single
freshness gap exceeded the fixed 0.5 s limit. One quiet-host run observed
5.69 Hz, 226 ms jitter, and 0.824 s age. A bounded 100 Hz and then 50 Hz
`/imu/body` experiment reduced IMU callback work but did not remove the gap;
the 50 Hz run observed 5.77 Hz, 296 ms jitter, and 2.617 s age. Those tuning
commits were therefore reverted by `305e324` rather than leaving an unverified
FAST-LIO behavior change in the product.

Jetson telemetry showed all six CPU cores online in MAXN mode, approximately
43°C temperature, no swap use, and no thermal or memory pressure. The remaining
evidence points to the Python large-PointCloud2 conversion/DDS boundary under
the combined dashboard and signed-bridge workload, not a safe reason to widen
the timestamp or freshness limits.

## Repository verification

- Targeted API and acceptance tests: 16 passed.
- JavaScript unit tests: 238 passed.
- Python suite: 670 total; 669 passed. The one error is the known macOS baseline
  where `/etc/os-release` is absent in
  `test_apply_os_release_override_must_match_running_host`.
- The deployed Control Bridge publisher-total fix was verified against the
  live API and acceptance recorder.

## Remaining risks and next safe step

1. Stop or reschedule the unrelated cluster-discovery/temporary-venv probe and
   keep it disabled during later Robot Scope acceptance sessions.
2. Profile or replace the Python large-PointCloud2 conversion boundary before
   changing IMU cadence, point decimation, QoS, process scheduling, or clock
   logic. A C++ conversion node or an equivalent measured design should be
   evaluated against the same byte layout and strict timestamp contract, then
   validated with FAST-LIO odometry before adoption.
3. Preserve the existing local modifications in the external Hesai workspace;
   the full installer remains intentionally blocked until their ownership and
   purpose are reconciled.
4. Navigation/localization and supervised motion scenarios remain incomplete.
   Motion validation requires the physical E-stop ready, a clear test area,
   low-speed limits, an operator present, and the physical remote in hand.
