# Initial-position proposal rejection diagnostics

Date: 2026-11-13, Asia/Seoul. Base main: `7433e89db42ded5efaec8a0ec4db3ae66cdfc574`.
This is a local software change and read-only field diagnosis, not a deployment
or approval for observation, INITIAL POSE, Nav2, goals or motion.

## Field evidence and limits

The user changed the map pair to `map_20261113_181538` (3D revision
`67df671eb06987fec3ba189aa0c369718de6d228b469bbc205c4a5e9a7a0e84e`) and
`map_20261113_181538_edited` (2D revision
`f7fe51817b9201a775b66092e12644f47a8831ff40a12a43c82c86ec0953860e`).
These are new user selections, not the historical November 9 pair restored by
the agent. Their coordinate relationship is operator-confirmed, not measured.

Two user-triggered jobs were inspected without submitting new calculations:

- `d1a16630e1e793df9a88592b`: global worker succeeded in 13.603 s, 10 retained
  candidates, proposal rejected with `PRIOR_NO_MATCH`.
- `fa1c9f8a779f4a503802b5c1`: global worker succeeded in 14.940 s, 9 retained
  candidates, proposal rejected with `PRIOR_NO_MATCH`. Pair generation
  `a0b738bb43c7472281df3e6cc6296891`, observation session
  `c55cb93cd9ba4c58ba2cf2ccb32f7626`.

Both jobs retained `AMBIGUOUS_ALTERNATIVES` / `AMBIGUOUS_UNVERIFIED_ESTIMATE`.
Worker completion is not proposal acceptance or localization success. The
observed session remained READY with valid preparation evidence, guard HELD
and no owner_failure. No physical-stop or autonomous-driving acceptance follows.

The latest DOM preserved the rounded draft X=4.083 m, Y=4.050 m, yaw=-3.042 rad,
but marked it stale/unconfirmed. A generic context-change message replaced the
server's rejection explanation. The exact real focus event was not captured;
blur/hidden-page draft suspension is a software mechanism, not a proven account
of the user's actions.

The existing server computes each candidate in navigation-map/base_link at the
prior's anchor time, then discards those comparison values on rejection. The
public global-job result exposes scan-time IMU transforms, not all inputs needed
to reconstruct the exact prior-time body comparison. Comparing raw IMU positions
directly with the rounded UI draft, inventing a zero odometry delta or body
offset, or moving the draft to a candidate would not be valid diagnosis.

## Change

After the existing candidate-set, geometry, duplicate-group and prior checks,
zero/multiple-match rejections now optionally return bounded historical
diagnostics: the actual prior, effective bounds, candidate planar poses,
distance, wrapped yaw difference and separate inside/outside flags. The same
matrix chain and already-computed values used by the decision are reused.
All rejection criteria, grouping rules, freshness, ownership and server
admission remain unchanged. Invalid candidate sets do not acquire diagnostics.
Rejected responses still have no usable body/IMU/geometry candidate and remain
`operational_application=NOT_RUN`. Expired contexts do not return these values.

The frontend keeps a separate, identified rejection history from the exact-job
status/cleanup response, including when a response arrives after draft
suspension. This history cannot populate proposal/geometry, enable confirmation
or bypass a stale draft. A new explicit calculation clears it. Numeric data is
bounded and checked for frame, units, finite values, distances and bounds before
display; invalid numeric metadata does not suppress the rejection reason.

The reason-loss regression was reproduced before the frontend fix in both
response-before-suspension and response-after-suspension cases. The two tests
failed on missing rejection history, then passed with action guards retained.
The initial browser-test attempt could not launch because the test-only Chromium
installation was missing; after installing the pinned Playwright browser,
the actual before/after reproduction ran. No robot browser package was changed.

## Validation and next step

Validation results are recorded with the published candidate. Windows Python
cannot import the Linux-only `resource` module through the existing application
package. This is an environment failure, not a skip or successful backend test.
No fake `resource` implementation is used. Linux CI is required for the Python
regressions and complete suite before considering device deployment.

The new diagnostic code must be deployed under a separately approved maintenance
scope before a new supervised calculation can provide exact field differences.
This change does not establish whether the operator draft, map coordinate
relationship or registration candidates disagree with the real robot position.
The small-first-feedback progress defect and autonomous-driving validation remain
outside this change.

Local checks before publication:

- JavaScript: 766 passed; final focused presentation tests: 14 passed.
- Related browser suites: 110 run, 104 passed, 6 failed because the existing
  Python-API fixtures invoke the unavailable Windows `python3` alias. These
  failures are not skips or successes. Final focused tests for delayed rejection,
  stale draft, diagnostic display/open-state and new-request clearing: 3 passed.
- Python focused test import failed on the existing Linux-only `resource`
  dependency. Full `unittest discover -s tests -v` was attempted, produced loader
  errors and stalled in the existing worker test; terminated after 120 seconds.
- Ruff (application/scripts), configured mypy, tracked-source secret scan and
  diff whitespace passed. No tolerance, stall timeout or robot control change.

Linux CI results are separate evidence and must be checked against the exact
published code candidate. No local Python or full browser-suite pass is claimed.

## Candidate and maintenance preparation

Published code candidate: `30b9caa95ac2aba3ad43d523d8aa935891c3a74d`.
The LF Git archive contains 2,735 files; every archived file matched its Git
blob. Archive SHA256:
`716293d44cfa950e219f657ccf4a5b373cd20264baaf719a4b5fc391cefc1c22`.
This archive is local only; no candidate release was uploaded or activated.

Read-only preflight on November 13 found dashboard PID 1030 and bridge PID 2858
both running from the exact `8d541acc0b8ed1fa581389a78d37e8f860500cfa` release.
The persistent selector also names that release and retains startup STOP.
Shared `.venv` and `workspaces` resolve to `/home/unitree/robot-scope/.venv` and
`/home/unitree/robot-scope/workspaces`. The candidate release directory is absent.
At 18:47:38 KST, signed control reported that same release, STOP=true, no lease
and Move=0 within the current bridge process lifetime. Observation session
`c55cb93cd9ba4c58ba2cf2ccb32f7626` was READY/active, guard HELD, owner_failure=null.
This is a timestamped software readback, not physical-stop confirmation.

The edited 2D map's family metadata links the current 3D revision through
`planar_xy_identity`; original and edited 2D metadata retain the same origin,
resolution and dimensions. This supports their declared coordinate provenance,
but does not measure the user's real position or validate the registration.

After successful exact-candidate CI, a separately approved maintenance scope
would cover ending the exact currently active observation, verifying STOP and
lease/ownership, deploying the verified archive while preserving both shared
links and XT16 executables, and restarting dashboard/control bridge. Back up the
mode-0600 selector on-device, change only ROBOT_SCOPE_DIR, and verify both process
roots, signed release, STOP, no lease and inactive observation after restart.
Unexpected activity or UNKNOWN blocks activation. Restore the saved selector to
the exact `8d541ac` release and restart the same services if postflight fails.
Preserve old release, maps and dependencies. The restart clears applied pair and
unsent draft by design; reconnecting the pair and any new observation/calculation
are separate steps. No INITIAL POSE, Nav2 start, goal or STOP release is included.

Documentation pre-commit checks repeated the required Windows full unittest
command: the same loader errors and stalled worker led to the 120-second limit,
not a pass. Related JavaScript tests passed 14/14 and diff whitespace passed.

## Exact-candidate CI and final readback

Both workflows completed successfully for code candidate
`30b9caa95ac2aba3ad43d523d8aa935891c3a74d`:

- [CI 43403431523](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43403431523):
  all seven jobs successful. Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12
  each ran 3,754 Python tests: 3,719 passed and 35 skipped, coverage 79%. Each
  environment passed 766 JavaScript tests, 349 browser tests (175 + 174 shards),
  10 mission fixture E2E tests and one manual 2D fixture E2E test. These are
  hardware-free checks, not robot navigation evidence.
- [I0 43403431463](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43403431463):
  product-and-capacity successful. The slower browser shard completed in 12.1
  minutes; no rerun or relaxed assertion was used to obtain the pass.

Final device read at 18:55:15.700 KST still reported exact release `8d541ac`,
STOP=true, lease=false, current-process Move=0, the same observation session
READY/active, guard HELD and owner_failure=null. The read-only SSH session was
closed. No observation start/stop, proposal calculation, INITIAL POSE, Nav2,
goal, STOP release, deployment or service restart was performed in this phase.

Next single action: obtain the separate maintenance approval for the verified
candidate and recovery plan above. Re-read the current observation/session and
control state at execution time; this final readback is not a future admission.
