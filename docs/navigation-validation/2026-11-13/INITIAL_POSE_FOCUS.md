# Preserve completed initial-position drafts across focus changes

Date: 2026-11-13, Asia/Seoul. Base code: `30b9caa`; base main: `c2f64ca`.

The user prioritized fixing INITIAL POSE becoming unconfirmed over further
cloud-to-map analysis. In the old frontend, both window blur and document hiding
called `preNavigationDraft.suspend()`. That marked even a completed, unsent
point/direction stale. Returning to the dashboard did not recover it: the user
had to draw it again, even when the map and runtime context had not changed.
This transition was reproduced in local browser tests. It does not prove that
every reported field occurrence came from focus rather than a failed state read
or a real map/session/runtime change.

The fix preserves completed local geometry on blur/hidden-page events while
clearing the active placement tool, stationary consent and proposal consent/use.
Returning to the page does not restore consent. The user must check their actual
position/direction and explicitly check the stationary assumption again. In
contrast, an interrupted drag remains unconfirmed, including a late pointerup.
Existing context invalidation, map/revision/calibration checks, failed-read
handling, actual runtime INITIAL POSE admission, proposal freshness and server
guards remain unchanged. A pre-navigation draft is still never SEND-able.
Manual-control blur/hidden fail-safe and recording cleanup still run before the
draft handler, even if draft handling throws.

Reproduction and validation:

- Before the fix: two new completed-draft blur/hidden tests failed with
  `INITIAL · 이전 미전송 초안 · 미확인`; the interrupted-drag guard passed.
- After the fix: all three focused browser cases passed. They cover unchanged
  coordinates, revoked stationary consent, no automatic consent on focus return,
  explicit re-check enabling calculation, blocked SEND and no unintended POST.
- The event-safety fixture was updated to execute the actual new handler and
  test completed and partial drafts, including injected consent/render failures.
  Focused event/preparation JavaScript checks passed 29/29; full JavaScript
  suite passed 774/774. JavaScript syntax check covered 135 modules.
- Complete related browser suites: 112 run, 106 passed and six failed in the
  existing Python API fixtures because Windows cannot invoke their python3
  alias. These are environment failures, not skips or passes.
- Required full Python unittest was attempted with the local venv, encountered
  the existing loader errors and stalled worker, and was terminated after 120 s.
  No full Windows Python pass or substitute resource module is claimed. Exact
  candidate Linux CI is required before considering deployment.
- Diff whitespace and tracked-source credential scan passed.

This is a local software fix. It has not yet been deployed and does not authorize
another service restart, observation, calculation, INITIAL POSE or movement.

## Initial candidate and maintenance boundary

Code candidate: `4d736299a13fb627e7de5c96e07bf8934970044e`.
The LF archive `nav2-candidate-4d73629-lf.tar` was prepared outside the repository.
Its 2,736 regular files matched the candidate Git blobs; archive SHA256 is
`3a0411a891f2700b3e5c933c615b6ac1fba2fd1fb305ceeaf364a008f44087db`.
It has not been uploaded or selected on the robot. This initial archive is not
deployment-ready: its complete CI found the browser fixture omission below.

The rollback release is the currently deployed
`/home/unitree/robot-scope-releases/30b9caa95ac2aba3ad43d523d8aa935891c3a74d`.
A future approved deployment must preserve both shared `.venv` and `workspaces`
links, back up the current selector, and re-read the exact observation session
before stopping it. Dashboard and control-bridge restart are separate from Git
publication. Keep STOP latched, check lease/move evidence and release identities
after restart, and inspect the browser after loading the new frontend. On failed
release verification, restore the selector to the existing release and verify
both services again; do not start observation or motion as part of recovery.
If session termination or safety readback cannot be verified, stop maintenance
instead of treating UNKNOWN as clear. This plan is prepared, not executed.

At 2026-11-13 19:42:31 +09:00, read-only control/observation responses showed:
bridge release `30b9caa95ac2aba3ad43d523d8aa935891c3a74d`, STOP latched, lease
inactive, bridge Move request count 0; observation
`7201f30957ef4b46811cf6af893156e2` READY, active/busy, guard HELD and no
owner_failure. These are timestamped software readbacks, not physical-stop or
localization-accuracy evidence.

## Initial candidate CI and browser fixture correction

For exact `4d736299a13fb627e7de5c96e07bf8934970044e`,
[CI run 43410384965](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43410384965)
passed the full Python suite on Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python
3.12: 3,754 tests per environment, 35 skipped, zero failures. Both passed all
774 JavaScript tests, 10 mission API-fixture browser cases and one manual-2D
API-fixture browser case. The independent competition integration job passed.
[I0 run 43410384941](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43410384941)
also passed; its expansion JS group had two explicit skips (84 passed).

The complete browser suite did not pass: each OS had 347 passed and four failed.
All four failures were in `navigation_event_safety.spec.mjs`: the isolated
registration fixture omitted the newly extracted `pausePreNavigationPlacement`
definition and raised ReferenceError before registering the listeners. This
fixture issue was missed by the earlier two-file local browser run, which did
not include that file. It is not counted as an environment failure or ignored.

The follow-up includes the real helper in that browser fixture, exercises both
completed and interrupted drafts, and verifies that the native EventTarget
reports exactly the injected consent/render/suspend error after the expected
fail-safe calls. Production JavaScript is unchanged by this follow-up.
After correction, the local native-event browser suite plus pre-navigation
draft suite passed 27/27; the event-safety Node suite passed 15/15.

## Follow-up candidate and later readback

The corrected candidate is `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`.
Its prepared LF archive contains 2,736 files verified against the Git blobs;
SHA256 is `0ec09da1376938b806d11144c9df98b06a3918cb5f306bba05de6913ce7b0825`.
The archive remains local; the device still reports `30b9caa`.

At 2026-11-13 19:56:10 +09:00, the same observation session was FAILED with
`result=timeout`, `limit_s=1800`, active=false, busy=true and can_stop=false.
Its guard was INVALID/CONTROL_BRIDGE_INHIBIT_UNREADY; owner_failure was null.
The control response still showed STOP latched, no lease and zero bridge Move
requests. No stop/start/restart or proposal request was issued during this fix.
This is not a clean STOPPED observation, and the leftover busy/guard state must
not be treated as clear. Read-only evidence is retained locally. Any approved
maintenance must re-read the state and verify actual observation-unit cleanup
before changing releases; no new observation is included in this fix's scope.
The final read-only check at 20:03:32 +09:00 returned the same release,
session/failure/guard state, STOP latched, no lease and zero Move requests.

Final exact-candidate results for `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`:

- [CI 43412313905](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43412313905): success.
  Each Linux environment passed 3,754 Python tests with 35 explicit skips
  (3,719 executed passes), all 774 JavaScript tests, 357 full browser cases
  (179 + 178 shards), 10 mission API-fixture browser cases and one manual-2D
  API-fixture browser case. The competition offline integration job passed.
- [I0 43412314055](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43412314055): success.
- The previously failing native-event browser fixture now passes in both OS
  environments. No disabled checks or relaxed product admission were used.

The following documentation-only publication records those results; it does not
change the tested application's code or the prepared deployment archive.
Actual device deployment and field verification of the new focus behavior remain
NOT_RUN, pending current-session maintenance authorization. The next action is
that scoped maintenance decision, not a new proposal calculation or motion test.

## Preserved input evidence for later analysis

Before this priority change, the user authorized exact input preservation and
confirmed a newly drawn stationary prior. The agent clicked proposal calculation
exactly once for job `8a7abdf65e7f3ced366b660c`. A bounded file-copy watcher captured
the input before the normal worker cleanup, without editing the input or worker.
The copied input context matched the completed job exactly; the files matched
their SHA256 declarations, and all seven copied backend source files matched the
input's source pin. No service deployment/restart was used for preservation.

- Input source stamp: `1794565465844563961`.
- Scan: 336 XYZ points, 8,064 bytes, SHA256
  `970656f4ad489ee943cbde73fd4cbe6aa4be9d00079c9b5febef6c457b353fc1d`.
- Map: 32,387 XYZ points, 777,288 bytes, SHA256
  `5faf3f82b91150b2e4bd0b2ff8ab726ded8d0eba3c3ed056981d2b02a1f904dd`.
- Input JSON: SHA256
  `4b1bb6feba98d1c09fc30cb2e13cfd343fd494d1b15f1877ff937256501c6191`.
- Remote evidence directory:
  `/home/unitree/robot-scope-diagnostics/prior-input-20261113/capture-1794565465844563961`.
- A verified local copy is outside the repository at `../nav2-preserved-input-20261113`.
  Raw arrays/map data were not committed. This is the exact registered cloud
  rebased to the FAST-LIO IMU, not a LiDAR raw-packet archive.

The worker succeeded. The DOM briefly showed proposal state ready; the later
API response was stale/OBSERVATION_SESSION_CHANGED. The observation session had
actually changed from `626c5b397c8c4bc68215ba63ca14925b` to
`7201f30957ef4b46811cf6af893156e2`. The agent did not change that session and did not
apply/send the proposal. A retained ready response with its complete pose/proof
was not captured, so this is not localization acceptance. Offline comparison of
this preserved input is deferred at the user's explicit request.
