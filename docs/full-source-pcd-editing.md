# Full-source PCD editing (local integration)

Base: `3de44c7df57730b7ebb6f0bc1e6159e182f44c73`; independent module commit:
`af30ce70c0b2ffc9ca0e8283ddb02c12ed03908f`. In this integration branch the
shared Maps UI, catalogue and HTTP patch is already applied. The historical
patch is retained for provenance; do not reapply it here. Both original working
directories and the received v0.3.1 backend remain unchanged.

## Data contract

The existing `features/map_editor3d/core.js` remains the polygon editor.
`full_source.js` consumes `editor.exportVersion()` plus a server-issued original
descriptor. It never uploads the preview's point array or an edited JSON cloud.

The descriptor has exactly `map_id`, `revision`, `sha256`, `frame_id`, `units: "m"`,
and `asset_role: "full_source"`. The request adds `schema:
"robot-scope.pcd-edit-request.v1"`, `name`, `purpose`, and `annotation`. A name uses
1–64 ASCII letters, digits, underscores or hyphens. Preview count and loaded
point count are display metadata only; neither controls processing completeness.

The trusted server resolver, not the request, supplies a `SourceAsset` path.
`PcdEditStore.descriptor()` hashes the full original. `save()` validates the
annotation's map ID/revision/frame against that descriptor, copies a private
source snapshot, verifies its SHA-256, filters every record, then rechecks the
source identity and hash immediately before registration. Stale requests fail
with `PcdEditConflict`. No source write, runtime installation or map switch occurs.

Only regions of the requested `visibility` or `localization` purpose remove
points, using their union. `keepout` remains an annotation. Inside includes polygon
edges and Z planes. Outside complements XY membership only, within the specified
Z slab. The Python implementation follows the existing editor's normalization
and `1e-12` epsilon; undo/redo produce the editor's final region snapshot, which is
stored with its version ID. History describes applied versions, not individual
mouse gestures or undo events.

## Supported PCDs and bounds

The codec supports little-endian PCD 0.7 `DATA binary`, matching the current
catalogue. ASCII and `binary_compressed` fail explicitly. Field order, scalar
types, all non-XYZ attributes, multi-count descriptors and VIEWPOINT are preserved.
Filtering copies entire record bytes. Output is unorganized (`HEIGHT 1`, `WIDTH`
and `POINTS` equal retained records). Nonfinite XYZ records are preserved and
counted, because no finite polygon can select them; they are never silently lost.
An empty result is rejected. Dimensions and payload length must agree exactly.

The service defaults to 256 MiB per original/output, 20 million input records,
100 regions and 256 vertices per polygon. Processing uses bounded record chunks
(at most 8 MiB of raw records). Up to 1,000 applied edit versions and a 2 MiB
manifest/request are accepted. There is no sampling, radius clipping, voxel
downsampling or coordinate transform in the server save path. The raw XYZ
observation and preview readers support non-XYZ multivalue fields and 64-bit
integer attributes without treating their extra values as points. XYZ fields
must each have COUNT 1. Preview remains sampled and has its existing display
limits; it is never the input population for saving or residual scoring. The
preview reader permits at most 256 unique fields and 64 KiB per point record,
matching the codec's bounded record format.

## Standalone registration

```python
from pathlib import Path
from robot_dashboard.pcd_editing.store import PcdEditStore, SourceAsset

def resolve_original(map_id):
    # Look up an allowlisted, trusted full original by opaque ID and revision.
    # Never construct this path from a client filename or preview asset.
    return SourceAsset(map_id=map_id, revision=trusted_revision,
                       path=trusted_original_path, frame_id=trusted_frame)

store = PcdEditStore(Path(private_output_root), resolve_original)
descriptor = store.descriptor(source_map_id)
saved = store.save(validated_request_from_editor)
registered = store.get(saved["id"])
```

The store publishes `<new-24-hex-id>/map.pcd` and `manifest.json` by atomically
renaming a complete hidden staging directory. Writers share a filesystem lock;
existing IDs are never replaced. Failure cleanup removes only this request's
staging/publication. Hidden staging directories are not registered. A crash
before rename may leave an unregistered `.stage-*` directory; it can be removed
offline after confirming no writer is active. A crash after the rename leaves a
complete registered pair. File and directory fsyncs provide durability on local
filesystems; network filesystems with weaker rename/flock semantics are outside
this contract. The output root must be private service-owned storage.

Each manifest records a fresh ID, a content-derived semantic revision, output
SHA-256, frame, metres, direct source descriptor, original root descriptor,
complete applied edit history, counts and creation time. The PCD hash and
manifest revision serve different purposes: revisions include provenance, while
SHA-256 describes file bytes. Existing source catalogue revisions remain opaque
filesystem-signature hashes. PCD VIEWPOINT is retained but is not treated as a
frame transform. Legacy PCD frame/unit assumptions must be established by the
catalogue owner before offering their descriptors (the base catalogue uses
`camera_init` and metre-valued XYZ).

Registered copies are immutable (`manageable: false`): derive a new copy for
further edits. `read_manifest()` verifies the manifest revision and PCD hash;
`list()` omits incomplete/corrupted registrations. A store's `source_resolver`
should pass the verified parent `origin` and `edit_history` into `SourceAsset`
for subsequent generations. No physical server paths appear in public metadata.

## Verification and integration

All new fixtures generate synthetic records under temporary directories. No
sensor recordings, teaching material or credentials are needed. Run:

```sh
python3 -m unittest discover -s tests -p 'test_pcd_editing_*.py' -v
node --test tests/test_map_editor3d*.mjs
```

This checkout includes the independent module, common wiring and historical
observation fixes. The saved-map list refreshes after registration without
installing or selecting the new map. An operator may subsequently select a copy
explicitly. A historical observation pins its semantic revision, frame/unit
declaration and original PCD hash, then scores the entire selected reference's
XYZ population. The underlying PCD coordinates are not transformed or rounded.

A derived map is a different reference from its parent. A lower residual against
that copy does not establish improvement against the unchanged parent reference.
Keep their IDs/revisions/hashes and results separate. Frame/unit declarations
remain unverified physical conventions. No edited map is installed in the robot's
localization runtime, and no historical result becomes a verified current pose
or temporal track. Operational map switching, Nav2 and robot actions remain
outside this local integration.

Catalogue scans verify each edited PCD's complete content hash. Polling many
large copies can therefore cause substantial disk I/O; no metadata-only cache
has been introduced to weaken the verification. Target-device load and actual
saved-data replay remain field validation tasks.
