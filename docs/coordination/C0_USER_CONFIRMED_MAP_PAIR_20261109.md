# C0 user-confirmed map pairing — 2026-11-09

Result ID: `C0-USER-MAP-PAIR-20261109-01`.
Implementation base: `cc7e0fc526eb2fec365f1df84d1dd5f422da83d1`, on the user-designated
`review/20261030-c0-3d-field-sweep` branch.

## Requested behavior

The operator determines whether the selected 2D occupancy map was derived from
the selected 3D map and still uses the same coordinate system. Stage 1 now has
an unchecked confirmation for that relationship. Applying it records the exact
map IDs/revisions, generation and server receipt time as **operator confirmation**.
The server does not require a matching conversion-family document for this path.
It does not infer correspondence from filenames or call the declaration measured
alignment, localization accuracy or a successful robot connection.

Changing either map or revision clears an unsubmitted confirmation. Applying it
consumes the checkbox; refresh never resubmits it or sends INITIAL POSE/goal.
An already applied pair remains usable while its pinned files/calibration remain
valid. Source files, calibration files and saved annotation data are not edited.

The API accepts `pair_confirmation: "derived_same_coordinates"` on the pair
endpoint. Existing clients that omit it retain the conversion-lineage contract.
Operator-confirmed bundles have `map_binding.source = "operator_confirmed"`,
`family = null`, and explicit `calibration.map_transform_source` provenance.
Their map-to-map transform is identity by the operator's declaration, not by a
server measurement. The occupancy YAML origin/resolution remain unchanged;
identity between map frames does **not** mean a zero occupancy-grid origin.
Runtime bundle validation rejects reuse with different pins, generation or
map transform. Body/sensor calibration, file/revision checks, idle ownership,
height/tilt preparation, observation freshness, matching quality and motion
gates remain in force. Invalid map files/sidecars can still fail file admission.

## Rotation and crop findings

`SavedMapCatalog._save_occupancy_copy` saves both edits as new managed files with
new IDs/revisions. Selecting an edited copy therefore requires explicit reapply;
an earlier confirmation does not describe that copy.

- **Crop:** shifts the YAML origin by the removed cell offset, rotated through
  the existing origin yaw. Retained cells keep their world coordinates. When a
  source conversion-family document exists, the crop inherits its 3D source and
  records the new occupancy geometry. A cropped map is not inherently an
  incompatible coordinate system. Reduced coverage can still affect matching
  or whether a goal is inside the map.
- **Saved rotation:** rotates occupancy pixels about the grid center, adjusts
  output size/origin, and keeps the old origin yaw. Walls therefore move in world
  coordinates. The existing implementation deliberately omits the v1 identity
  conversion-family document for rotated copies and their descendants. The old
  lineage path can reject them with `MAP_PAIR_LINEAGE_MISMATCH`. Operator
  confirmation removes the lineage prerequisite but does not compute a missing
  rotation/translation. Such a map must not be declared to share coordinates
  until that relationship is actually established. No new rotation transform
  editor or automatic correction was implemented here.

These findings concern saved-map editing, not rotating/panning the display.

## Validation

All fixtures are synthetic and robot-free; no result establishes physical
alignment accuracy.

| Check | Result |
| --- | --- |
| Complete Python unittest discovery | 3,423 run, 3,421 passed, 2 optional skips; 137.798 s |
| Preparation browser regression | 87 passed; Chromium, localhost fixtures, 1.7 min |
| JavaScript unit tests | 82 passed |
| Frontend syntax | 114 modules passed |
| Ruff / configured mypy / tracked-source credential scan / pip check | Passed |

Python skips are the optional SVG plotting and rosbags backends. New cases
exercise absent lineage, explicitly overridden source-family association,
unchanged body calibration/occupancy geometry, immutable job provenance, stale
map rejection, strict API transport and idle/origin interlocks. Existing tests
for crop origin correction and rotated-copy lineage removal passed. Browser
coverage includes confirmation consumption, revision invalidation, passive
reload and no automatic action dispatch.

The initial sandboxed focused run was interrupted (exit 143) after an asyncio
executor-shutdown hang; it is not counted as a pass. The complete run used normal
local test socket/thread permissions without substituting synchronous workers.
Private first-run/final logs remain outside Git. Remote CI for this new commit
and a deployment on the newer device base are separate pending checks.

## Deployment boundary

No device deployment, observation, Nav2 start, INITIAL POSE, match or goal was
performed for this change. Last read-only release observation was
`59714317c5abefca43b25fe8c78015f7843f387c`; that is newer than the C0 base and is
not a current physical readiness claim. Do not overwrite it with the C0 tree.

Read-only GitHub comparison at that exact SHA found application pair handling,
runtime bundle validation and preparation.js identical to the C0 base. Its API
router additionally guards `MANUAL_SEEDED_2D` in selection/matching; these guards
must survive any future port. Its saved-map converter additionally reports
`finite_points`; crop/rotation behavior above is unchanged. This comparison is
source compatibility evidence, not verification of live imported/disk files.

Before deployment, port this focused change onto the then-current authorized
release base, retain intervening functionality, validate it, and follow the
existing backup/activation/rollback procedure under the current device owner.
No historical deployment tool or old trial window is authorized by this report.
