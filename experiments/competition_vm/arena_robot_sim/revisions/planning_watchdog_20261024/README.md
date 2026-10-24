# Real-clock planning stall and command lease harness

VM-only, not native ROS or a robot driver. This does not replace frozen navigation trajectories and sends no actuator commands. A synthetic output tuple is recorded by an independent wall-clock gate.

## Design
- Planner or injected sleeping function runs in a separate Linux process, never on the watchdog thread.
- Pending planning immediately holds zero. Completion/cancellation clears the old command; a fresh sequenced command is required.
- Planner budget 0.10s (local test assumption, not a reinstated user operating cap); polling cancels late workers. No blocking join on the gate path; cleanup is explicit and bounded.
- Separate 0.01s-period watchdog records zero after a 0.10s command lease, even while the calling controller sleeps.
- Receiver TTL and source age are independently parameterized at 0.25s; observation-gap limit is separately 0.50s. New receipt cannot refresh old acquisition. Identity changes invalidate sensor/command state.
- Timed-out or identity-mismatched plans cannot revive previous commands.

## Limits
Real monotonic time and process/thread sleeps are used rather than the prior synchronous simulator clock. Tests cover expiry, timeout/cancel, duplicate sequence, stale acquisition, observation gap, receiver expiry, identity changes. This does NOT prove hard realtime, physical stopping, hardware watchdog behavior or integrated navigation. OS scheduling can delay the watchdog; this is not a certified safety controller.

The frozen planner is too slow for the configured freshness/control budget. Holding zero on timeout is a correct failure outcome, not successful navigation. Do not extend TTL to disguise this problem. Profile and actual observed-fixture cancellation results are recorded separately.

Run python3 test_runtime_guard.py. Guard needs only the standard library; actual planner uses existing NumPy/SciPy modules.

## Actual results

15 wall-clock tests pass. A controller sleep of 0.18s expires its prior command after about 0.101s. CPU-busy planner worker cancellation takes about 0.110s while the watchdog continues producing zero; an actual frozen build_path invocation times out in about 0.111s with 11 recorded zero samples and no surviving child. These are measured VM latencies, not guaranteed deadlines. See wall_clock_results.json and actual_planner_timeout.json.

Initial OPEN planning profile uses actual raycast observations, not the hidden truth raster. Median build_path latency is 2.206s over five calls. allowed() accounts for 83.8% cumulative profile time and polygon_collision 81.1%; percentages overlap because calls nest. An isolated exact-coordinate memoization preserves all 411 returned [x,y,yaw] values bit-for-bit on this fixture and reduces median latency to 1.306s (1.69× faster). It still exceeds both 0.1s control and 0.25s source-age budgets. This optimization is NOT integrated into the frozen controller and not claimed correct on arbitrary changing maps.

Outcome: demonstrable fail-closed real-clock harness plus reproducible planner performance blocker. No successful realtime navigation claim. A future planner/consumer integration needs independent plan-validity and fresh per-tick collision checks; no source time or TTL should be stretched to admit these stale plans. CPU quotas and user operating settings were not changed.

## Independent-review fixes

The first harness allowed a late recv to commit READY after the budget; a concurrent cancel could also be overwritten. Both failures are preserved in runtime_guard_before_review.py and reproduced by new tests. Current code rechecks the deadline after receiving, and uses a lock/token plus identity-aware commit to discard cancelled or superseded results.

A pipe recv itself can still wait. These changes bound result eligibility, not the duration of every planner API call. The independent command gate remains zero while planning is pending or a command lease expires. Do not describe this as a hard bounded-response planner or a physical stop guarantee. Real integration would need bounded IPC/framing and a separately supervised output process as appropriate.
