# Actual input overlay and global map

`slam_features` validates PointCloud2 layouts, offsets/types/count/endian,
row padding, payload length, finite coordinates and bounds. ROS stamps are
decimal strings on the wire. Receipt monotonic time and source time stay
separate; sensor-to-browser latency is unknown without clock qualification.

Only actual left rectified IR input is overlaid. The label is current
observations/reprojected, not original native2D tracks. With map_T_optical,
camera coordinates are inverse(map_T_optical)*map_point, then the validated
rectified projection is applied once. Source time/camera/resolution/calibration/
epoch/pose are joined; late or stale/LOST data hides observations. Unsupported
ROI/binning/raw distortion is unavailable rather than approximately corrected.
The actual camera image still renders without a valid overlay.

Global map points are independent of the current camera field of view. Source
snapshots replace complete visualization snapshots, including deletions and
loop corrections. Spatial LOD retains global extent instead of firstN points;
bounded region detail is available in the pure store. Global scope and complete
coverage are separate properties. The runtime's capped LL_MAP export keeps
coverage unknown/subset, total null and backend cap32768 visible. A static map
snapshot age differs from runtime heartbeat age and image freshness.

The existing RobotScene3D provides orbit/pan/zoom/fit and trajectory; the scoped
UI adds map/current-observation/trajectory/follow toggles and a paired image
canvas. It does not intercept movement keys. All synthetic screenshots/tests are
explicit fixtures. Installed output semantics and loaded-map optical/time
alignment still need live qualification. Localize rotates map_epoch and clears
cached features before new frames can be shown.

The optional camera_view is derived only from matched actual image/CameraInfo/
source-time optical pose. The UI displays its position and calibrated rays,
not the camera-link/body pose. Ray length1m is a visual convention; measured
scene depth is unknown. Missing/stale/LOST calibration hides the frustum without
erasing the saved map trajectory. Native localize quarantines callbacks until
completion and rejects queued pre-completion source stamps in the new epoch.
Uncertain native timeout retains quarantine until owned process cleanup.

Wire endpoint is exactly /api/v1/ws/slam, matching the server router and the
strict browser fixture. Native localization callback completion alone is not
localize_success: the adapter waits up to5s for current owned epoch, fresh
corrected map-frame camera pose/tracking newer than the response source fence,
and runtime readiness. Failure preserves separate official/native result and
requires an explicit new-session retry; there is no automatic repeat.
