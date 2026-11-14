# Same-time UDP and ROS wall-range audit

Date: 2026-11-14, Asia/Seoul. Scope: navigation sensor/pose provenance;
no experiment mode or production configuration change.

## Current INITIAL POSE and physical reference

The first action in this investigation was a read of the user's open
`#navigation` dashboard. It displayed **X 4.083 m, Y 4.156 m, yaw -3.064 rad**,
explicitly an **unsent local draft**. These are three-decimal DOM display values,
not an intercepted full-precision request. The stationary acknowledgement was
unchecked, server handoff absent, and operational localization not applied.
No pose was sent or edited by the agent.

That draft differs from the earlier `(4.670812, 3.429015)` comparison point.
Its distance to the old unaccepted dense fit is **0.497247 m**, with at most
0.000707 m error from XY display rounding. The earlier **1.409103 m** was a
different, historical draft-to-candidate comparison, not a physical position error.

The operator confirmed the highlighted upper/right 2D outer lines are the walls
they mean, and that roughly **220 / 230 cm** was measured from body centre with
a tape perpendicular to the walls. Their initial answer suggesting a position/
posture change was immediately corrected to "아니 없는듯" (apparently not).
Consequently **actual movement between captures is not established**. Neither
the user nor an agent is assigned responsibility for the different old/new clouds.

## Corrected time attribution

The previously quoted 1.50 / 1.97 m came from the **14:26 preserved cloud**.
Describing that as a current live measurement was inaccurate. The 15:26 passive
UDP capture and 15:50 simultaneous UDP/ROS capture contain different principal
plane ranges. Host arrival times, not the sensor's inconsistent UTC epoch, identify
these capture windows.

| Source and origin | Upper corresponding plane | Right corresponding plane |
| --- | ---: | ---: |
| 14:26 preserved FAST-LIO IMU cloud | 1.496 m | 1.974 m |
| 15:50 UDP / ROS, LiDAR origin | 2.23567-2.23638 m | 2.39836-2.39886 m |
| Same input, recorded nominal LiDAR-to-IMU transform | 2.23157-2.23228 m | 2.14889-2.14938 m |
| 15:50 FAST-LIO body cloud | 2.22964-2.23345 m | 2.14948-2.15180 m |
| Operator tape measurement, physical body centre | about 2.20 m | about 2.30 m |

Plane ranges are perpendicular distances to fitted planes. LiDAR origin, FAST-LIO
IMU origin and the physical body centre must not be treated as the same point.
The upper/right labels are geometric associations; physical identity of each
fitted surface with the surveyed outer wall is not independently established.
The configured 0.25 m LiDAR/IMU displacement explains the right-wall range change
between those two coordinate origins. It does not establish the physical body-
centre calibration. Remaining approximately 3 cm / 15 cm differences from the
operator measurements are unresolved; they are not new operating corrections.

## Same-window chain verification

Successful observation session: `62168cbd843b4ada80e71c57e264dd09`.
The collection retained original UDP payloads and original ROS CDRs, without
starting any proposal/global-observation job or changing sensor settings.

- **UDP to driver `/lidar_points`:** six complete frames, 500 packets and
  64,000 points per frame, matched by exact per-point sensor microsecond timestamps.
  All **384,000 XYZ/ring/intensity records match in order exactly**; XYZ hashes
  match and coordinate error is zero. Another partial frame's 23,424 points match.
  The first ROS frame predates the UDP window and is not claimed as matched.
- **Driver to bridge `/velodyne_points`:** all eight stored bridge frames equal
  their unique source `/lidar_points[::4]` XYZ/intensity/ring sequences exactly,
  **128,000 points**. Time/header rebasing is separately checked. No XYZ scaling
  or extra translation is introduced by this bridge stage.
- **Bridge to FAST-LIO body:** eight body outputs have the corresponding raw
  header plus maximum relative point time. Nominally transformed raw/body wall
  range differences are upper -3.797 to +0.074 mm, right -0.948 to +0.596 mm.
  This does not reproduce the old approximately 0.7 m discrepancy.
- **Sparse `/cloud_registered` and measured Odometry:** seven body/world/pose
  triples share an identical end stamp. Applying the inverse measured Odometry
  to the sparse world cloud gives upper-plane ranges 2.2026-2.2090 m and right
  2.1442-2.1475 m. These differ from the dense body-plane fits by respectively
  2.19-2.84 cm and 3.59-5.56 mm. Sparse support is only 28-31 / 13-14 points,
  and the upper fitted normal is more tilted; voxel averaging and the different
  point populations prevent treating both fits as equally precise. There is
  no observed 70 cm or 1.4 m change in this current chain.

The 10,023 simultaneously captured UDP packets have consecutive sequence numbers,
incoming packet type 0 and destination 192.168.123.18. All advertise protocol 6.1,
16 lasers, 8 blocks, distance unit byte 4 (0.004 m) and dual-return mode 0x39.
Expected geometry was decoded from the installed SDK definitions and exact
correction CSV, then validated against actual driver output as above; this was
not a compiled full-driver replay. Whole UDP payload duplicates were absent.
Equal adjacent dual-return distances/intensities explain observed repeated returns
in this sample; this is not a universal claim about every historical duplicate.

The DDS graph snapshot contains one expected publisher per observed topic:
Hesai driver, XT16 bridge, or laser_mapping as appropriate. This Humble runtime
does not pass MessageInfo into the subscription callback, so per-message GIDs
and DDS source timestamps are unavailable and recorded as null. Content/time
matching supplies the frame link; a graph snapshot alone is not per-message
publisher identity proof.

Separately, the 15:26 UDP sample's full 16-channel versus matching 4-channel
selection changes principal ranges only 1.2-1.5 mm. Dropping channels does not
reproduce the historical 1.50 / 1.97 m values in that current sample.

## Extrinsics and decoder audit

The preserved 14:21-14:27 FAST-LIO `mat_pre.txt` contains 3,753 finite,
time-ordered rows. Installed `laserMapping.cpp:1030-1032` confirms column order.
Although `extrinsic_est_en=true`, translation differs from its configured initial
value by at most **0.267 mm**. Maximum Euler-axis deviations are
0.0566 / 0.0938 / 0.0117 degrees. Large extrinsic drift is not evidenced in that log.

Installed driver/SDK source revisions match the existing pinned revisions.
The copied selected driver configuration disables XYZ transform, distance
correction and XT spot correction. SDK distance conversion is integer range times
header unit divided by 1000, followed by the recorded angular correction and
trigonometric projection. Exact same-window output agreement validates these
calculations for the sampled packets. Artifact integrity is not a physical
range-accuracy or body-centre survey.

## Attempts and final robot state

Two initial precondition checks stopped **before any start/stop request**:
an existing READY session was present when STOPPED was required, and later the
pinned existing READY session had become STOPPED. Observed intervening session
changes are not attributed to an actor without further evidence.

Three agent-started observations followed; each was ended by its exact session ID:

| Host start time | Session | Result |
| --- | --- | --- |
| 15:46:40 | `ea27c233aac849dc9169f2a472255671` | Collector ROS logging path failed before data capture; safely stopped |
| 15:49:26 | `1cbc3532dbc043c5ac86f6808f03cdb2` | Collector callback expected unsupported MessageInfo; safely stopped |
| 15:50:39 | `62168cbd843b4ada80e71c57e264dd09` | Simultaneous capture completed; safely stopped |

The first two are diagnostic helper failures, not robot failures or successful
validation trials. The helper was corrected outside Git: explicit writable ROS
log path and a callback compatible with this installed ROS version. ROS creation
and one-argument point-cloud/IMU/Odometry serialization preflights passed before
the successful retry; diagnostic fixture records are separate from sensor data.

Successful run received 21 messages on each cloud topic, 20 Odometry and 826 IMU
messages, saving the first eight originals per topic. It preserved 10,023 UDP
payloads with host arrival times and packet metadata. During its status checks,
the same session stayed READY with signed inhibit HELD, STOP=true, lease=false,
and Move count unchanged at zero.

Final readback **15:50:48 KST**: observation STOPPED, active=false, busy=false,
session=null, guard=null; STOP=true, lease=false, bridge Move=0. Actual executable
release remains `8234fcdb3d79b69c8b942d9bb42bfc25e57b141c`.

A fresh read at **16:04:22 KST** again returned STOPPED, active=false, busy=false,
session=null, guard=null, owner_failure=null, STOP=true, lease=false and Move=0.
The bridge reported the same release. This is a status readback, not independent
physical proof of robot standstill.

Total agent requests in this range investigation: observation start **3**, exact
session stop **3**, proposal calculation/confirmation **0**, INITIAL POSE **0**,
operational registration/Nav2/goal/STOP release/movement **0**. Dashboard/control
services were not deployed or restarted. No production code/configuration changed.

## Preservation and software checks

All raw maps, points, UDP, CDR, correction CSV, and diagnostic artifacts remain
outside Git in `../nav2-live-analysis-20261114/runtime-range-audit/`, with robot
copies under `/home/unitree/robot-scope-diagnostics/current-cloud-20261114/`.

- `paired-current-20261114T065039Z.zip` SHA256:
  `808e7a27bb6010b43760865216fe0798fab2efcfd035b41d7e1a9f56418c06d9`.
- Paired `udp.bin` SHA256:
  `b2d820145c5960e99574ccc1cbb50c4dd798a2c8890ab1c137a5b6628269d711`.
- `paired-udp-ros-match/report.json`, `paired-ros-chain-audit/report.json`,
  `extrinsic-log-summary.json`, original source manifests and helper scripts
  retain detailed comparisons and limits.
- Earlier preserved inputs were not overwritten or substituted for this capture.

Required Windows full unittest: **1,798 tests, 24 failures, 420 errors, 22 skips**,
26.355 s, not a pass. Navigation/draft JS: **25 passed**. Separate bridge tests:
9 passed, 2 Windows errors from missing bash. No claim is made that all full-suite
failures were individually classified.

Prior exact documentation commit `96d3420` had passing Python/JS and I0, but CI
failed in an Ubuntu 24.04 mission fixture waiting for `planning_delayed=true`
before STOP was clicked. `9a09fce` had a different diagnostics-details-open browser
failure; `b47b069` passed all jobs. Those commits change documentation only.
Failures are retained as failures, not dismissed as proven flakes or hardware
motion failures. New published-commit CI is reported separately.

Next one task: after the operator relocates the robot, preserve a new same-window
UDP/ROS capture and compare **changes** in both wall distances with new tape
measurements. Keep origins explicit and do not carry old candidates or clouds
forward as current. No initialization value has been accepted by this investigation.
