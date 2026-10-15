# Capability audit

Reference source: Isaac ROS release 3.2 e31f4cc1d41a329a01946e5fe63669f8b15da677,
locally preserved reference sources and repository experiment launch contracts.
Installed historical apt 3.2.6 is not proven built from that exact source SHA.

| Capability | supported_in_source | installed | available_now | software_verified | hardware_verified | blocked_reason |
|---|---|---|---|---|---|---|
| FAST-LIO fixed adapter | yes | existing configured manager | runtime preflight | fixture | no new test | device handoff |
| Stereo tracking / mapping | yes, vo / slam_vo | historical 3.2.6 | opt-in broker/preflight | native-call fixture | no | Gate 16 |
| VIO | yes | historical | no | disabled gate | no | IMU_NOT_QUALIFIED |
| Left rectified IR | yes | historical stereo640×480 | runtime input contract | parser/clock fixture | no | Gate 16 |
| Current observations | LL_OBSERVATIONS XYZ in map frame | unverified exporter | conditional | projection fixture | no | installed semantics / time / optical TF |
| Global map visualization | LL_MAP map-frame snapshot | unverified exporter | conditional | global fixture | no | Gate 16 |
| Every retained landmark | visualization capped | unknown | no verified export | partial contract only | no | MAP-02 |
| Native save | FilePath save_map | historical save | gated | service/error/hash fixture | no | Gate 16 |
| Native saved localization | LocalizeInMap + verified hint | historical code3 failure | gated | scratch/native-call fixture | no | new separate-session acceptance |

Reference limits: current observations2,048, map landmarks32,768, pose graph2,048.
RGB encodes visualization color, not a native stable ID/confidence. No original
2D tracks are exported here. Whole snapshots replace previous snapshots; points
are not accumulated across map corrections. `engine_total_count=null`, coverage
unknown/subset and backend_limit remain visible. A small cloud is not proof of
complete retained-map export. No proprietary database parsing/export is used.

Corrected camera-link SLAM pose comes from `visual_slam/vis/slam_odometry`,
not the VO `tracking/odometry`. Source-time observed optical TF composes the
camera pose. Observations are reprojected only with matching image, CameraInfo,
calibration revision, source clock, frame, epoch and <=20ms total skew. Missing
TF or unsupported calibration hides the overlay. Both operational output TF
flags stay false; the overlay never enables them.

Managed launch enables observations/landmarks/SLAM visualization explicitly.
GetParameters checks effective mode/export/TF flags and actual publisher/input
status before ready. No ROS installation produces unavailable, without fixtures.
Installed complete-map SDK export remains unresolved: before MAP-02 can PASS,
verify an installed public API for all retained landmarks or implement a pinned
public SDK wrapper with total/coverage tests. Raising the web LOD cap cannot
recover points omitted upstream.
