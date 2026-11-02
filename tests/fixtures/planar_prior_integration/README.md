# Offline prior integration harness

This fixture exercises actual dashboard code against actual loopback ASGI routes. It is a software test with synthetic maps, observations, solver candidates, ownership, and service/runtime transport. It provides no device-state, physical stationarity, location accuracy, ROS, or Nav2 evidence.

## Execution layers

- `browser_probe.mjs`: actual preparation component and ASGI proposal/confirmation/stop routes. The component receives a synthetic draft getter; this mode does not exercise map drawing.
- `full_app_probe.mjs`: actual index.html, app.js, canvas pointer handling, staged draft, proposal, confirmation, observation stop, explicit mock Nav2 start, explicit draft re-confirmation or fresh redraw, INITIAL POSE and explicit matching. It reuses `tests/e2e/dashboard_backend.mjs` for unrelated dashboard HTTP/WebSockets.
- `mock_runtime.py`: synthetic Nav2 launch and INITIAL POSE/ROS receipt transport. The actual manager snapshots a bundle; actual `OperationalLocalizer.reseed`, `start_matching`, and receipt waiters enforce their software gates. Matching uses the actual operational ASGI route. The full navigation coordinator start route, ROS callbacks/publishers, Nav2 nodes/TF and registration convergence do not run. A match request accepted by this fixture is not successful map alignment.
- `retention_adapter.py`: calls the product worker's actual `_retained_candidate_metadata` on synthetic candidate arrays; it never constructs `operator_prior_resolution`. The actual product selector/coordinator creates that proof. Synthetic attempt IDs/FAILED_RANSAC padding and the injected `execution.worker_reaped`/source-pin envelope are trusted fixture inputs, **not** proof that an external solver ran, was reaped, or had its real files checked. `REVIEWED_HASHES` is a reviewed hash list, not a file-verification result. Truncation means deliberate synthetic candidate omission.
- `assertExecutorEvidence`: observes actual proposal.start thread/name/absence of a running loop and separate solver/ASGI thread IDs. `asyncio.to_thread` is never replaced. `assertExactStopReceipt` binds stop POST/session/start/nonce/dispatch to the actual observation session's receipt state. The stop service itself is synthetic.

## Pins and invocation

Set `PRIOR_SOURCE_ROOT`, `PRIOR_HASH_MANIFEST`, `PRIOR_RETENTION_ADAPTER`, `PRIOR_RETENTION_ADAPTER_SHA256`, `PRIOR_OUTPUT_DIR`, `PRIOR_RUN_LABEL`, and `PRIOR_CHROMIUM`. `PRIOR_NODE_ROOT` selects the existing Playwright dependency root separately from the pinned source. Use an existing Python environment with the project dependencies and existing Node/Chromium; do not install anything for this fixture.

The JSON source manifest contains `snapshot_id`, `complete_source_snapshot: true`, and a `files` object of relative paths and SHA-256 values. A Git checkout is checked against all tracked and nonignored untracked paths. A plain exact archive uses `snapshot_kind: "git-archive"`, checked against all files recursively. Keep bytecode/output outside that snapshot and set `PYTHONDONTWRITEBYTECODE=1`. Verify the source manifest again after every run; archive each run's harness files and environment pins separately.

The adapter entrypoint remains `attach_real_retention_evidence(result, context, *, variant)`. It additionally exports `SOURCE_PIN` and `SOURCE_PIN_SHA256` to configure the synthetic runner's trusted envelope. Only a reviewed adapter with an explicit hash may load. Freeze product and harness separately before final acceptance.

Start `fixture_server.py` on `127.0.0.1:4397` and run either probe. Runs must be serialized; preserve first failures and repaired executions under different labels. `PRIOR_CASE_FILTER` selects component cases. Set `PRIOR_REQUIRE_GROUPING=1` for the final explicit grouped-member contract: missing/unknown grouping policy fails closed and additional duplicate-group cases run. Legacy baseline runs omit it; do not use legacy-mode results as final grouped-contract evidence.

HTTP overrides validate the allowed origin, including late ASGI passthrough and response-mutation routes. The full app also installs a final origin-checking fallback before execution. The Python connect/subprocess wrappers are partial guards, not an operating-system network sandbox; browser internal traffic and every possible socket API are not certified blocked by this code. No fixture handler contacts a device. Use the separately authorized execution environment and do not interpret these guardrails as a general security boundary.

## Optional-bounds candidate — validation pending

The current probes target a UI draft with X/Y/yaw and explicit stationarity acknowledgement, without uncertainty inputs. They require `bounds`, `bounds_source` and `effective_bounds` to be absent from the UI request. The actual server proof must preserve that original prior and separately bind `server_policy` to effective limits of 0.25 m / 0.20 rad. `bounds_assertions.mjs` validates this provenance before current/group/handoff comparisons; an unchecked fallback to raw prior bounds is not accepted. Legacy proof without the new fields is supported only when the original prior explicitly contains valid bounds.

The component matrix adds missing/forged policy-proof cases and distinguishes two paths for a candidate about 0.3 m from the draft: the new bounds-free request is rejected by selection, while an explicit wide legacy API prior may produce an informational proposal but confirmation must still return 409. A dedicated synthetic `odom-drift-server-policy` input aligns a 0.18 m drift with the existing 0.08 m duplicate spacing, preserving the representative-inside/member-outside test under the 0.25 m server limit. No product limit, grouping threshold or source gate changes.

These adaptations have **not yet been executed** against the final backend/UI snapshot. C0 owns the final freeze and start signal; the historical passing results below apply only to their named earlier manifest. C1.3 will run the component matrix and full-app scenario once each on the same approved exact snapshot, preserving first failures. C0 owns broad Python/Node/static validation, including the helper assertions.

## Recorded frozen validation

On 2026-11-02, snapshot `C0-ACK-ENTRY-20261102-01` passed both probes with `PRIOR_REQUIRE_GROUPING=1`. Each probe ran once, sequentially, without source changes or retries:

| Probe | Result | Scope |
|---|---|---|
| `browser_probe.mjs` | **31 PASS / 0 FAIL**, exit 0 | Independent preparation component ↔ actual ASGI cases |
| `full_app_probe.mjs` | **PASS**, exit 0 | One full-app scenario: seven main stages plus one preserved-draft reconfirmation assertion; eight PASS entries |

All **2,325 source paths and their SHA-256 values** matched the common manifest before and after execution; the Git index contents and index-file bytes also remained unchanged. The manifest SHA-256 was `453be7cedad9eb5e703cfd320fc7cdcb4f29767eac7611ad2d27a7ff0c06e456`. Both per-run harness archives matched the pin. This documentation update follows that validation; the manifest identifies the tested snapshot, not these subsequently updated documents.

The full app exercised canvas drawing → actual prior proposal/proof → explicit confirmation and observation stop → mock Nav2 start → preserved draft remaining unconfirmed → explicit reconfirmation and SEND POSE → actual ASGI match acceptance. It used the preserved-draft path, with no fresh-redraw fallback. Proposal, confirmation, observation stop and match POSTs each occurred once; mock Nav2 start and mock INITIAL POSE each occurred once. No automatic INITIAL POSE or goal was sent; no goal was sent at all. The actual preparation readback reached `MATCH_ARMED`, while localizer `ready` remained false and `estimated_pose` remained null.

The later generic `/__fixture/result` collector reported `OUTCOME_UNKNOWN / HANDOFF_MATCH_CURRENT_UNCONFIRMED`: its `manager.status()` calls handoff status without a `RuntimeHealthSample`, so the current-match check fails closed. The preparation-inputs API separately supplies health and reported `MATCH_ARMED`. The same split exists in the earlier passing full-app artifact. These reads are non-atomic, and the mock synthesizes health freshness on reads; they do not establish sustained matching, operational readiness, a state deterioration, or registration convergence. Both readouts remain in the evidence.

The response-loss case now records and waits for lost-confirmation HTTP 503 → confirmed preparation HTTP 200 → injected preparation HTTP 503 consumed before reload → recovered HTTP 200. Structured readback checks bind the generation, handoff and session IDs and current `can_stop`; the applied-geometry assertion requires the positive prefix and cannot match the negative “없음” display. The case retains one confirmation and one explicit exact-session stop, without an automatic retry or forced click.

The full-app observer samples rendered controls from before the first acknowledgement check, every 100 ms, with a 200-sample cap and 512-character preview limit. It preserves the original two checks, one click and action timeout. The frozen run collected 21 samples and ended `CLICK_RESOLVED`: both acknowledgements remained checked across sampled invalid/expired previews, then cleared after submission handling. Sampling can miss shorter transitions and does not expose internal gate timing or prove the earlier timeout's cause.

The proof assertion uses the producer's deadline expression, `accepted < expiry && expiry <= accepted + 120`, with finite-value checks and no epsilon. Two regression cases cover subtraction rounding above 120 for a valid producer deadline and rejection of the next binary64 value above that deadline. The separately recorded helper run passed all seven cases; these are not added to the component count.

The grouped case preserved six retained entries, two eligible/matching raw members, and one matching hypothesis with member indices `[0, 1]`. The actual product generated the resolution proof and checked member geometry/current-pose evidence. A separate case kept the representative inside the prior while another member moved outside; confirmation returned HTTP 409. Original ambiguity true/false remained unchanged in the response and proof, with distinct UI wording. Confirmation payloads omitted client prior/proof, and exact-session stop receipts and actual executor thread separation were checked in both probe modes.

Earlier baseline failures and repairs remain separate evidence. In particular, a fixture result collector originally bypassed the API coordination lock and caused a lock inversion. Its thread stacks were preserved; result/context reads now use the same async coordination → actual `to_thread` boundary as the API. The expanded response-loss/readback/reload/explicit-stop case passed after that harness repair and in the frozen run. This does not establish a device incident or a defect in the serialized production HTTP path.

The earlier `C0-INTEGRATED-OFFLINE-20261102-01` snapshot covered 2,323 paths and separately passed 31 component cases and the full-app scenario; its manifest SHA-256 was `dabfc6ef7c15baa1d31155e7ea6a24bba92de6db039fd987a30719b09ae44bf9`. First failures from `ci-deadline-full-app-first` (confirmation-click timeout), `consent-final-component-first` (30 PASS / 1 FAIL, disabled-stop timeout), and `consent-final-full-app-first` (conditional-acknowledgement check failure) remain preserved under their original labels. The latest passing runs neither replace those artifacts nor establish every earlier failure's cause.

See [CASE_MATRIX.md](CASE_MATRIX.md) for the exact passing cases and untested layers. No hardware, ROS callback, actual Nav2/TF, external solver subprocess, registration convergence, or deployment result is claimed.
