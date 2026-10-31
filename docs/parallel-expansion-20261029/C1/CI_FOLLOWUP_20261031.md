# C1 follow-up: shared browser timeout, 2026-10-31 KST

**NO_PRODUCTION_SOURCE_CHANGE. Shared fixture lifetime defect reproduced;
the exact sufficient cause of the original timeout remains unproven.**

The existing C1 branch starts at `e0bc9cf8ba8bd22b406a287e1a9ef867a0cd367b`,
clean and equal to remote. Its [original CI 41024138006](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41024138006)
remains **FAILURE**, with no rerun requested. The previous successful C1 source
is `50600c7bce6f5fae743cd836ca1d8ee68d91b05a`
([CI 40846353053](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40846353053)).
The final chat receipt records this evidence-only submission's separate HEAD,
remote equality and completed CI; a new green run would not repair the defect.

The user retained C1-only ownership and prohibited shared CI/app changes.
This continuation changes C1 documentation/evidence only. The actual composition,
error propagation and D1/C2 compatibility from
[CURRENT_COMPOSITION_20261030.md](CURRENT_COMPOSITION_20261030.md) remain frozen.
No peer is repinned and no unavailable collision input is fabricated.

## Original failure and trace

Ubuntu 22.04 / Python 3.10 job `123958119303` failed test #103/227,
`tests/e2e/live_observation.spec.mjs:853`,
"course boundary manual drawing, save, reload and real seed payload preserve active observation".
The error is **Test timeout of 20000ms exceeded**, not a revision/error-code
assertion. Browser results are 226 PASS / 1 FAIL; mission fixture tests were
skipped after this failure. Ubuntu 24.04 passed 227 browser and 10 mission tests;
the offline integration job also passed. The overall run is still FAILURE.

[Artifact 12964220614](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41024138006/artifacts/12964220614)
has SHA-256 `10661e86aff19587ea5fba542364513ae793dc6ef3e29245e5adbe5ad2e1706e`.
The locally preserved ZIP matches this digest. Its trace contains **13,470**
`webSocketRoute.send: Target page, context or browser has been closed` errors:

| Original fixture location | Closed-target errors |
|---|---:|
| `dashboard_backend.mjs:265` camera | 3,977 |
| `dashboard_backend.mjs:280` camera | 3,977 |
| `dashboard_backend.mjs:244` pointcloud | 1,702 |
| `live_observation.spec.mjs:90` pose | 3,651 |
| `live_observation.spec.mjs:83` joints | 163 |

These are stale fixture activity from closed pages. Two footer pointer
interceptions are recorded at trace-relative 15,726.159 and 16,401.577 ms during
the saved-course reload interaction. The weight-change disabled-state assertion
starts at 19,706.136 ms and completes at 20,311.514 ms. Cancel, screenshots and
final assertions are subsequently recorded as completing without individual
assertion errors, ending around 21,219.502 ms. A later recorded assertion does
not override the runner's whole-test timeout. Trace clocks are preserved as
recorded, not treated as direct CPU or deadline measurements.

There is no host CPU profile or cleanup-fix A/B run. Timer activity, pointer
interception and elapsed time are observations; their relative contribution or
sufficiency is not established. This must not be labelled simply flaky or fixed.

## Controlled local comparison

The test, backend fixture, static server, Playwright configuration, package lock
and CI workflow have identical Git blobs at both C1 revisions. The tested
static assets are also unchanged in the C1 diff. This test uses the Node static
server and synthetic browser API/WebSocket fixtures; it does not mount C1's
`expansion_services` router. This identifies the exercised boundary, rather than
claiming that unchanged source cannot fail.

C7 diagnostics were exported read-only from
`ec724dafd33db92ecb27db17e0bdd2eee5a30455` and their Git blobs verified before
and after execution. They import the target checkout's actual shared fixture.
No C7 source was copied into C1 or modified.

| C7 diagnostic | Exact Git blob |
|---|---|
| `socket_cleanup_probe.mjs` | `174c568e5b6419ec1638bd0af8cc1a2ce99992d8` |
| `summarize_original_traces.py` | `c4aa1988986250504fe2bf56ecb863c55a57a48e` |

Both are under `experiments/expansion_20261030/c7_capacity/ci/` in C7.

| Local run | Previous `50600c7…` | Current `e0bc9cf…` |
|---|---|---|
| Actual context-close diagnostic, three rounds | REPRODUCED_SHARED_FIXTURE_TIMER_LEAK | REPRODUCED_SHARED_FIXTURE_TIMER_LEAK |
| Socket-close callbacks | 0 / 0 / 0 | 0 / 0 / 0 |
| Intervals retained after successive context closes | 1 / 2 / 3 | 1 / 2 / 3 |
| Further callbacks in successive 300 ms windows | 2 / 5 / 8 | 2 / 5 / 8 |
| Original test alone, unchanged 20 s timeout, zero retry | PASS, 4,927 ms | PASS, 5,024 ms |

The diagnostic clears its observed timers in `finally`; that local cleanup does
not change the shared suite. Single-test success is distinct from the original
227-test sequence and does not turn its failure into a pass. No repeated tuning
or full-suite browser run was used to seek a green result locally.

Local environment: Ubuntu 24.04.5, Node 20.20.2, npm 10.8.2, Python 3.12.3,
Playwright 1.62.1, Chromium 151.0.7922.34. **Ubuntu 22.04 standalone: NOT_RUN**;
this host is not the GitHub runner image. Initial sandbox execution could not
launch Chromium; the same diagnostic ran with host permission afterward.
Every socket in the diagnostic is intercepted in memory; no robot is contacted.

## Concrete shared-owner change and acceptance

The remaining change belongs to the **shared browser fixture owner**, not a
fabricated C1/C2/C3 role assignment. No message has been sent to another owner.
The proposed limited change is:

1. In `tests/e2e/dashboard_backend.mjs:233–287`, give each intercepted socket an
   idempotent timer disposer. Track both camera/pointcloud intervals and the
   reconnect timeout. Invoke it on socket close and independently on page/context
   teardown; remove the teardown listeners when disposed. Preserve close counters
   as socket-event evidence instead of synthesizing them during page disposal.
2. In `tests/e2e/live_observation.spec.mjs:81–97`, apply the same lifecycle to
   pose/joint intervals, and release `state.emitPose` only when it still refers
   to that socket's sender. Preserve input cadence, stamps and assertions.
3. Run the same actual-context diagnostic after the fix: after each close,
   retained intervals and further callbacks must both be zero. Cover reconnect
   timeout cleanup too. Then run the unchanged failing course test and the whole
   browser suite on both original Ubuntu images with the existing 20 s timeout.
   If timeout remains, investigate footer interception separately, retaining
   the safety HUD and ordinary click semantics.

This is a reviewable change proposal, not an applied or validated fix. Applying
it requires the shared owner's work or explicit expansion of the user's C1-only
scope. Do not increase timeouts, force clicks, remove assertions or silently
retry to call the original failure resolved.

## Evidence and reproduction

Compact receipts are in [ci-followup-20261031/validation.json](ci-followup-20261031/validation.json),
with the original trace summary, course-action timeline, exact source comparison
and before/after context-close observations alongside it. Raw original ZIP and
local traces remain under `/tmp/c1-e0bc9cf-ubuntu22-browser.zip` and
`/tmp/c1-ci-followup-20261031/`; they are not committed.

With an independent checkout at each exact C1 SHA and its lockfile dependencies:

```sh
# Export these two C7 files with git show at the SHA above, verify git hash-object,
# and chmod 0444 before running them. Do not use a moving C7 checkout.
python3 /absolute/readonly-c7/summarize_original_traces.py /absolute/original.zip
PLAYWRIGHT_BROWSERS_PATH=/path/to/chromium-1234 \
  node /absolute/readonly-c7/socket_cleanup_probe.mjs /absolute/c1-checkout
# Run each target once, sequentially, with Node 20 on PATH:
node node_modules/@playwright/test/cli.js test \
  tests/e2e/live_observation.spec.mjs:853 --reporter=json --trace=on \
  --output=/absolute/separate-output-directory
```

Full Python/JS and static/security results before this evidence commit are
recorded in `validation.json`. The final chat distinguishes its new CI from
the retained original failure. ROS/native, product composition rendering,
measured inputs and robot execution are not expanded by this diagnostic work.
No main merge, deployment, shared app connection, goal, TF or control occurred.
