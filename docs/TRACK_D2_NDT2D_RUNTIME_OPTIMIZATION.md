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
