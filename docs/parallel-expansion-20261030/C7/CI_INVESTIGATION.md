# C7 remote CI investigation — 2026-10-30

**Closure status: BLOCKED_EXTERNAL_OWNER.** The initial remote failure is retained.
No C7 production defect has been demonstrated. Shared Maps UI and browser fixture
changes require their owners; this investigation does not edit those files.
The submitted commit and its current CI result must be checked independently of
the original run. A later green run does not resolve the reproduced defects.

## Fixed sources and isolation

- Repository: `Phjrab/robot-scope-ros2-dashboard`.
- C7 branch: `review/20261030-x-c7-capacity-diagnostics`.
- Initial remote C7: `3d77ac29e34205d8173085dae950bb999cfdf816`, exactly the requested SHA.
- Reference main: `5154761bba6fa4f171881e61f986901e2b415ed9`, also unchanged at initial clone.
- Independent clone: `/home/desktop1/Documents/ChatGPT/robot/c7-ci-investigation-20261030`.
- Independent detached main clone: `/home/desktop1/Documents/ChatGPT/robot/c7-ci-main-20261030`.
- Raw evidence: `/home/desktop1/Documents/ChatGPT/robot/c7-ci-evidence-20261030`.
- No original chat checkout was modified. User-specified branch/scope overrides
  the default main-only instruction in repository `AGENTS.md`.

`source-comparison.json` records hashes. All `tests/e2e/` and
`robot_dashboard/static/` files, CI workflow, Playwright configuration, package
lock, and Python requirement files are byte-identical between fixed main and C7.
The original C7 diff only adds files in the four authorized directories.

Before submission, remote main advanced to
`846121b4988ed2932d329020857925558f8f2c79` while C7 remained at the original SHA.
Its one new commit only updates/adds the October 29/30 heading field-check docs
(two files, 249 added lines). `ci-evidence/remote-ref-observation.json` records
the exact paths and observation time. It does not alter the tested UI, E2E, or
dependencies. The requested comparison baseline remains `5154761…`; the newer
main was fetched for inspection only and was not merged into C7.

## Original evidence, preserved before any new CI

[Original run 40932918269](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40932918269)
is attempt 1 at the initial C7 SHA. Both jobs ran 227 browser tests, one worker,
no retry, 20 s test timeout and 5 s assertion timeout.

| Environment | Job | Failed test / sequence | Original browser result | Artifact |
|---|---|---|---|---|
| Ubuntu 22.04 / Python 3.10 | [123655803080](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40932918269/job/123655803080) | `global_observation_history.spec.mjs:90`, assertion :102; #54/227 after :63, before :110 | 226 pass, 1 fail, 14.0 min | [12924402324](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40932918269/artifacts/12924402324) |
| Ubuntu 24.04 / Python 3.12 | [123655803545](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40932918269/job/123655803545) | `mount_calibration.spec.mjs:343`, call :369, helper :142; #143/227 after :329, before :390 | 226 pass, 1 fail, 15.0 min | [12924267721](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40932918269/artifacts/12924267721) |

Python (3,139, 3 existing skips), JavaScript (700), static checks, dependency
audits, and competition offline integration passed. Mission real-API E2E was
**SKIPPED_BY_PRIOR_STEP_FAILURE** in both original hardware-free jobs.

The raw ZIP hashes match GitHub's artifact digests:

- 12924402324: `d11bb2cb5140ccd9d15291d2b6146aedac1a9a7ae04463873804c7f77c5d4251`.
- 12924267721: `780f4f12585d539c1acad47b55b00f634f3b3b7fbd66b9d186465a4c22697306`.

Each contains `test-failed-1.png`, `error-context.md`, and `trace.zip` under its
failed test directory. Screenshots were visually inspected; the traces were
parsed as data. Raw job logs and ZIPs remain in the evidence directory above;
compact excerpts, trace summary, and hashes are committed under `ci-evidence/`.
Excerpts retain original raw-log line numbers; only trailing whitespace is
trimmed in those derivative text files. The full raw logs are unchanged.
Artifact expiry supplied by GitHub: 2027-01-27 UTC. They contain synthetic data.

## Ubuntu 22.04: lost historical-open action

**Confirmed shared controller defect; original failure is consistent with it.**
The original trace has no request for `/global-jobs/dddddddddddddddddddddddd`.
The previous `cccc…` request succeeded. The second open click was accepted by
Playwright as visible/enabled; three periodic status requests began at trace
monotonic 201796.689–201797.122 ms. The click was performed at 201806.055 ms and
finished at 201820.370 ms. The page remained `IDLE · HISTORICAL_ONLY` for the
entire unchanged 5 s assertion. This is not a 404 response rendered incorrectly.

`GlobalObservationController.poll()` sets `reading = true` without notifying
`changed()`. `snapshot().canOpenHistorical` includes `!reading`, and
`openHistorical()` returns immediately if that gate is false. The UI's 1 s timer
renders **before** starting `poll()`, leaving an apparently enabled button while
the model rejects the action. `HistoryOpen` calls `sync()` again, but does not
queue or report the rejected user intent. Completing the poll does not retry it.

`history_poll_probe.mjs` gates the actual unchanged controller's status response.
It reproduces zero state-change notifications on poll start, zero detail GETs
for an open during the poll, and an empty error after completion. An explicit
second open after completion produces the expected synthetic 404 message.
The probe reproduces on both fixed main and C7. It uses no C7 runtime/imports.
The original trace lacks direct model-state instrumentation, so the precise
in-memory value at the original click is inferred from this matching sequence,
not claimed to be recorded by the trace.

## Ubuntu 24.04: accumulated fixture timers and exhausted test budget

**Confirmed stale WebSocket activity in the original trace; exact sufficient
cause of the 20 s timeout remains unproven.** Do not merge this with the history
race or label it merely a slow estimate response.

The failed test trace contains **14,845** `webSocketRoute.send: Target page,
context or browser has been closed` errors from earlier fixtures:

- `tests/e2e/dashboard_backend.mjs:265` and `:280`: 3,910 each (camera).
- `tests/e2e/dashboard_backend.mjs:244`: 2,142 (pointcloud).
- `tests/e2e/live_observation.spec.mjs:90`: 4,726 (pose, two stack variants).
- `tests/e2e/live_observation.spec.mjs:83`: 157 (joints).

These are Node fixture intervals owned by previously closed pages. In the source,
interval cleanup relies on `WebSocketRoute.onClose`; page/context teardown lacks
an independent timer disposer. The original history trace also contains 3,078
camera-send errors, but that does not establish one common root cause.

The actual `socket_cleanup_probe.mjs` confirms the lifecycle defect on both main
and C7 with Playwright 1.62.1 / Chromium 151.0.7922.34: three consecutive context
closures invoke **zero** socket-close callbacks, retain **1 → 2 → 3** intervals,
and execute **2 → 5 → 8** additional fixture callbacks in the successive 300 ms
observation windows. The probe itself clears every observed interval in `finally`.
This establishes a shared fixture leak independently of runner speed; it does
not establish that the leak alone caused the original mount timeout.

The mount test performed saved-artifact import and 12 manual point additions
before analysis. Relative to trace start, the stationary-condition check began
at 18,576.591 ms and completed at 20,298.050 ms; the estimate-click step began at
20,521.260 ms and the visibility assertion at 20,579.537 ms. The browser trace
does not record an estimate POST, but its API-event recording ends near the
budget boundary. The later `error-context.md` shows all three conditions checked,
the analysis button busy, and no result. Therefore absence from that truncated
network recording does **not** prove that the estimate was never sent. It also
does not establish an estimate-handler deadlock. The trace records eight pointer interceptions
by the Settings safety HUD/footer, including two around the budget boundary.
The screenshot shows the HUD/footer over the lower calibration area. The failure
is whole-test budget exhaustion with hidden results, not evidence that a completed
estimate was refused by C7 or the solver.

The stale interval leak and pointer interceptions are observed facts. Their
relative CPU/latency contribution, whether either alone is sufficient, and any
runner-specific scheduler contribution require an owner-controlled A/B test.
There is no host CPU profile in the original artifact. A cleanup fix must be
validated before claiming that it resolves this exact timeout.

## Main comparison and environment limits

[Main run 40838551921](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40838551921)
at the exact reference SHA passed both 227-test browser suites and both 10-test
mission E2E suites. Its actual logs were downloaded, not inferred from a badge.

| Field | Ubuntu 22.04 main / C7 | Ubuntu 24.04 main / C7 |
|---|---|---|
| Runner image | both `20261025.340.1` | both `20261025.353.1` |
| Python | both 3.10.22 | both 3.12.15 |
| Node / npm | both 20.20.2 / 10.8.2 | both 20.20.2 / 10.8.2 |
| Playwright / Chromium | both 1.62.1 / 151.0.7922.34 | both 1.62.1 / 151.0.7922.34 |
| Dynamic Python drift | Pydantic 2.14.1→2.14.2, core 2.50.1→2.50.2, OpenTelemetry API 1.45.1→1.45.2 | same three changes |

The two browser tests mock their API in Node. The static server only uses Python
for a WebSocket origin-rejection probe; these two tests intercept WebSockets.
No evidence connects the Python package drift to their failures. A successful
main suite does not disprove the deterministic controller defect or a timing leak.

Local host is Ubuntu 24.04.5, Python 3.12.3, Node 20.20.2, npm 10.8.2,
Playwright 1.62.1, Chromium 151.0.7922.34. Python patch and host hardware differ
from GitHub; local runs are not advertised as identical hosted-runner images.
No Ubuntu 22.04 runtime/container is available locally. Its standalone replay is
**NOT_RUN**; original full-suite evidence is reported separately. No workflow
or shared test was edited to manufacture an environment-specific replay.

## Ownership and minimum follow-up

There is no CODEOWNERS file or authoritative role mapping for these shared paths.
Owners below identify the subsystem, not an invented C1/C2/C3/C4 assignment.
Relevant `git blame` authors are Hajoon Park; this report does not message them.

1. **Maps historical observation UI owner**:
   `robot_dashboard/static/features/maps/global_observation_contract.js`
   (`snapshot`, `poll`, `openHistorical`) and `global_observation.js` (:192–204),
   regression `tests/e2e/global_observation_history.spec.mjs:90`.
   Reproduce with the gate probe and original trace. Make polling-state changes
   observable and serialize an accepted explicit open behind an in-flight status
   read, rechecking map/source/generation and active-owner guards before opening.
   A blocked intent must remain explicit rather than disappearing. Do not remove
   those guards. Add a deterministic delayed-status overlap regression asserting
   one detail GET, the original missing-job error, cleared output, and no writes.
2. **Shared browser E2E fixture owner**:
   `tests/e2e/dashboard_backend.mjs:233–287` and
   `tests/e2e/live_observation.spec.mjs:81–97`.
   Reproduce with `socket_cleanup_probe.mjs`, then the original full suite.
   Own all camera/pointcloud/pose/joint intervals and reconnect timeouts in an
   idempotent disposer; call it on page/context teardown as well as socket close.
   Release callback references such as `state.emitPose`. Verify no callback/send
   occurs after context closure across successive tests. Then rerun the original
   #143 test and full suite on both Ubuntu images with unchanged timeouts.
3. **Settings layout / cockpit safety HUD owner**, if timeout persists after
   fixture cleanup: `robot_dashboard/static/features/settings/mount_calibration.js`
   and `.css`, `robot_dashboard/static/features/cockpit/safety_hud.js` and
   `safety_hud_view.js`, and associated CSS.
   Reproduce the original 1280×720 viewport and manual-point workflow, including
   the three condition checkboxes; use trace pointer-interception evidence.
   Preserve safety controls while making the calibration controls reachable.
   Do not use forced clicks or remove the results assertion as a workaround.

No shared source, shared test, timeout, assertion, byte bound, TTL, controller,
sensor policy or workflow is changed here. The C7 implementation and historical
performance JSON remain intact. Sensor-to-render latency stays **UNKNOWN**;
all follow-up execution is synthetic/offline, with no Jetson performance claim.

Commands, final local outcomes, and submission status are in `VALIDATION.md` and
`VALIDATION.json`; `ci-evidence/` contains the compact machine-readable records.
