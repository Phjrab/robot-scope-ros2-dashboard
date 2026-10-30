# Latest: ROUND2

See [ROUND2_RESULTS.md](ROUND2_RESULTS.md) for actual **5/5 native PASS**, canonical consumer tests and first-blocker evidence; [ROUND2.md](ROUND2.md) documents the corrected boundaries. The original first-round result below is retained as historical evidence.

# D3 collision geometry and isolated-simulation handoff

## Published candidate and scope

- Branch: `review/20261029-x-d3-collision-sim`.
- Fixed latest-start BASE: `47ae383fff5bfa12c20d523d2851a952dbb60f4b`.
- Published source/test-content SHA: **`236700a66a74f07e92dd753dacf894c089e789ed`**.
- Local tested commit: `b18b2cb809ba9a75739e54697eb2fc1e99e41104`; connector-created
  source commit has exactly the same complete tree
  `1dc6a4f6fb91e326dde3abaaabf7c0606dfa475b` and all 14 changed blobs verified.
- Final delivery adds this handoff only. Its exact SHA is the branch HEAD / the
  commit containing this document, reported with the delivery. A commit cannot
  embed its own hash; source/test identity above is stable and independently
  verifiable. No implementation changed after final tests.
- Publication used Git-data connector, original BASE tree and one parent, then
  ordinary fast-forward for this document. No force-push, main edits, merges or PR.

Only four owned directories changed: `robot_dashboard/collision_geometry_core/`,
`tests/expansion_d3/`, `experiments/expansion_20261029/d3_collision_sim/`, and this
D3 documentation directory. Existing user/other-role work remains unchanged.

## Implemented

- Metric SE3 URDF FK: root + joint origin + motion + collision origin; joint
  axes/limits, boxes, spheres and conservative cylinder-enclosing capsules.
  Official pinned source yields 27 primitives, not viewer lite geometry.
- Explicit mount primitives; source/runtime model hash and revisions separated
  from padding. Unmodeled physical brackets, LiDAR, Jetson/cables and measured gait
  envelope remain declared. No unsupported meshes silently approximated.
- Signed conservative distances/overlap, separate padded/unpadded results,
  one-time uncertainty and gait margin, current pose vs held-joint future sweep.
  Translation, pure rotation and bounded constant-twist hypotheses are covered.
- Source clock, epoch, frame/map generation, calibration, pose/joint/obstacle age
  and skew gates. Sparse missing points never certify free space.
- Named foot/support-plane association, finite patch containment and bounded
  tolerances; low obstacles/body collisions remain active.
- Independent analytic oracle plus raw FOV/noise/occlusion sensor generator.
  D2 sees only raw points, never hidden oracle object locations.
- Predictive simulated-command stop stays latched while the observer continues
  within its fixed remaining window. Actual simulation geometry contact,
  cancel and infrastructure failure have distinct terminal outcomes.
- Six native scenario requirements are generated, not fabricated run outcomes.

## Actual verification (2026-10-29, current dot VM)

Environment: Debian 13 Linux x86_64; Python 3.12, NumPy 2.3.5, SciPy 1.17.0.
These are VM measurements only, not Jetson/robot latency.

| Evidence/check | Result |
|---|---|
| UNIT focused geometry/gates/observer | **PASS: 24 tests**, 0.729 s |
| Independent oracle | PASS: 80 deterministic random rotated-box/circle comparisons |
| SYNTHETIC reproduction | PASS: empty complete fixture CLEAR; current body overlap, translation sweep and pure rotation sweep STOP_REQUIRED |
| C1 exact-pin real wire validator | PASS |
| D2 exact-pin raw points -> real core/tracker -> D3 | PASS: hidden second object remains occluded; one observed geometry; sparse clearance remains UNKNOWN |
| Python full repository discovery | **FAIL/environment-limited: 3001 tests, 36 errors, 11 skipped**, 101.817 s |
| Full Python error attribution | 25 local socket `PermissionError: [Errno 1] Operation not permitted`; 11 missing `cv2`; no D3 focused failure |
| Related JS regression | **PASS: 699/699**, no skips |
| Frontend syntax smoke | **PASS: 112 modules** |
| Whole `robot_dashboard scripts` Ruff | PASS |
| Tracked-source secret scan after staging | PASS |
| Import/runtime boundary | No ROS/process/model acquisition side effects |
| NATIVE_NAV2_SIM | **NOT_RUN** (all six cases) |
| Full mesh collision backend | NOT_RUN / unsupported, explicit rejection |
| REPLAY_REAL, real mount/calibration/stop qualification | **INPUT_REQUIRED** |
| Actual robot/device | **DEVICE_NOT_RUN**, deliberately not contacted |

Full discovery was run rather than replaced by focused checks. Environment errors
are disclosed, not counted as passing or silently skipped. No socket permission
escalation, robot connectivity attempt or cv2 install was used to evade them.
Raw logs, generated points, results, build/install trees and private inputs are
not committed. Source/tests/generators/reproduction commands are the deliverable.
GitHub CI belongs to its exact commit; inspect that commit's Actions/checks,
not a different role's passing CI. Final delivery reports the terminal state.

## Native availability and remaining limits

Read-only inspection found no ROS/container CLI, rclpy, `/opt/ros` setup or
Docker/Podman socket. A bounded workspace check found the historical committed
C3 image-lock only, not an executable runtime. Existing C3 documentation records
native tests on GitHub-hosted Ubuntu 22.04 and authoring-host unavailability; it
does not establish a usable runtime in this current Debian VM. No completed
install was repeated. No native graph or host setup was attempted.

Therefore actual Nav2 command->fake plant motion, costmap ingestion, path changes,
controller consumption, feasible-goal completion, blockage/stale stops and yaw
terminal outcomes remain NOT_RUN for D3. The original narrow-route/yaw failures
were not erased; no robot size, padding, controller or speed was tuned to pass.
The fixture gate is not a native controller result. Actual contact is not inferred
from modeled overlap; nothing here certifies real-world safety.

## Read-only dependencies and handoff

- C1: `2402c02c6f91ba54064894b21735e01b98610acd`.
- D2: `c0d266e290a2d29c173d3b83520f8c96efea9447`.
- Unitree source: `f3772ce54c56ef2d34c6aee8100bc768896c7d19`, source blob
  `70bce96b3e96a1c4cf5eeb1753bbd4351c9122e4`; local URDF SHA256
  `8f4571b49f35ce04b8833d561c403bddeb9cd8f7077e2ddbee82895726de487c`.

See [REPRODUCE.md](REPRODUCE.md) for exact commands and numerical limitations;
[INTEGRATION_POINTS.md](INTEGRATION_POINTS.md) for C1/C3/C4 calls, metadata and
future arbitration boundary. No C1 schema/service, C2/C3 UI or C4 ROS port was
copied, replaced or integrated.

**Next one item:** supply the approved isolated Humble/Nav2 1.1.20 + C4 adapter
execution environment for the six-case native test. Physical geometry/calibration
inputs remain prerequisites for later physical qualification, not a reason to
block this completed offline candidate. Integration/deployment still requires
separate user authorization.

Latest C4 native-input preparation and preserved baseline: [C4_NATIVE_RESULTS.md](C4_NATIVE_RESULTS.md).
