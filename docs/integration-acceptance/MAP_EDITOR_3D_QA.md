# Mac integration follow-up — 2026-10-18

The VM delivery below is retained as historical provenance. The Mac integration
preserves current app/router/scene/calibration changes and adds minimal hooks.
All four actual Playwright editor tests now pass with synthetic fixtures, including
exclusive 2D/3D modes, dirty drafts, source contracts, invalid polygons, import/export
and outside exclusion. Browser checks issue no server mutations and preserve the
original points. Screenshots are retained privately as `map-editor-2d.png`,
`map-editor-3d.png`, `map-editor-outside-before.png` and
`map-editor-outside-course.png`. These are synthetic UI checks, not robot/map
accuracy validation. Current full-suite results and exact commit are recorded in
the integration closeout; the historical VM failures below are not current results.

See [SAVED_3D_OBSERVATION.md](SAVED_3D_OBSERVATION.md) for runtime separation and
charging hold. No robot deployment or service restart has occurred in this stage.

## Historical VM delivery record

# Saved-map editor QA

Validated in the cloud workspace on 2026-10-18. No robot, Jetson, runtime-map, TF, or navigation writes were performed.

## Executed checks

- Full JavaScript suite: **445 passed, 0 failed** (`npm run test:unit`). The pre-feature baseline was 415 passed.
- Focused 3D core, workspace, and existing 2D suite: **46 passed, 0 failed**.
- 3D workspace/controller coverage: **10 passed**, using a small deterministic DOM/canvas fixture. This verifies controller state and event behavior; it does not claim real browser layout, visual rendering, or accessibility acceptance.
- Full Python suite: **2,220 tests run; 25 errors; 1 skipped** (`python3 -m unittest discover -s tests -v`). The same 25 test identities failed before the feature changes. All are socket `PermissionError: [Errno 1] Operation not permitted`: 24 `test_slam_broker` cases and one `test_depth_capture_integration.DepthBrokerTests` case. No new Python errors or failures appeared.
- Playwright discovery: **4 tests found** in `tests/e2e/map_editor3d.spec.mjs`; syntax checks passed.
- `git diff --check` passed.
- Existing `robot_dashboard/static/map_editor.js` is byte-identical to the committed baseline (SHA-256 `c7943c7f94b4bc82f777efb973b09a9407ce0550d8aed2a29f3ed628caf4b44a`). Existing 2D unit coverage remains part of the passing full suite.

The added initializer initially crossed an existing 6,900-line application-root test limit. The adapter was extracted into the new feature module and the final full suite passed without weakening or changing that existing test.

## Controller coverage

- A single existing editor panel; mutually exclusive 2D/3D state and preserved drafts on mode switches.
- Polygon click and keyboard handling; blank/non-finite/inverted Z limits; invalid self-intersecting polygons.
- Undo, redo, confirmation cancellation, reset, dirty-unload warning, and source-replacement cancellation.
- Independent visibility/localization/keepout membership; preview hides visibility points only.
- Inside/outside selection and separate visibility/localization edited-copy exports.
- Immutable original input; exported source identity, unique version identity, units, and `runtime_installed: false`.
- Sampled/unverified inputs marked `preview_only: true` with explicit preview-only status.
- Strict version import, bad schema/source/extra fields, invalid JSON, oversized files, and asynchronous import races preserve the current draft.
- Stale/mismatched saved-cloud adapter responses fail closed.
- The controller performs no network requests or mutations during these tests.

## Additional private-sample check

The implementation check used a private 4,000-point sample with an outside-polygon localization exclusion. The localization copy retained 1,959 points and excluded 2,041; the visibility preview remained at 4,000 points and the original input stayed unchanged. Only these aggregate metrics are included; the source data and coordinates are not part of the deliverable.

## Browser acceptance still pending

**The four Playwright tests have not run in a real browser. No screenshots were produced and no visual acceptance is claimed.**

Installed Chromium was attempted with `--no-sandbox`, but the execution sandbox rejected its process-singleton Unix socket. The supported escalated launch also failed during environment setup on a read-only filesystem mount, before Chromium ran. Testing did not bypass those restrictions.

On an approved environment with Chromium available, run:

    npx playwright test tests/e2e/map_editor3d.spec.mjs

The prepared tests cover real dashboard integration, exclusive modes and dirty drafts, unsafe polygon/heights, history, local version import/export, outside-course filtered-copy export, no server writes, and page errors. A successful run produces these screenshots in Playwright's test output:

- `map-editor-2d.png`
- `map-editor-3d.png`
- `map-editor-outside-course.png`

These files are expected outputs, not completed deliverables. Inspect them for clipping, overlapping controls, canvas transforms, and readable preview-only notices before accepting the visual UI.

## Full output files

Complete baseline/final command output was retained during validation. This source delivery includes the summary above rather than the full logs. The Python command returned nonzero; it is not a full passing suite.
