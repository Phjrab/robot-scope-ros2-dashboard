# Non-driving follow-up — 2026-10-16

The user reopened all remaining work except driving and confirmed current
stationarity and onsite physical-stop/recovery availability. The operator's
manual-control handover remains in effect: the control bridge stays stopped.
Stationarity alone is not a request to restore it. Existing deployments and
observations remain evidence for their exact source and conditions only.

## Baseline and ownership

Work began on clean main/origin `361c019`; the initial deployed source was clean
`50a30f29580df19450e033fd35777862845b99f7`. Read-only device inspection at
2026-10-16T10:26:59Z found dashboard PID986/invocation
`13ff4f7b1ed74188838d4ab3e37d88f6`, bridge inactive/PID0, SLAM IDLE and camera
free. The broker still runs as UID1000 in the preserved Isaac image. The socket
is `/run/robot-scope-slam/broker.sock`; cooperative camera/domain locks remain
installed. Dashboard domain0/CycloneDDS and isolated Isaac domain71/FastDDS are
separate and unchanged. The preserved VSLAM installation was not rebuilt.

Source owners have separate files; the root integrator owns combined checks,
main publication and any later deployment. No branch, worktree or PR is needed.
Raw evidence, coordinates, images, native maps and environment files remain in
the sibling private validation directory, outside Git.

## Implemented software

- Native Save displays pending/completion/failure, bounds the browser response
  wait and confirms an uncertain response with the exact same idempotency body.
  It never adopts an unrelated catalogue job. Session/generation/engine/epoch
  fencing also prevents a late save response from stopping a replacement session.
  Visual saves explicitly disable LiDAR-only 2D conversion. Uncertain request
  recovery is kept in current-page memory; it is not persisted across reload.
- Saved preview export provides XYZ, bounded trajectory CSV, one saved camera
  pose CSV and provenance with exact package/preview/native revisions and file
  hashes. It uses verified immutable saved bytes without reading the native DB.
  The UI links the expected revision. Export validates finite geometry, frame and
  any explicit pose context. Approximate snapshot time and unknown/subset
  coverage remain explicit. It does not claim a complete retained native map.
- Stereo and overlay diagnostics report bounded cache ranges, freshness,
  candidate rejection reasons and pixel eviction counts. Optional diagnostics
  yield wire budget before existing geometry. They do not change candidate
  selection, 1s freshness, 5ms stereo pairing or 20ms overlay tolerance.
- `ROBOT_SCOPE_CONTROL_BRIDGE_AUTOSTART=0` permits a dashboard restart while
  preserving manual handover. It disables automatic startup only; explicit
  confirmed lifecycle controls and their preflights remain unchanged. Default
  behavior remains enabled. The actual service environment must carry this
  setting before any restart during the current handover.
- Policy readback adds bounded per-endpoint pre-cleanup future state and
  tick/dispatch/authority/batch timing. It does not change the 500ms deadline,
  750ms freshness, semantic revision or enforcement scopes. See
  [POLICY_READBACK_TIMING.md](POLICY_READBACK_TIMING.md).

Independent review reproduced and repaired diagnostics exceeding a supported
small wire budget and optional camera-pose context mismatches. Neither finding
establishes the historical live UI-save or stale-startup cause.

Source candidate `cdebee40d212759703300ffc1e2de17ed93a4846` was published.
Exact [CI38888252489](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38888252489)
passed both Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12 matrices.

A subsequent software-only unit adds an exact-pinned geometry collision-mask
builder and offline CLI. It preserves normalized source occupancy bytes, blocks
unknown/non-free cells and all closed-cell KEEP_OUT intersections, and creates
new immutable hash-bound private outputs. Rotation, thin polygons and boundary
contacts are covered. It has no runtime publisher or policy-positive branch and
is not included in the prepared `cdebee4` deployment bundle. See
[COLLISION_MASK_ARTIFACT.md](COLLISION_MASK_ARTIFACT.md) for geometry, numerical
bounds, source preservation and validation details.

## Actual approved deployment and stationary observation

The user approved the grouped deployment, camera/broker scope, same-position
reuse, isolated domain84 planning and a separate single operating localization
window. On 2026-10-16 around11:04Z, clean source
`cdebee40d212759703300ffc1e2de17ed93a4846` was deployed and dashboard/broker
restarted. Dashboard PID87657/invocation `162f310dab5a44ac8526e803f6a05c74`
and broker PID87441/invocation `29240030c5be4cb9b36773e35f35e74b` were
recorded. Bridge PID0 remained inactive throughout; dashboard environment now
sets `ROBOT_SCOPE_CONTROL_BRIDGE_AUTOSTART=0`. This disables dashboard automatic
startup, not the systemd unit's boot enablement (which still reads enabled).

The preserved Isaac image is
`sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5`.
Runtime logged D435i firmware5.17.3.10, RealSense ROS4.51.1/librealsense2.55.1,
640×480×30 IR stereo, and cuVSLAM12.6. Package engine metadata3.2.6 is a separate
version field. No new complete runtime-binary attestation is inferred from these
logs. The four scope/input/camera/runtime configuration byte hashes, invocation
and source pins are in `NONMOTION_VALIDATION.json`. Dashboard stays on
domain0/CycloneDDS; Isaac stays on domain71/FastDDS with UID1000/shared locks.

All three sessions used `visual_stereo`, mapping/`slam_vo`, IMU fusion false,
and both operating TF publication flags false. Pose reference is
`vslam_lab_camera_link`, not a verified Go2 body pose. Stop guards requested stop
at90 seconds if still active, with150-second cleanup targets. Actual UI stop
completed earlier in all three sessions:

| Actual session | Result | Cleanup age |
| --- | --- | --- |
| `4e8eee4e310b4b5a89330e1857c5ef15`, generation1 | UI native Save SUCCEEDED; save-then-stop legitimately saved a second package; official requery/native ZIP/preview ZIP succeeded | 85.377s |
| `d13575d226454688b2e8e1f9ec90891c`, generation2 | Newly saved package reused at operator-confirmed same pose; official localization failed; UI failure retained | 72.645s |
| `9d1e58c7297f4f09a69eff80f0fc3b97`, generation3 | Approved normal recheck: real image, camera6DoF, tracking, overlay, map, trajectory and UI native Save observed | 77.618s |

Session1's exported package `np_f297168960ef4c668eb6a3f64a492b3e` has
native content revision
`bcc231aba03754c27eacd375f30f49ad2cb04e1616abe520dee12d2884c019af`.
Independent84 offline checks confirmed immutable export member hashes and finite
geometry:162 XYZ rows,1024 bounded trajectory rows and one camera-pose row.
Its native DB is688128 bytes. HTTP downloads succeeded; the browser download
completion itself was not confirmed. Both legitimate session1 saves are kept.
Session3 saved `np_2ac3530408cd43e68f3238a64e5d307d`, native DB1888256 bytes,
and final catalogue requery retained it and all previous packages.

The first two automated collectors exited before observation because the
integrator supplied20 retained full frames above the tool's18 limit. Those
sessions have UI screenshots, save/runtime and guard evidence, **not continuous
collector series**. The corrected third collector used12 and verified startup.
It collected220 WS messages:114 active and106 inactive. All114 active samples,
spanning51.0405 seconds, reported READY for image, camera pose, tracking, overlay,
camera view, current observations, global map and trajectory. Independent19
checks confirmed timestamps, context and ten distinct saved JPEGs. This is
sampled evidence, not a guarantee of uninterrupted readiness between samples.

Stereo/view paired timestamps were equal; overlay spans were40–992ns. In76 of
114 samples the selector used an older actual cached quartet after rejecting a
newer mismatched one. The real session1 diagnostic likewise rejected33.303–
66.606ms quartets then selected a fresh952ns quartet. Existing5ms/20ms pairing
limits and1s freshness were unchanged. Global previews held526–646 points and
bounded trajectories430–1024; coverage/retained engine total remain unknown.
The UI keeps the saved static map/trajectory after stop and marks expired live
channels STALE_SOURCE rather than pretending they are live.

The retained same-device calibration contract came from actual stereo
CameraInfo/static TF with projection-baseline agreement. Current derived
intrinsics, dimensions and frame IDs were stable in all114 samples. However,
the selected current bundle lacks the full raw left/right K/P/R/D and static
chain, so it does not independently requalify current full-matrix equality.
`calibration_revision` is the input-contract hash, not a current CameraInfo/TF
hash. Retain this distinction. A future calibration audit needs those complete
values without rewriting source frames, timestamps or matrices.

USB2.1 and124 inter-frame jitter warnings (maximum133.24ms) remain in the logs.
One CUVSLAM_INVALID_ARG occurred after SIGINT/tracker destruction; both camera
and component processes subsequently exited cleanly. No causal claim connects
these warnings to reuse failure. Camera estimated displacement is not physical
robot motion or independent accuracy evidence.

## Actual reuse result and remaining minimum work

The first reuse click was rejected by frontend INVALID_POSE_HINT after the new
session cleared old fields, with no native dispatch. Re-entering the exact
verified saved camera hint led to one official localization dispatch. It failed
in125.656ms with native Error3 (`CUVSLAM_CAN_NOT_LOCALIZE`), surfaced as
OFFICIAL_LOCALIZATION_FAILED. Native load remains unknown, corrected-pose and
localization success false; a retry requires a new session. The failed attempt
and source timestamp were retained, not restamped or relabeled successful.

Installed public SDK/source review supports the existing camera/base conversion
and asynchronous image arguments. It supplies no justified minimal adapter fix.
Sparse stationary-map coverage is a hypothesis, not a proved cause. Next work
is an exact-package diagnostic with supported vendor detail and a qualified
camera hint; any additional physical coverage needs its own approved operator
movement scope. The failed row does not block observing or saving new maps.

## Isolated product NativePlanner and operating diagnostics

The actual installed Humble native planner ran through the product HTTP route,
default factory and NativePlanner on domain84/localhost CycloneDDS with private
TF topics and a synthetic80×80 map. No controller, BT, bridge, camera or operating
DDS action was used. Result: **ACTUAL_NATIVE_SYNTHETIC_HTTP_ROUTE PASS**. Free
space returned HTTP200 and an original27-pose native path; occupied, unknown and
outside targets were rejected by authoring; disconnected space returned
HTTP409/PLANNER_DID_NOT_SUCCEED. The unknown-crossing case is OBSERVATION_ONLY:
76 footprint-clearance violations, zero explicit UNKNOWN violations, and no
retained original rejected path. It is not unknown-space enforcement proof.

Eighteen independent checks confirmed selected source hashes, native executable/
loaded Navfn/config identity, exact action evidence and owned cleanup. Production
policy remained false with no operational pose. This closes a narrow real native
product-route row, not all operational UI/real-map/controller/KEEP_OUT acceptance.
See [NATIVE_PLANNER_ACCEPTANCE.md](NATIVE_PLANNER_ACCEPTANCE.md).

The separately approved operating localization window ran once11:13:55–11:15:16Z,
including explicitly approved static base→LiDAR and odom→base TF, with no
initialpose, goal or bridge restart. It reached WAITING_INITIAL_POSE in12.367s.
All39 retained policy attempts had the two planner futures pending and the
other eight complete. Retained logs show101 global-costmap waits for missing
map-frame TF, which strongly explains blocked activation but does not establish
a DDS fault or the exact executor cause. No stale startup was observed; historical
stale cause remains UNCONFIRMED. The policy scopes and500ms/750ms limits remain
unchanged. See [POLICY_READBACK_TIMING.md](POLICY_READBACK_TIMING.md).

The collector's final host probe ran with only3.43ms remaining and timed out.
Actual result remains **ABORTED**, with38 fully checked samples and one HTTP-only
partial sample. STOP's3s response timed out, but subsequent exact-owner polling
and process inspection confirmed cleanup in6.431s. A private collector v4 repair
is software/fake-tested only; it does not rewrite this result or authorize a
second window.

## Software validation, actual map artifact and final ownership

`NONMOTION_VALIDATION.json` separates software tests, exact-source CI, deployment
and actual observations. cdebee4 passed Python2070 (2068pass/2skip), JS387 and
Chromium110. Offline mask source4497f7f passed combined Python2091 (2089pass/
2skip, including24 socket tests rerun with local permission), Ruff and configured
mypy. Both exact-source CI matrices passed. Unchanged full checks were not
repeated to manufacture new hardware evidence.

A read-only extraction of the actual supplied catalogue map and its empty
annotation set produced an offline artifact using4497f7f while preserving all
six remote map-family pins. No source map was changed or reidentified by its
local copy path. Artifact digest:
`84d4146e4d47543e77c9f3e2ddb6eeac3f3029cc98f2dd85f94e858cddc20427`.
Empty KEEP_OUT annotations mean this validates source occupied/unknown geometry,
not actual KEEP_OUT enforcement. See [COLLISION_MASK_ARTIFACT.md](COLLISION_MASK_ARTIFACT.md).
No native publisher, ingestion witness or positive policy branch was deployed.

Final readback2026-10-16T11:23:39.844991Z: clean deployed cdebee4; dashboard and
broker active; bridge inactive/PID0 and automatic startup false; VSLAM IDLE;
camera unreserved and host owner probe free; preserved lock files/socket UID1000.
Navigation/localization/goal idle, initialpose0, FAST-LIO pipeline stopped. The
pre-existing persistent Hesai preview remains running without FAST-LIO; this is
not a leftover navigation/VSLAM process. No bridge restoration is pending.
Existing maps, missions, bags, Isaac installation and unrelated local UI edits
are preserved. The unrelated presentation/index/E2E work is excluded from this
acceptance publication and from the cdebee4 deployment evidence.

## Remaining conditions

Actual observation/save/requery/export/stop succeeded. Basic image/pose/overlay/
map/trajectory visualization has sampled live evidence. MAP-02 full retained
export remains blocked on a vendor-supported full/frozen/paged contract plus an
independent retained total/exhaustion witness; bounded preview is not that proof.
MR-MS-003 remains PARTIAL: native mask publishing, global/local/controller/BT
and map-epoch ingestion/enforcement still require implementation and qualification.
All enforcement scopes remain false. Neither is a Stereo mapping prerequisite.
Native reuse failed as recorded; precision against independent truth and Go2 body
extrinsic qualification are not performed. Driving was not applied. No further
runtime window or background continuation is scheduled by this record.
