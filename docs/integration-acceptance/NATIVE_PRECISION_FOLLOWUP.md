# Native map, policy and precision follow-up — 2026-10-16

The user reopened retained-map extraction, native map reuse, MR-MS-003 and
precision/body-pose work, while excluding driving. The user confirmed that no
independent truth or camera-to-body measurement is available and requested
measurement guidance. Missing measurements block only those physical evaluation
rows; Stereo observation and map creation remain independent.

## Source, ownership and actual baseline

The initial main/origin was `d6eb0e7c162e8e6f708a74d88b948b3c03bcea2f`.
During this work the separate UI owner published
`dba753c4c2f29342cd410da77bb7a80ba9061ae8`; those UI changes were preserved.
No branch, worktree or replacement UI/adapter was created. Root owns combined
validation/publication/deployment; delegated owners returned reviewed code.

Read-only device checks at 2026-10-16T12:18:08Z still showed backend
`cdebee40d212759703300ffc1e2de17ed93a4846`, dashboard PID87657/invocation
`162f310dab5a44ac8526e803f6a05c74`, broker PID87441/invocation
`29240030c5be4cb9b36773e35f35e74b`, bridge inactive/PID0, camera free, SLAM
IDLE. The three previously deployed static UI files are modified/untracked
relative to the backend checkout and are preserved with exact byte hashes.
Deployment must back them up before bringing the checkout forward; no reset,
clean or stash deletion is allowed. Existing maps, missions, bags and VSLAM
installation remain in place.

Dashboard domain0/CycloneDDS, broker socket
`/run/robot-scope-slam/broker.sock`, UID1000 and shared locks remain unchanged.
Isaac remains domain71/FastDDS in its preserved image. Dashboard bridge autostart
is still0, and the physical manual-control handover keeps the bridge OFF.
No operating localization window, initialpose, goal or robot motion was repeated.
The persistent Hesai preview remains untouched.

## Implemented and reviewed

- Native reuse now records bounded request/result diagnostics with exact opaque
  native hash, normalized hint/frame, context digest, service outcome, clock
  fences and fresh-pose confirmation. Parsed native log events remain candidates
  with unknown attribution. The25s service timeout and5s confirmation remain.
  [MAP02_COMPLETENESS.md](MAP02_COMPLETENESS.md) describes the contracts.
- An immutable collision-mask publisher and opt-in Humble profile connect the
  prior artifact to real native consumers. Production policy readback observes
  publisher identity and freshness. Publication is not ingestion or enforcement;
  all enforcement scopes remainfalse. No operating config is replaced.
  [COLLISION_MASK_RUNTIME.md](COLLISION_MASK_RUNTIME.md) defines the next evidence.
- Offline precision evaluation requires independently measured extrinsics,
  world alignment, truth and timing. It validates SE3, exact source artifacts and
  one-to-one timestamp pairing without fitted alignment. Synthetic tests prove
  arithmetic only. [측정 안내](POSE_MEASUREMENT_GUIDE.ko.md) lists the actual
  values to obtain; [POSE_PRECISION_CONTRACT.md](POSE_PRECISION_CONTRACT.md)
  and its blank input example define the evaluator.
- The existing sensor collector now retains complete CameraInfo ROI together
  with binning, K/P/R/D, frame and timestamp. A private comparator checks current
  samples against preserved Oct13/14 stereo CameraInfo and five camera-only TFs.
  Historical projection/TF baseline is0.04991525784134865m; this is not a Go2
  body extrinsic. New live full-matrix capture has not yet run for this candidate.

## Actual offline extractor experiments

Pinned upstream cuVSLAM source `33da60662b27c0c5b63e0597bd778066af2731ed`
(15.0.0) has a supported `map_extractor` source target. Installed SDK remains12.6.
Its compatibility with the existing native DB is unknown. The richer retained
manual map's50,511,872-byte DB was copied and hashed; original package bytes were
not changed. Separate CPU-only scratch builds used bounded low-priority work,
no ROS/GPU/camera and no system install.

Experiment01 stopped during configure after36.129s because the host's optional
OpenCV CMake package referenced an absent library. Experiment02 used the standard
optional-package disable flag, configured successfully, and failed compiling the
upstream CPU branch after213.145s: `ImageContext::support_depth_` is declared
inside USE_CUDA but referenced unconditionally. Both experiments confirmed no
remaining owned session processes and unchanged input/experiment DB hashes.
No extractor binary executed and no export was produced. Any subsequent isolated
CPU source repair must retain its patch/hash and be labeled modified-upstream.

Even an exported JSON would not by itself close MAP-02: SDK DB compatibility,
native64-bit IDs, coordinate-frame definition and an independent retained-total/
completeness guarantee still require evidence. Existing preview exports stay
bounded previews with coverageunknown.

## Validation and next concrete runtime work

Combined project-venv Python suite:2152 tests,2150pass/2skip,77.304s. JS unit387
pass. Focused Chromium SLAM/presentation/mission-route43pass. Ruff, configured
mypy, tracked-secret scan,84-module frontend syntax and diff checks pass. The
first full invocation incorrectly used system Python and had25 import errors;
its failed log is retained, not counted as acceptance. The project-venv run
resolved the environment issue without installing dependencies. Private fake
extractor-boundary20 and native-mask-preparation11 tests are separate from real
native execution. Independent code reviews found and closed cleanup/identity,
interrupt evidence and FIFO blocking issues.

The deployable candidate is `3986a75ff0bfaecd6ceb5ea33958d494cedf4343`,
published to main. Its exact GitHub CI run38900248792 passed on Ubuntu22.04
Python3.10 and Ubuntu24.04 Python3.12, including full browser CI. The candidate
includes these source changes and the separately published UI. Deployment
review closed two findings: the delayed restart API cannot be treated as a
new-process witness, and current lifecycle blockers must be checked before
source mutation. The prepared script now requires changed dashboard/broker
InvocationIDs, current product idle gates and exact environment/source hashes.

### Actual CPU extraction after candidate publication

Experiment03 applied the independently reviewed CPU-only declaration repair to
fresh upstream scratch; the archive and installed VSLAM were unchanged. It built
the extractor successfully, binary SHA256
`08ba6286e9663c98c0b8e46342f18e2c629f7186a70b3f22cb194abde9f79720`.
The first extraction then returned255 with `Failed to load the map!`.
Source inspection found a10GiB read-only LMDB mapping request conflicting with
the runner's2GiB virtual-address cap. That generic error alone did not prove
DB incompatibility. The complete run took367.059s and qualified all owned
process cleanup and copied-input preservation.

Experiment04 reused that exact binary without rebuilding, in fresh scratch.
Only the extractor's virtual-address cap became12GiB to accommodate that mapping;
monitored RSS6GiB, freeRAM2GiB, disk/scratch and60s work bounds stayed unchanged.
It completed in0.621706s with13993 unique exported integer-ID landmarks,175
keyframes and178 edges. Output JSON is2,614,229 bytes, SHA256
`22224cef79077d12ef27f8e760b3d7b2d77a015ece1290c9083d30418e2a506a`.
The input source/copy and binary source/copy hashes were unchanged and owned
cleanup passed. This is **actual modified-upstream CPU extraction**, not an
official unmodified binary or a qualified general12.6→15 compatibility result.
Raw XYZ and a neutrally labeled keyframe-transform CSV are retained privately.
An independent offline check found finite geometry, unit quaternion error at
most2.616e-7, no duplicate serialized IDs/relations/edges, no missing serialized
pose references and one connected pose component. All23676 landmark-to-keyframe
references and both derived files were checked against the unchanged JSON.
There were no exact-zero XYZ rows. These checks validate this output's internal
consistency, not its completeness relative to the original native database.

Independent source review found that the extractor ignores loader/traversal
return values, can skip missing poses and narrows native IDs to int. Its local
variable `rig_from_world` also conflicts with the getter's documented
`world_from_keyframe` direction. No inverse, ROS coordinate conversion or body
pose is inferred. An initially direction-labeled private CSV is explicitly
superseded by the raw neutral CSV; original JSON is unchanged. Timestamp-free
keyframes are not a time-indexed trajectory. Exit0, finite geometry and unique
exported IDs do not prove retained completeness. MAP-02 remains unqualified
pending loader/error/count/ID/frame/weight and source-format evidence.

### Pending grouped device observation

The grouped runtime scope is deployment/dashboard+broker restart; two stationary
same-pose Stereo sessions with native save/requery and one reuse dispatch, full
CameraInfo/TF observation,90s stop-request/150s cleanup targets; then domain84
isolated native global/local costmap ingestion/clear/expiry and product planner
checks. This newly prepared harness also activates the controller lifecycle to
read its local costmap, but sends no FollowPath or NavigateToPose goal and runs
no BT. Its nominal watchdog/cleanup envelope is190.5s plus scheduling/I/O.
That scope needs current field confirmation before execution. No operating
localization window is included. Successful preparation is not actual execution.
The grouped approval was requested once and is pending. At12:38:15Z the device
still had the same dashboard/broker invocations, backendcdebee4 with the three
preserved UI files, SLAM IDLE, camera free and bridge inactive/PID0. No candidate
deployment, new camera session or native costmap window has been executed.

Private raw evidence is under sibling
`robot-scope-hardware-validation-private/followup-native-precision-20261016/`
and `map02-supported-extractor-20261016/`; it remains outside Git. The companion
validation JSON records exact selected source/log hashes and test types. Actual
runtime results must be appended before any acceptance row is promoted.
