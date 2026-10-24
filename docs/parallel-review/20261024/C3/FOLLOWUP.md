# C3 native Humble follow-up

Branch: `review/20261024-c3-nav2-benchmark`. Continues reviewed `d023131`.
At follow-up start remote main was `7ef47dc249e4dba83865e78dc283f40013ea92de`;
it was read, not integrated or changed. Independent C3 clone was clean.

First actual hosted run: [40096839736](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40096839736), source `2495f7bdbad5ff83d1b4c8ff7171260618f4e5bd`.
Humble image built successfully; network-none container started real ROS servers.
Graph audit rejected the native `/diagnostics` topic before activation. This is
an environment/harness failure, not a controller result. Native completed comparisons: 0.
Fix: namespace diagnostics explicitly; keep graph rejection checks intact.
Also avoid duplicate SIGINT delivery from both launcher and descendant cleanup.

Second run [40097188846](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40097188846), source `c8e52b80df3cd4a0b48b79908be62957d5d325c2`, passed graph isolation and loaded the real RPP plugin.
Activation stopped because Humble also loads the default NavigateThroughPoses
tree, which requires the intentionally disabled Backup action. The fix supplies
a matching forward-only through-poses tree with native Spin/Wait. The normal
NavigateToPose tree and controller limits stay unchanged. Costmap footprint,
inflation and scan configuration now also receive runtime parameter readback.

Third run [40097544519](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40097544519), source `3f7abe20924a8da11493762095006d81306e2fa8`, activated all five native lifecycle nodes.
Graph audit then found two publishers belonging to the same behavior server:
Humble TimedBehavior creates one velocity publisher per plugin, including Wait.
The audit now requires the exact configured behavior-plugin count with the same
owner for every endpoint. Foreign owners and extra/missing endpoints still fail.

Fourth run [40098000263](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098000263), source `6d9b111b10ab4163cede32bf73ea151b1432b27c`, reached the native NavigateToPose/FollowPath goal and controller output.
Humble rclpy's default executor discards the DDS metadata returned by
`Subscription.handle.take_message`; its callback receives only the message.
The Humble-only executor adapter now retains the original metadata for the two
raw command subscriptions, while delegating all other subscriptions unchanged.
Source age still uses the actual DDS source timestamp, never a receipt restamp.
Shutdown callback exceptions now preserve a FAIL result instead of losing it.

Fifth run [40098521277](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098521277), source `4a7bfae8d1f88722a2faa81af5b6d291b53dd6ed`, reached the empty-path goal with real RPP commands (`Reached the goal!` / `Goal succeeded` in native.log).
Final report serialization rejected ROS's numpy uint8 UUID elements. The 16
original UUID bytes are now explicitly converted to JSON integers, with length
and range validation. This run is retained as a report-writing failure, not a
completed validated comparison; the eight-case gate correctly stopped at one.

Sixth run [40098944552](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098944552), source `dd715db33617df00f69f944a6398ebe1d63bcbbd`, attempted all eight cases.
All four RPP cases passed independent validation: empty/diagnostic goal reached,
blocked/dropout SAFE_WAIT, no footprint contacts or keepout violations. MPPI's
four attempts activated its native plugin but stopped before goals because its
default `/trajectories` publisher escaped the namespace. This visualization topic
is now explicitly remapped into `/c3_nav2`; the outside-topic audit is preserved.
This is 4 validated native results, not an 8-case completed native comparison.
The original eight-attempt summary is retained in `results/minimum_attempt_40098944552.json`.

The next run still gates on one empty RPP case: only actual GOAL_REACHED plus
independent evidence PASS permits the remaining seven sequential cases. The separate synthetic obstacle
diagnostic has a full-footprint swept reference feasibility check. That reference
is never supplied to Nav2 or used to move the plant. Original arena fixtures,
including D0 strict-parking SAFE_WAIT cases, remain unchanged.

Artifacts retain logs/trace/package lock for 14 days; generated maps are excluded.
The workflow has only branch/path-limited push, contents:read, one hosted job,
35-minute job timeout (12-minute build, 20-minute native step) and cancellation of obsolete runs. Build networking is separate
from runtime `--network none`; no secrets or robot endpoints.
