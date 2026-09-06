# ADR: 3D/2D map-family lineage

Status: accepted for Track D0

## Decision

Robot Scope stores an explicit `robot-scope.map-family.v1` document beside
each lineage-aware managed occupancy pair. The private sidecar is named
`<map>.map-family.json`, is created with mode `0600`, is bounded to 16 KiB,
and is never embedded in the Nav2 YAML or source PCD.

One document pins:

- random 24-hex `family_id` and `mapping_session_id` values;
- exact source PCD opaque ID, filesystem-signature revision and frame;
- exact occupancy opaque ID, revision, frame, dimensions, resolution and origin;
- the fixed planar XY identity projection from the source frame to `map`;
- all converter inputs plus a deterministic canonical SHA-256 parameter hash;
- a semantic family revision and optional predecessor revision.

The mapping-session identity is created when the catalog validates and
snapshots the source PCD for a lineage-aware conversion. It identifies that
bounded PCD-to-occupancy derivation; it does not claim a vendor sensor timestamp
or recover a pre-existing physical capture session that was never recorded.
The direct dashboard conversion and the staged `PCD+2D` saver both publish the
same contract. The staged saver re-pins IDs to the final managed root before
its hard-link transaction publishes the artifacts.

## Lifecycle rules

- PCD conversion creates a new family and never modifies the PCD.
- An edited occupancy copy keeps the family and exact source PCD pins, creates
  a new occupancy/family revision, and records its predecessor.
- Occupancy rename keeps the family but re-pins the new path-derived occupancy
  ID/revision. Existing PCD opaque-ID behavior is unchanged.
- Occupancy deletion removes only its YAML, PGM, annotations and lineage
  sidecars. It never deletes the source PCD or another family member.
- A missing sidecar means `unlinked`. Similar names never create a relation.
- Unsafe, symlinked, oversized, malformed or pin-mismatched sidecars fail
  closed rather than being treated as valid lineage.

## API and navigation boundary

The read-only endpoints are:

```text
GET /api/v1/saved-maps/{map_id}/family
GET /api/v1/map-families/{family_id}
```

They expose bounded semantic records only; paths are never serialized. There
is deliberately no endpoint that binds arbitrary maps into a family.

`NavigationMapSnapshot` privately retains the exact family, source PCD and
occupancy pins. `require_map_family()` is the fail-closed placeholder for a
future D1 relocalization candidate: unlinked maps, a changed source revision,
a changed occupancy revision or another family are rejected.

## Compatibility and safety

Historical maps remain readable and navigable with `None` private family
fields. Their lineage is never guessed. Existing PGM/YAML resolution, origin,
occupancy encoding, map editor behavior and ordinary navigation startup are
unchanged. This ADR adds no ROS owner, registration, initial-pose publisher,
goal, lease, control authority or robot motion.

