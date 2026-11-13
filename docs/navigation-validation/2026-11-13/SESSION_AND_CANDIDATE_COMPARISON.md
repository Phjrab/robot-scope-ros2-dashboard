# Observation lifecycle and candidate comparison, 2026-11-13

## Scope and deployed state

Read-only investigation, offline comparison, and the already approved stationary
trial were continued after charging/reconnection. The initial PC address was on
a different subnet; HTTP timeout was not classified as robot failure. The user
restored the 192.168.0.x LAN and explicitly confirmed on-site stop supervision.

Actual dashboard and bridge release after reboot was
`8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`; browser source matched this release.
Boot ID was `61842994-bca5-46d6-adcf-53881125bcb5`. Both service restart counts
were zero at inspection. Published main at the start was
`32b9e2d4085f04a86dba7a560564e5355b055486`. The completed-draft focus fix is
deployed; its earlier software validation and limitations are in
[INITIAL_POSE_FOCUS.md](INITIAL_POSE_FOCUS.md). This investigation changes no
executable code and does not deploy or restart dashboard/control services.

## Historical session change: facts and limits

Job `8a7abdf65e7f3ced366b660c` completed at monotonic 4375.990815283 in
observation `626c5b397c8c4bc68215ba63ca14925b`. Session
`7201f30957ef4b46811cf6af893156e2` started at 4406.972319, 30.981504 seconds
later and 700.444684 seconds after the previous observation began.

The old boot journal was unavailable (only volatile current-boot journal), but
persistent syslog and auth.log retained these explicit native commands:

| KST | Evidence |
| --- | --- |
| 19:25:03 | sudo `systemctl --no-block stop robot-scope-observation.service`; systemd stopping, deactivated successfully, stopped |
| 19:25:10 | sudo `systemctl --no-block start robot-scope-observation.service`; systemd starting, started |
| 19:25:11 | New laser_mapping process initialized |

Both sudo working directories were the then-deployed `30b9caa...` release.
This establishes real service stop/start, not only browser draft invalidation.
Normal 1800-second expiry does not explain the timing. No dashboard restart
appears in this window; dashboard PID 64791 persisted across it.

The original HTTP initiator is **unidentified**. Ordinary HTTP access logging is
disabled. WebSocket connections from .6 and .14 are not evidence of who sent a
mutating request. The release working directory is consistent with dashboard
dispatch, but does not independently prove its parent caller. The frontend
observation handlers require explicit invocation and do not automatically retry;
blur/visibility invalidation does not call observation start/stop. Backend status
refresh and guard failure handling do not automatically restart this service.

## Current trial: separate user-confirmed actions

The user directly confirmed observation stop/start changed
`15672f65b9084ac596e1e04c08d4030b` to
`52cf3b25545d4dc6b8423e296b90a967`, and separately confirmed pressing calculate.
These confirmations apply to the current trial, not the unidentified 19:25 actor.

The resulting job/proposal was `fe40d20dc6f03713c9e1834e`, request ID
`navigation-proposal-514485e5948c1bb474f2fb3bf67d2c68`.
Created/completed monotonic times were 1378.817099251 / 1391.634446202.
The recorded input stamp was `1794572875485123395`; completion appeared in the
browser around 21:28:09 KST. Same-session result readback persisted through
21:30:54.898 KST. Pair generation was `8409e46836ba4920835367d4e81296d4`.

The worker **succeeded**, but the navigation proposal was **rejected** with
`PRIOR_NO_MATCH`, cleanup SETTLED, worker inactive. Proof/provenance was null;
seed_geometry and initialization_handoff were null, and the apply button was
disabled. No valid proposal/proof was available for step ② confirmation.
There was no confirmation request or server handoff to compare.

The user clicked before the agent's complete request recorder was ready. The
direct POST request/response and client draft revision were not captured. Job
metadata, all retained candidates, rejected proposal, server diagnostics, and
same-session DOM/state were preserved. Do not invent the missing request fields
or treat a later expired GET as the original rejection.

## Why this result differs from the earlier briefly-ready result

Both use map_20261113_181538 + map_20261113_181538_edited, identical map array
SHA256 `5faf3f82b91150b2e4bd0b2ff8ab726ded8d0eba3c3ed056981d2b02a1f904dd`,
32,387 reference points, and the same map revisions/calibration SHA256.
The 3D revision is `67df671eb06987fec3ba189aa0c369718de6d228b469bbc205c4a5e9a7a0e84e`;
2D revision `f7fe51817b9201a775b66092e12644f47a8831ff40a12a43c82c86ec0953860e`;
calibration `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`.
Profile remains go2-onboard and controller odometry is
`/robot_scope/nav/controller_odom_fastlio`.

Both worker executions have backend pin
`47ea8760ff6a0522067850a6bd10b330ca8a21c9c5ed12c82a1936ba9541bcef` and worker SHA256
`3e5403b50fe661ccbb06db736c62c7d97270350272b70b6c3b999391a916cde3`.
The 30b9caa-to-8234fcd changes do not change the registration backend.
Both jobs used global search, seed=null, six attempts (0–5), eight retained
candidates, native thread caps of one, and completed/reaped within 120 seconds.

| Measurement | Earlier 8a7 job | Current fe40 job |
| --- | --- | --- |
| Input points | 336 | 378 |
| Temporary lowest-RMSE candidate (zero-based) | #4 | #6 |
| Inlier RMSE | 0.068865969 m | 0.253632613 m |
| Full-scan RMSE | 0.068865969 m | 0.432424076 m |
| Overlap (nearest-map distance <= 0.75 m) | 1.000000 | 0.933862 |
| Native execution time | 7.319 s | 7.713 s |
| Candidate behavior | #2/#3/#4/#5 cluster near x=3.97–3.99, y=4.06–4.08 | No candidate within operator-prior bounds |
| Proposal evidence | Brief ready DOM; full ready proof not saved; subsequently session-stale | Preserved rejection PRIOR_NO_MATCH in same session |
| Applied to step ② | Not done | Not done |

Cluster coordinates above refer to IMU at capture in the localization map, not
an independently measured robot location. Old yaw was about -170.5 degrees.
RMSE and overlap measure point-cloud fit, **not physical localization accuracy**.
Both results retain unresolved ambiguity; temporary minimum-RMSE selection is
not operational acceptance. High overlap alone is weak evidence: this backend's
overlap radius is 0.75 m, and excluded points do not contribute to inlier RMSE.

The current authoritative server comparison transforms candidates to base_link
in the navigation map at the prior anchor. Prior was
x=3.9848961407774457, y=4.1965879855189705, yaw=-3.056690860140071.
Every retained candidate failed both server bounds (0.25 m, 0.20 rad).
The nearest by XY was #1 at x=-0.924519153533902, y=2.086667873030337,
yaw=-0.4516607599632445: **5.343605657 m and 2.605030100 rad (~149.26 degrees)**
away. The minimum-RMSE candidate #6 was 10.650062267 m away.
This is not a borderline tolerance failure.

The concrete failure is upstream of confirmation: the retained global candidate
pool misses the operator-prior region. Application code launches global search
and uses the prior to select candidates afterward; it does not seed a local fit
at the clicked position. Pinned backend uses FPFH/RANSAC at 0.15/0.30 m feature
scales, six seeded attempts, then local refinements. Earlier attempts 1–4 began
near the eventual good cluster; current coarse proposals already begin elsewhere.
The finite retained pool is explicitly not globally exhaustive.

Changed input is established: current scan SHA256
`63597209a1e221e0685147e9a488b4f9f629c75d35fb7a966ba6602290d725ab` differs from the
old preserved scan. Both use cached registered XYZ rebased via exact-stamp
FAST-LIO odometry to the IMU. The old and new odometry origins belong to different
sessions and cannot be subtracted to infer physical movement.

It is plausible that changed visible geometry/point distribution caused different
feature correspondences and search convergence. **The deeper cause is not yet
proved:** the new 378-point XYZ file was not preserved before normal worker
cleanup. We cannot distinguish scene change, input geometry or upstream sensing
issues by residual summaries alone. The user's position estimate has not been
independently surveyed either. Do not blame the prior, claim a frame defect, or
increase bounds based on this evidence.

## Offline verification and retained evidence

Original input.json, scan.f64 and map.f64 hashes were reverified. A previous
documentation typo in the scan SHA256 was corrected; raw bytes were untouched.
An offline NumPy nearest-neighbor calculation independently reproduced inlier
RMSE, full-scan RMSE and overlap for **all eight old candidates** against every
point of the full preserved map (RMSE agreement <1e-9 m). This rechecks residuals,
not native global-search repeatability or physical accuracy.

Outside Git, relative to the repository parent:

- `nav2-preserved-input-20261113/`: original exact 336-point input and map.
- `nav2-session-change-20261113/`: copied syslog/auth excerpts, trial readbacks,
  failed job/proposal/operational state, `compare_candidates.py`, and its
  `comparison.json` output.
- `nav2-same-session-result.local.json` and `nav2-same-session-rejection.png`:
  preserved rejection and disabled confirmation UI.

Remote evidence is under
`/home/unitree/robot-scope-diagnostics/session-change-20261113/trial-122504`.
Read-only recorders made no observation mutations. The obsolete recorder was
terminated after checking its exact command; its replacement exited on rejection.
Raw maps/clouds, local evidence JSON and credentials are not committed.

## Operation count and final readback

For this resumed trial, agent mutation requests: observation start **0**, proposal
calculate **0**, confirm/apply **0**, exact-session observation stop **1**.
The user confirmed their own restart and calculation; no claim is made to an
exhaustive count of other user/client requests without an HTTP access log.

At 21:35:21.780 KST the agent sent the already-authorized cleanup POST once with
`confirmed=true`, `session_id=52cf3b25545d4dc6b8423e296b90a967`.
Response was HTTP 202 STOPPING. At 21:35:23.940 KST it read back:
STOPPED, active=false, busy=false, session=null, guard=null, result=success;
control STOP=true, lease=false, bridge Move count=0, release=8234fcd.
The response retained an earlier owner_failure sample for dataset OWNER_LOCK_BUSY
at monotonic 1712.964522588; it was not silently relabeled as clear. A fresh
21:46:36.700 KST readback confirmed the same STOPPED/inactive/not-busy/no-guard,
STOP=true, lease=false, Move=0 and release, with the same historical owner sample.

INITIAL POSE send, Nav2 start, operational registration, goals, STOP release and
motion requests were all **0**. No automatic retry/recalculation/application was
performed after rejection. Step ② same-session application remains unverified.

Next one task: arrange exact input capture before a separately agreed fresh
stationary calculation, then compare the failed XYZ with the map and the old
preserved scan. Do not replay an expired proposal or broaden acceptance bounds.

## Validation of this documentation-only update

Local event-safety/preparation JS: **29 passed**. Relevant mocked browser
regressions: **6 passed** (rejection diagnostics, exact-session stop during a read,
explicit grouped-proof consent, and prior/calibration/map consent invalidation).
The first browser attempt stalled in the sandbox; the next encountered its
occupied local port. After identifying and cleaning up only this test's process
tree, the normal-permission run passed all six tests.

The required full Windows unittest was invoked again. It encountered five loader
errors and stalled at the existing competition worker test; the 120-second
timeout's sandboxed taskkill failed, so the identified test process tree was
explicitly terminated with normal permissions. **Not a full-suite pass.** A
focused loader reproduction confirmed the existing unavailable Unix `resource`
module. These are not new failures from a documentation-only change.

The exact deployed 8234fcd Linux CI run 43412313905 and I0 run 43412314055 were
rechecked: both succeeded. Those are software/mock results, not stationary
hardware or localization acceptance. Diff whitespace check passed. No new robot
deployment is required for this documentation update.
