# Deployment gate — not executed

This document is a review checklist for stage16, not permission to operate.
Do not deploy/restart/take camera merely because software tests pass.

Record exact candidate SHA and completed CI, current deployed SHA/dirty state,
rollback release, named operator/resource window, camera owner/viewers/container,
map/config hashes and private backup location. Preserve the existing Isaac image,
experiment workspace, datasets, maps, Nav2 policies and control services.
MS is the shared integrator; agree a deployment/performance window with MR and
hardware/UI/resource owners. None exists for this software delivery.

The dashboard loads the integration without starting devices. Its preferred
optional environment key is ROBOT_SCOPE_SLAM_BROKER_SOCKET, an absolute private
same-UID Unix socket. Run broker only inside the preserved Isaac environment in
an approved isolated observer process; dashboard retains its operational DDS.
No API can supply arbitrary executable/topic/domain/image/path.

Broker entry point is python -m robot_dashboard.slam_broker. Fixed arguments:
--socket, --runtime-root, --package-root, --config, --camera-handoff, --camera-lock.
Use identical absolute shared package root on both sides (dashboard runtime's
multi-slam/packages), private0700 parents,0600 files, same UID, and shared camera
lock visible to both broker and RGB relay. The relay's ROBOT_SCOPE_CAMERA_LOCK
must name this same file; do not allow an uncoordinated relay to respawn.
Do not remove an existing broker socket without owner/process investigation.
No new systemd unit or restart has been installed by this change.

The private runtime config contains observed input_contract/camera_contract paths,
stereo_profile, distinct domain_id/operational_domain_id, domain_available and
current domain_checked_at_utc. It accepts only observed live rectified inputs.
The preserved experiments/isaac_vslam/config/launch_contract.py validates them.
Do not manufacture contracts, calibration hashes or unused-domain evidence.
Camera handoff requires lock_protocol=robot-scope-camera-v1, checked_at_epoch,
relay_released=true and exact devices; it expires after300s. Recheck actual owner
immediately before acquisition. OS owner probe fails closed.

For explicitly isolated direct testing only, ROBOT_SCOPE_SLAM_ENABLE=1 and
ROBOT_SCOPE_SLAM_RUNTIME_CONFIG select the same fixed adapter; localhost FastDDS
is required. Never set these isolation keys on the operational dashboard to make
an error disappear. Broker configures its own localhost FastDDS environment.

After approval: read-only baseline, stationary tracking, mapping/readback, actual
left IR/projection/global stream, two viewers, native save, stop/owner handback,
offline preview, separately approved native reuse with known hint. Record exact
SHA/config/source stamps/frame/coverage, actual publisher/process inventory and
results. Localize acknowledgement alone does not establish fresh valid pose.
A new600s visualization-inclusive workload needs an exclusive resource window;
previous VO/LiDAR measurements cannot be reused. Follow stage16 gates A–E.

Stage17 operational pose, initial pose, Nav2 goals and movement remain separate.
Sparse landmark absence is never free-space evidence. No deployment performed.
