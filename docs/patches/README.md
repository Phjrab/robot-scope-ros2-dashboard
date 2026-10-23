# Optional common Maps/catalogue/API wiring

**Integration checkout:** this patch has already been applied here, together
with semantic-reference verification and the local localization fixes. Do not
run the application commands below again in this checkout. The following text
records the original module handoff and remains useful for a clean base checkout.

`0002-full-source-pcd-integration.patch` is a reviewable integration patch based on
`3de44c7df57730b7ebb6f0bc1e6159e182f44c73`. It is **not applied** in this branch.
The independent `robot_dashboard/pcd_editing/` package and
`static/features/map_editor3d/full_source.js` must be present before applying it.
No localization, map switching, ROS, Nav2, traffic-light, slalom, deployment, or
publication work is included.

## Apply in the integration owner's checkout

```sh
git apply --check docs/patches/0002-full-source-pcd-integration.patch
git apply docs/patches/0002-full-source-pcd-integration.patch
python3 -m unittest discover -s tests -p test_pcd_editing_integration.py -v
python3 -m unittest discover -s tests -p test_saved_maps.py -v
node tests/test_map_editor3d_workspace.mjs
```

Check the current branch/worktree first and resolve overlap with the other
window's changes in its own integration checkout. This file is an artifact, not
an instruction to modify that window's working directory. Applying the patch
changes only:

- `robot_dashboard/saved_maps.py`
- `robot_dashboard/app.py`
- `robot_dashboard/static/features/map_editor3d/workspace.js`
- `robot_dashboard/static/app.js`
- `tests/test_map_editor3d_workspace.mjs`
- new `tests/test_pcd_editing_integration.py`

## Contract and behavior

- `SavedMapCatalog.pcd_edit_source(id)` resolves a catalogue-owned full binary PCD
  through a trusted server-side `SourceAsset`. It returns exactly `map_id`,
  `revision`, `sha256`, `frame_id`, `units: "m"`, and `asset_role: "full_source"`.
- `GET /api/v1/saved-maps/{id}/pcd-edit-source` returns that descriptor. The read
  route follows existing same-origin read behavior; the mutation route below
  requires the actual Origin header and unlocked competition state.
- `POST /api/v1/saved-maps/{id}/pcd-edited-copy` accepts the independent adapter's
  strict `robot-scope.pcd-edit-request.v1` document. It verifies route/source ID,
  full-source identity, hash, annotation provenance and geometry, then delegates
  to the store. Catalogue I/O runs in `asyncio.to_thread`. Success is HTTP 201
  with `{ "map": metadata }`; stale identities are 409, invalid edits are 422.
- The first explicit managed catalogue root must be writable and scan depth must
  be at least 2. Publications live at `pcd-edits/{new-24-hex-id}/map.pcd` plus
  `manifest.json`. New bytes and manifest publish together. Original maps are
  read only during the edit.
- Rescanning validates manifest revision, output hash, identity, binary header,
  and point count before registering the published ID/revision/frame/units and
  full provenance. Invalid or incomplete publications are omitted instead of
  receiving a fallback path-derived ID. Download bundles preserve semantic
  revision and include the provenance metadata.
- Published copies have `manageable: false`: they can be used as parents for new
  edits, but existing single-file rename/delete operations cannot corrupt their
  immutable manifests.
- The existing editor still displays its sampled/rounded preview and exports
  local annotations/preview JSON as before. An optional save callback adds a new
  name field and explicit full-original PCD save button. Only annotations and
  source identity are sent; preview point buffers are never uploaded as originals.
  The app fetches the current full-source descriptor, uses the strict adapter,
  and refreshes the saved-map list display. It does not select the new map, call
  `refreshSavedMaps()` (which can select maps), change navigation options, install
  a map, or touch localization state. The display refresh explicitly preserves
  even an empty selection. A failed catalogue refresh after a successful save
  reports the saved ID and a refresh warning while preserving the success result.
  Source switches and in-flight draft edits
  do not cause an older save to clear the current draft.

## Coordinate conventions and integration boundary

PCD bytes do not inherently declare a ROS frame or physical units. Existing
legacy catalogue records use the existing product conventions `camera_init` and
metres; this patch explicitly inherits them and performs no frame transform or
unit conversion. Verify the operator's legacy source convention before later
runtime use. Derived manifests preserve the server-resolved frame and unit.

The original optional patch did not adapt the observation reader's
filesystem-signature revision check. The current integration separately adds
semantic-revision, PCD hash, frame and unit verification to `raw_global_reference`
for immutable edited maps, while retaining the legacy revision check. Its compact
provenance identifies the direct parent and original root. This enables explicit
historical observation of an edited reference; it does not install a runtime map
or validate current body pose or tracking.

## Validation performed in an isolated temporary copy

The patch was generated without modifying the branch's existing common files.
Synthetic PCD fixtures only were used: no robot, sensor capture, classroom data,
service restart, deployment, or GitHub write.

- New catalogue and FastAPI wiring tests: **7 passed**. These check original-byte
  preservation; output registration/reload and derivation history; stale identity;
  hash/manifest tampering; explicit frame preservation; download hash/revision;
  real same-origin and unlocked guards; HTTP 201/403/409/422/423/404; and worker
  thread offload. Route functions are extracted from the real patched app into a
  minimal FastAPI ASGI harness, so the robot application lifespan never runs.
- Existing saved-map catalogue tests: **55 passed**.
- Existing and added 3D workspace controller tests: **15 passed**. The added callback harness executes the real
  dashboard callback and overview function to verify successful-save/catalogue-
  refresh failure and empty-selection races without changing normal refresh behavior.

The ASGI test harness includes a short event-loop timer because this restricted
Linux environment suppresses cross-thread self-pipe wakeups. It uses in-process
ASGI transport without a listening network server. These are controller and
contract checks, not a claim of a browser visual smoke test or robot validation.
