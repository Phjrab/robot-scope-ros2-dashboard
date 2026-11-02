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

## Recorded frozen validation

On 2026-11-02, snapshot `C0-INTEGRATED-OFFLINE-20261102-01` passed both probes with `PRIOR_REQUIRE_GROUPING=1`. Each probe ran once, sequentially, without source changes or retries:

| Probe | Result | Scope |
|---|---|---|
| `browser_probe.mjs` | **31 PASS / 0 FAIL**, exit 0 | Independent preparation component ↔ actual ASGI cases |
| `full_app_probe.mjs` | **PASS**, exit 0 | One full-app scenario: seven stages, including the additional preserved-draft reconfirmation assertion |

All **2,323 source paths and their SHA-256 values** matched the common manifest before and after execution; the Git index contents also remained unchanged. The manifest SHA-256 was `dabfc6ef7c15baa1d31155e7ea6a24bba92de6db039fd987a30719b09ae44bf9`. This documentation update follows that validation; the historical manifest identifies the tested snapshot, not these subsequently updated documents.

The full app exercised canvas drawing → actual prior proposal/proof → explicit confirmation and observation stop → mock Nav2 start → preserved draft remaining unconfirmed → explicit reconfirmation and SEND POSE → actual ASGI match acceptance. It used the preserved-draft path, with no fresh-redraw fallback. No automatic INITIAL POSE or goal was sent; no goal was sent at all. The actual preparation readback reached `MATCH_ARMED`, while localizer `ready` remained false and `estimated_pose` remained null. This establishes explicit match arming, not registration convergence.

The grouped case preserved six retained entries, two eligible/matching raw members, and one matching hypothesis with member indices `[0, 1]`. The actual product generated the resolution proof and checked member geometry/current-pose evidence. A separate case kept the representative inside the prior while another member moved outside; confirmation returned HTTP 409. Original ambiguity true/false remained unchanged in the response and proof, with distinct UI wording. Confirmation payloads omitted client prior/proof, and exact-session stop receipts and actual executor thread separation were checked in both probe modes.

Earlier baseline failures and repairs remain separate evidence. In particular, a fixture result collector originally bypassed the API coordination lock and caused a lock inversion. Its thread stacks were preserved; result/context reads now use the same async coordination → actual `to_thread` boundary as the API. The expanded response-loss/readback/reload/explicit-stop case passed after that harness repair and in the frozen run. This does not establish a device incident or a defect in the serialized production HTTP path.

See [CASE_MATRIX.md](CASE_MATRIX.md) for the exact passing cases and untested layers. No hardware, ROS callback, actual Nav2/TF, external solver subprocess, registration convergence, or deployment result is claimed.
