# Deployment gate — stationary observation and save completed

This document preserves the stage16 review gates, not permission to operate.
Do not deploy/restart/take camera merely because software tests pass.

The user approved the reviewed installation of source `ffa1b21` and normal
same-scope stationary rechecks. Final deployed source `50a30f2` completes actual
stereo display, matched-pixel overlay, native save, normal UI stop and camera
cleanup. Catalogue/offline preview/export reread and artifact hashes passed.
The guard-preserving corrections are described in the acceptance report.
Exact source/runtime/config and the completed versus remaining scope are
recorded in [STEREO_OBSERVATION.md](../integration-acceptance/STEREO_OBSERVATION.md)
and [STEREO_OBSERVATION.json](../integration-acceptance/STEREO_OBSERVATION.json).

Record exact candidate SHA and completed CI, current deployed SHA/dirty state,
rollback release, named operator/resource window, camera owner/viewers/container,
map/config hashes and private backup location. Preserve the existing Isaac image,
experiment workspace, datasets, maps, Nav2 policies and control services.
MS is the shared integrator; agree a deployment/performance window with MR and
hardware/UI/resource owners. The approved stationary observation/save/requery
window is complete;
extensions must follow their current applicable conditions.

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
The reviewed probe, cooperative relay, broker user service and dashboard restart
were installed for the approved first observation.

The private runtime config contains observed input_contract/camera_contract paths,
stereo_profile and distinct domain_id/operational_domain_id. It accepts only
observed live rectified inputs.
The preserved experiments/isaac_vslam/config/launch_contract.py validates them.
Do not manufacture contracts, calibration hashes or unused-domain evidence.
Legacy configuration retains domain_available/current domain_checked_at_utc and
the 300s camera handoff: lock_protocol=robot-scope-camera-v1, checked_at_epoch,
relay_released=true and exact devices. The existing standalone camera launcher
also retains its current-owner/time-slot/300s observation requirement.

The broker may instead use an explicitly approved fixed managed scope. Runtime
config's managed_scope and --camera-handoff must identify the same private,
canonical same-UID JSON policy. Its exact schema is SCOPE_FIELDS in
robot_dashboard/slam_managed_scope.py: fixed scope ID, camera device inventory,
distinct domain IDs, separate shared camera/domain lock paths, cooperative owner
policy, installed relay path/source hash, lock-helper hash, observed host PID
namespace and fixed owner_probe_socket. No example values or expiry timestamp
establish current ownership. A policy/source/device/namespace change requires a
new reviewed scope; never refresh old observation timestamps to enable startup.

Every managed acquisition first holds the shared camera flock, verifies that
the actual relay source and waiting process use that lock, and requests a new
read-only ownership report from the fixed root-owned local probe service. The
client authenticates the root peer, exact device inventory/host namespace and
timestamps from this request (at most 5s old). Free, occupied and unavailable are
distinct. Missing helper, incomplete FD visibility, stale/invalid reports and
uncooperative relays fail closed; there is no partial unprivileged-probe fallback.
The helper neither acquires a camera nor stops processes. Its installation and
the relay's shared-lock installation were included in the approved deployment;
subsequent changes retain the applicable deployment gates.

The same-UID broker holds the domain flock before its existing live DDS graph
check and child launch. The per-start reservation proof records the original
successful probe timestamps and live parent FDs/inodes; proof reads never
restamp them. The managed launcher checks that evidence separately from the
unchanged historical sensor/profile contract. Native image/pose source stamps,
stereo synchronization and runtime freshness checks remain authoritative.
Both reservations survive client disconnects and remain held until exact owned
child/observer cleanup is confirmed. RESOURCE_CONFLICT carries bounded resource
and reason labels; it never forwards raw process output or filesystem paths.

Host PID visibility is necessary for relay and reservation checks. The prepared
isolated broker configuration uses --pid=host, --network=none, --ipc=private and
the existing runtime UID with exact shared paths; it exposes no Docker socket.
It must not receive broad root/privileged ownership merely to bypass a probe.
The fixed read-only host probe is responsible for complete device-owner checks.

For explicitly isolated direct testing only, ROBOT_SCOPE_SLAM_ENABLE=1 and
ROBOT_SCOPE_SLAM_RUNTIME_CONFIG select the same fixed adapter; localhost FastDDS
is required. Never set these isolation keys on the operational dashboard to make
an error disappear. Direct testing retains the legacy attestation path; the
managed reservation path is bound through the broker's actual camera owner.
Broker configures its own localhost FastDDS environment.

Acceptance sequence: read-only baseline, stationary tracking, mapping/readback, actual
left IR/projection/global stream, two viewers, native save, stop/owner handback,
offline preview, separately approved native reuse with known hint. Record exact
SHA/config/source stamps/frame/coverage, actual publisher/process inventory and
results. Localize acknowledgement alone does not establish fresh valid pose.
A new600s visualization-inclusive workload needs an exclusive resource window;
previous VO/LiDAR measurements cannot be reused. Follow stage16 gates A–E.

Stage17 operational pose, initial pose, Nav2 goals and movement remain separate.
Sparse landmark absence is never free-space evidence. Native save and offline
requery are verified; native localization/reuse, full retained export and driving
readiness are not established.
