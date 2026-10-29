# Offline multimap baseline

Core dependencies: NumPy + SciPy; existing PCD binary codec and tested SE3
validator/rigid-fit primitives are imported read-only. No Open3D dependency.

## Fixed algorithm and limits

- 2–8 full sources; binary little-endian PCD, existing 256 MiB/20M-point bounds.
  Hash/options-keyed bounded cloud cache; deterministic stride then voxel
  representatives (default 1,500, maximum 4,000 points). Cached normals and
  rotation-invariant local-neighbour-distance signatures. Full export is NEVER
  sampled. Inputs are immutable and checked again at publication.
- Seeded path: robust weighted point-to-point rigid ICP (existing `_rigid_fit`),
  three correspondence scales (12/6/3 × resolution), 30 iterations each.
  Compared by construction with existing unweighted `register_se3`: keeps its
  rigid SVD fit/SE3 convention while adding robust weights and multi-scale
  gates for map overlap. Not claimed to outperform point-to-plane methods.
- Automatic path: one fixed CPU baseline, PCA-sign hypotheses plus 128
  deterministic local-distance-signature RANSAC trials; best six proposals
  refined by the same ICP. No scale fitting, parameter sweep or perfect-global
  registration claim. Distinct near-equal candidates remain ambiguous.
- Both directional overlaps >= .35, >=12 inliers, spatial eigen-ratio > .002,
  inlier RMSE <1.5 × resolution are required. Gates are resolution-scaled and
  exercised by noisy partial fixtures, wrong-seed/different-place, symmetry and
  plane tests. These fixture choices are NOT calibrated real-world thresholds.
  Normal eigenvalues, condition proxy and residual samples remain separate.
- Graph: quality-ranked spanning initialization, anchor fixed at identity,
  loop residual gating (6 × resolution translation / .15 rad rotation), robust
  least-squares global SE3 adjustment (50 evaluations). All edges uncertain;
  none become odometry because of array position. Outlier rejection is not a
  proof against a high-scoring false spanning-tree edge: unresolved topology
  needs priors/independent evidence. Disconnected sources get no invented pose.
- `T_A_B` is nested row-major 4×4, maps column B into A; distance m, angle rad;
  proper SE3 only. C1 adapter uses flat16. Covariance/information unavailable,
  not fabricated. Independent real-map accuracy UNKNOWN.

## Reproduce

From repository root, no robot and no retained map artifacts:

```sh
OPENBLAS_NUM_THREADS=1 python3 -m unittest discover -s tests/expansion_d1 -v
OPENBLAS_NUM_THREADS=1 python3 -m experiments.expansion_20261029.d1_multimap.reproduce
python3 -m robot_dashboard.multimap_core --help
```

The generator writes synthetic PCDs only in caller temporary storage. The
reproducer exercises two/three partial maps, actual solver/full export and CLI.
Exact C1 compatibility has separate instructions in C1_COMPATIBILITY.md.

CLI: `python3 -m robot_dashboard.multimap_core REQUEST.json --resolver
PRIVATE_MAP_ID_TO_PATH.json --proposal NEW_PROPOSAL.json [--export-root PRIVATE_DIR]`.
Output proposal creation is exclusive. CLI is trusted local-only, not HTTP.
Non-solved candidate exits 2 and cannot export. Invalid input errors fail closed;
C1 should map those to FAILED/REJECTED job terminals, never successful maps.

Full export preserves scalar record bytes including 64-bit intensity/time;
rotates XYZ and complete normal triplets; rejects schema differences and unknown
vector/multi-count layouts rather than silently losing fields. Original raw
snapshots remain private in the output. VIEWPOINT is omitted because no single
sensor acquisition pose exists. Per-source record ranges preserve local epochs.
Atomic staged directory publication, exclusive lock and content hashes require
private local filesystem semantics. No deduplication, masks or raw asset Git
publication. For service revision, lineage and occupancy limitations see
INTEGRATION_POINTS.md.
