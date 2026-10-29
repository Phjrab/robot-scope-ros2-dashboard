# C2 handoff — multi-map selection and fusion review UI

Latest: [Round 2 compatibility and freeze](ROUND2.md). The evidence below is the preserved round-1 record.

2026-10-29 (Asia/Seoul). **UI_MODULE_TESTED / PRODUCT_WIRING_DEFERRED / DEVICE_NOT_RUN**.

An insertable `mount(host,{catalogue,jobs,renderer,onReview,...})` module and a
separate loopback test host are implemented. The existing product app, single
PCD editor, Goal URDF renderer, 3D Nav2 and final-heading work remain unchanged.
No robot, ROS graph, sensor, TF, navigation/control endpoint or deployment was
accessed. No solver, sensor fusion, collision algorithm or C1 service is copied
or implemented in C2.

## Git identities and publication

- Repository: `Phjrab/robot-scope-ros2-dashboard`.
- Branch: [`review/20261029-x-c2-map-ui`](https://github.com/Phjrab/robot-scope-ros2-dashboard/tree/review/20261029-x-c2-map-ui).
- BASE_SHA: `f469155c2b0c505f3e472e878f75029d7b8d39df`, fresh clone's actual remote main at start; fixed for this submission. The prompt's older investigation SHA was not used to reset any checkout.
- Code + verification SHA: **`94d460f3dcf95d59e6661c59f96164c41eb3a284`**. Its source/tests are exactly the bytes validated below. Earlier implementation commit: `ba86e5b6c60ae8bd39cbcbb7dd684a5b43e38a68`.
- FINAL_PUBLISHED_SHA: the commit containing this initial HANDOFF, reproducibly identified by `git rev-parse HEAD` on the published branch. Its parent is the code SHA above; it adds only this handoff and the verification SHA/tree metadata. A commit cannot contain its own SHA, so no invented literal final SHA is embedded here. The final chat report supplies the actual published HEAD.

```sh
git fetch origin review/20261029-x-c2-map-ui
git rev-parse origin/review/20261029-x-c2-map-ui
git log -1 --format=%H -- docs/parallel-expansion-20261029/C2/HANDOFF.md
git diff --name-only f469155c2b0c505f3e472e878f75029d7b8d39df origin/review/20261029-x-c2-map-ui
```

Work was done in independent ordinary clone
`/home/desktop1/Documents/ChatGPT/robot/parallel-c2-map-ui-20261029`.
The shared root branch/index was not changed. No main/other-role commit, merge,
cherry-pick, force push, pull request or product wiring was performed.
Only these four owned directories differ from base:

- `robot_dashboard/static/features/multimap_fusion/`: contract/state machine, bounded overlays, scoped CSS, mount API, public RobotScene3D adapter, C1 wire/HTTP translation.
- `tests/expansion_c2/`: contract/geometry/state/transport tests and browser E2E.
- `experiments/expansion_20261029/c2_map_ui/`: synthetic generators, test hosts, reproducible environment and actual result reports.
- `docs/parallel-expansion-20261029/C2/`: contract, future integration points, this handoff and ten screenshots.

## Implemented behavior

Multiple sources show name/session/revision/count/meters, per-source colors,
opacity, visibility and sampled extents. A chosen anchor remains identity.
Duplicate revisions and overlapping ancestor DAG inputs stay explicit warnings;
a previous merged source is preserved as a separate immutable source.

Server job progress, cancellation, failure/retry and disconnected/ambiguous
results are visible. Manual XY drag/yaw, keyboard nudges, advanced Z/roll/pitch,
explicit or actual-sample XYZ correspondences, before/after and separate prior /
solved layers are implemented. Correspondences require non-collinearity and
spread; 2D pixels never invent a Z coordinate. Optional provider heatmap and
unknown-preserving derived 2D views are shown only when supplied.

Draft revisions/tickets, pinned identities and proposal revisions protect manual
edits from late responses. Undo/redo/reset restores draft only. Explicit warning
acknowledgement and candidate review precede export. Save never sends preview
arrays, preserves originals/current selection and checks new ID/revision/hash.
C1 review increases server proposal revision; C2 validates and uses it for save.
An exported but unregistered C1 candidate is reported as saved with catalogue
registration pending. It never becomes an active localization/navigation map.

## Exact dependencies, read-only compatibility

- C1 final tested SHA: **`54629c793ad4ae0ea88127f00ed1b7f8805fc4e2`**.
- D1 final tested SHA: **`cbedd05ba6f97dad5506e8003302f689ed8fcb4c`**.
- Earlier C1 bootstrap inspected: `2402c02c6f91ba54064894b21735e01b98610acd`; superseded for final compatibility by the C1 SHA above.

Both were exported from Git to separate `/tmp/c2-c1-exact-54629c7` and
`/tmp/c2-d1-exact-cbedd05` directories. The test host imports the exact external
modules through PYTHONPATH. Counterpart code is not copied into the submission.
C1's existing router/catalogue/job manager/store receives D1's existing
`solve_contract`; C2 adds test wiring and bounded preview translation only.

The same browser host used two 400-point synthetic full-source PCDs created by
D1's generator, with known priors entered through the UI. C1 HTTP enqueue/status
returned an actual D1 SOLVED_CANDIDATE (one connected component, accepted edge),
then C1 review revision 2 and new full-source export/GET hash confirmation.
Source/target overlap and RMSE/p95 are shown separately. This is **SYNTHETIC**
algorithm/transport/UI compatibility, not real-map accuracy or product integration.
C1 does not register that export in its source catalogue; the final screenshot
shows this pending state honestly. No arbitrary runtime budget was silently
passed to D1. All fixture and exact test mutations are confined to multimap
job/review/export; forbidden navigation/control mutation count is zero.

## Actual final verification

Environment: Linux x86_64, Python **3.12.3** in `/tmp/c2-venv`, Node **24.22.1**,
Playwright **1.62.1**, Chromium headless **151.0.7922.34**. Dependencies are pinned
in the recorded [environment](../../../experiments/expansion_20261029/c2_map_ui/python-environment.txt).
No ROS runtime was started. All generated PCDs/points remain temporary/in memory.

| Check | Classification | Actual result |
| --- | --- | --- |
| C2 contract/state/geometry/strict C1 DTO/HTTP adapter/import checks | UNIT / SYNTHETIC | **20 PASS**, 0 FAIL, 0 SKIP |
| Browser source selection, keyboard/drag, rotated non-square view, advanced pose, real XYZ pick, dirty confirm, late response, cancel/retry, disconnected/ambiguous states, save, loading/schema recovery, themes, 390/1440px, resize/HiDPI and exact dependencies | UI_FIXTURE + SYNTHETIC | **18 PASS**, 0 FAIL |
| Actual exact C1 HTTP + D1 solve/review/export/reload | SYNTHETIC, included in browser run | **PASS**; details/hashes/metrics in browser-results.json |
| Existing `node --test tests/*.mjs` under Node 24 | UNIT | **699 PASS**, 0 FAIL, 0 SKIP (77 files) |
| AGENTS `python3 -m unittest discover -s tests -v` with venv Python | UNIT / SYNTHETIC baseline | **3,116 run: 3,114 PASS, 2 SKIP**, 0 FAIL; 97.137 s |
| API/traffic assertions for open/drag and all actions | UI_FIXTURE / SYNTHETIC | **0 nav/initialpose/goal/cmd/control mutations**, all browser traffic loopback |
| Owned-path and staged-whitespace audit; Python host compile | STATIC | **PASS** |
| REPLAY_REAL / NATIVE_NAV2_SIM / device / deployment / product wiring | Explicit boundary | **NOT_RUN** |

The two Python skips are optional SVG plotting and optional rosbags backend tests.
They are not device-test results. Initial system Node 18 had seven existing ESM
load failures, and initial system Python lacked project dependencies (115 errors).
The final runtime/venv resolves those environment failures. Restricted sandbox
bind/async limitations required the already authorized local test execution.
A repeated exact export correctly rejected an already used immutable name; the
final E2E uses a new per-run name. These attempts are recorded in verification.json.

Evidence:

- [Machine-readable verification](../../../experiments/expansion_20261029/c2_map_ui/verification.json)
- [Browser results, exact SHA metrics and HTTP audit](../../../experiments/expansion_20261029/c2_map_ui/browser-results.json)
- [Unit results](../../../experiments/expansion_20261029/c2_map_ui/unit-results.txt) and [regression summary](../../../experiments/expansion_20261029/c2_map_ui/regression-summary.txt)
- [Manual prior / dark](screenshots/01-manual-prior-dark-1440.png), [three-map disconnected](screenshots/02-disconnected-three-maps.png), [before](screenshots/03-before-ambiguous.png), [after](screenshots/04-after-ambiguous.png)
- [Fixture new PCD](screenshots/05-new-pcd-saved.png), [390px light/HiDPI](screenshots/06-mobile-light-hidpi.png), [1440px resized light](screenshots/07-desktop-light-resize.png)
- [Exact C1 contract fixture](screenshots/08-c1-exact-contract-fixture.png), [actual D1 synthetic proposal](screenshots/09-exact-c1-d1-synthetic-solved.png), [C1 export/hash and pending catalogue](screenshots/10-exact-c1-d1-new-export.png)

Reproduction commands, including exact exports and the same browser host, are in
[the test-host README](../../../experiments/expansion_20261029/c2_map_ui/README.md).
Core commands used:

```sh
C2_C1_FIXTURE=/tmp/c2-c1-contract-fixture-54629c7.json C2_C1_EXPORT=/tmp/c2-c1-exact-54629c7 \
  node --test --test-isolation=none tests/expansion_c2/*.test.mjs
node --test tests/*.mjs
timeout 180s /tmp/c2-venv/bin/python -m unittest discover -s tests -v
# Start exact_service_host.py per README; set its printed loopback URL:
C2_C1_SERVICE_URL=http://127.0.0.1:<printed-port> \
C2_C1_FIXTURE=/tmp/c2-c1-contract-fixture-54629c7.json \
  node tests/expansion_c2/browser.e2e.mjs
```

## Remaining one action

**After the ongoing work's verification and separate user approval, bind this
module to the common product host and trusted C1 catalogue/reload/auth lifecycle.**
The precise read-only call sites and missing shared renderer/reload hooks are in
[INTEGRATION_POINTS.md](INTEGRATION_POINTS.md). Product source registration,
activation, real-device alignment/navigation and deployment remain unverified
and unperformed; they are not prerequisites for this published offline module.
