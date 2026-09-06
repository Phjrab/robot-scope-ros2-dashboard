# Track D1 offline registration acceptance

Status: `OFFLINE_REGISTRATION_SOFTWARE_PASS`

```text
OFFLINE_REGISTRATION_SOFTWARE_PASS
LIVE_CANDIDATE_NOT_RUN
CANDIDATE_NOT_APPLIED
GOAL_NOT_RUN
MOTION_NOT_RUN
```

## Implementation

- ROS-independent C++17 preprocessing, spatial index, bounded coarse search
  and SE2 ICP refinement.
- Strict binary PCD loader with float32 `x/y/z` and point-count bounds.
- Strict Python input/result models and confidence recomputation.
- One-job fixed-argv process adapter with timeout and process-group cleanup.
- Deterministic hardware-free benchmark; no map/PCD fixture is committed.

## Required synthetic corpus

| Case | Evidence |
|---|---|
| room corner | distinct corpus recovery |
| L corridor | distinct corpus recovery |
| parallel corridor | asymmetric and repeated corridor cases |
| pillars | distinct corpus recovery |
| rotation only | known-transform recovery |
| translation only | known-transform recovery |
| combined transform | known-transform recovery |
| 30% dropout | known-transform recovery |
| 50% dropout | known-transform recovery |
| Gaussian noise | deterministic 0.02 m noise |
| 10–30% outliers | deterministic 20% outliers |
| partial FOV | half-space partial cloud |
| repeated/symmetric corridor | false HIGH confidence prohibited |
| too few points | preprocessing rejects |
| no overlap | fail-closed child result |
| wrong seed | fail-closed child result |
| second-best ambiguity | confidence policy rejects HIGH |
| z/roll/pitch invalid solution | 3DoF core plus z-band rejection |
| timeout | process group killed and slot released |
| malformed PCD | adapter rejects before child start |

## Measured software evidence

Apple Clang 17, arm64 macOS, ten 2,530-point distinct room transforms:

```text
translation median = 0.005111 m
translation p95    = 0.016583 m
yaw median         = 0.173053 deg
yaw p95            = 0.280628 deg
runtime p50        = 221.024 ms
runtime p95        = 245.573 ms
child peak RSS     = 2,080,768 Darwin bytes (about 1.98 MiB)
```

These are deterministic synthetic results. They do not establish XT16 live
accuracy, aarch64 performance, dynamic robustness or motion safety.

## Acceptance matrix

| Check | Result |
|---|---|
| deterministic 3DoF recovery | PASS |
| translation median <=0.15 m / p95 <=0.30 m | PASS |
| yaw median <=3 deg / p95 <=8 deg | PASS |
| ambiguous false HIGH confidence | 0 / PASS |
| binary PCD/path/symlink/size/point bounds | PASS |
| malformed JSON/result/non-finite rejection | PASS |
| deterministic ranking and fixed top-K | PASS |
| timeout/process-group cleanup | PASS |
| one job at a time | PASS |
| no ROS dependency in core | PASS |
| no HTTP/UI/live/apply/motion integration | PASS |
| PCL NDT benchmark | NOT RUN — unavailable in authorized environment |
| PCL GICP benchmark | NOT RUN — unavailable in authorized environment |
| aarch64 build/runtime | NOT RUN — D1 prohibits Jetson access |

## D2 handoff

D2 is conditional, not automatically live-ready. Before stationary live use:

1. build the exact release on the external Orin without changing production;
2. record resolved PCL version/components and compare NDT/GICP against the same
   synthetic corpus, or explicitly retain the reference backend with evidence;
3. pin a D0 `family_revision` and resolve all paths server-side;
4. add only an explicit observation-only owner;
5. obtain fresh approval before any Jetson service/process change.

Registration candidates remain advisory and cannot be applied automatically.
