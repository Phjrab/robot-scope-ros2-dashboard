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

The next run still gates on one empty RPP case: only actual GOAL_REACHED plus
independent evidence PASS permits the remaining seven sequential cases. The separate synthetic obstacle
diagnostic has a full-footprint swept reference feasibility check. That reference
is never supplied to Nav2 or used to move the plant. Original arena fixtures,
including D0 strict-parking SAFE_WAIT cases, remain unchanged.

Artifacts retain logs/trace/package lock for 14 days; generated maps are excluded.
The workflow has only branch/path-limited push, contents:read, one hosted job,
35-minute job timeout (12-minute build, 20-minute native step) and cancellation of obsolete runs. Build networking is separate
from runtime `--network none`; no secrets or robot endpoints.
