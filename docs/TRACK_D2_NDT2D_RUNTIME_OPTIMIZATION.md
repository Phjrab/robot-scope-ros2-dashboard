# Track D2 NDT2D runtime optimization

Date: 2026-09-08

## Exact live failure

After CI run `34145999112` passed both matrices, exact release
`3388718f85be1666be57b39660fe0fd618230448` was installed on the external
Jetson only. Its archive SHA-256 was
`50580d90bab19776f39feec787cfc3fc12888f0a1c84f1f9d9001f098a8b74c6`.
The PCL-enabled aarch64 build and CTest passed, and the fixed-grid NDT2D
benchmark again passed 10/10 cases. The dashboard was restarted from that
exact release; the onboard Bridge release and services were not changed.

The observation-only pipeline reached readiness. Exactly one candidate job,
`bd83e1acc2b5250cd948aa9d`, used the pinned free-review family and unchanged
REGION seed. Collection and map preflight passed:

```text
frames = 25
raw_points = 366401
filtered_points = 1197
reference_points = 182949
known_free_cells = 526539
```

The child exceeded the existing 15-second process deadline before returning
registration diagnostics. The job failed closed as `offline registration
timed out`; it produced no candidate or preview layer and applied nothing.
Reverse cleanup stopped the operation-owned FAST-LIO/IMU pipeline while the
persistent XT16 preview remained running. Control stayed lease-free, deadman
false and exact-zero with zero Move, non-zero Move and action requests.
Navigation, Localization and goal remained idle.

## Narrow optimization

Code inspection identified repeated target construction: the unchanged
182,949-point reference was passed to a newly constructed NDT2D object for
each of the same three bounded refinement seeds. The implementation now
constructs that fixed registration input once per child and reuses it only
within that child. It does not cache across jobs or inputs.

The process timeout, seed count, grid, extent, iteration ceiling, result
ordering, convergence policy, confidence policy and out-of-plane rejection
remain unchanged. GICP remains offline-only and the portable backend remains
the default.

An isolated external-Orin build passed CTest and the strict ten-case benchmark:

```text
cases = 10
converged_cases = 10
accepted_cases = 10
acceptance_pass = true
translation median/p95 = 0.001277 / 0.003105 m
yaw median/p95 = 0.028152 / 0.097857 deg
runtime p50/p95 = 956.454 / 1003.046 ms
```

This isolated benchmark is software qualification only. A new exact release
and a fresh stationary live job are still required before D2 can pass.

```text
D2_EXACT_3388718_DEPLOYMENT=PASS
D2_LIVE_COLLECTION=PASS
D2_LIVE_REGISTRATION=FAIL_TIMEOUT
D2_NDT_TARGET_REUSE_SOFTWARE=PASS_AARCH64
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_PIPELINE_STATE=STOPPED
FINAL_PREVIEW_STATE=RUNNING
```

## Exact optimized release deployment

Commit `fb0555f7a94715cf82743512df0451139e6913cf` was pushed to `origin/main`.
CI run `34147692182` passed both Ubuntu 22.04/Python 3.10 and Ubuntu
24.04/Python 3.12 matrices. The exact archive SHA-256 was
`07f3deea79f9e57820109b85573f7a67e4fa5324eb2202ed51c968bd0f4de767`.

The inactive external-Orin release rebuilt both PCL binaries, passed CTest
1/1 and reproduced the strict NDT2D benchmark with 10/10 converged and
accepted cases. Its runtime p50/p95 was 957.273/1,002.529 ms. The external
dashboard alone was switched through its fixed lifecycle API. It became ready
from the exact release with PID 189848, instance
`ee0898bb6bea43cc98317f068668d3e5`, and `NRestarts=0`. Release `3388718...`
and the pre-switch environment remain available for rollback.

The persistent preview recovered, but the robot-side management host
`192.168.50.30` subsequently became unreachable (`Host is down`). The prior
battery observation had fallen to 3 percent. The external dashboard therefore
reported signed Bridge status waiting. Because the D2 stationary preflight
requires an authenticated ready Bridge and fresh stationary evidence, no
second live candidate job was created. The fail-closed gate was preserved.

```text
D2_EXACT_FB0555F_DEPLOYMENT=PASS_EXTERNAL_ONLY
D2_EXACT_FB0555F_CI=PASS
D2_EXACT_FB0555F_AARCH64_BUILD=PASS
D2_EXACT_FB0555F_LIVE_CANDIDATE=NOT_RUN_ROBOT_HOST_UNAVAILABLE
D2_LIVE_CANDIDATE_PASS=NOT_YET
D3_READY=false
CANDIDATE_APPLIED=false
INITIAL_POSE=NOT_RUN
NAV2_GOAL=NOT_RUN
MOTION=NOT_RUN
FINAL_DASHBOARD_STATE=ACTIVE_EXACT_RELEASE
FINAL_MAPPING_PIPELINE_STATE=IDLE
FINAL_PREVIEW_STATE=RUNNING
FINAL_CONTROL_STATE=DISARMED_ZERO_BRIDGE_WAITING
```
