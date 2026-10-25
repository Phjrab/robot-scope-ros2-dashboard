# C1 Round 3 — first receipt, bounded observations, executable offline signal path

Date: 2026-10-25 KST. Branch: `review/20261024-c1-integration-r2`.
Work started at `765622ecbe20dd29b40296dd2ad24fa508ac9443` (clean independent clone).
This is incremental software integration. No main ref change, PR, robot access,
service change, deployment or physical motion was performed.

## Adopted deltas and preserved evidence

| Source | Previously adopted → reviewed target | Integration |
| --- | --- | --- |
| main | `7ef47dc249e4dba83865e78dc283f40013ea92de` → `104692fa0070ef085eee918913ea05fdb2d88c05` | Automatic initial estimate proposals and deployment records preserved as patches; main ref untouched |
| L1 | main `104692f` → `5339e3b5c9906991e08766b61bd27d92e725aa6f` | Branch exists; reviewed connection-loss distinction and proposal-input reset adopted |
| C2 | `efc2df6bfaad8f0032fee758b12e250435ffc71c` → `ae52d9899c743221c88c9e0e1bab2a4a543103eb` → `135da05adb9206f13505ef63cfd5710f4dde7fb4` | Exact corrective code adopted; C2-owned source files are byte-identical |
| C4 | `e2e9c5087767f3953d715c61e76388e4769d34b4` → `380800ca9e211495769fe60ee8221e3f4fb40f16` | First receipt / explicit age / identity contract, diagnostics and tests adopted |
| C3 | `d0231311c41c9dcb81df35d7138cf11207be49c9` → `16c63e08be5a7c10887e9e05cae94e94788e990f` | Reviewed native eight-trial evidence and offline source/tests adopted |
| D0 | `6403aab3afef96efa778b5265afd7ce5b351265c` → reviewed `b1561bfc23c7935dcd61cb08605fde4e4b4f0a91`; observed newer `69789d3cadded006dfc303e65e57f61941753214` | Read-only optional experiments. Original traffic/avoidance/integration source unchanged; no source/evidence rebinding required |

Only old-to-new diffs were applied. C2 merge conflicts were receipt-field migration,
native-owner port plumbing and source-supported dwell. The correction from the C2
owner supersedes temporary merge resolutions. Prior STOP fencing, operator pause,
shared coordination lock, durable `native_required` restart marker and two-leg
ownership remain intact. C1 owns session/ingress/worker/shared service/UI/CI changes.

RPP is the next integration baseline. This does not replace production controller
configuration or repeat native Nav2 trials. C3's MPPI diagnostic 65-second timeout
remains a failed diagnostic. D0 open-layout/animation/progress results are not
promoted to strict-narrow success. Original `map_transform=null` and unverified
field dimensions remain unchanged. Different D0/C3 revisions are not ranked.
Historical evidence manifests/hashes were not overwritten. The optional D0
videos, compressed traces and new collision experiment were not copied into this
signal-path submission.

## Time and ownership contract

C4 produces `first_received_s`, `source_age_at_first_receipt_s`, `processed_s` and
`identity_verified`. C1 checks frame/context/source/config/signal/crossing binding;
C4 projection receives the original first receipt. C2 join uses explicit first
age and checks any legacy completed-age fields for consistency. Processing or
polling never refreshes the receipt or adds the inference residence twice.
Receiver-clock identity is local and pinned; no cross-host monotonic subtraction.
Old-only context is rejected rather than guessed. TTL remains 0.25 seconds.

The session now calls actual `NativeRuntime.receive/tick/start/stop/cleanup`.
C2 remains the sole action owner. C1's coordinator uses the C2 public continuation
and command-context checks. After awaited planning, coordinator rechecks the same
owner guard immediately before goal submission. STOP retires the single gate and
fences the coordinator before durable IO can await. Operator pause cannot be
consumed as an approach cancellation. D0 lifecycle is comparison evidence only.

Cross tests import actual C4 pipeline/Observation/projection and C2 join/runtime
with C1 session. Only detector inference and physical boundaries use explicit
synthetic fixtures. Covered: positive inference + queue latency, identical image
bytes on new verified frames, repeated source stamp, unknown/unverified clock,
FIRST_RECEIPT_MISMATCH, conflicting legacy age, stale GREEN, duplicate polling,
epoch replacement and different crossing association.

## Observation retention and durable effects

Pure observation/health ticks no longer call the service request transaction.
The session keeps one latest packet and at most 64 recent transport-ID hashes.
C2's bounded per-component producer/epoch/sequence high-water remains the replay
boundary after transport cache eviction. Exact duplicate packets are health ticks
and cannot renew freshness. A process restart recovers no GREEN, dwell, RELEASE,
command or executable native owner. Reads/reconnects do not create runs.

Start/stop remain durable user intents. Each goal, cancel and constraint intent
and result crosses the existing service transaction before the port effect.
Uncertain intent receipts are not replayed. HOLD/cancel remain fail-closed even
when audit storage is unavailable. No background write can overtake an effect.
Pure ticks do not deepcopy/write the whole store or copy the normalizer. Packet
freezing and bounded input fingerprints are local; durable effects still perform
synchronous write-before-effect persistence.

Retention policy remains 64 definitions, 32 historical runs, 256 durable intent
receipts; no blanket clear or automatic active-ledger eviction. Explicit deletion
of an idle definition preserves run history. A genuinely full intent/history
store requires explicit operator archival. Raising limits is not the solution.

Endurance test: 1,200 inputs at 10 Hz virtual cadence (120 seconds), 1,200 duplicate
packets with reconnect reads, zero store writes during pure RED observation;
approach and exit issued exactly once. Full-ledger and write-failure tests retain
STOP while blocking new goals. This is software longevity evidence, not a
real-time or physical braking certification.

## Browser reproduction

Use the existing dedicated fixture server; no production activation endpoint was
added. The fixture binds only `127.0.0.1` and has no robot adapter.

```bash
# Existing Python/Node environment; optional competition dependencies are required.
PYTHONPATH=.:tests python3 tests/competition_fixture_server.py
# Open http://127.0.0.1:4187/?offline_signal=1#missions
# Select GREEN, RED, UNKNOWN or delayed-plan; click the explicit offline start.
```

The existing mission screen shows OFFLINE SYNTHETIC, source/mode, phase, last
observation time, raw/stable signal, blocked reason, separate feet/stop evidence,
goal count, movement evidence and phase history. Browser refresh is read-only.
The simulation sends actual C4 observations through C2 join/runtime and C1 session.
Approach terminal → HOLD ACK → independent feet + STOP for >=2 seconds → GREEN →
exit goal → independent simulated motion → completion. RED/UNKNOWN remain held.
STOP during delayed planning prevents a second goal. No fixture is labeled LIVE.

```bash
PYTHONPATH=.:tests python3 -m unittest discover -s tests/competition_integration -t tests -v
PYTHONPATH=.:tests python3 -m unittest discover -s tests/competition_native -t tests -v
PYTHONPATH=.:tests python3 -m unittest discover -s tests/competition_traffic -t tests -v
python3 -m unittest discover -s experiments/competition_nav2/tests -v
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 -m ruff check robot_dashboard scripts
python3 -m mypy --config-file mypy.ini
python3 scripts/check_repository_secrets.py
npx playwright test --reporter=line
npx playwright test -c playwright.competition.config.mjs
```

## Submission validation

Functional commit: [`bb6f42ae987bb15805bbcbb15e1ddbc4be458c6c`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/bb6f42ae987bb15805bbcbb15e1ddbc4be458c6c).
Exact code CI: [40163680026](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40163680026),
head `bb6f42ae987bb15805bbcbb15e1ddbc4be458c6c`. This is the actual submitted
run, not the earlier r2 run. Its live result is available at that link; the exact
final report-commit CI outcome is also reported in the submission response.
The report-only commit does not rewrite this document to contain its own SHA.

Local candidate results:

| Actual command group | Result |
| --- | --- |
| `unittest discover -s tests -v` (Python 3.12.3, `PYTHONPATH=.:tests C2_CROSS_REQUIRED=1`) | 2,924 run, 2,921 pass, 3 explicit skips; 96.583 s |
| Explicit Node geometry parity rerun | 1 pass; Node-path skip resolved |
| C1 actual package integration | 38 pass, including 1,200 virtual ticks + 1,200 duplicate/reconnect inputs |
| C2 dedicated + pinned historical cross tests | 108 pass; includes preserved C1 start fence |
| C4 dedicated tests | 69 pass |
| C3 offline tests | 43 pass; no new native trial |
| `node --test tests/*.mjs` (Node 20.20.2) | 666 pass |
| Common Chromium E2E | 198 pass, 7.4 min |
| Dedicated mission real-API Chromium E2E | 9 pass, 39.1 s; actual C4 projection/C2 join in the final demo |
| Ruff / mypy / frontend syntax / tracked secret scan / pip check / diff check | PASS; mypy 4 files, frontend 107 modules |

The remaining two local skips are optional SVG plotting and rosbags backend,
not signal-path tests. The initial full run did not have Node on PATH; its one
geometry parity skip was rerun explicitly with `PCD_EDIT_NODE` set to the already
installed Node binary. An earlier sandboxed Node run only reported file wrappers;
the 666 count above is the actual unsandboxed individual-test result. Initial
component failures during migration were fixed before these candidate checks.

C2 final remote report head is `8a58370be8562a8f40377ab659ee3f7776fe5200`;
its only delta after adopted `135da05` is [C2 ROUND3](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/8a58370be8562a8f40377ab659ee3f7776fe5200/docs/parallel-review/20261024/C2/ROUND3.md).
Remote ancestry was verified. C1 separately verified/adopted L1 `5339e3b`;
C2's report-time statement about not finding L1 does not replace C1's check.

CI requires exact old Git objects for C2 comparative tests and sets
`C2_CROSS_REQUIRED=1` in all three jobs, so missing history cannot silently skip
those tests. Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12 jobs install the
optional competition libraries and run the actual browser/API demo. CI uploads
`browser-evidence-<os>-python-<version>` screenshots and the actual software JSON
trace on success as well as failure. Artifacts are available under the exact run.
No robot credentials or raw video/weights/bag/map assets were added.

Changed-file inventory is the functional commit diff (84 files). Most adopted
files are reviewed role code, reports, source tests and compact evidence. C1's own
implementation is `competition_native/session.py`, `ingress.py`, traffic
`worker.py`, shared `mission_coordinator.py`/`service.py`, existing mission
`workspace.js` + `offline_signal.js`, dedicated fixture server/integration/E2E
tests and `.github/workflows/ci.yml`. Historical D0 evidence binding is unchanged.

## One remaining task

Qualify one real sensor-to-final-consumer binding: independently measured feet
and physical STOP, verified camera clock/identity, and the final actuator consumer.
Until that evidence exists, physical activation remains unavailable. MPPI tuning,
optional D0 videos and broader native trials are not prerequisites for this
software candidate.
