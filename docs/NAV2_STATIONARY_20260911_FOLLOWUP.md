# September 11 stationary Nav2 follow-up

External release: `be1bc093564d93e7b534178b1fe0342e4277cc3a`.
Bridge release: `10a7fa9cec2c329f2c50edc9ad98de13a22689da`.
Map: `8dc355f6be3eb392345ac7ab`, revision
`26199766d211ef2b4940b80863f91e5245716df8bd28c71590d03ce886eb28cb`.
Parameters: `4327ec7817bbb226bf4a16ca4f64e0d73eeee3dc150c8947c206fc56172388ad`.

After the operator rebooted the robot, an initial-pose-free 180-second
observation collected 286 snapshots. Maximum callback arrival gap was
0.169312 s and source-header gap was 0.100152 s. No translation/heading jump
or Bridge motion request was observed. API cleanup and process inspection
passed.

The operator subsequently supplied initial pose through the dashboard in job
`f76266a0d0554e439f4a5cd894c26222`. A separate 180-second localized observation
collected 282 snapshots, all READY, with maximum callback arrival gap
0.215899 s and source-header gap 0.100147 s. No goal, translation/heading jump,
or change in Bridge motion counters was observed. This is sampled stationary
evidence, not formal C4 route acceptance or successful goal execution.

## Cleanup defect and correction

The stop API reported idle/stopped but FAST-LIO PID 446045 survived with PPID 1,
PGID 445952 and the session's exact temporary parameter file. It was stopped
with an identity-checked TERM request; subsequent inspection found no Nav2,
navigation runtime or FAST-LIO process. Persistent XT16 preview was preserved.
Thus automatic process cleanup failed, while assisted final cleanup passed.

The launcher previously used leader liveness for both monitoring and cleanup.
If the leader exited first, cleanup skipped its surviving process group.
Cleanup now checks live members of the original setsid group/session, bounded
by the recorded leader start time, and rejects a recycled leader identity.
Normal runtime leader-liveness checks are unchanged. INT/TERM/KILL escalation
retains the existing short waits and only targets the launcher's owned groups.

A Linux regression test creates its own session, reaps the leader while a
SIGINT-ignoring child survives, and verifies TERM cleanup. It also rejects a
start-time mismatch. The test passed on the external Linux host without ROS
topics, service changes or deployment. macOS skips this Linux-only test.

## RMW diagnostic limitation

The deployed Humble rclpy executor takes a `(message, metadata)` tuple; the
custom executor preserves that metadata. However the upstream Humble
[CycloneDDS RMW implementation](https://github.com/ros2/rmw_cyclonedds/blob/humble/rmw_cyclonedds_cpp/src/rmw_node.cpp)
explicitly sets `received_timestamp = 0` in `message_info_from_sample_info`.
This explains the unavailable receipt/queue diagnostics with matching rejected
and missing counts (2564 at the end of the localized observation). It is not
evidence that all DDS packets were lost. The exact installed native library's
take result has not been separately instrumented in this follow-up.

Zero continues to fail validation. Neither message source time nor callback
time can substitute for DDS receipt. The 0.25 s readiness limit is unchanged.
Separating DDS delivery from executor scheduling requires another measurement
method; the existing RMW fields cannot do that on this implementation.

## Remaining gates

Software validation: repository virtual-environment Python discovery ran 1396
tests with no failures and one Linux-only skip; that skipped test passed
separately on the external Linux host. JavaScript unit tests passed 293/293.
Bash syntax, Ruff on the added test and `git diff --check` passed. System Python
discovery ran 1379 tests but could not import two modules because its environment
lacks `fastapi` and `pydantic`; this is an environment failure.

The earlier operator-triggered goal still failed with arrival gap 0.305144 s;
the new stationary observations do not resolve that failure. The cleanup
correction needs exact-release deployment and a further process-cleanup check
before it can be claimed hardware-validated. No deployment, service restart,
initial pose or goal was performed as part of this software correction.
