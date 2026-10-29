# C2 — published canonical contract and zero-residual follow-up

2026-10-29 (Asia/Seoul). **C2_COMPATIBLE_FROZEN** on the exact new pins below.
This closes the unavailable-commit item in [ROUND2.md](ROUND2.md). Its prior
results and CI failures remain preserved as historical evidence.

## Exact identities and scope

| Input | SHA |
| --- | --- |
| Starting C2 HEAD | `47a1d031d797c098c38a0147894523d07d30db8f` |
| Tested C2 code/tests/evidence | `7e1deb0c0419be6f7a93b832f2b12b12ee24be65` |
| C1 canonical/services dependency | `4e1dd519a707169da5f88cf2a92a20ed3e701cc7` |
| D1 zero-residual dependency | `203c144f6b4a90966839c34b603ae12ee676cb12` |
| Observed main, read only | `5154761bba6fa4f171881e61f986901e2b415ed9` |

Only the existing `review/20261029-x-c2-map-ui` branch is submitted. The final
commit adds documentation to the tested commit; the final chat receipt supplies
its literal SHA and confirms remote equality. No tested implementation changes
are hidden in that documentation commit.

C1 map DTOs remain **0.1**. The new **0.2** contract applies to observations/scene,
which C2 does not consume. Canonical C1 example file SHA-256:
`255316ee5218598d2789ab73bb354b1774eda47023522127b5ac6fdc0d210a08`.
The actual two-map request canonical hash remains
`c7c82d1e42dc24154548715013c60b7efedd39791ae550a012d39f436d65b013`.
Exports are `robot-scope.multimap-fusion.v1`, UI is `robot-scope.multimap-ui.v1`.

External exports are `/tmp/c2-c1-exact-4e1dd51` and
`/tmp/c2-d1-exact-203c144`. All 15 C1 and 17 D1 source/test files matched Git blobs
and had write permissions removed. Imports use only these exact exports. No
merge/cherry-pick or counterpart source publication occurred.

## Minimal changes

- Production behavior: unchanged. `c1_contract.js` updates only the displayed
  tested C1 SHA constant; map validation/translation/state/rendering stay frozen.
- Test host: optional `--exact-zero` generates independently identified,
  identical 125-point dyadic lattices (two selected by the browser) using D1's existing PCD writer. The actual
  solver, candidate selection, metrics, worker, router and store are untouched.
- Browser check: `C2_EXACT_ZERO_ONLY=1` checks a real zero candidate and explicit
  review/export. Existing mocked zero-display coverage remains separately labeled.
- Service check now also verifies the new real `GET /multimap/exports` list.
- Original browser report takes C1/D1 SHA labels from explicit environment pins;
  an omitted pin is `UNSPECIFIED`, not the old hardcoded SHA.
- New small evidence is under `experiments/expansion_20261029/c2_map_ui/round2_latest/`.
  Round-1/earlier-round-2 evidence is unchanged. Generated PCDs remain temporary.

## Execution

| Check | Result | Classification |
| --- | --- | --- |
| C2 unit/DTO/state | 20 PASS, no skip | UNIT/mock plus exact C1 Python validation |
| Original browser sequence | 18 PASS | UI_FIXTURE plus actual TCP HTTP/D1 synthetic flow |
| Round-2 browser sequence | 5 PASS | Actual 2/3-map, incremental merge, refusal; zero-display case separately UI_FIXTURE |
| Service sequence | 5 PASS | Actual D1 + C1 ASGI HTTP/worker/BundleStore; no solver mock |
| Exact-zero end-to-end | 1 PASS | Actual D1 candidate + TCP HTTP + UI + review/export |
| D1 published zero-residual regressions | 7 PASS | Six injected numerical-boundary cases and one unmocked identity solver case |
| Full Python | 3,116 run; 3,114 PASS, 2 existing optional SVG/rosbags SKIP; 0 failures | Repository offline regression |
| Full JS | 699 PASS; 0 skips/failures | Repository regression |

Exact-zero output: RMSE **0**, p95 **0**, one accepted edge, zero rejected edges,
UI `0.0000 p95 / 0.0000 RMSE`, **250 full-source points** after explicit review
and save. Output PCD SHA-256:
`f3665d7a38da6c61faa7e3eec6e0ca9f2fb6a1b122f5fe1676daaf14870d10fa`.
No patched refine/metric function or fixture proposal is involved in that browser
case. D1's separate boundary regressions validate ranking 0 before positive/None,
invalid residual rejection, deterministic ties and retained overlap priority.

The unchanged normal flows preserve ID/revision/hash/frame, anchor, manual seed,
source CAS, cancelled/late responses, map-switch and disconnected-source defenses.
Actual `(A+B)+C` remains 1,200 points with all roots and a new identity.
Actual `(A+B)+(B+C)` remains rejected without dedup or hidden inputs. Original
source hashes remain unchanged; list/get/reload confirm offline BundleStore only.

ROS/native/device execution: **NOT_RUN**. Real venue map accuracy:
**INPUT_REQUIRED**. These are synthetic numerical/storage results, not measured
field registration or robot navigation evidence.

## CI receipt

Starting C2 HEAD [run 40838306845](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40838306845)
completed **SUCCESS**. Both Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12
jobs passed Python 3,116 (2 existing skips), JS 699, browser 227, and mission API
fixture 10. Competition offline integration also passed. This closes the prior
pending status; it does not retroactively erase the earlier failed run or prove
its timeout's root cause. No shared test/timeout/CI rule was changed.

Dependency CI observed at this follow-up: D1 final SHA
[40839477220](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40839477220)
**SUCCESS**. C1 final docs SHA
[40842714164](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40842714164)
was **in progress**; C1 records successful source/test SHA `4b9c02b…` separately.
These are separate from the actual local composition against the final pins.
The new C2 publication run is also separate; the final chat reports its observed
status without claiming an unfinished run has passed.

## Reproduction and one remaining contract handoff

Use the previous README export procedure with the exact new SHAs above. Set
`PYTHONDONTWRITEBYTECODE=1`, `OPENBLAS_NUM_THREADS=1`, and external `PYTHONPATH`.
Use `/tmp/c2-venv/bin/python` and Node 24.22.1 / Playwright 1.62.1 / Chromium
151.0.7922.34, as in the previous comparison. Computations were sequential.

1. Run `round2_service_check.py` with the new C1/D1 and C2 experiment paths.
2. Start `exact_service_host.py --round2`; run `round2_browser.mjs` with its
   printed `C2_C1_SERVICE_URL` and the service report. Stop that host.
3. Start `exact_service_host.py --round2 --exact-zero`; run the same browser
   script with `C2_EXACT_ZERO_ONLY=1` and a fresh report path. Stop that host.
4. Start the default two-source host; run original `browser.e2e.mjs` with the
   latest fixture, explicit `C2_C1_SHA`/`C2_D1_SHA`, `C2_SKIP_SCREENSHOTS=1`, and
   a separate `C2_REPORT_PATH`. Stop it after the regression.
5. Run `node --test --test-isolation=none tests/expansion_c2/*.test.mjs`, full
   Python discovery and `node --test tests/*.mjs`. D1's exact external
   `test_zero_rmse.py` is run read only by unittest discovery from `/tmp`.

**One remaining handoff: C1 should carry the specific ancestry refusal and trusted
lineage through its HTTP source/error contract.** At this exact SHA, private
`CatalogueAdapter.pinned()` reports `duplicate ancestor across fusion inputs`,
but `router.py` still returns generic `stale input/revision or immutable conflict`.
C2 displays that received reason honestly; it cannot manufacture the missing
server reason or catalogue lineage. Saved manifest ancestry is retained. No C1
code was changed and no automatic watcher was started.

No new chat, product connection, main integration, shared app/renderer/CI edits,
robot access, deployment, ROS/TF publication or physical motion occurred.
