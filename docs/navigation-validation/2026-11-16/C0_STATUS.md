# C0 integration status — 2026-11-16

## Scope and current state

Offline integration plus read-only robot inspection. No deployment, service restart,
session change, STOP release, initial pose or motion command was performed. The fetched baseline was `a81ef92f6942d85f9e06c548a08a444b845f5536`.
Software fixes were committed and pushed as `afcce2f29b1b0a50762d630c460d6b611833553f`.
The final UI change removes four redundant preparation checkboxes, adds actions
inside all six step cards, and collapses technical evidence. Existing guarded
robot actions and backend admission remain in effect. The user requested work
to end after UI completion and commit; robot deployment remains NOT_RUN.

The last verified robot release remains `37b4f80`. Read-only live evidence
identified bridge PID 2931 at `/proc/2931/cwd` as that release; dashboard PID
2796 and observation service PID 20009 were observed. STOP was latched, with no lease and zero
commands. Motion observation was `INVALID` because SportModeState position was
invalid; Nav2 was idle. The base tree (`d7807de`) is not the deployed runtime.
These software readbacks do not establish a physical halt.

## Validation snapshot and triage

- **Python baseline:** 3,802 tests; 8 failures, 262 errors, 37 skipped. This is
  not a clean integration result. The dominant environment errors are missing
  Linux `/proc` entries on macOS (41), restricted socket operations (39), and
  temp-path symlink rejection (28). Two launcher tests also fail because the
  checkout path contains a space and the generated shebang resolves
  `/Users/hajoonpark/robot` as the interpreter. The slow-confirmation test and
  three race variants timed out waiting for slow-validation entry; one
  read-only acceptance test sees a `FAIL` in its check set. No confirmed
  critical/high safety defect was
  established by this baseline; classify the loader issue as medium and fixed
  by C1, pending integrated validation.
- **JavaScript baseline:** 781 passed, 0 failed; syntax check completed.
- **CI reference:** baseline Linux CI succeeded for [main integration](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43816019396)
  and [I0](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43816019415).
  This is supporting baseline evidence, not a result for the current changes.
- **Focused change checks:** C1 launcher post-source `--check-load`: 5 tests
  and 22 jobs passed. C2 actual pose-receipt freshness 1 s gate: 120 Python
  and 18 JavaScript checks passed. C4 symmetric ICP residual and grid bounds:
  23 Python and 2 JavaScript tests passed. UI checkbox removal/cards: IMPLEMENTED; 781 JavaScript tests and syntax
  checks for 136 modules passed. Browser validation is recorded below. Integrated Python run: 3,818 tests, 12 failures, 69 errors, 37 skips (**BLOCKED** on macOS); full JavaScript prior to final UI: 781 passed. `/proc` identity, temporary-file group ownership and dependent handoff thread waits account for observed failures; Linux CI for the new commit remains required.

Agent model/reasoning record: C1 Astra/high; C2 Sol/high; C3 changed from
Astra to Sol/high; C4 Sol/high; C5 Luna/medium. These are process notes, not
validation claims.

## Safety and timing interpretation

No critical/high safety finding is confirmed from the reviewed evidence. The
bridge watchdog threshold (200 ms, signed-command age) and Nav2 manager limit
(300 ms, raw-command age) measure different streams and are not interchangeable.
No deployment or motion authorization is implied by this report.

## Field benchmark record

All values below are intentionally blank until collected during an authorized,
supervised field run. Do not infer or backfill values from offline checks or
historical runs.

| Field | Value |
| --- | --- |
| Map ID / map revision | FIELD_PENDING |
| Calibration ID / revision | FIELD_PENDING |
| Robot release / software revision | FIELD_PENDING |
| Start pose / direction | FIELD_PENDING |
| Goal pose / direction | FIELD_PENDING |
| Action result / terminal reason | FIELD_PENDING |
| Distance and time to goal | FIELD_PENDING |
| Commanded / observed velocity | FIELD_PENDING |
| Stall intervals / progress events | FIELD_PENDING |
| TF and sensor gaps (source and receive times) | FIELD_PENDING |
| Recovery events / count | FIELD_PENDING |
| Watchdog events / readbacks | FIELD_PENDING |
| Resource use (CPU, memory, temperature) | FIELD_PENDING |
| STOP request / independent readback | FIELD_PENDING |

## Final UI validation

Browser checks: 112 scenarios; 110 passed in the final full run, then the two
remaining obsolete UI assertions were corrected and both passed in the focused
retry (4.8 s). No product code changed for that retry. Desktop 3-column and
mobile single-column layouts were visually inspected; no mobile overflow.
`node --test tests/*.mjs`: 781 passed; frontend syntax: 136 modules;
`git diff --check`, Ruff and configured Mypy checks passed.
Linux CI for afcce2f was still in progress when the user requested termination
after the UI commit; no overall CI success is claimed. Independent C3 safety review accepted the
UI action forwarding and action-time acknowledgements with no blocker.

The offline correction menu targets the browser PC at `http://127.0.0.1:8091/`.
A local analysis server was started and its page opened successfully; outputs
use a separate `offline-slam-analysis` directory. No operational map was changed.
