# MAP-02 retained-landmark completeness

Updated 2026-10-16 KST. **PARTIAL / full-retained acceptance BLOCKED.** Global map
visualization and access to every retained native landmark are separate results.
This follow-up fixes a false completeness condition and investigates the actual
installed SDK without starting a container, camera, ROS pipeline or GPU job.

## Current actual bounded export — 2026-10-16

The approved cdebee4 stationary run completed UI native Save, package requery,
native ZIP and preview ZIP. Independent84 checks validated162 finite XYZ rows,
1024 bounded trajectory rows, one camera pose and exact archive/member hashes.
A later observed session showed526–646 global preview points and saved another
native package. These are actual bounded visualization/save/export results,
not every retained landmark. Coverage remains unknown, engine total null and
preview consistency approximate. New-session native localization failed Error3;
that does not erase the successfully exported bytes. See
[NONMOTION_FOLLOWUP.md](NONMOTION_FOLLOWUP.md) for exact identities and cleanup.
The SDK completeness gap below remains; no unsupported native DB parser or
unlimited sentinel was introduced.

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

## Latest official source and offline extraction qualification

The official source was checked again at Isaac ROS commit
`9058506efd0b967ac894a717bdbe98df017637e5` (release5.0,2026-09-22).
Its ROS package is now `isaac_ros_cuvslam`; the installed3.2.6 runtime and SDK12.6
were not upgraded. Its [.gitmodules](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam/blob/9058506efd0b967ac894a717bdbe98df017637e5/.gitmodules)
pins [cuVSLAM33da60662b27c0c5b63e0597bd778066af2731ed](https://github.com/nvidia-isaac/cuVSLAM/tree/33da60662b27c0c5b63e0597bd778066af2731ed),
whose VERSION is15.0.0. These are different source/API versions; a new source
contract does not establish compatibility with preserved12.6 native DB bytes.

The [new public API](https://github.com/nvidia-isaac/cuVSLAM/blob/33da60662b27c0c5b63e0597bd778066af2731ed/libs/cuvslam/cuvslam2.h)
still documents a maximum allocation for `Slam::EnableReadingData` and returns
landmarks plus a timestamp from `ReadLandmarks`. It supplies no documented
independent retained total, page cursor/exhaustion or frozen-generation token.
Its `Odometry::GetFinalLandmarks` describes final VO landmarks across frames;
that is not a contract for every retained saved SLAM landmark. The latest ROS
visualization helper still publishes XYZ/RGB rather than immutable native IDs.
No unlimited sentinel or count copied from the returned vector was inferred.

A useful new candidate is NVIDIA's official
[tools/map_extractor](https://github.com/nvidia-isaac/cuVSLAM/blob/33da60662b27c0c5b63e0597bd778066af2731ed/tools/map_extractor/map_extractor.cpp).
It opens a saved DB with `READ_ONLY_EXISTS`, queries its spatial index and
writes `map.json` in its working directory. It uses the vendor's own classes;
the dashboard has no new internal DB parser. The tool serializes landmark IDs
with `static_cast<int>`, so its JSON does not establish lossless64-bit IDs.
No12.6→15.0 saved-DB guarantee, independent total, pinned snapshot identity,
coordinate-conversion qualification or resource guarantee was found in the
inspected API/README/build/tool sources. Successful execution alone would be an
observable saved-map export with unknown coverage, not full-retained acceptance.

Private preparation is in `map02-supported-extractor-20261016/`. The exact
official source archive is250,635,594 bytes, SHA256
`b38c50db8264c011b6efeadf524beaee40522ab6a01bf03be8ecbbba09833cc1`.
Its895 regular/directory members and257,157,690 uncompressed bytes were checked.
The manual native ZIP was read only as opaque bytes into a new0400 scratch
copy:50,511,872 bytes, SHA256
`c93dd90078f17f56480feced9fef08c421124188190c2ce02ed8aeb1f4b6d1ef`.
Original native ZIP/package/preview hashes were unchanged. The local prepare
check passed without building or executing cuVSLAM. Public source/dependency
URLs, pinned hashes and a bounded experiment runner remain private; no SDK,
maps, generated JSON or build tree is committed.

The integration owner separately ran the initial CPU-only configure experiment
in a new Jetson scratch tree. It failed after36.129 seconds because the host's
optional OpenCV CMake config referenced missing `libopencv_core.so.4.8.0`.
Owned-session cleanup was verified and both native copies remained unchanged;
no native extractor ran. A second, fresh experiment used the standard
[`CMAKE_DISABLE_FIND_PACKAGE_OpenCV=TRUE`](https://cmake.org/cmake/help/latest/variable/CMAKE_DISABLE_FIND_PACKAGE_PackageName.html)
option in a fresh configure. The extractor target does not need OpenCV, while
its optional tests/tools try to discover it. `BUILD_TESTING=OFF` alone does not
skip the project's unconditional test subdirectories. The operating OpenCV
installation/configuration is preserved.

Experiment02 configured successfully with those exact sources/options, then
the CPU-only build failed at53% after213.144710126 seconds. The pinned
`libs/sof/image_context.h` declares `support_depth_` only under `USE_CUDA`, while
its constructor and accessor in `image_context.cpp:22,161` reference it
unconditionally. This is an observed upstream CPU-compilation failure; the
native extractor never ran and saved-DB compatibility remains unverified.
Both input copies stayed byte-identical and owned-session cleanup qualified.
Private `experiment02/` retains exact configure/build logs, process records and
report. A minimal CPU-only declaration repair can be evaluated separately in a
new scratch tree, explicitly as modified upstream source, without changing the
preserved source archive or operating SDK. Build success from such an experiment
would still supply no retained-total or completeness guarantee.

The private runner builds only `map_extractor`, parallel2/nice10, with CUDA,
ENFORCE_GPU, NVTX, RERUN, CERES and CUNLS disabled and LMDB enabled. It installs
no system packages and isolates HOME/cache/tmp and CMake/Git registries inside
new scratch. It checks the reviewed archive and opaque copied map, uses
cooperative wall-budget checkpoints, bounds retained logs/output and polls
scratch/owned-session RSS/free resources. Each fresh session/PGID is checked
by Linux start ticks and cleaned on failure or normal leader exit. This covers
the pinned compiler's owned session; hostile `setsid` escape and hard real-time
syscall/JSON-parser limits are not claimed. Twenty hardware-free boundary
checks passed. Build/DB compatibility and qualified complete export remain
separate results requiring actual experiment evidence and vendor guarantees.

## Native localization diagnostic follow-up

The existing service path now produces a bounded structured request/result
diagnostic: normalized map_T_camera_link hint and configured base reference,
opaque native-file SHA256/size, session/generation/epoch digest, request digest,
service-response boolean, elapsed time, source-clock fences and confirmation
reason. Up to64 attempts write separate request/result JSON files (0600,
32KiB maximum each) in the existing private owned run directory. This preserves
evidence even when the service call raises and the coordinator stops the job.
Native hashing reads at most256MiB; oversized/unavailable/changing bytes remain
explicitly unverified and do not invent a hash. This is a pre-request byte
observation, not an SDK map-format interpretation or retained-count source.

The raw runtime log remains capped at1MiB, with available bytes read/flushed
promptly. A separate128-event ring accepts only known localization event/code
patterns from the exact native ROS logger, with4096-byte line and16-event
window limits. It drops paths, raw messages, poses from log text and exception
text. Candidate error names are referenced specifically to the preserved12.6
header; unknown codes receive no invented meaning. Both the log-sequence fence
and the native emitted source timestamp must fit the request's clock window.
Missing/changed clocks and old/foreign logs do not qualify. Since native logs
contain no request ID, correlation and attributed SDK status remain unknown
even when candidate events fall inside the window. A logged success can never
promote a false service response.

The25-second service timeout,5-second fresh corrected-pose/TRACKING confirmation,
frame/epoch fences, failure quarantine and `operational_pose_approved=false`
are unchanged. The API still cannot diagnose the underlying cause of native
Error3 from the boolean alone. Fresh runtime traces under separately current
conditions, a legitimate operator-verified map_T_vslam_lab_camera_link hint and
the exact preserved package/config are the next minimum native-reuse evidence.
The historical manual-map camera pose does not become a current hint after
movement. Focused helper9 and runtime38 software regressions passed, including
private-data exclusion, bounded logs/hashes, old-event rejection, timeout
evidence, a nonblocking FIFO rejection and unchanged success/freshness authority; scoped Ruff/diff checks
passed. The new diagnostic code has not been deployed or exercised on hardware
by this MAP-02 follow-up.

## Actual modified CPU extractor observation

After candidate3986a75 publication, a separate build with the reviewed CPU-only
`support_depth_` declaration repair succeeded. No installed SDK/source was
changed. The modified binary hash is
`08ba6286e9663c98c0b8e46342f18e2c629f7186a70b3f22cb194abde9f79720`.
Its first generic load failure under2GiB virtual AS was not DB incompatibility
proof: the pinned loader requests a10GiB read-only LMDB map. Reusing the same
binary in new scratch with extractor AS12GiB and unchanged RSS/freeRAM/disk/
cleanup controls produced JSON in0.621706s, without rebuilding or camera use.

Observed output:13993 landmarks/unique exported integer IDs,175 keyframes,
178 endpoint edges;2,614,229 bytes, SHA256
`22224cef79077d12ef27f8e760b3d7b2d77a015ece1290c9083d30418e2a506a`.
Input and binary sources/copies were unchanged; owned cleanup passed. The raw
JSON/XYZ and neutral raw-transform CSV remain in private experiment04 evidence.
This is an actual extraction observation with retained coverageunknown.

Do not promote it to complete retained export. The pinned source ignores loader
and query completion status, narrows IDs, can omit poses and can produce fallback
coordinates. The extractor variable name and pose getter's documented direction
conflict; no pose inversion or ROS frame assignment is justified. Keyframes lack
timestamps; edge output lacks transforms/covariances. Independent retained total,
native64-bit ID/weight and frame/unit/rig/source-format contracts remain needed.
See [NATIVE_PRECISION_FOLLOWUP.md](NATIVE_PRECISION_FOLLOWUP.md) for exact
experiment separation, the failed attempts and current pending device scope.
