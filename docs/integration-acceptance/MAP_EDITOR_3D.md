# Saved map editor: 2D / 3D mode

## Scope and safety

This is a cloud-VM-only implementation prepared on committed base `78e23ce`.
No Mac files, public branch, robot, Jetson service, TF, Nav2 configuration, or map files were changed.
Fetching current public main could not be verified because the tool's approval-review infrastructure failed. Merge these small insertions into current main rather than replacing shared files.

The existing saved-map **2D editor panel** now contains one mode selector. The default is 2D; choosing 3D hides all 2D tools/canvas/save controls, and vice versa. Mode switches preserve both drafts, and display an unsaved-draft warning. Existing 2D engine, painting, copy-save, reset, rotation and source-switch confirmation logic are unchanged. Selecting a different saved map still uses existing 2D source-switch rules, distinct from merely changing editor mode.

3D mode edits **annotation volumes** and exports a **filtered XYZ JSON copy**, without rewriting source PCD bytes. Select a saved 3D map in the existing catalog, select 3D editing mode, then press “선택한 3D 지도 불러오기”. Missing map identity, source revision or frame blocks editing. The XY canvas uses the cloud's existing frame in metres without any transform. Click vertices, set inclusive min/max Z bounds, choose a region kind and inside/outside selection, and add the region. Outside selection excludes XY-outside points only within the chosen Z slab; polygon boundaries stay inside.

- `visibility`: hides matched source points only in the editor preview when its checkbox is enabled.
- `localization`: independent exclusion proposal. Does not remove visible points or alter current localization.
- `keepout`: independent keepout proposal. Does not remove points, turn occupancy cells into free space, or install a costmap filter.

Counts represent union membership independently for each kind. Overlap between different kinds is intentional. Preview membership is calculated over the loaded cloud sample, which can be smaller than the full PCD. Canvas drawing is additionally bounded to 100,000 points. The display labels sampled source counts when supplied by the server. To edit all usable loaded XYZ points, use the existing saved-map point budget ALL option and reload; the editor limit is 1,000,000 points. Full raw PCD processing must be independently reviewed before downstream use.

There is no network write path. Annotation export downloads a new annotation-version JSON file. Edited-copy export downloads a new JSON pointcloud, with filtering explicitly selected for visibility OR localization; keepout never filters copies. Copy exports contain source identity, original/loaded/output counts, regions, purpose, metres and runtime_installed:false. They do not create a server saved-map entry, alter a map family, produce a PCD, publish ROS messages, or install a Nav2 filter. When source_points differs from loaded count or is missing, copy export is explicitly named PREVIEW-ONLY and sets preview_only:true. Equal counts are labeled complete-normalized-snapshot: the backend rounds XYZ and does not preserve original PCD attributes/precision. Runtime installation and original full-PCD processing require a separately reviewed implementation. Original source points remain immutable. Repeated exports receive distinct version IDs. Import must match the loaded map ID, revision (including its type) and frame exactly.

## Controls

- Click at least 3 vertices; Backspace removes the final vertex, Escape cancels selection.
- Add validates simple, nonzero-area, unclosed polygons (3–256 vertices) and finite ordered height bounds.
- Undo / redo cover annotation edits and imports; reset is also undoable.
- Mode switches preserve pending polygon vertices, height fields, regions and 2D state.
- Loading another 3D source, importing over changes, and reset prompt before replacing work.
- Closing/reloading the page warns when a 3D draft is not exported. Drafts are memory-only: export before closing.
- Import accepts at most 2 MiB of JSON, at most 100 regions, and checks schema, identity, fields and numbers before replacing anything. Imports are atomic; invalid files leave the draft unchanged.

## Minimal integration with concurrent work

New independent files:

- `robot_dashboard/static/features/map_editor3d/core.js`
- `robot_dashboard/static/features/map_editor3d/workspace.js`
- `robot_dashboard/static/features/map_editor3d/editor.css`
- `tests/test_map_editor3d.mjs`
- Additional UI tests delivered in this patch.

Only shared files touched:

1. `static/index.html`: add the feature CSS link in `<head>`; wrap the existing 2D toolbar through `mapEditorMessage` in `<div id="mapEditor2D">`. The existing 2D nodes/IDs stay intact. Do not wrap the neighboring crop panel.
2. `static/app.js`: add one named import of `initializeMapEditor3D`; append one initializer passing the existing panel, read-only current saved-cloud data, the existing 2D dirty predicate and redraw callback. The adapter passes raw saved-cloud coordinates, not scene-transformed points. It does not change `scene3d.js`, live pointcloud transport, TF or pose paths.

Use the included `integration.patch` with `git apply --check` first. Concurrent app.js/index.html changes must be reconciled by the exact insertions above; do not overwrite those files from a full copy. No commit or push is included.

## Validation

See `MAP_EDITOR_3D_QA.md` beside this file for actual passed checks and environment-blocked checks. Browser screenshot / visual acceptance is not claimed until an actual browser run succeeds.

## Run locally on an approved checkout

Run the normal dashboard; open Saved Maps and its existing editor panel. The feature is entirely client-side and needs the normal saved-map endpoint response `{revision, frame_id, points}` and catalog ID.

Tests:

    node --test tests/test_map_editor3d.mjs tests/test_map_editor3d_workspace.mjs tests/test_map_editor.mjs
    npm run test:unit
    python3 -m unittest discover -s tests -v
    npx playwright test tests/e2e/map_editor3d.spec.mjs

Playwright needs a permitted Chromium installation. No test fixture includes private LiDAR source data.
