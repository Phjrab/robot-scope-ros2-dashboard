# Geometry-only collision-mask artifact v1

Status: SOFTWARE UNIT. This is an offline artifact builder, not a native policy
provider, deployment profile, mask publisher, or enforcement/ingestion witness.
MR-MS-003 remains PARTIAL. This work does not gate Stereo VSLAM observation.

`robot_dashboard/navigation_collision_mask.py` accepts a frozen
`NavigationMapSnapshot`, the existing validated annotation schema, all six exact
map-family pins, and an explicit expected annotation revision. It recomputes the
annotation content revision and rejects missing/mismatched/forged pins. The
artifact digest is SHA-256 of the canonical manifest with `artifact_digest`
omitted. It covers schema/profile, geometry/frame, every source pin, full
annotation revision, numerical boundary margin and all payload hashes. It does
not include wall time, output location, source paths, or a mutable display name.

## Geometry and preserved data

- `source.occupancy.bin` preserves the input ROS bottom-up row-major occupancy
  bytes exactly, including unknown byte 255. Source files are never rewritten.
- `mask.occupancy.bin` is 0 only where the original byte is exactly 0 and the
  entire closed cell is outside every KEEP_OUT polygon. All other cells are 100.
  Unrecognized nonzero source values are blocked, never converted to free.
- Polygon world coordinates are transformed through the inverse map-origin
  rotation and translation. Rasterization tests polygon edges against whole
  closed cells and detects cells enclosed by a polygon. A thin polygon, an edge
  crossing, and a corner touch cannot be missed merely because no cell center
  lies in the polygon. Concave simple polygons are supported; self-intersection,
  repeated vertices, adjacent overlapping edges and numerical degeneracy reject
  the whole build. Clockwise and counterclockwise winding are accepted.
- The recorded numerical margin is at least 1e-9 cells and scales with input
  floating-point magnitude. More than 0.001 cell required margin rejects the
  input. Boundary expansion only blocks additional cells. It is **not robot
  footprint dilation** and cannot establish robot clearance or driving safety.
- The complete annotation revision is bound, including point/advisory edits.
  SLOW_ZONE and WAIT_ZONE remain advisory; no velocity/control effect is created.
- `mask.pgm` reverses row order only when encoding the image (white free, black
  blocked). `mask.yaml` retains resolution/origin and a relative image name.
  Frame identity remains explicit in the manifest. `annotations.json` stores
  the existing normalized annotation contract.

There is no effective radius/footprint fallback. The manifest explicitly states
`footprint_expansion: none`, `runtime_policy_enforced: false` and
`native_ingestion_evidence: not_provided`. A map-server-shaped YAML/PGM pair does
not prove either costmap loaded it or respected its frame and masks.

## Bounds and publication

The builder rejects more than 1,048,576 cells or more than 2,000,000 units of
raster work (sum of each KEEP_OUT bounding-box candidate-cell count times its
vertex count). Existing annotation count/document/vertex limits also apply.
It never truncates geometry or emits a partial successful artifact.

Publication requires an existing real absolute parent and a new destination
directory. Existing files, directories and symlinks are refused. Payloads are
written exclusively with no symlink following; the directory is private and
files become read-only (directory 0500, files 0400). These permissions prevent
accidental edits; the owner can still alter permissions, so consumers must
verify manifest hashes. The manifest is written last as the completion marker.
Ordinary write failure removes this invocation's new output. Process/host crash
may leave an incomplete directory, which must not be consumed and is never
overwritten on retry. No filesystem WORM guarantee is claimed.

## Offline CLI

Run from the source checkout, using real catalog identities and a new output
outside the source map root:

```sh
python3 scripts/build_navigation_collision_mask.py \
  --maps-root /private/maps \
  --output /private/collision-artifacts/new-artifact \
  --family-id <24hex> --family-revision <64hex> \
  --pcd-map-id <24hex> --pcd-revision <64hex> \
  --occupancy-map-id <24hex> --occupancy-revision <64hex> \
  --annotation-revision <64hex>
```

The existing catalog requires `managed_roots` even for geometry and annotation
read APIs. The CLI registers only the supplied root and calls read APIs; it does
not call conversion, annotation update, rename, delete or snapshot publication.
It verifies the PCD revision, map-family geometry and source/map/annotation pins
again before publishing. A validated in-memory snapshot remains a historical
artifact if source data changes later; runtime admission must revalidate its own
current map/annotation identity rather than treating this export as freshness.

No robot service, camera, DDS, TF, initialpose, goal, provider or HTTP endpoint is
changed or contacted. Generated payloads are private evidence and must not be
committed to the source repository. No real catalogue export or native execution
is implied by software regression results.

## Verification and remaining minimum work

`tests/test_navigation_collision_mask.py` exercises exact pins and forged
annotations; known/unknown/source preservation; whole-cell, thin-edge,
corner-touch, rotated-origin and concave geometry; malformed polygons; advisory
semantics; deterministic digests; numerical/work bounds; immutable publication
and failure cleanup; and a synthetic real-catalog export with byte/mtime/mode
source preservation. These are software tests, not runtime enforcement evidence.

Local verification on 2026-10-16: `.venv/bin/python -m unittest discover -s tests
-p 'test_navigation_collision_mask.py' -v` passed 21 tests; Ruff passed for the
three new Python files; the CLI `--help` smoke passed. No device export, native
mask publisher, policy-positive test or deployment was run by this unit's author.

Combined verification ran all 2,091 Python tests. The macOS sandbox denied Unix
socket bind in 24 existing broker tests; rerunning only those 24 with local socket
permission passed. Combined result: 2,089 passed and two environment skips
(optional rosbags and Linux-only process sessions). No code change or test
exclusion was used to resolve that environment error. Repository Ruff, configured
mypy and CLI smoke passed. Independent final review found no actionable defect.
The frontend is unchanged from `cdebee4`; its passed JS387/Chromium110 checks are
not presented as new tests of this offline module.

Next units remain: a native publisher and immutable map/annotation binding;
versioned opt-in global/local/BT collision profile with verified effective
circle/polygon footprint behavior; actual ingestion/frame/transform/source
incarnation and clear/restart witness; controller/internal-replan enforcement;
and active-run loss tests. Only those producers and native evidence can justify a
future positive production policy branch. Do not weaken freshness, timeouts or
the existing false policy scopes to consume this artifact.

## Actual catalogue input — offline artifact, 2026-10-16

Source4497f7f built a private artifact from the actual supplied catalogue map:
302×176 cells,0.05m resolution, frame map, source map revision
`cd5a43773f7e4d2e9b21d3b1cb8822a4ef0ce1bf6a7cf5de61eafd7a5b71db2c`.
A read-only cdebee4 source-byte-verified extractor captured the remote normalized
snapshot and exact family/PCD/occupancy pins at11:14:47–48Z. Local reconstruction
preserved those identities rather than rebinding them to copied local paths.
Source bytes/annotations were not changed. Extractor fake regression:8 PASS.

Snapshot SHA256:
`e190c8b85952c7cc47031efca79d4ebdd4adf7497bf3e22ba2094c0b9cec4546`;
artifact digest:
`84d4146e4d47543e77c9f3e2ddb6eeac3f3029cc98f2dd85f94e858cddc20427`.
The actual annotation set is empty, revision
`574d8500b8b2e5d081a215c4dcf20abb533bd1ce865404980182476b01959da7`.
This is actual-source offline geometry evidence, not an actual KEEP_OUT test,
native map/costmap ingestion, footprint expansion or runtime enforcement.
All generated map bytes and the reconstruction receipt remain private.
Exact source CI38891097324 passed both Linux/Python matrices; no4497f7f runtime
deployment was performed. The next native integration units above remain open.
