# Non-driving follow-up — 2026-10-16

The user reopened all remaining work except driving and confirmed current
stationarity and onsite physical-stop/recovery availability. The operator's
manual-control handover remains in effect: the control bridge stays stopped.
Stationarity alone is not a request to restore it. Existing deployments and
observations remain evidence for their exact source and conditions only.

## Baseline and ownership

Work began on clean main/origin `361c019`; deployed source is clean
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

## Validation and actual acceptance boundary

Combined source/test hashes and local results are recorded in
`NONMOTION_VALIDATION.json`. These are software regressions. Saved real preview
serialization was also checked offline: 13,993 XYZ points, 1,024 bounded
trajectory points and one camera pose. That does not qualify a live endpoint or
the new UI on the device. Existing exact-source CI is not reassigned to this
candidate; its publication/CI and deployment are recorded separately.

The next live scope must pin the new candidate, preserve bridge-off startup,
restart dashboard and broker, and use a bounded stationary mapping/save/export/
stop window. Any reuse attempt needs an exact newly saved package plus a fresh
camera-link hint and an operator-confirmed unchanged physical pose. Official
localization completion and fresh corrected pose/TRACKING in the new epoch are
separate checks; geometric accuracy and body extrinsic qualification remain
independent. Stop/cleanup is prepared before acquiring the camera.

An isolated product NativePlanner HTTP harness can use synthetic geometry and
native installed planning binaries in a separate domain with private TF topics.
It cannot substitute for production dashboard/map/costmap acceptance. Operating
localization startup also emits operating static/odometry TF even without an
initialpose, so it needs a separately identified pipeline window; it must not be
silently included in camera observation.

## Remaining conditions

MAP-02 full retained export still lacks a vendor-supported full/frozen/paged
contract and independent retained count or exhaustion evidence. Existing preview
export is useful but does not close that row. See
[MAP02_COMPLETENESS.md](MAP02_COMPLETENESS.md).

MR-MS-003 still needs qualified map/annotation-pinned mask, costmap, controller,
BT and map-epoch ingestion evidence. All enforcement scopes remain false.
Historical stale startup remains UNCONFIRMED. Neither blocks Stereo mapping.
No driving command, operating VSLAM TF, initialpose or navigation goal belongs
to this follow-up. Precision evaluation against independent truth and Go2 body
pose qualification have not been performed.
