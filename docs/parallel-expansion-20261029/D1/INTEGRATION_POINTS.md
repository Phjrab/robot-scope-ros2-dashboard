# D1 integration points (not applied)

## C1 — services/job owner

- `robot_dashboard.multimap_core.solve(request, resolver, progress, cancel_token)`:
  trusted pure-local solver with no process, ROS, model, HTTP or device startup.
  `resolver(descriptor) -> Path` must bind immutable ID/revision/hash to a private
  full-source asset. Do not accept client paths. Enforce acquisition units/axes
  upstream; unknown gravity remains unknown, never an inferred flattening.
- `contract_adapter.to_core_request` / `proposal_to_contract` translate the
  injected C1 types tested at `2402c02c6f91ba54064894b21735e01b98610acd`.
  See C1_COMPATIBILITY.md; no shared validator is duplicated.
- Run bounded numerical work in C1's isolated worker, not an HTTP event loop.
  C1 owns queue limits, deadline/process termination and stale-job revision
  comparison against CURRENT service revision. D1's export `expected_revision`
  guard only compares supplied revisions; it does not know current service state.
- `export(core_proposal, expected_revision, resolver, private_output_root)`
  atomically produces a new immutable result directory; C1 may separately
  register it only after its own approval/current-revision check. Idempotency is
  for the exact proposal (including runtime metadata), not a fresh solve.
- Persist `sources[].provenance = {id, parents:[...]}` when a fused source is
  reused. Root identifiers must retain immutable original identity. Missing
  lineage on an externally fused input cannot be reconstructed from a PCD.
  `(A+B)+C` is supported; `(A+B)+(B+C)` is rejected for review even if duplicate
  transforms agree. No silent root deduplication or invented mapping session.
- Existing `map_lineage.build_family_document` is a future adapter point: use
  the materialized merged PCD as NEW source, with FusionManifest beside it.
  Identity source-to-occupancy is justified only after matching fused frame,
  origin/resolution and explicit named surface. Old families/presets unchanged.

## C2 — map UI

- Source-colored `quality.source_previews` are explicitly sampled previews.
  Never feed them to export. Full export rereads every original record.
- Show source session identities, transforms, directional overlap, residual
  p50/p95 and spatial/normal eigenvalues separately; covariance is unavailable.
- Show alternatives and disconnected components; prompt for anchor-relative
  SE3 seed or at least three well-distributed noncollinear correspondences.
  Initial/manual guesses, computed candidates and operator acceptance are
  distinct. A small RMSE or SOLVED_CANDIDATE is not independent accuracy proof.
- Display residual sample locations as potential rigid-drift evidence, not an
  elastic correction. No trajectory/keyframe reconstruction is provided.
- Manual XYZ/RPY can use existing `from_translation_rpy` (metres/radians).
  Never reinterpret two `camera_init` strings as a common origin.

## Occupancy and semantic boundaries

An explicit `occupancy_surface={name,z_min,z_max,resolution}` on the retained
core proposal selects a named obstacle height band in FINAL fused coordinates.
Output is sparse occupied cells with UNKNOWN everywhere else and zero free
cells. This is not ground classification, inferred traversability, free-space
ray tracing or an automatically usable Nav2 map. Ramp/multi-floor/overhang
selection requires a trusted driving surface and remains unsupported when
unspecified. No horizontal leveling is performed. Source observed-free evidence
resampling, operator-declared free annotations and annotation transforms are
NOT implemented: they cannot become FREE accidentally. Localization masks and
dynamic-object removal are not applied; all full records survive.

No C2 UI, C4 ROS ports, live map installation, robot connection, deployment,
main integration or navigation control is included.
