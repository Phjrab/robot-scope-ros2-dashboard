# UI readability validation

Only the independent UI clone and loopback mock server were used. No Jetson,
robot endpoint, ROS service, live ARM, mapping, navigation or STOP request was
used. Publication is separate from operating deployment.

## Reproduce the UI checks

Run from the UI clone root after `npm ci`:

```sh
mkdir -p /private/tmp/robot-scope-ui-readability-baseline
git archive 42c6cce986029548e5cc7e0f6f9bd830144cabe3 robot_dashboard/static | tar -x -C /private/tmp/robot-scope-ui-readability-baseline
UI_READABILITY_PHASE=before UI_BASELINE_STATIC_DIR=/private/tmp/robot-scope-ui-readability-baseline/robot_dashboard/static npx playwright test --config docs/ui-readability/playwright.config.mjs --reporter=line
npx playwright test --config docs/ui-readability/playwright.config.mjs --reporter=line
```

The dedicated server binds `127.0.0.1:4198`; `UI_READABILITY_PORT` can select a
different unused port. `reuseExistingServer` is false. Playwright starts and
cleans up its own server. Output is isolated under
`/private/tmp/robot-scope-ui-readability-artifacts`. Browser routes reject
non-loopback HTTP requests and unhandled WebSockets. The backend fixture is
`tests/e2e/ui_redesign_fixture.mjs`, using synthetic map, cloud and camera data.
Baseline assets are archived from Git, with no checkout switch or uncommitted
changes copied from any other checkout.

## Browser coverage and evidence

`captures/before` and `captures/after` contain matching scene, state, theme and
viewport filenames. `evidence/before-browser.json` and
`evidence/after-browser.json` record text, font sizes, line heights, box bounds,
clipping, overflow, canvas backing size, DPR, STOP trial hit tests, requested
API mutations, console/page errors and attempted external requests.

| View | State and theme | CSS viewport |
| --- | --- | --- |
| Cockpit | synthetic normal, dark and light | 1440 × 900 |
| Cockpit | stale cloud/camera, dark | 1280 × 800 |
| Cockpit | disconnected, light; data absent, dark | 1024 × 768 |
| Cockpit | synthetic normal, light | 768 × 1024 |
| Cockpit | synthetic normal, dark | 720 × 450 |
| Mapping | synthetic normal, dark | 1440 × 900 |
| Maps | selected synthetic map, light | 1440 × 900 |
| Navigation | long Korean server error, dark | 1280 × 800 |
| Capture | synthetic normal, light | 1024 × 768 |
| Settings | synthetic normal, dark | 1280 × 800 |

720 × 450 is the CSS reflow equivalent of a 1440 × 900 window at 200%.
It is not actual browser/OS zoom. That case scrolls the workspace into view;
navigation may be above the viewport. The test requires at least 80 CSS px of
unobstructed scene above the fixed Safety HUD, a visible STOP target at least
44 px high, and no horizontal document overflow. Initial visual review caught
a full-scene obstruction that the old STOP-only geometry assertion missed;
the added scene-height assertion protects this behavior.

`evidence/actual-fonts-contrast.json` measures actual computed foreground colors
against ancestor backgrounds with alpha compositing after theme transitions
settle. It records any gradient so those samples are not represented as exact
flat-background measurements. CDP `CSS.getPlatformFontsForNode` reports the
rendered custom IBM Plex Sans KR glyphs on the Korean page title; this is
additional to loaded-font checks. Captures were visually inspected, including
desktop dark/light, portrait, the short viewport and long Korean errors.

The disclosure test exercises keyboard Inspector expansion/collapse, menu
collapse/restore, layout-edit entry, layout library disclosure, apply, route
exit and STOP hit testing. It verifies one renderer, unchanged camera and
LiDAR connection counts across presentation toggles, canvas DPR sizing and
zero sensor demand after leaving Cockpit. It sends no control mutation.
`evidence/disclosure-lifecycle.json` is written after those assertions pass.
It also verifies the observe-mode **열린 패널** disclosure exposes existing
active panels while hiding inactive source entries and layout-edit controls.
This restores mouse/touch access to an overlapped panel when active navigation
locks layout editing; it uses the existing launcher bring-to-front behavior.
The native camera **전송·연결 정보** summary is opened and closed through actual
clicks, including panel scrolling, with extra metrics visible then hidden.
The subsequent renderer, stream and layout-storage preservation assertions
remain unchanged.
The separate 1024 × 768 DPR2 case verifies backing canvas dimensions, real
CSS-coordinate pointer hit testing, wheel zoom and drag orbit through changing
camera diagnostics, without any robot command. See
`evidence/tablet-dpr-pointer.json`.

## Results

- Baseline capture matrix: **PASS**, 12 cases (41.7 s initial run). Baseline
  critical STOP text and token contrast already passed; these were not claimed
  as existing failures.
- Final browser suite after the active-panel and camera-metric fixes: **PASS**,
  4 tests in 3.6 min while another browser suite was also running. This includes the
  12-case capture matrix, actual font/contrast check, disclosure/edit/layout
  storage/subscription test, and DPR2 pointer test. Final unobstructed scene
  heights are approximately 503 px at 1440 × 900, 403 px at 1280 × 800,
  364 px at 1024 × 768, 490 px in portrait and 148 px in the short viewport.
- Revised sampled visible-text contrast: dark minimum 8.65:1; light minimum
  6.23:1 in the final black/green palette run. All sampled text exceeded 4.5:1.
- Initial disclosure test: **FAIL → FIXED / PASS**, sensor launcher was visible in
  operate mode because CSS expected a `data-expanded` attribute the launcher
  did not set. The final run verifies it is hidden in observe mode and available
  in edit mode.
- Expanded layout-library defect: **FIXED / PASS**. The final test verifies
  body width at least 300 px, name input width at least 140 px and the reset
  control reachable by a trial hit after scrolling, without issuing a reset.
- Portrait camera metric clipping: **FIXED / PASS**. Primary FPS, age and
  resolution now precede the image, with native technical details after the
  image. The final matrix verifies every primary value lies inside the panel
  content bounds. Panel-layer geometry stays the same between observe and
  edit modes, preserving saved-layout restoration. Small saved panels can
  still scroll their image/details; the focus control remains available.
- Added native camera-details open/close check: **PASS**, targeted disclosure
  test in 3.9 s after the matrix, without repeating the unchanged matrix.
- No uncaught page exceptions or attempted external origins in the matrix.
  Existing fixture behavior produces `/static/data/go2_saved_map.json` 404
  and, only for the disconnected case, `/api/v1/state` 503. Their browser
  resource-error console entries are explicitly recorded and allowlisted;
  they are not described as a zero-console-error run.

The final desktop and layout-edit captures were visually reviewed. Editing
tools retain their own scrollable panels; normal observation removes those
panels from the scene. The final desktop canvas is 1214 × 506 CSS px compared
with 1006 × 644 in the baseline: it is wider, with a separately reserved safety
region, rather than a larger total canvas area. Connection text increased from
14 to 15 px; the safety summary and STOP label increased from 14 to 16 px.
`COMPARISON.html` provides all 12 before/after pairs and links to original images.

## Repository regressions

| Check | Command / result | Evidence |
| --- | --- | --- |
| Full Python unittest | `.venv/bin/python -m unittest discover -s tests -v`: **PASS**, 1483 run, 1 platform skip (117.3 s) | `evidence/python.txt` |
| Full JavaScript unit | `npm run test:unit`: **PASS**, 346/346 | `evidence/unit.txt` |
| Existing UI behavior | `UI_EVIDENCE_ROOT=docs/ui-readability/behavior npx playwright test --config docs/ui-readability/playwright.behavior.config.mjs --reporter=line`: **PASS**, 8/8 | `evidence/behavior.txt` |
| Existing 67-case browser suite | `npx playwright test --config docs/ui-readability/playwright.regression.config.mjs --reporter=line`: intermediate 66/67; the remaining geometry defect was removed and affected coverage re-run below | `evidence/regression-accepted.txt` |
| Final affected Cockpit coverage | Same config with `--grep 'Cockpit|Safety HUD|active manual lease'`: 20/23 passed; 3 hit the unchanged global 20 s deadline during concurrent browser work | `evidence/regression-cockpit-final.txt` |
| Isolated final retry of those 3 | Same config with `--grep 'camera panels share|preset saves normalized|Apply persists panels'`: **PASS**, 3/3 in 11.7 s, no timeout or assertion changes | `evidence/regression-isolated-final.txt` |

Together the full run and final affected checks cover all 67 existing scenarios,
with no unresolved failing scenario. This is not claimed as a single final
67/67 run. Repeated full checks were stopped after focused verification passed.

Text logs retain their result/error content; trailing whitespace is normalized for Git.

Failures during implementation are **ITERATION_FAIL**, not BASELINE_FAIL:

- A hidden collapsed launcher blocked mouse/touch selection of an overlapping
  panel while active navigation locked editing. The top-bar open-panel selector
  restores only the existing bring-to-front path. The original mission mutation,
  no-auto-ARM and mutual exclusion assertions still pass.
- A temporary mode-specific panel-layer inset made restored geometry differ by
  70 px. That approach was removed. Edit and observe retain the same panel
  coordinate space; primary camera metrics were reordered instead. The final
  Apply and named-preset round-trip checks retain their original 2 px tolerance.
- An intermediate JavaScript check caught `app.js` exceeding its existing size
  bound. The existing display dictionary was moved to `status_labels.js`; the
  assertion was not weakened. All 346 checks now pass.
- The final three browser timeouts occurred during concurrent capture work and
  passed unchanged when run alone. They are recorded as run failures rather than
  silently represented as first-attempt passes.

Presentation tests were updated only for Korean visible labels, original enum
`data-state` attributes, direct entry to edit mode, and technical camera metrics
inside their explicit details container. The dedicated-window expectation
reserves 150 px for the permanent safety region. Resize coverage first creates
space before testing growth; launcher selection brings overlapping panels to
the front before interacting. No force-click, removed safety assertion or
lowered behavioral threshold was used.

The full regressions cover software STOP pending/acknowledged/error, explicit
E-stop clear, ARM denial, manual/autonomous exclusion, page-exit cleanup,
keyboard/gamepad behavior, camera/pointcloud ownership and reconnect, panel
move/resize/compact/focus/lock/recovery, storage migration/corrupt preservation,
map pan/zoom/annotation/crop/revisions, and cross-origin WebSocket rejection.
All robot mutations in these tests target the mock backend only.

The Python environment is the clone-local `.venv` (Python 3.13.2, repository
requirements plus httpx); Node dependencies came from the unchanged lockfile via
`npm ci`. No system Python, OS packages or dependency manifest was changed.
The browser regression server and WebSocket probe use separate loopback ports
4199 and 4200 (`UI_REGRESSION_PORT`, `UI_PROBE_PORT`). Both require a free port
and never take over an existing server.

`evidence/scope-contract.json` records all 437 original DOM IDs preserved,
no duplicate ID, no non-UI production-file change, and SHA256 hashes for the
final changed static assets. `git diff --check` passes.

## Not run / scope limits

- **NOT_RUN:** actual Safari, physical iPad, touch hardware and actual OS/browser
  200% zoom. Chromium CSS viewport checks are not iPad validation.
- **NOT_RUN:** real sensor performance, streaming bandwidth, robot operation,
  ARM/deadman/watchdog behavior on hardware, operating deployment.
- The fixture cannot prove Jetson migration integration. Re-run regression
  tests after integration against the resulting static assets and existing
  API contracts before the migration owner considers deployment.
