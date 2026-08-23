# Phase 15 — Map Operations: POI, Home and Safety Zones

Phase 15 adds a revisioned operational annotation layer beside managed 2D
occupancy maps. It does not modify the source PGM/YAML pair, generate Nav2
configuration, install a costmap filter, start a process, or change a motion
gate. Robot-connected verification remains deferred until the user requests a
supervised hardware session.

## Ownership and file layout

For a managed `map-server-pgm` pair, `SavedMapCatalog` owns one optional private
sidecar:

```text
classroom.yaml
classroom.pgm
classroom.annotations.json
```

`map_annotations.py` is a pure schema and geometry boundary. It has no
FastAPI, ROS, subprocess, shell or filesystem dependency. `SavedMapCatalog`
remains the only path authority and supplies the pinned occupancy geometry.
`MappingCoordinator` serializes annotation writes through the same application
coordination lock as map mutations and rejects them while Navigation or another
map operation is active.

The original PGM/YAML bytes and their map revision are unchanged by annotation
updates. Rename validates and republishes the sidecar under the new map ID and
map revision inside the existing rollback transaction. Delete backs up and
removes the sidecar with the map pair. Unsafe symlinks, owners, modes, file
types, sizes and corrupted content fail closed.

## Versioned document contract

Schema version 1 has only fixed fields:

```json
{
  "schema_version": 1,
  "map_id": "24-lowercase-hex",
  "map_revision": "64-lowercase-hex",
  "annotation_revision": "64-lowercase-hex",
  "revision": "64-lowercase-hex",
  "points": [],
  "polygons": []
}
```

`annotation_revision` and the compatibility alias `revision` are the SHA-256
of the canonical document excluding both revision fields. An absent sidecar is
represented by a deterministic empty revision, so the first update also uses
compare-and-swap. PATCH requires both the exact current `map_revision` and
`base_annotation_revision`; stale clients receive a conflict and must reload.

Publication uses a private same-directory `O_EXCL` temporary file, complete
write, file `fsync`, map and annotation target recheck, atomic `os.replace`, and
parent-directory `fsync`. The temporary file is removed after every failure.

## Types and semantics

Point annotations:

- `POI`: named navigation destination;
- `HOME`: the single operator-defined home pose for this map;
- `DOCK`: a named approach pose only; it does not actuate or negotiate with a
  charger;
- `INSPECTION_POINT`: named inspection destination.

Polygon annotations:

- `KEEP_OUT`: operator-authored safety-zone metadata;
- `SLOW_ZONE`: operator-authored reduced-speed metadata;
- `WAIT_ZONE`: operator-authored waiting-area metadata.

Polygon labels and colors are display and future Mission Manager metadata in
version 1. They do **not** alter Nav2 global/local costmaps or controller speed.
Costmap-filter integration requires a later explicit opt-in design and cannot
be inferred from a saved polygon.

Validation requires finite bounded coordinates, vertices inside the pinned map,
3–64 vertices per nonzero-area polygon, at most 64 points, 32 polygons, 96
total annotations and 2,048 total polygon vertices. Names are NFC-normalized,
1–64 characters and limited to letters, numbers, spaces, `_`, `-`, `.`, `(`
and `)`. Every point must be on a known-free cell,
annotation IDs are server-generated opaque 24-character lowercase hex values,
and only one `HOME` is allowed.

## Stable API and goal path

The fixed endpoints are:

```text
GET   /api/v1/saved-maps/{map_id}/annotations
PATCH /api/v1/saved-maps/{map_id}/annotations
POST  /api/v1/navigation/goal/annotation
```

PATCH is a full-document replacement with both revision pins. The annotation
goal request contains only map ID, map revision, annotation revision,
annotation ID and strict `confirmed: true`. The server resolves the saved point
under both revisions and then calls the existing Navigation goal path. That
path still requires the shared localization pipeline, runtime capability,
active pinned map and known-free robot-radius clearance before the ROS gateway
can send a goal. No file path, ROS topic, Nav2 parameter or arbitrary command is
accepted.

This read/list/update/resolve contract is the stable Mission Manager boundary.
Mission sequencing is not implemented in Phase 15.

## Browser behavior

The Navigation static-map canvas displays saved points and polygons. Editing is
available only for a managed 2D map while Nav2 and application mutations are
idle. Point placement requires a known-free canvas cell; polygon drawing is
bounded to the map. Dirty edits must be saved or discarded before Nav2 starts
or a different map is selected. A saved point's `GO` button is enabled only
through the existing Navigation goal readiness gate and sends the exact saved
annotation revision.

The editor explicitly labels zones as display-only and never claims that a
KEEP OUT or SLOW zone is enforced by Nav2.

## Compatibility and deferred acceptance

- Existing map data, map ID/revision, Navigation pose/goal endpoints and
  control/mapping/navigation safety boundaries are unchanged.
- Saved-map list entries receive one additive `annotations_url` for supported
  occupancy maps.
- Map rename/delete now include the optional sidecar in their existing atomic
  transaction; clients that do not use annotations continue to see a
  deterministic empty document.
- No migration scans arbitrary files. Only the fixed sibling sidecar name is
  recognized.
- Hardware-free tests cover schema bounds, CAS conflicts, filesystem safety,
  atomic publication, rename/delete, coordinator locks, API inventory, UI
  projection and fake-backend browser flows. Robot motion and live Nav2 were not
  run.

The later supervised check should confirm only the existing annotation-goal
path on the same deployed commit and map revision. It must not be used to claim
costmap-zone enforcement, which is outside this phase.

## Hardware-free acceptance

The final Phase 15 verification completed without starting a service, mapping
process or Nav2 process and without sending a robot command:

| Check | Result |
| --- | --- |
| Full Python unit/contract suite | PASS — 640 tests |
| Full JavaScript unit/contract suite | PASS — 162 tests |
| Playwright dashboard E2E | PASS — 12 scenarios |
| Dashboard JavaScript syntax | PASS — 20 modules |
| Python compileall | PASS |
| Repository secret scan | PASS |
| `pip check` | PASS — no broken requirements |
| npm production audit | PASS — 0 vulnerabilities |
| `git diff --check` | PASS |

Ruff, Mypy and Gitleaks were not installed in this environment. Their absence
was recorded rather than replacing them with a weaker or newly downloaded
tool. Existing failure-containment tests intentionally emit synthetic dataset
exception logs while still passing.
