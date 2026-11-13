# Clicked-position local registration trial

## Decision

The user requested a trial starting at the clicked position, retaining the new
behavior only if it works well, otherwise retaining current behavior. The
existing seeded-local implementation was exercised on frozen historical input.
It converged near the earlier plausible candidate group, but **failed its existing
acceptance policy** (`HIGH_RESIDUAL`, `admissible=false`). Production behavior,
running release and navigation handoff were therefore left unchanged.

This was a numerical offline experiment on the Jetson using existing code, not
a fresh live observation, accepted proposal, step ② application or localization
success. No dashboard/control service restart or deployment occurred.

## Exact experiment and limitations

- Running/exercised release: `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`.
- Implementation: `relocalization/seeded_initialization.py:run_seeded_arrays`,
  through the existing isolated `RegistrationWorker`.
- Frozen scan/map: exact preserved 19:24 job `8a7abdf65e7f3ced366b660c`,
  336/32,387 points; original hashes checked before and after.
- Tested X/Y/yaw: last explicitly entered 21:28 prior,
  `(3.9848961407774457, 4.1965879855189705, -3.056690860140071 rad)`.
  This prior was tested against the older frozen scan; it was not asserted to be
  the robot's current location or propagated through cross-session odometry.
- Z/roll/pitch: extracted from the old candidate #4's full matrix, explicitly
  labelled **unverified preserved-prior hypothesis**, not replaced with zeros.
  This is favorable answer-derived initialization, not an independent estimate.
- Preserved calibration has identity navigation/localization and IMU/base
  transforms. That coordinate assumption was recorded in the trial request.
- Bounds: XY 0.25 m, yaw 0.20 rad, Z 0.10 m, tilt 5 degrees. Residual enforcement
  remained enabled with the existing seeded-local RMSE cap of 0.05 m. These
  parameters were supplied only to the offline helper, not saved to production.
- One call to `run_seeded_arrays`; no global-search fallback or retry. Internal
  coarse seed preparation and fine ICP are stages of that one bounded call.

The previous failed 21:28 job's 378 XYZ points were not available. This trial
therefore does not reproduce that failed input or establish live robustness.
Source/proposal freshness admission was not exercised by this direct frozen-data
helper, and no proposal/proof was created. A successful numerical result alone
would not have authorized a current-session handoff.

## Result

| Measure | Result |
| --- | --- |
| Numerical convergence | true, fine stage 14 iterations |
| Result X/Y | 3.984235009 / 4.081786004 m |
| Result yaw | -2.975287741 rad |
| Movement from tested seed XY/yaw | 0.114803886 m / 4.664055 degrees |
| Movement from seed Z / tilt | 0.004127130 m / 0.038531 degrees |
| Inlier count / overlap | 336 / 1.0 |
| RMSE | 0.068331205 m |
| Existing local RMSE cap | 0.050000000 m |
| Final status | REJECTED / HIGH_RESIDUAL / admissible=false |

All seed bounds passed. Rejection was from the existing residual cap, not
out-of-bounds correction or timeout. The global backend and local backend have
different result/admission contracts: the earlier global temporary candidate's
0.068865969 m residual was not proof of passing this local 0.05 m gate.
No threshold was tightened or relaxed for this trial.

The local residual improves on the earlier global candidate #4 by only about
0.000535 m (0.78%). It reaches the same plausible region, but that small change
does not establish a practically better estimator. Being near the clicked prior
is also not independent validation because the prior guided the search.

An independent full-map nearest-neighbor computation over every original scan
point produced RMSE **0.06833120503889017 m**, matching worker RMSE
**0.06833120503889112 m**. Full-scan RMSE was identical; all 336 points were
within the existing 0.75 m correspondence radius. These are fit residuals, not
physical position error measurements.

## State preservation and evidence

Before and after the experiment: control STOP=true, lease=false, bridge Move=0;
observation STOPPED, active=false, busy=false, session=null, guard=null. The
previous owner_failure sample (dataset OWNER_LOCK_BUSY, monotonic 1712.964522588)
remained historical evidence and was not relabeled clear.
Fresh readback at 21:57:02.329 KST confirmed the same values and release.

This trial's robot mutation counts: observation start/stop 0/0, proposal requests
0, step ② confirmation 0, INITIAL POSE send 0, Nav2/registration/goal/STOP release
0. One frozen-data numerical call wrote only diagnostic files. Raw inputs were
unchanged, no executable repository code changed, and no deployment occurred.

Exact helper, request, result and log are retained outside Git:

- Local: `../nav2-prior-seeded-20261113/`.
- Remote: `/home/unitree/robot-scope-diagnostics/prior-seeded-20261113/`.
- Previous comparison: [SESSION_AND_CANDIDATE_COMPARISON.md](SESSION_AND_CANDIDATE_COMPARISON.md).

Only this record is published. No raw point cloud, map, credential, or diagnostic
JSON is committed. The user's conditional request resulted in **keeping the
existing production behavior**, not installing a partial seeded-proposal path.
Any later live trial needs fresh source-bound full-pose evidence and preservation
of its exact input before evaluating whether seeded search is better.

## Validation

Independent frozen-input scoring matched, and original input hashes remained
identical. Existing event-safety/preparation JavaScript checks passed 29/29.
The required Windows full Python unittest completed in 25.983 seconds with
1,798 tests reported, **25 failures, 422 errors, 22 skips; not a pass**. Unlike
the prior sandboxed run, this normal-permission run terminated without hitting
the 120-second timeout. Observed platform errors include unavailable Unix
`resource` and `os.geteuid`; the complete log is retained outside Git as
`../nav2-session-change-20261113/seeded-trial-unittest.log`. Failures are not
silently discounted, and no platform patches were made for this documentation
update. The exact unchanged deployed release's Linux CI success remains separate
evidence. These checks do not turn the rejected numerical experiment into
hardware localization acceptance.
