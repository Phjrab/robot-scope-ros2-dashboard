# Track C4B — Supervised short low-speed goal retry

Status: `NOT_RUN`

This document is a future execution prompt only. It does not authorize a goal,
normal navigation session, lease, ARM, deadman, non-zero command or robot
motion. Never reuse the C4A localization-only approval as C4B motion approval.

Use the then-current `origin/main` as source of truth. Start by reading
`AGENTS.md`, checking HEAD, `origin/main`, the working tree and latest CI, then
read the Track C2/C3/C4A acceptance records and the control/navigation safety
ADRs. Preserve Track A/B, `competition-pdf-direct`, strict wireless
`/utlidar/robot_odom`, its 500 ms source-age and 100 ms future-skew guards, the
0.5-second odometry stale limit, TF/jitter/timestamp/reset/jump/frame checks,
publisher cardinality, server velocity clamps, watchdog, lease, deadman and
exact-zero behavior. Do not update firmware, change networking, edit/delete a
map, start mapping or run Mission.

## Fixed starting evidence, not reusable approval

- C4A implementation release:
  `116455335b091d5962aef15f90e49b69c1fad0a9`.
- C4A map: `map_20260902_161903_edited`.
- Map ID: `f292601e2c8b269eb635cb0f`.
- Map revision:
  `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93`.
- Parameter revision:
  `194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`.
- Prior pose: `(0.0, 0.0, 0.0)`; it must be physically reconfirmed and must
  never be assumed from the earlier run.
- C4A stationary result: 600/600 READY samples over 599.06 seconds, raw rate
  9.926524-10.077452 Hz, maximum gap 0.141802 seconds, zero Move requests,
  no goal, no lease and no non-zero command.

## Stop before motion approval

1. Re-run hardware-free C2/C3/C4A regressions and the complete required test
   suites. Any regression blocks C4B.
2. Deploy the exact clean commit through the existing reversible release path;
   never update the old dirty checkout in place. Record hashes and rollback.
3. With the robot stationary, re-run C2 NG0 and a lease-free C3 localization
   session. Show the exact live map/revision/parameter revision and candidate
   pose, obtain a new initial-pose-only confirmation, publish `/initialpose`
   exactly once, prove localized NG1 and reverse-clean that session.
4. Reconfirm fresh LowState, battery and joint telemetry; signed bridge
   authenticated READY; exactly one Robot Scope Sport publisher, zero foreign
   named publishers, ten expected anonymous Unitree publishers and eleven
   total; no manual lease; deadman released; exact-zero command.
5. Start the explicit `go2-xt16-wireless-competition-fastlio` normal navigation
   session with the pinned revisions. This is the only phase allowed to acquire
   the navigation lease. Never hold a manual-control lease concurrently.
6. Obtain a separate one-shot initial-pose confirmation, publish it exactly
   once, keep the goal idle and require continuously stable READY for at least
   10 seconds. The C4 checker must require `health.state == READY`, the exact
   rate-gate policy, maximum gap <=0.25 seconds and all unchanged hard guards.
7. Calculate and display, without sending anything: actual start pose and
   heading, exact proposed goal `(0.25, 0.0, 0.0)`, 0.25 m straight-line
   distance, map/path overlay, every traversed cell, robot-radius clearance,
   nearest occupied/unknown cell, forward stopping corridor, configured 35%
   speed scale applied once, server clamps and expected stop behavior.
8. Confirm the robot is standing and stationary at the displayed start pose,
   facing the displayed direction, with at least 0.40 m clear ahead. Require a
   physical E-stop/remote in hand, on-site safety observer and cleared area.
9. Stop and wait for a new, exact user message containing the map/revision,
   start/goal poses and physical-safety confirmation. General approval, C3,
   C4 or C4A approval is invalid. Do not send the goal in the same turn that
   computes the candidate.

## Only after fresh exact C4B approval

Submit exactly one goal at `(0.25, 0.0, 0.0)`. Do not infer, adjust, retry or
send a second goal. Continuously observe raw command, signed bridge output,
TF, both costmaps, localization, controller progress, publisher cardinality
and the physical robot. Record maximum requested/accepted velocity and confirm
the 35% scale was applied once. On arrival, prove exact-zero output and record
final pose/error and stop latency.

Immediately cancel through the fail-safe path, command zero and reverse-clean
for unexpected direction/speed, obstacle/corridor violation, localization
loss, map mismatch, stale/future/reset/jump, sensor interruption, child crash,
network loss, publisher conflict, lease ambiguity, manual/deadman input,
watchdog fault, progress stall or unexpected Sport request. Use the physical
E-stop if software cancellation is not visibly effective. Never auto-resume.

Finally release the navigation lease, stop the stack in reverse order, restore
the production profile and prove goal/session/pipeline idle, lease inactive,
deadman released, exact zero and no C4B-owned process. Record each gate as
`PASS`, `FAIL`, `BLOCKED` or `NOT_RUN`; ambiguity is never `PASS`. Run focused
and complete Python/JavaScript/browser tests, review the diff, create a focused
detailed commit, push `origin main`, wait for CI and stop. Do not continue to a
longer goal, obstacle trial, Mission, fault injection or soak without a new
prompt and approval.
