# C0 preparation and active-bridge integration

Result ID: `C0-INTEGRATED-OFFLINE-20261102-01`

This report records the first offline integration snapshot for an operator draft before sensor preparation and guarded observation while the control bridge remains running. Its published commit `8d22fada23c60fa86e47d3fd24f0e9af57432b82` later failed CI as described below. Subsequent repairs and validation belong to separate snapshots. No result here establishes a current robot pose, successful map match or readiness for physical navigation. Deployment and hardware validation remain separate.

Subsequent fixes and frozen results are recorded in [C0 follow-up results](C0_FOLLOWUP_RESULTS.md).

## Behavior

1. Connect the selected 3D localization and 2D navigation maps and draw a position/direction draft. This draft narrows the sensor-based initialization proposal; drawing or restoring it sends no INITIAL POSE or goal.
2. Acquire fresh stationary observation evidence, calculate the proposal, inspect height/roll/pitch and source/quality evidence, and explicitly confirm eligible geometry. A prior supplies neither missing sensor measurements nor permission to ignore ambiguity or quality gates.
3. Start Nav2 with the existing control and verify its nodes/TF. First stop the exact observation session and satisfy its handoff conditions.
4. Reconfirm the preserved draft after runtime changes or draw a new one, explicitly SEND POSE, verify the matching receipt, then separately start stored-map matching. The display combines INITIAL POSE and matching in stage 4; restoring the draft triggers neither action.
5. Inspect the current estimate, correction count, freshness, residual/overlap and runtime application evidence. Residual/overlap is not physical position accuracy.
6. Send a goal only after the existing readiness and safety gates permit it.

The preparation panel retains text links to existing Nav2, INITIAL POSE and goal controls. Two expected handoff transition states preserve the draft as stale and unsendable; map, calibration, pair-generation changes and other invalid conditions invalidate it. Visibility/blur draft handling cannot prevent the existing disarm and camera cleanup listeners from running.

## Active bridge and exact stop

An active bridge is eligible only when its current authenticated identity, invocation and status are valid, ownership is clear, and command/action/lease gates are satisfied. Observation obtains an acknowledged inhibition token before starting. Transport and bridge core reject drive/action requests while that token is retained; normal stop and emergency-stop paths remain available.

Source/identity/epoch changes or stale bridge status invalidate the observation. Releasing inhibition requires accepted stop dispatch for the exact observation session, confirmed inactivity with no pending job, and the matching release acknowledgement. Natural service exit or an unacknowledged stop does not establish that receipt. `OBSERVATION_STOP_ACCEPTANCE_UNCONFIRMED` keeps the hold and identifies the need for independently verified recovery; no timeout automatically re-enables motion.

The imported bridge candidate was reviewed and rebased onto `06bd98ba279e149bfecfd91007d65002d83e30b0`. C0 additionally repaired the exact-stop acceptance gap. Candidate patch SHA-256: `db898d848dbfe11f3e6691063947049dadb2e6113cd786878ad6f886ecb13155`.

## Conditional hypothesis policy

The selector verifies the pinned backend's existing full SE(3) duplicate relation and first-representative ordering. It does not introduce a new XY/yaw-only grouping rule, threshold or best-residual shortcut. Original candidates, digest and ambiguity remain intact. Raw candidate counts and verified hypothesis counts are separate, and member height/tilt differences remain visible.

Every matching member must satisfy the operator prior. Confirmation checks all members against one fresh, owner-validated current pose sample; normal forward timestamp progress is permitted, while stale/reversed/source-invalid evidence is rejected. Existing handoff bounds, TTL, one-use constraints, stop receipts and explicit pose requirements remain in force. A retained conditional group is not proof of global uniqueness or physical accuracy.

## Frozen validation

The first combined snapshot contained 2,323 files. Complete file sets and SHA-256 values were unchanged across the C0 checks and the independent ASGI/UI runs. Manifest SHA-256: `dabfc6ef7c15baa1d31155e7ea6a24bba92de6db039fd987a30719b09ae44bf9`.

| Check | First result | Scope |
| --- | --- | --- |
| Python discovery | 3,397 PASS / 2 optional SKIP | 3,399 cases; optional SVG plotting and rosbags dependencies absent |
| Node tests | 738 PASS / 0 FAIL | Full root JavaScript test set |
| Ruff / mypy / syntax / tracked-secret scan / diff check | PASS | CI static scope; mypy 4 files; frontend syntax 114 modules |
| Related browser suite | 89 PASS / 3 FAIL | All 92 requested cases executed before repair |
| Actual ASGI/preparation component | 31 PASS / 0 FAIL | One final run with grouping assertions required |
| Full application flow | PASS | Canvas draft, proposal, explicit confirm/stop, mock Nav2, preserved-draft reconfirmation, explicit pose receipt, matching arm |

The three browser failures concerned old stage-one completion/current-step expectations without a draft and an obsolete stage-one label. The original logs, screenshots and traces are retained. A test-only repair explicitly checks missing draft → stage 1 needs input → context-bound draft with bounds/acknowledgement → stage 2, preserving the existing invalidation, recovery and pending-action checks. The three repaired cases passed once; the complete affected file then passed all 61 cases once. These are separate runs, not a claimed new 92-case run. All 406 product files in the test copy and integrated tree matched the frozen snapshot. Final test file SHA-256: `dbcc3112548e2edd4cc029b99006f7db03e27ac481370bf3b04432e9160985f0`. Before publication of `8d22fada`, only this browser test and documentation changed after that frozen validation; full Python/Node and ASGI/UI checks were not redundantly repeated.

The full-app terminal state is `MATCH_ARMED`; the localizer remains not ready with no estimated pose. No automatic INITIAL POSE and no goal were sent. The actual ASGI coordinator/manager, selector, localizer reseed/start and receipt waiters were exercised. Sensor samples, solver candidates/execution, Nav2 launch, ROS receipt transport, map pixels and dashboard transport were synthetic. Metadata envelope/worker-reaped fixture inputs do not prove external solver execution, process reaping or source-file verification. No actual ROS/TF, registration convergence, robot stationarity or hardware accuracy was tested. Origin routing guards are not an OS-wide network-isolation proof.

## Preserved failures and repair boundaries

- The previous published checkpoint `06bd98b` and its CI run `41304523565` failed two Node source-order assertions on both OS jobs; browser jobs were skipped after that failure. The safety listener repair passed that snapshot's Node set. The older failure was not rerun or relabeled.
- An exact-stop synthetic counterexample failed twice before C0 repaired inhibition release. The corrected bridge cases preserve the hold when stop acceptance is unknown.
- A grouped-candidate counterexample exposed representative-only current-pose checking. Confirmation now checks every member. A later timestamp-equality check was corrected to allow a fresh forward sample without allowing stale or reversed evidence.
- A full-app test exposed draft loss in expected handoff transition states. The UI now preserves it as stale, requiring explicit reconfirmation and separate transmission.
- Confirmation-loss recovery initially deadlocked the integration fixture because its diagnostic endpoint bypassed the product API coordination lock. The fixture boundary was repaired; this is not an established cause of any historical field failure.
- An independent concern about mutation of private proof memory was withdrawn as an API defect: strict request validation, server-owned recomputation and copied readbacks prevent the demonstrated client-injection path. This does not claim immunity to arbitrary trusted-memory corruption.

## Publication and hardware status

Role-owned commits were serialized, with each role committing its own work:

| Owner | Commit | Change |
| --- | --- | --- |
| C0 | `0ba895b7a78e39d52b03f2878aaf0f7b08fde11a` | Reviewed bridge integration and exact-stop repair |
| C1.1 | `6b6c9e2800d3b446ef6dda3daadba933da2b009a` | Verified duplicate groups and fresh all-member confirmation |
| C1.2 | `f7bae0121d7a8ad625444b12b9694aa8f152c047` | Draft lifecycle, safety listeners, proof display and browser expectation repair |
| C1.3 | `19138b32cdfb5213bbbc586f07827c00217ffe8f` | Actual ASGI/full-app synthetic harness and results |
| C1.4 | `b7d1b1814cabb3e28ab809e8dde34b7099fa63fd` | Independent review |
| C0 | `8d22fada23c60fa86e47d3fd24f0e9af57432b82` | First integrated validation report and remaining field/deployment limits |

Intermediate commits are not independently represented as fully validated releases. The first integration's published SHA was `8d22fada23c60fa86e47d3fd24f0e9af57432b82`. Its first CI run `41370328845` failed on Ubuntu 24.04/Python 3.12 with one handoff-provenance error; subsequent Node/browser checks on that OS were skipped. Ubuntu 22.04/Python 3.10 passed, including 307 browser cases and 10 separate mission API cases. Competition offline checks passed. The failure and limits were recorded in commit comment `207679682`. No CI rerun was requested. Later candidate results do not replace this first failure or validate this exact SHA retroactively.

No device access, deployment, sensor observation, live Nav2 start, INITIAL POSE, goal or physical movement occurred during this offline integration. The last recorded deployed source was `f50989a37b0203634f8dccefc4d149edafe0eadc`; this is historical evidence, not a current base check. Maps, calibration, sensor/drive settings and policy gates were not changed on the device. No expansion branches were integrated.

The next field operation requires a current read-only base/protection/ownership check and a newly confirmed stationary/recovery window. Use the established backup/release procedure only if its expected base matches current evidence; otherwise prepare a matching procedure before deployment. Keep the previous verified release and protected assets available for recovery. Any uncertain observation stop retains inhibition until independently verified recovery. Physical P1/P2 travel, stop/dwell, green-button departure, ramp continuity and current robot/goal visualization remain to be validated in their own dependency order and explicit trial scope.

The offline deployment review found a concrete limitation: the previous deployment helper restarts and verifies the dashboard, not a newly loaded control-bridge process, and is pinned to a different historical base. It must not be reused for this candidate. A matching plan must account for both processes, their actual import/release paths and hashes, separate bridge restart/recovery, authenticated protocol status and acknowledgement. The optional path-derived `release_commit` field alone is neither required protocol support nor proof of loaded source. Unknown bridge identity or inhibition state must not be replaced with inferred values. This plan requires current read-only evidence before it can become executable.
