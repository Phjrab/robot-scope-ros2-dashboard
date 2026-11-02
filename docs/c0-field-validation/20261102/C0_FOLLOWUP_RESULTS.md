# C0 deadline and proposal-consent follow-up

Result ID: `C0-ACK-ENTRY-20261102-01`

Current work order and completion criteria: [C0 remaining-work checklist](../C0_REMAINING_WORK.md). Device versions and statuses below are historical observations from this report's own checkpoint.

This follow-up preserves the first published CI failure and the later full-app failure, then validates a separate repaired snapshot. Hardware, deployment and physical-navigation readiness are outside this result.

## First published CI

Commit `8d22fada23c60fa86e47d3fd24f0e9af57432b82`, run `41370328845`, attempt 1: FAILURE. Ubuntu 22.04/Python 3.10 passed Python 3,397 cases with 2 optional skips, Node 738, browser 307 and a separate mission API browser set of 10. Ubuntu 24.04/Python 3.12 had 3,396 Python passes, 1 error and 2 skips; Node/browser were skipped after that error. Competition offline checks passed. The original run was not rerun.

The Ubuntu 24.04 error was `INITIAL_GEOMETRY_PROVENANCE_REQUIRED` in handoff validation. The actual timestamp operands were not logged, so the exact CI cause remains unconfirmed. A deterministic same-path counterexample showed that subtracting accepted time from its generated expiry can round above the TTL. The repair checks the same producer expression, `accepted < expiry <= accepted + TTL`, without epsilon or changed TTL. The next representable value beyond the bound, invalid/future values and existing prior bounds remain rejected. Backend, UI and harness comparisons now agree.

## Preserved intermediate failure

The separate deadline snapshot contained 2,325 files. Python 3,400 PASS / 2 optional SKIP, Node 739 PASS, helper assertions 7 PASS, preparation browser file 63 PASS, actual ASGI component 31 PASS and static checks passed. Its first full-app run failed at confirmation click actionability after the first three stages. Proposal POST 1; confirmation, stop and match POST 0. Confirmation through matching were not reached. The source files remained unchanged during those runs.

A separate browser experiment reproduced explicit conditional consent being cleared when the same proposal briefly exceeded display freshness. This is not proof that it caused the intermediate full-app timeout. The UI now preserves only an explicitly checked consent bound to the same proposal, map, calibration, source, draft and proof; confirmation still requires fresh evidence and all existing gates. Invalid context or proof clears consent. No automatic check, confirmation, shortened polling or longer timeout was added.

Independent review found a second issue in the first consent candidate: old proof bindings survived a new explicit calculation. Two browser failures were preserved. New requests now clear prior bindings and prior checks, while proof changes within one request remain invalidating and old replies remain fenced. Related repaired cases passed 8 plus a separate RUNNING-to-READY case. The superseded consent snapshot was captured but its integrated checks were not started.

The full-app harness now samples checkbox, disabled and CSS/size visibility state around its original click every 100 ms, bounded to 200 samples. It changes neither clicks nor consent. Sampling can miss shorter transitions and is not proof of Playwright actionability or internal gate state.

## Consent integration first outcomes and follow-up

The next 2,325-file snapshot passed Node 739, helper assertions 7, preparation browser 76 and static checks. Its actual ASGI component run completed all 31 cases: 30 PASS / 1 FAIL. The failing response-loss/status-failure case timed out on observation stop after an HTTP 503 left no current observation snapshot. The full-app run passed three stages and failed while explicitly checking conditional consent, before any confirmation POST. Its DOM sampler was not started because sampling began after the two checks. Original evidence and unchanged before/after source hashes are preserved.

A controlled browser experiment then reproduced freshness expiring between pointer click and the change handler: the checkbox was reverted even though the immutable proof remained valid. The repair permits explicit consent against the same validated proof during a freshness gap; confirmation and geometry preview retain strict freshness checks. The before/after reproduction failed/passed once, and nine separate related cases passed. These results do not establish the precise timing of either earlier full-app failure.

The failed component used a one-shot preparation HTTP 503 injection without waiting for the previous refresh to finish or proving that the injected response had been consumed. Recorded request order differed from the earlier passing run; the failure remained until the reload read. Its recovery text assertion also matched the negative “no applied values” message. The harness now waits for confirmed readback, observes the injected 503 and UI error before reload, and verifies current matching generation/session/handoff and can_stop after reload. Positive geometry assertions exclude the negative text. A private targeted run passed once with one confirmation and one stop; no product stop gate was changed. This targeted run also used the updated acknowledgement product, so it is not an isolated same-product causal A/B experiment.

## Final frozen validation

Snapshot `C0-ACK-ENTRY-20261102-01` contains 2,325 files. Complete before/after file hashes matched. Manifest SHA-256: `453be7cedad9eb5e703cfd320fc7cdcb4f29767eac7611ad2d27a7ff0c06e456`.

| Check | Result | Scope |
| --- | --- | --- |
| Python discovery | 3,400 PASS / 2 optional SKIP | Earlier deadline snapshot; all Python files and dependencies unchanged afterward |
| Node / helper assertions | 739 PASS / 7 PASS | Separate root test and harness assertion invocations |
| Ruff / mypy / syntax / secret scan / diff | PASS | Existing static scope; mypy 4 files; frontend syntax 114 modules |
| Preparation browser file | 79 PASS / 0 FAIL | One run of the full affected file, not all browser files |
| Actual ASGI component | 31 PASS / 0 FAIL | One run after reviewed fixture synchronization repair |
| Full application flow assertions | 8 PASS | Seven main stages plus explicit preserved-draft reconfirmation |

The final full-app run issued one proposal, one geometry confirmation, one exact observation stop, one mock Nav2 start, one explicit INITIAL POSE and one match request. No goal was sent. DOM sampling collected 21 records, with both explicitly selected acknowledgements retained through stale-disabled intervals and a later successful click. The sampler had no recorded read/marker error, but its timing and coverage limitations remain.

The path reached `MATCH_ARMED`; the final separate evidence read was `OUTCOME_UNKNOWN` / `HANDOFF_MATCH_CURRENT_UNCONFIRMED`. Those are distinct observations. The run proves the exercised request/receipt path, not persistent matching, a ready localizer or navigation readiness. Sensors, solver execution, Nav2 launch and ROS transport were synthetic. Real ROS/TF, registration convergence, external solver/process lifetime, physical stationarity and position accuracy remain untested. The terminal uncertainty is retained rather than replaced by the earlier successful step assertion. Read-only backend analysis found that the diagnostic result collector calls manager status without a current health sample, which intentionally returns this unknown state after matching is armed; the preceding preparation read supplies a fresh synthetic health sample and can return MATCH_ARMED. Existing tests explicitly expect both responses. The reads are not atomic, and mock health synthesizes freshness on each read. This explains the distinct code paths without proving sustained real sensor health or identifying an additional product defect.

## Publication

Each role committed its own changes in sequence:

| Owner | Commit | Scope |
| --- | --- | --- |
| C1.1 | `0e304b66a944bc0e10fa0dce28a686b11198acb1` | Backend deadline comparison and strict boundary tests |
| C1.2 | `7c20b4b546d4b9b5458c070ce85cc853f057cf63` | UI deadline, explicit consent continuity/recalculation and browser regression cases |
| C1.3 | `a41b27977f4aa89bc0d2fcd32ff565b3e7403f1f` | Strict deadline assertion, synchronized failure/recovery verification and bounded DOM diagnostics |
| C1.4 | `37d2723cd6ad3f234f358776fa7e769ff846a9f1` | Independent follow-up review and limits |
| C0 | This report's commit | Combined results, historical report correction and remaining work |

At this report's commit, publication and the new exact-SHA CI result are pending. The resulting SHA and CI outcome will be recorded in its GitHub commit comment; the failed `8d22fada` run remains unchanged and is not rerun. Passing local checks do not establish the new CI result, deployment readiness or hardware behavior.

## Hardware and deployment boundary

No device access, deployment, live observation, live Nav2, INITIAL POSE, goal or movement occurred in this follow-up. The last recorded deployed source is historical `f50989a37b0203634f8dccefc4d149edafe0eadc`; current device base is unverified. Existing maps, calibration, sensor/drive settings, policy gates and expansion branches were not changed.

The historical deployment helper is pinned to an older base and restarts only the dashboard. A current-base procedure must verify and back up both dashboard and bridge code/processes, authenticated protocol and protected assets. Unknown observation stop or inhibition retains the hold; a bridge restart is not automatic recovery. Current field conditions, ownership and a concrete stationary/recovery window are required before device work. Physical P1/P2 stop/dwell, green-button departure, ramp continuity, actual Nav2/TF application and visualization remain separate unverified work.
