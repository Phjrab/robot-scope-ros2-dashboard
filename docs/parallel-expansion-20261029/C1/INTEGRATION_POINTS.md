# Future integration points (read only; BASE_SHA f469155c2b0c505f3e472e878f75029d7b8d39df)

No root mount, product registration, DB migration, activation, ROS graph or robot
connection was applied. Line numbers below refer to the fixed base unless noted.

| Existing function / context | Future arguments / link |
| --- | --- |
| `robot_dashboard/app.py:289` `saved_maps()` | Supplies an existing `SavedMapCatalog`; use a future trusted allowlist `list_ids`, descriptor+`SourceAsset` resolver and bounded preview callback for `CatalogueAdapter`. Never expose catalogue private paths. |
| `robot_dashboard/app.py:1391` `main()` / `SavedMapCatalog.from_profile(...)`, then `:1450` `RUNTIME.saved_maps = catalog` | Future lifecycle owner constructs `BundleStore(private_candidate_root, adapter)` and `FusionJobManager(adapter, exact_SHA_D1_adapter, store, max_queue=4, max_history=32, max_job_bytes=256MiB)`, and calls `close()` on shutdown. No import-time startup. |
| `robot_dashboard/saved_maps.py:397` `SavedMapCatalog.from_profile`; `:438` `_pcd_edit_source_asset`; `:464` `pcd_edit_source`; `:480` `list_snapshot` | Trusted resolver returns existing PCD `SourceAsset` plus `MapSourceDescriptor` with full hash/count/field schema and genuine acquisition metadata. Legacy single-source descriptors continue working as before. SourceAsset path remains server-only. Fusion reload is a separate port, not product registration. |
| `robot_dashboard/app.py:615–616` `include_router(create_map_families_router(...))` and `create_pcd_editing_router(...)` | Only after separate integration approval: `expansion_services.router.create_router(manager, adapter, scene, store, authorize=<host authentication>, require_origin=<host mutation/origin gate>)`. Both callbacks are mandatory. No test bearer may become production auth. |
| `robot_dashboard/api/dependencies.py:37` `require_same_origin`, `:45` `require_competition_unlocked`; `robot_dashboard/http_security.py:8` `is_same_origin` | Future host origin callback must compose applicable competition/lifecycle/revision policy with existing origin checks. Existing origin check alone is not authentication. C1 does not invent or disable production authentication. |
| `robot_dashboard/app.py:237` `api_response_security` | Preserve existing no-store/security response behavior and host request/concurrency limits. New API includes no goal, green/motion, lease or activation endpoint. |
| `robot_dashboard/application/runtime.py:43` `ApplicationRuntime.saved_maps`, `:76` `configure_observation_stores` | Future explicit lifecycle storage for `SceneSnapshotService`; D2/C4 calls `ingest("obstacle_frame", wire_dict)` and D3 `ingest("collision_assessment", wire_dict)`. Other slots carry the documented read-only observation envelope. Explicit increasing map generation and source-epoch reset are required. |
| `robot_dashboard/map_lineage.py:103` `build_family_document`, `:164` `parse_family_document` | Current parser mandates a real non-null mapping_session_id. A multimap fusion has no single such session. C1 emits `legacy_family.status=DEFERRED`, preserves the real source DAG and materialized planar XY identity, and does not fabricate a session or alter this parser. Honest synthetic-origin support requires a separately approved shared schema/adapter change before product catalogue/family registration. |
| `robot_dashboard/pcd_editing/pcd.py:42` `_read_header`; `pcd_editing/store.py:45` `SourceAsset`, `:138` `_open_regular`, `:237` `_registry_lock` | Reused read only for binary full-source schema, safe I/O and atomic directory publication. Existing edit manifests represent one source and must not be reused to mislabel a multimap result as a single-session edited map. These internal helpers are base-pinned coupling to revisit if upstream changes. |

Owned implementation entry points (current source):

- `expansion_services/catalogue.py`: `CatalogueAdapter.resolve/pinned/list/preview`, `ResolvedSource`, `validate_dag`.
- `expansion_services/jobs.py`: `FusionJobManager.enqueue/status/cancel/review/export/close`.
- `expansion_services/export.py`: `BundleStore.get/reload`; `reload` returns a new unregistered full source and expanded provenance DAG.
- `expansion_services/scene.py`: `SceneSnapshotService.ingest/snapshot/reset/reset_source/metrics`.
- `experiments/expansion_20261029/c1_service_host/host.py`: `create_test_host(root, token)` and explicit `main()` demonstrate standalone factory binding.

These are documentation of future links, not automatic integration hooks. Existing
3D Nav2, Goal URDF and final-heading work remains outside C1 ownership.
