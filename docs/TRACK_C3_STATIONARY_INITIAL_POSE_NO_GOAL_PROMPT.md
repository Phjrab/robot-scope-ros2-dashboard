# Track C3 — Stationary Initial Pose + Localized No-Goal

Use the current `origin/main` after Track C2 as the source of truth. Read
`AGENTS.md`, repository HEAD/worktree, latest CI,
`docs/ADR_COMPETITION_FASTLIO_CONTROLLER_ODOM.md` and
`docs/TRACK_C2_COMPETITION_FASTLIO_NO_GOAL_ACCEPTANCE.md` first.

Preserve Track A/B, `competition-pdf-direct`, the strict wireless
`/utlidar/robot_odom` transport and its 500 ms/100 ms guard. Use only the
explicit `go2-xt16-wireless-competition-fastlio` profile and the fixed
controller topic `/robot_scope/nav/controller_odom_fastlio`. Do not add a
fallback or start the onboard wireless odometry sender/receiver.

## Preconditions

- Track C2 software, stationary sensor/controller-odometry and 60-second NG0
  rows must all be `PASS` on the deployed commit.
- Robot is stationary with physical remote/E-stop and a safety observer.
- Control lease inactive, DISARMED, deadman false and exact-zero command.
- Exact managed map `map_20260902_161903_edited`, ID
  `f292601e2c8b269eb635cb0f` and revision
  `7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93`
  are re-read from the live catalog. Abort if either changed.
- A known-free initial pose with robot-radius clearance is selected and
  visually confirmed by the operator.

## Authorized work

1. Re-run C2 NG0 and confirm `WAITING_FOR_INITIAL_POSE`.
2. Publish exactly one confirmed initial pose through the existing
   revision-pinned dashboard API; do not repeat automatically.
3. Verify `map -> odom -> base_link`, localization readiness, stable global
   and local costmaps, goal state `idle`, no lease and no motion.
4. Run `scripts/check_competition_no_goal_ready.py --stage localized` for a
   bounded stationary observation.
5. Reverse-clean up Nav2, navigation runtime, FAST-LIO/bridge/Hesai and remote
   sensor owners. Verify no child, publisher or fixed socket residue.
6. Run focused and complete tests, update the acceptance record, make one
   focused commit and push `origin main`.

## Prohibited work

Do not send a navigation goal, acquire a navigation/control lease, ARM, hold
deadman, publish nonzero velocity, start `cmd_vel_to_sport`, move the robot,
change firmware/clock/network, delete a map, loosen freshness/jump/velocity
bounds, or auto-resume after a fault.

Immediately clean up and report `FAIL` for a nonzero private command or Sport
request, publisher conflict, stale/future/reset/jump, child crash, map revision
mismatch, localization loss, resource exhaustion, network loss or ambiguous
ownership. C4 short low-speed goal work is a separate prompt and approval.

Report exact commit/deployment, map ID/revision, initial-pose coordinates and
confirmation, topic/frame/QoS/rates, TF and costmap status, command isolation,
resource use, cleanup, tests, PASS/FAIL/BLOCKED/NOT_RUN table, commit SHA and
push result.
