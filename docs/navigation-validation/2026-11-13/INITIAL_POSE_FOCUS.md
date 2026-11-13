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
