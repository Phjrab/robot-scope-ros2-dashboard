# Track C4 — Supervised Short Low-Speed Goal

Status: `NOT_RUN`

Use the current `origin/main` after the accepted Track C3 commit as the source
of truth. Read `AGENTS.md`, repository HEAD/worktree, latest CI,
`docs/TRACK_C2_COMPETITION_FASTLIO_NO_GOAL_ACCEPTANCE.md`,
`docs/TRACK_C3_LOCALIZATION_ONLY_NO_GOAL_ACCEPTANCE.md` and the relevant
control/navigation safety ADRs before taking any action.

Preserve Track A/B, `competition-pdf-direct`, the strict wireless
`/utlidar/robot_odom` transport and its 500 ms source-age/100 ms future-skew
guards. Do not loosen velocity clamps, watchdogs, source-clock checks,
publisher-cardinality checks or filesystem safety. Do not update firmware,
change network configuration, delete/edit a map or start a Mission in C4.

## Hard preconditions

- C3 initial-pose-only and localized no-goal acceptance is `PASS` on the exact
  deployed commit and exact managed map/revision.
- Resolve the existing Control Bridge publisher-cardinality mismatch first.
  Repository configuration now pins the operator-confirmed Go2 v1.1.15
  baseline to exactly ten anonymous Unitree publishers, but this does not
  satisfy the gate until the same focused commit is deployed to both control
  endpoints and a stationary lifecycle check proves one Robot Scope
  publisher, zero foreign named publishers, ten anonymous Unitree publishers
  and eleven total publishers. `manager_closed`, bridge unavailable or any
  foreign/ambiguous Sport publisher blocks C4.
- Robot battery, LowState and joint telemetry must be fresh. The robot must be
  standing and stationary in the confirmed map pose.
- A physical remote/E-stop, safety observer and clear operating area must be
  present. Confirm the maximum low-speed limit on screen.
- Show the operator the exact start pose, goal pose, straight-line distance,
  map ID/revision, path preview, occupied/unknown-cell clearance and stopping
  corridor. Obtain an exact C4 approval after showing these values. Earlier
  C3 or general approvals do not authorize motion.
- The goal must be in known-free space with robot-radius clearance and a clear
  corridor. Keep the first goal straight and no farther than 0.30 m. Do not
  infer or silently adjust its pose.

## Authorized sequence after the exact approval

1. Re-run hardware-free C2/C3 regression tests and a fresh prelocalization NG0
   observation, then clean that lease-free session. Do not weaken or repurpose
   the C3 localized checker: it intentionally requires `localization_only` and
   is not a C4 motion-session acceptance checker.
2. Add or use a distinct C4 checker that recognizes only the normal
   navigation session, verifies the same exact map and sensor contracts and
   records lease/command state without changing the C3 checker semantics.
3. Start the explicit `go2-xt16-wireless-competition-fastlio` normal
   navigation session using the pinned map and parameter revisions. This is
   the only C4 step allowed to acquire the navigation lease; never acquire a
   manual-control lease at the same time.
4. Publish the separately confirmed initial pose exactly once and wait for
   stable `map -> odom -> base_link`, `/amcl_pose`, both costmaps and required
   lifecycle nodes. Keep the goal idle during this stabilization window.
5. Recheck lease ownership, bridge readiness, LowState freshness, command
   source, speed clamp and watchdog immediately before the goal.
6. Submit exactly one operator-confirmed goal, at most 0.30 m away, with the
   configured 35% speed scale applied once. Preserve the server-side clamp.
7. Observe the raw command, signed bridge command, TF, costmaps, localization,
   controller progress and physical robot continuously. The observer must be
   ready to use the physical E-stop/remote.
8. Confirm arrival and exact-zero output. Cancel if progress stalls or the
   robot deviates. Do not retry automatically.
9. Release the navigation lease, stop the stack in reverse order, restore the
   production profile and prove no goal, command or C4-owned process remains.

## Immediate abort conditions

Immediately cancel, command zero through the existing fail-safe path and
reverse-clean for any unexpected direction, excessive speed, obstacle/corridor
violation, localization loss, map revision mismatch, stale/future/reset/jump,
XT16/IMU/odometry interruption, child crash, network loss, publisher conflict,
lease ambiguity, deadman/manual input, watchdog fault or unexpected Sport
request. Use the physical E-stop when software cancellation is not visibly
effective. Never auto-resume or send a second goal after a fault.

## Required evidence and completion

Record the exact source and deployed commits, map and parameter revisions,
approved start/goal poses and distance, clearance proof, topic/frame/QoS/rate
evidence, publisher counts, speed-limit evidence, lease transitions, command
maximums, stop latency, final pose/error, physical observation, resource use
and reverse-cleanup inventory. Mark each acceptance item
`PASS`/`FAIL`/`BLOCKED`/`NOT_RUN`; ambiguity is never `PASS`.

Run focused and complete Python/JavaScript/browser tests, review `git diff`,
create one focused detailed commit and push `origin main`. Stop after C4. Do
not begin longer goals, obstacle avoidance, Mission execution, fault injection
or soak testing without a new prompt and approval.
