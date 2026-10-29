# C2 round 2 — compatibility and freeze

2026-10-29, Asia/Seoul. **C2_COMPATIBLE_FROZEN — current pinned combination only.**
Actual C1/D1 synthetic registration and full-source export remain verified.
The requested newer canonical/zero-RMSE commits were not published at the initial
remote fetch; their compatibility is **NOT_RUN**, not a pass for an unavailable
revision. No follow-up watcher or new chat was created.

## Scope and identities

- Branch: `review/20261029-x-c2-map-ui`; starting C2 HEAD `5eed1a9959ca25a4f30bd5b5712806a5ad660c51`.
- Tested source/tests/evidence commit: `24b3d873053f7b3652e93251443ca8bfd88dd078`.
- Final documentation/publication commit: the commit containing this report;
  its literal HEAD and remote match are supplied in the final chat report. This
  documentation commit does not change the tested implementation or test bytes.
- Exact read-only C1: `54629c793ad4ae0ea88127f00ed1b7f8805fc4e2`.
- Exact read-only D1: `cbedd05ba6f97dad5506e8003302f689ed8fcb4c`.
- Comparison base: `f469155c2b0c505f3e472e878f75029d7b8d39df` (actual C2 base).
- Remote main observed at start: `5c1ffe3ba3c070e67e143d39b65650cc8dba5f2e`.
  The prompt's `d8d15e52a94d9f77242914bb6e0393322c81171c` was not used to reset anything.
- C1 wire version `0.1`; UI `robot-scope.multimap-ui.v1`; BundleStore
  `robot-scope.multimap-fusion.v1`.
- Canonical actual two-map request SHA-256:
  `c7c82d1e42dc24154548715013c60b7efedd39791ae550a012d39f436d65b013`.
  D1 generator seed 92, 400 points/source; request ID `c2-round2-1`.
- External export bytes were compared with Git blobs: C1 13 files, D1 9 files,
  all exact. C1 contracts/services/pcd_editing and D1 multimap_core,
  experimental_se3, generator are imported only from `/tmp` exports.
  No other-role source is copied into this branch, merged, or cherry-picked.

## Narrow changes

- `c1_contract.js`: reject frame/session/unit drift between UI identity and the
  preserved C1 descriptor, in addition to ID/revision/hash drift.
- `c1_ports.js`: preserve all ancestor IDs in the returned saved-map descriptor
  from the actual manifest DAG, including roots of an earlier merged source;
  mark storage as `offline BundleStore`.
- `index.js`: show that storage classification beside the verified saved identity.
- Test host `host.html`: preserve the server's JSON HTTP error detail instead of
  reducing every refusal to `C1 HTTP 409`.
- Existing external-composition host factored into `compose()`, with an optional
  three-source/offline-bundle catalogue for tests. This binds the existing C1
  `BundleStore.reload` through DI; it is not product saved-map registration.
- C2 tests add real service/CAS/ancestry checks, a focused browser sequence,
  frame/session/zero-metric assertions, and an observational URDF probe.
  Existing browser checks support a separate report path and skipping image
  capture; no assertions were removed. Round-1 reports/screenshots are preserved.

No new UI workflow, renderer, registration algorithm, service API or product mount
was added. All edits are within the four C2-owned directories.

## Actual execution and limits

Small reports are in `experiments/expansion_20261029/c2_map_ui/round2/`.
Generated PCDs and expanded proposal point samples stayed in temporary directories.

| Check | Result | Evidence class |
| --- | --- | --- |
| C2 unit/contract/state tests | 20 PASS, 0 skip | UNIT/mock + exact external C1 Python DTO validation |
| Existing C2 browser regression | 18 PASS | UI_FIXTURE, plus separately recorded actual TCP HTTP + D1 core synthetic solve/review/export |
| Round-2 browser sequence | 5 PASS | 2-map, 3-map, `(A+B)+C`, overlap refusal use actual TCP HTTP/core; zero display uses UI_FIXTURE with actual core metric |
| Round-2 service sequence | 5 PASS | Actual D1 core + actual C1 ASGI HTTP/manager/BundleStore, synthetic PCDs |
| Full Python discovery | 3,116 run: 3,114 PASS, 2 SKIP (SVG/rosbags optional dependencies), 0 fail | Repository offline regression; not a ROS/native deployment run |
| Full baseline JS | 699 PASS, 0 skip/fail | Repository JS unit regression |
| Protected E2E base / C2 HEAD | 2 / 2 PASS on each | Same local runner/browser/fixture, original tests unchanged |
| URDF observation base / C2 HEAD | PASS / PASS | Real static URDF-derived mesh asset; backend fixture |
| Actual recorded venue maps | INPUT_REQUIRED | No such inputs supplied |
| ROS/native runtime, robot, motion, deployment | NOT_RUN | No claim of actual ROS/native/robot execution |

The service sequence verifies 800-point A+B, 1,200-point A+B+C, and 1,200-point
(A+B)+C outputs, new ID/revision/hash, exact output hash reload, five ancestry nodes
for the incremental result, and original source bytes unchanged. Explicit review
is required; a repeated review with the old revision returns 409. Changing source
revision after completion also returns 409. A cancelled candidate cannot be
reviewed. Existing late-response, map-switch and disconnected-source defenses
remain covered by the unchanged regression cases.

`(A+B)+(B+C)` is rejected by real `CatalogueAdapter.pinned` with
`duplicate ancestor across fusion inputs`. **The pinned C1 router erases that
specific reason**, returning `stale input/revision or immutable conflict`.
The browser now displays that exact received detail and retains both inputs.
The test does not claim that the precise ancestry reason reaches HTTP; the report
marks `BLOCKED_C1_GENERIC_CONFLICT`. No client-side dedup or hidden input was added.
C1's source listing also lacks lineage metadata; the new saved-result descriptor
retains manifest ancestry, while catalogue ancestry propagation remains a C1
contract follow-up.

Actual `D1.metrics(points, points, identity, .05)` returned exact `rmse_m == 0.0`.
C1-to-UI DTO translation retains zero; the browser displays `0.0000 p95 / 0.0000
RMSE`. This is **not** proof of corrected D1 candidate ranking: the pinned
`multimap_core/solver.py:191` still uses `rmse_m or 1e9`. Its replacement commit
was unavailable and was not patched in C2.

## Remote CI and protected URDF investigation

The actual C2 starting-HEAD push run is
[40830021190](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40830021190).
Both hardware-free jobs (Ubuntu 22.04/Python 3.10 and Ubuntu 24.04/Python 3.12)
failed browser E2E: **226 passed, 1 failed**. Python ran **3,116**, skipped 2,
and JS passed **699**. The URDF test passed in both jobs. This differs from the
prompt's 3,214/706/URDF-failure description; that description cannot be attributed
to this SHA's inspected run.

The actual first failing assertion is in `tests/e2e/mount_calibration.spec.mjs`,
case at line 343, helper `estimate()` at line 144:
`expect(locator('#mount-calibration-results-content')).toBeVisible()`;
received hidden, enclosing test timeout 20,000 ms. The mission real-API step was
then skipped. Competition offline integration passed. The earlier base run
[40826730094](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40826730094)
is successful. This does not establish why the later full browser run timed out.

Limited local comparison used Ubuntu 24.04.5, Node 24.22.1, Playwright 1.62.1,
Chromium 151.0.7922.34, one worker, identical exported fixture/config. Node differs
from GitHub's Node 20; this is a controlled local base/branch comparison, not an
identical hosted-runner reproduction. Both original cases (URDF and saved
SYNTHETIC mount calibration) passed on both SHAs in 5.4 s per two-test run.
The shared app/navigation/scene/model/test bytes are identical between those SHAs;
C2 is not imported by the product entrypoint.

URDF observational reports show:

- Asset `/static/assets/go2/go2-official-lite.json`: HTTP 200, 73,634 bytes, same
  SHA-256 `a638b56b309d37b089dc2e22d5683289be8268ce69a2cdd71ecf943d9294056f`.
- Both observed scene instances (`sceneCanvas`, `savedSceneCanvas`) were ready
  before dragging; model `Unitree Go2`, no model error.
- Actual `savedSceneCanvas.drawRobotMapPreview` returned true five times per run;
  first successful draw at about 509.5 ms / 609.9 ms after page navigation.
- No page exceptions or pose/goal mutations. Both had the same three resource-404
  console messages; captured `go2_saved_map.json` 404 did not prevent mesh draw.
- No fake draws, assertion deletion, timeout extension, shared-source edit or skip.

Protected-owner handoff: if the URDF timeout recurs on its exact failing SHA,
observe `app.js applyRobotModel()` completion/generation and
`drawNavigationPosePreview()`'s **savedScene3d** instance, plus
`go2_official_model.js drawRobotMapPreview()` readiness guard. A read-only model
ready/asset/generation hook would make the race observable. No speculative shared
fix is made. For the actual mount-calibration timeout, retain the failing trace
and inspect the estimate response/result invalidation at the helper above; its
root cause was not reproduced by this limited run. Full CI remains independently
reported; C2-only passes do not make it green.

Final publication CI is not yet completed when this documentation is committed.
The final chat report records the exact pushed HEAD and its observed CI status;
no new run is claimed green here. The known previous HEAD run above remains FAIL.

## Reproduction

Use the exact dependency export commands in the experiment README, the recorded
Python environment, and Node >=20. One computation/browser runner at a time.

```sh
export C2_C1_EXPORT=/tmp/c2-c1-exact-54629c7
export C2_C1_FIXTURE=/tmp/c2-c1-contract-fixture-54629c7.json
export C2_PYTHON=/tmp/c2-venv/bin/python
node --test --test-isolation=none tests/expansion_c2/*.test.mjs

PYTHONPATH="$C2_C1_EXPORT:/tmp/c2-d1-exact-cbedd05:$PWD/experiments/expansion_20261029/c2_map_ui" \
  OPENBLAS_NUM_THREADS=1 "$C2_PYTHON" tests/expansion_c2/round2_service_check.py /tmp/c2-round2-service.json
PYTHONPATH="$C2_C1_EXPORT:/tmp/c2-d1-exact-cbedd05" OPENBLAS_NUM_THREADS=1 \
  "$C2_PYTHON" experiments/expansion_20261029/c2_map_ui/exact_service_host.py --round2
# Use the printed loopback URL, with Playwright available:
C2_C1_SERVICE_URL=http://127.0.0.1:PORT C2_ROUND2_SERVICE_REPORT=/tmp/c2-round2-service.json \
  C2_ROUND2_BROWSER_REPORT=/tmp/c2-round2-browser.json node tests/expansion_c2/round2_browser.mjs
# Stop that host. Run the default two-source host for the original regression:
C2_C1_SERVICE_URL=http://127.0.0.1:PORT C2_SKIP_SCREENSHOTS=1 \
  C2_REPORT_PATH=/tmp/c2-round2-regression-browser.json node tests/expansion_c2/browser.e2e.mjs
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
```

For the protected comparison, export each SHA's `robot_dashboard/static`,
`tests/e2e`, `tests/fixtures`, `playwright.config.mjs` and package files to distinct
`/tmp` directories; supply the same Playwright 1.62.1 dependency directory.
Run `playwright test goal_precision.spec.mjs mount_calibration.spec.mjs --grep
'Navigation initial pose|imports saved SYNTHETIC artifacts' --reporter=line` once
per export, then `C2_PROBE_ROOT=<export> C2_PROBE_REPORT=<json> node
tests/expansion_c2/urdf_probe.mjs`. The probe records real draws and never forces
success. All servers bind loopback only.

## Freeze and one next connection

**One C2 follow-up: pin the published C1 canonical contract + D1 zero-RMSE fix and
rerun this same compatibility sequence**, including specific ancestry error/lineage
propagation. Do not reopen UI development or automatically wait for those branches.
The separate whole-repository CI failure/pending state above remains visible and
is not waived by this freeze.

No product app connection, main integration, robot access, shared controller/ROS/TF
change, deployment or physical movement was performed. No PR was created, no
force-push used, and only the existing C2 branch is submitted.
