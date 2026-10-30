# C1 latest composition and map-error propagation

2026-10-30 KST. Existing branch `review/20261029-x-c1-services`; start HEAD
`50600c7bce6f5fae743cd836ca1d8ee68d91b05a`, clean and equal to remote.
Its [CI 40846353053](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40846353053)
completed SUCCESS. This is the predecessor's result, not the new submission's CI.

Latest source/test code and this evidence are committed together. The final chat
receipt supplies the exact containing HEAD, remote equality and its completed CI
result. A commit cannot embed its own hash. File hashes and execution receipts
are in [CURRENT_EVIDENCE.json](CURRENT_EVIDENCE.json).

## Pinned owners and current verdict

| Role | Exact SHA | Use |
|---|---|---|
| D1 | `203c144f6b4a90966839c34b603ae12ee676cb12` | Actual solver for compatibility and saved-ancestry error |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` | Actual perception/tracker/compactor |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` | Actual geometry/assessment/normalizer bridge |
| C2 | `7625c87ede2489143c44862d883e10fc1791df28` | Actual JavaScript HTTP solve/review/save/list/reload |
| C3 | `e394b090221c555cf0649021d132163596c19fe2` | Actual 0.2 parser, adapter and stateful consumer, including latest receipt/expiry guards |
| C4 | `7ac0d55b07abd20902d6d756c6b225733613fea7` | Actual CanonicalCorePorts/Runtime and owner input fixtures |
| C7 | `ec724dafd33db92ecb27db17e0bdd2eee5a30455` | REPORT and diagnostics read-only review; no C7 implementation imported |

C3's latest pause/freshness work was complete at startup; its exact HEAD had
already completed [CI 41004220872](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41004220872)
SUCCESS. ROUND2_V02 and PAUSED_FRESHNESS were read, alongside C4 FOLLOWUP and C7
REPORT. Older C4 documentation's C3 failure refers to its older C3 pin.

Read-only `git archive` exports are checked against exact Git blobs before and
after execution, including the C4 input fixtures and actual C2/C3 JS sources.
Import-origin assertions verify D1/D2/D3/C4 ownership. No counterpart implementation
is copied, patched, merged or cherry-picked into C1. C1 is the local real package.
The run order is D1/C2 compatibility, then D2→D3 through C4, C1 HTTP, and C3.

**Actual latest D2/D3→C4 CanonicalCorePorts/Runtime→C1 0.2 HTTP→C3: PASS.**
The old `C1_VERSION_UNSUPPORTED` and `UNSUPPORTED_D3_ASSESSMENT` are preserved in
[ROUND2_FOLLOWUP](ROUND2_FOLLOWUP.md) as historical results, not current failures.
Those old replay pins remain unchanged.

Inputs are C4's exact generated point/robot-state fixtures. No copied solver,
collision engine, hand-built successful assessment or substitute DTO is used.
C4 invokes D3's real bridge and C1's actual ClockBinding/time normalizer; full
references, original receipt and source expiry remain intact. The sparse case
has no coverage certificate and remains UNKNOWN. All command checks use the
owner's memory-only sink and retain HOLD/zero; no control publication occurs.

Real authenticated loopback uvicorn/FastAPI responses are read as exact text
and passed unchanged to C3's parser/adapter/consumer. Ready response: 10,558 bytes,
SHA256 `21351322ce2d69d5e9579d8a2e3430c9408586c6d77c77e8ade64751e20a7e41`.
C3 accepts one actual obstacle. Actual missing pose/joints and scalar-only D3
envelopes keep **drawable collision UNAVAILABLE**, with
`POSE_JOINT_OR_SOURCE_INSUFFICIENT`. Acceptance is not full collision visualization.
The adapter's missing reference value is null; an initial harness assertion
incorrectly expected false and was corrected to the actual null contract. Neither
owner code nor a safety acceptance criterion was changed for this correction.

## Required negative cases

| Case | Observed result |
|---|---|
| Duplicate/old sequence | C1 ingest False; C4 DUPLICATE_OR_REORDERED_INPUT; C3 OUT_OF_ORDER |
| Source restart, seq 0 | Explicit C4 rebind + C1 reset_source accepts new epoch; old epoch rejects in C1/C4/C3 |
| Changed map revision/generation | C1 reset clears sources; old-map input rejects; C3 C1_MAP_GENERATION_MISMATCH |
| Wrong source clock / clock epoch | C4 CLOCK_MAPPING_CONTEXT_MISMATCH, UNKNOWN/HOLD |
| Expired mapping window | C4 OUTSIDE_CLOCK_MAPPING_WINDOW, UNKNOWN/HOLD |
| Different host clock at C1 | Service age unknown, payload unavailable; C3 does not show it |
| Original TTL expiry / 1.5 s transport delay | C1 expiry suppresses; C3 keeps expired data unavailable |
| 2.6 s queued presentation / expired response then delayed ready | Original receipt age preserved; stale/invalidated data does not revive |
| Missing pose / joints | Real D3 has no mapped valid interval; runtime UNKNOWN/HOLD; no fabricated C3 data |
| Empty sensor geometry / mismatched geometry identity | Empty remains UNKNOWN; mismatched geometry rejects |
| Unauthorized HTTP | 401; mutation origin gate remains 403 |
| High host ns above 2**53 | Actual C4/C1 0.2 and C3 retain exact decimal strings |
| 128 KiB transport / serialization overflow | Existing Python encoder and C3 parser reject |
| Normalization overflow | Actual 0.1 input is 16,384 B; real upgrade produces 16,388 B and C1 rejects |
| Latest storage overflow | Five 16,384 B samples total 81,920 B; sixth rejects False |

Size tests are explicitly fault injections into actual outputs/derived envelopes,
not additional actual sensor scenarios. Storage boundaries and integrity policy
remain unchanged. C7's catalogue reread/cache, whole-frame rejection and metrics
candidates were reviewed but not implemented or described as measured defects.
The new profile makes no throughput or sensor-to-render latency claim.

## Map compatibility and corrected error propagation

Actual D1 plus actual C2 HTTP ports still solve, review, save and reload two
400-point sources into all 800 output points. Normals/intensity, original hashes,
output hash, shared-root rejection, stale apply and cancellation pass.
PCD SHA256 stays `46be1a0ec38166fc78e7d0344d3e241d57e3c29807f22e819e22e04d1ec9dbde`.
The map check reran after the harness-only JS assertion correction and the final
HTTP policy-preservation guard; it was not tuned or expanded. D1/C2 and their already-confirmed three-map/incremental work
are now frozen. No D1 formulas, frames, provenance or C2 screen changes.

The previous C1 router collapsed all Conflict exceptions into the same
`stale input/revision or immutable conflict` detail. The actual saved merged map
plus its original source now returns HTTP 409 with **ANCESTRY_OVERLAP** and a
specific safe message; no extra job or saved bundle is created.

Production changes are limited to `expansion_services/{errors,catalogue,jobs,router}.py`:

- Fixed allowlisted codes/messages; exception text is never interpolated.
- Specific DAG, source identity/content/metadata/revision and proposal revision
  causes remain distinct from generic REQUEST_CONFLICT.
- HTTP status and string detail compatibility stay intact; additive `error` holds
  `{code,message}`. List/preview/asset error paths retain failure statuses.
- Worker status retains its legacy `error` and adds safe `error_detail`; unexpected
  worker errors use JOB_FAILED. No failed proposal is published.
- Internal I/O is 503; unexpected synchronous work is safely reported as 500.
  Authentication, origin and bounded request parsing remain unchanged.

[ERROR_CONTRACT.md](ERROR_CONTRACT.md) is the minimum C2-owner handoff: prefer HTTP
`error.code/message` and job `error_detail.code/message`, retaining legacy
fallbacks. Display as text and keep rejection policies. No message was sent to
another chat and no C2 source was edited.

## Reproduction and verification scope

```sh
# Fetch the exact current_pins.json SHAs, then:
python -m tests.expansion_services.prepare_dependencies \
  --pins tests/expansion_services/current_pins.json
PYTHONDONTWRITEBYTECODE=1 python -m tests.expansion_services.current_composition \
  --deps /tmp/<readonly-export-root> --node /path/to/node-24 \
  --output /tmp/c1-current-composition.json
python -m unittest tests.expansion_services.test_errors -v
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
node --check tests/expansion_services/current_consumer.mjs
python -m ruff check robot_dashboard scripts tests/expansion_services
python -m mypy --config-file mypy.ini
python scripts/check_repository_secrets.py
```

The explicit peer composition requires read-only exports and is separate from
ordinary unit/CI totals. Error fault tests use a labelled plumbing solver; the
actual D1 path above is a separate run. No test deletion, extra skip, threshold
relaxation or shared CI change is made. The containing HEAD's remote CI must
complete before the final chat verdict; previous green runs do not substitute.

Final local checks on the committed source content:

- Python 3.12.3: **3,156 run, 3,154 PASS, 2 existing optional SKIP**, 100.427 s,
  with `C2_CROSS_REQUIRED=1`. Ten new error regressions are included. Skips remain
  optional SVG plotting and rosbags dependencies.
- Node 24.22.1: **77 test files PASS**; syntax **112 dashboard modules** plus the
  new consumer probe. Actual pinned JS consumer assertions also PASS separately.
- Ruff (including C1 tests), mypy 1.13.0 (4 repository-configured files), staged
  credential scan and whitespace/ownership checks: PASS. No shared dependency
  file changed; mypy was installed only in the existing `/tmp` test venv.
- Explicit actual owner composition: **PASS**, with correct unavailable collision
  display and memory-only HOLD evidence. The actual response hashes and 51 owner
  blob checks are preserved in CURRENT_EVIDENCE.json.

ROS/native processes, browser rendering of this composition and physical robot:
**NOT_RUN**. Existing D3 native evidence is not re-executed or promoted to this
whole chain. Production pose/joints/drawable collision and measured clock/mount/
coverage remain **INPUT_REQUIRED**. No main merge, shared app mount, deployment,
robot connection, goal, TF or control publication occurred.
