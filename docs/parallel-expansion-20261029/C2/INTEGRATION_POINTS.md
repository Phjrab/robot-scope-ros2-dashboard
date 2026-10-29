# C2 future integration points

Status: UI_MODULE_TESTED / PRODUCT_WIRING_DEFERRED / DEVICE_NOT_RUN.
Base: `f469155c2b0c505f3e472e878f75029d7b8d39df`. All locations below remain read only.

| Existing context | Future binding after separate product integration approval |
| --- | --- |
| `robot_dashboard/static/app.js` `refreshSavedMaps()` (base line 2995), `savedMapCatalog`, `savedPointDataUrl()` | Provide a dedicated local fusion catalogue adapter with full pinned descriptor/session/hash/point schema and a bounded preview. Do not call the existing refresh function as C2's refresh callback: it also synchronizes navigation selection. C2's `catalogue.list()` only updates its own list. |
| `app.js` import/call `initializeMapEditor3D`, `features/map_editor3d/workspace.js` | Create a separate host element and call `mount(host,{catalogue,jobs,renderer,onReview})`. Include `multimap_fusion/style.css`. Preserve the single-cloud editor and its full-source save path. No such call was added. |
| `scene3d.js` `RobotScene3D.setPointCloud`, `resize`, `destroy` | C2 `createRobotSceneRenderer(RobotScene3D)` uses these public APIs, `showRobot:false`, bounded 12,000 merged preview points. Existing 3D orbit/projection is reused. Per-source colors/opacity and manual-vs-solved layers appear in the separate XY canvas. The shared renderer currently has one diagnostic `setPointCloudOverlay` only; it is not overwritten for C2. |
| Future shared renderer hook (currently absent) | If per-source color is required inside the orbiting 3D view, add a separately reviewed public `setMapOverlayLayers([{source_id,color,opacity,visible,points,T_fused_source,kind}])` with bounded buffers. Keep map layers separate from Goal/Initial URDF and sensor/robot pose layers. C2 does not call private `_project` or replace URDF hooks. |
| Existing theme/typography and coordinate conventions | Scoped CSS inherits `--text`, `--muted`, `--line`, `--panel`, `--panel-strong`, `--font-ui`, `--font-mono`. The test host reads existing `styles.css`. XY uses meters, +Y up, a single isotropic scale in CSS pixels and inverse rotation for drag; HiDPI affects the raster only. |
| C1 exact `54629c793ad4ae0ea88127f00ed1b7f8805fc4e2` | Use `createC1Ports(request)` for the published source/job/review/export API. The transport owns authentication/origin. Full C1 descriptors remain unchanged under `wire_descriptor`; no sampled point buffer is sent to job/save. Review advances proposal revision and export uses the server revision. No public product mount/auth change was made. |
| C1 `CatalogueAdapter.preview` | A trusted provider must supply `{schema:'robot-scope.multimap-ui.v1',units:'m',input_pin:{id,session_id,revision,sha256},points:[x,y,z,...]}`. Missing preview fails closed. A null C1 mapping session is displayed as `unverified:<map_id>`, never claimed as real acquisition provenance. |
| C1 `BundleStore.reload` / legacy map family | Export manifests have a new ID/revision/output PCD hash and `operational_installed:false`. C1 does not automatically register exports in its source/product catalogue. C2 verifies the export by GET, retains its ID and reports a catalogue refresh without inventing a new source registration. A trusted future reload/catalogue adapter must publish the genuine new source/DAG before it can be fused again through C1. |
| D1 exact `cbedd05ba6f97dad5506e8003302f689ed8fcb4c` | The test host injects D1 `solve_contract` into C1 `FusionJobManager`. D1's `manual_review` intentionally yields NEEDS_PRIOR, so explicit automatic jobs map to `auto` / `seeded`. D1 progress pair-count events are translated to C1 scalar progress in the test host. No algorithm is implemented in C2. |

No integration with active localization/navigation maps, TF, initialpose, goal,
control, deployment, product entrypoints or existing heading work was performed.
The loopback proxy in the test server is an explicit test-only binding to a
127.0.0.1 C1 test URL and a public synthetic bearer; it is not product auth.
