# MAP-02 retained-landmark completeness

Updated 2026-10-16 KST. **PARTIAL / full-retained acceptance BLOCKED.** Global map
visualization and access to every retained native landmark are separate results.
This follow-up fixes a false completeness condition and investigates the actual
installed SDK without starting a container, camera, ROS pipeline or GPU job.

## Evidence and verified boundaries

| Evidence | Exact identity | What it establishes |
| --- | --- | --- |
| Integration source baseline | main `2555f3763996c7b331389924bb5df48d62094736` | Existing adapter, broker, feature stream and map packages are reused |
| Preserved visual SLAM reference source | `e31f4cc1d41a329a01946e5fe63669f8b15da677` | Source contract only; does not identify an installed executable |
| Stopped installed runtime container image | `sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5` | Image identity read on 2026-10-15, no restart |
| Installed SDK header | `/opt/ros/humble/share/isaac_ros_nitros/cuvslam/include/cuvslam.h`, 36,953 bytes, SHA256 `fd1bd9eb4db0f396c8047d1500583c603b9f8a5680ad43203ecbce00a69dbaa2` | API documentation inspected from stopped filesystem |

The header and remote command output remain in the private evidence directory
`robot-scope-hardware-validation-private/integration-20261015/`; the SDK is not
vendored into Git. Its files are `cuvslam-installed-header.txt`,
`ms-source-sdk-readback.txt` and `ms-source-readback.txt`.

Reference source was also read through GitHub at the exact SHA:

- [visual_slam_impl.cpp lines 110–120](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam/blob/e31f4cc1d41a329a01946e5fe63669f8b15da677/isaac_ros_visual_slam/src/impl/visual_slam_impl.cpp#L110): LL_OBSERVATIONS requests 2,048 items and LL_MAP 32,768. These are visualization read limits.
- [landmarks_vis_helper.cpp lines 80–170](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam/blob/e31f4cc1d41a329a01946e5fe63669f8b15da677/isaac_ros_visual_slam/src/impl/landmarks_vis_helper.cpp#L80): EnableReadingDataLayer precedes StartReadingLandmarks, and FinishReadingLandmarks releases the borrowed array. PointCloud2 exports XYZ and RGB; native ID and weight are not separate fields. Grayscale/RGB derived from IDs cannot reconstruct IDs or confidence.
- [CMakeLists.txt lines 39–51](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam/blob/e31f4cc1d41a329a01946e5fe63669f8b15da677/isaac_ros_visual_slam/CMakeLists.txt#L39): SDK path comes from the `cuvslam/isaac_ros_nitros` ament resource. The installed resource readback is `share/isaac_ros_nitros/cuvslam`.

Installed header findings are narrower than a claim that complete export is
impossible:

| Supported API/structure | Verified semantics | Missing completeness evidence |
| --- | --- | --- |
| `CUVSLAM_StartReadingLandmarks` / `FinishReadingLandmarks` (lines 925–945) | Thread-safe, lock-free borrowed data-layer array; must finish reading; fills array fields | No retained-total, truncation flag, page cursor/end, map revision or full-generation guarantee in this header |
| `CUVSLAM_EnableReadingDataLayer` (lines 904–913) | `max_items_count` means maximum item count | No documented `0 = unlimited` or other uncapped sentinel; do not guess |
| `CUVSLAM_LandmarkInfoArrayRef` (lines 528–532) | Timestamp, `num`, pointer to landmark list; native signed int64 ID, weight, XYZ in `LandmarkInfo` | `num` is returned-list size; it is not an independent retained engine total |
| `CUVSLAM_GetLastLandmarks` (lines 853–860) | Current visual-odometry 3D tracks, explicitly for visualization; caller preallocates `max` | Not a retained-map exporter |
| `CUVSLAM_GetLastLeftObservations` (lines 842–851) | Current visual-odometry 2D tracks, explicitly for visualization | Not map coverage and not what the present XYZ reprojection overlay reports |
| `GetAllPoses` / `CUVSLAM_GetAllSlamPoses` | Optimized camera poses, bounded by requested count | Poses are not landmarks; no retained landmark total |
| `SaveToSlamDb` | Official native DB persistence | Native DB is not a documented full XYZ/PCD export API |

The installed binary's actual LL_MAP selection, small/large-map truncation,
deletion and optimization behavior remains **NOT_RUN**. No supported iterator,
tile/page exporter or freeze/revision API was found in this inspected header or
reference ROS interfaces. Undocumented exports/symbols and internal DB layout
were not treated as supported APIs. A vendor contract or supported SDK extension
could still supply the missing guarantees.

## Software change and regression

`FeatureStream.replace_global` previously accepted `coverage=complete` whenever
`engine_total_count == source_count`. That also accepted a cloud with rejected
nonfinite/out-of-range points and an unsubstantiated count copied from the cloud.

The store now requires an explicit `NativeFullSnapshotEvidence` adapter
attestation for a complete claim: a qualified native API contract, native frozen
snapshot ID, matching engine revision and source stamp, an independent retained
count source, and bounded immutable unique native integer IDs matching the raw
source and retained counts. A SHA256 over source identity, layout and raw cloud
bytes binds that evidence to this exact export, so an equal-count/equal-stamp
replacement cannot borrow an old attestation. The store validates consistency; an attestation is
not itself proof that a vendor API is qualified. No current Isaac adapter emits
this attestation. The envelope is an internal adapter contract, unavailable to
HTTP clients and independent of selection/operational pose authority.

Missing attestation downgrades a complete request to `unknown`; a greater known
retained count or rejected XYZ makes coverage `subset`. The reason and bounded
evidence summary are visible in snapshots. Invalid evidence fails atomically,
and consumer mutations cannot change the cached evidence. Native IDs are not
recovered from color or exposed as current-observation IDs.

Display LOD and region queries operate on the same retained exported snapshot.
They preserve its source coverage and snapshot identity. Replace semantics still
remove deleted/moved points, epoch resets still clear old generations, and
unchanged map age remains independent of the runtime heartbeat. No append union,
increased exporter cap, synthetic point detection or total substitution was
introduced. `IsaacStereoAdapter` still supplies `coverage=unknown`, cap 32,768,
and `engine_total_count=null`.

| Verification | Result | Interpretation |
| --- | --- | --- |
| `test_slam_features.py` | 42 PASS with repository Python 3.13 venv | Synthetic contracts, projection, identity/count/generation mismatches, rejected points, atomic replacement, LOD/region and detached evidence |
| `test_slam_ros_runtime.py` | 26 PASS | Existing fake ROS/runtime contract; no installed runtime was launched |
| `test_slam_packages.py` | 17 PASS | Existing synthetic native-file preservation and package integrity tests |
| Python compile / scoped `git diff --check` | PASS | Static syntax and whitespace |
| Actual product native full-map export | NOT_RUN / BLOCKED | No qualified complete exporter or approved runtime window |

Local logs: `/private/tmp/robot-scope-map02-{features,runtime,packages}.log`.
An initial system-Python broad SLAM attempt had missing FastAPI and sandbox Unix
socket errors; it is not a product failure or a passing broker check. Whole
candidate verification belongs to the integration owner.

## Smallest supported next work

1. Obtain the installed SDK/vendor guarantee for LL_MAP selection, exhaustion,
   deletion and optimization semantics, including whether an uncapped or paged
   supported API exists. Retain total `null` until an independent source exists.
2. A bounded wrapper extension can already preserve native ID/weight, exact
   timestamp, frame conversion and replace semantics while the borrowed array
   is valid. That improves diagnostics but remains `unknown/subset` coverage
   until the preceding guarantee is established. Do not label it a full export.
3. For a supported full snapshot, freeze and identify a native generation,
   verify total provenance and unique IDs, finish the read before releasing the
   snapshot, then publish atomically. The current envelope supports only this
   complete snapshot case; unknown-total exhaustion evidence needs a separately
   reviewed contract rather than a made-up retained count.
4. If only paging/tiles are supported, use a single pinned revision, bounded
   page size/memory/time, explicit terminal cursor, duplicate/missing-ID and
   page-count validation, checksum manifest, and atomic generation replacement.
   Abandon the candidate on revision changes. Validate delete/update and loop
   correction; do not accumulate unrelated capped snapshots.
5. Under the separate stage 40/41 conditions, compare actual installed exporter
   output against that qualified contract with a map larger than the current
   cap and known landmarks outside the current view. Prove same-generation
   original detail retrieval, then record exact source/image/library/config
   hashes and resource bounds. Only that evidence can close MAP-02.

Other LiDAR/MR acceptance can proceed independently. MS's full original retained
map requirement remains unfulfilled and must not be reported COMPLETE.

## Saved visualization export follow-up

The existing dashboard native ZIP already preserves the official native DB,
manifest and saved preview JSON. The saved manual-observation preview has13,993
exported global XYZ points, a1024-point bounded SLAM path and one saved camera
pose. The independent private collector's230 camera samples are separate
evidence; a saved preview does not contain that full sample series. The exact
runtime and observation record remain in `STEREO_OBSERVATION.json`.

`GET /api/v1/slam/packages/{id}/preview-export?expected_revision=<revision>` now
adds a separate read-only ZIP with XYZ, trajectory CSV, single camera-pose CSV
and provenance JSON. It reuses the package store's revision/hash checks and
private spooled download path. The native ZIP format/import path is unchanged.
The export never starts an adapter, contacts hardware, reads native DB layout,
adds points or synthesizes native IDs. Each source stamp/frame/epoch remains
bound to the saved layer; current runtime identity or download time is not
substituted for missing capture evidence. The saved approximate preview
relationship remains approximate.

The exporter independently rejects nonfinite/out-of-range coordinates,
frame/epoch mismatches, invalid pose geometry and CSV identifiers, more than
60,000 points per layer and output beyond32MiB/store limits. File hashes and row
counts are recorded. A source `complete` declaration is retained only as a
declaration; derived coverage remains unknown, engine total remains null and
native completeness is explicitly unverified. Source subset coverage stays
subset. This completes usable export of saved visualization data, not MAP-02's
full retained native export.

Focused software regression: saved-preview export5 PASS, SLAM API16 PASS and
existing native packages20 PASS. These cover exact coordinates/source stamps,
unknown capture time, no native reads/runtime calls, bounded validation,
revision/hash conflicts, source completeness claims and unchanged native ZIP
roundtrip. No full source suite, deployment, SDK installation, camera or robot
operation was repeated for this follow-up. Full-retained acceptance still
requires the vendor/SDK guarantees and qualified runtime comparison listed above.

The same serializer was also checked offline against the retained real manual
preview:13,993 XYZ rows,1024 bounded trajectory rows and one camera-pose row,
with unknown coverage, approximate consistency and null capture time preserved.
This is saved-evidence software verification, not deployed runtime acceptance.
The derived ZIP and hash/identity record remain private as
`vslam-followup-20261016-1852/manual01/product-preview-export-offline-v3.zip`
and its `-verification.json` sibling. Original native/preview evidence is intact.
