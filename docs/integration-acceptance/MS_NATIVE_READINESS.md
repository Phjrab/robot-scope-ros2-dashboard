# MS native integration readiness

Updated 2026-10-15 KST. **Software preparation PARTIAL; product live execution
NOT_RUN.** This is an installation and validation handoff, not authorization to
deploy, restart a service, take a camera, start a pipeline or apply a pose.

## Current source and actual runtime

The integration reuses `slam_wiring`, `SlamSessionManager`, `IsaacStereoAdapter`,
the private same-UID Unix broker, `FeatureStream`, `MapPackageStore` and the
managed launch. Baseline main is `2555f3763996c7b331389924bb5df48d62094736`.
No engine, adapter, UI or mission structure was recreated.

Read-only device inspection on 2026-10-15 still found operating checkout
`/home/unitree/robot-scope` at clean `416d25c6e1c98b0c51097c9d6576b6ae34a690e9`.
That older checkout is not this integration candidate. Existing operational
services and the on-demand relay retain their ownership even with no camera FD
open. No containers were running. `/usr/local/libexec/robot-scope/` contained
the old `realsense_mjpeg_relay.py`, not an installed native broker/helper.

The preserved lab source is
`e31f4cc1d41a329a01946e5fe63669f8b15da677`; stopped runtime image is
`sha256:f9d47c621390b34544de684fea8d62c9bba82f834daa6696733277773f85fdb5`.
The SDK header was read without starting that image:
`/opt/ros/humble/share/isaac_ros_nitros/cuvslam/include/cuvslam.h`, SHA256
`fd1bd9eb4db0f396c8047d1500583c603b9f8a5680ad43203ecbce00a69dbaa2`.
Source SHA, image ID and header hash are separate provenance fields. They do not
substitute for the actual loaded `libvisual_slam_node.so`/`libcuvslam.so` hashes.
Exact current live readbacks and private configuration stay in
`robot-scope-hardware-validation-private/integration-20261015/`.

The following SHA256 values identify the local source inspected for this
handoff. Only `slam_features.py` and its dedicated regression test change in this
MS follow-up; the remaining rows identify the reused installation candidates.
Recompute the manifest if the integrator changes any source before deployment.

| Source path | SHA256 |
| --- | --- |
| `robot_dashboard/slam_wiring.py` | `69b8336221b7cfec0121c4d3aaed9ddd52b361e9987659b52e9157bd13e39c8c` |
| `robot_dashboard/slam_sessions.py` | `48fad81b3baebe847ef21c08828441f5cb8d251ed0bb01517cf8302a35c73995` |
| `robot_dashboard/slam_ros_runtime.py` | `17bae670fca6aaa30e7ca3e832d71f4c234febf4e2dffa0327139ee677aa6b8f` |
| `robot_dashboard/slam_broker.py` | `b2eec546f96241bf2e35d227b3c971317a5892e68232cf18616cc7c64192a6b5` |
| `robot_dashboard/slam_camera.py` | `9463464f21c74b9746e5d1ffb732e6285ac3a14faae72d4c0bd38545c385a825` |
| `robot_dashboard/slam_features.py` | `2a9281228afbac63319391dda694090558685a02df09818de19e15dc1c825837` |
| `robot_dashboard/slam_packages.py` | `610078d17404bcd800a3ae3819d776660caa85d46e0ad7f7b6c3e661d991ef46` |
| `scripts/slam/managed.launch.py` | `de4e787ccc4b92322c6152a1ce9d99bb2cd4f3f2a52ed2c629f5d2d722885364` |
| `scripts/realsense_mjpeg_relay.py` | `3f1292dcdce7f8cb786aad2b1ce13e6a69f619001939643642101e1c80d9eb85` |
| `experiments/isaac_vslam/config/launch_contract.py` | `d6bd905950e002d1caf31d5d1020dd4434804085216c44a72127a3fa7218e8a7` |
| `tests/test_slam_features.py` | `f228464ca6cf8af198529499a989e16357998e2572b5ed0b87c609a4553fdc42` |

## Fixed installation boundary for stage 40

| Item | Existing source contract | Remaining actual installation evidence |
| --- | --- | --- |
| Dashboard entry | `configure_slam` constructs adapters; no ROS import/device open/process start | Exact candidate installed and running; current service argv/environment/source hashes |
| Broker argv | `python -m robot_dashboard.slam_broker --socket ABS --runtime-root ABS --package-root ABS --config ABS --camera-handoff ABS --camera-lock ABS` | Same fixed argv, source hash, approved supervisor/unit and named owning UID; no broker installed by this follow-up |
| Broker privilege | Same effective UID at Unix peer; private socket and parent, owner matches, mode 0600 socket/0700 parents; rejects existing socket | Actual UID/GID/mode, parent mount identity and crash/cleanup supervisor behavior |
| Native paths | Opaque API package IDs; broker only accepts same-root staging/scratch/native layout and rejects symlinks/unsafe owner/mode | Identical absolute package root mounted in both dashboard and isolated environment |
| Camera exclusion | Relay and broker call the same `acquire_producer_lock`; flock held for full producer lifetime | Approved relay installation must find `robot_dashboard/slam_camera.py` relative to its real deployed script, and both processes must resolve one shared lock inode |
| Handoff | Private same-owner JSON, `lock_protocol=robot-scope-camera-v1`, current devices, `relay_released=true`, age 0–300 s, then lock and fail-closed OS owner probe | Current explicit operator/owner handoff; FD absence alone is insufficient |
| DDS | Dashboard keeps operational CycloneDDS. Broker clears CycloneDDS/FastDDS profile variables and runs localhost FastDDS in a checked distinct domain | Exact dashboard and broker environments, domain availability checked within five minutes; separate domain is not resource isolation |
| Launch | Fixed `scripts/slam/managed.launch.py`, `component_container_mt`, validated live rectified input/camera contracts; private immutable run copies and launch manifests | Installed executable/dependency path and loaded library hashes; calibrated current sensor profile and optical transforms |

No app/API gains Docker socket access, sudo, arbitrary shell/executable/image,
topic/domain or caller-selected filesystem paths. No new unit, helper or camera
policy has been installed. A source import/capability success is insufficient.
The existing `/usr/local/libexec/...` relay location differs from the repository
script location; deploying only that script without its helper resolution and
shared lock configuration is incomplete.

The runtime config is a private 0600 same-owner regular file. It supplies observed
`input_contract`, `camera_contract`, `stereo_profile`, isolated `domain_id`,
`operational_domain_id`, `domain_available=true`, and current
`domain_checked_at_utc`. Contract/config hashes and private source/runtime paths
must be frozen in the stage 40 deployment manifest. Never manufacture observed
contracts or relax freshness/startup timeouts to obtain readiness.

## Product readiness and visual verification

Source readiness checks GetParameters against the expected bool values,
advancing source timestamps, fresh left/right images, corrected map-frame pose
and tracking state, process liveness, unique publishers, current calibration,
stereo timing/resolution and baseline. The fixed corrected pose source is
`/vslam_lab/visual_slam/vis/slam_odometry` in `vslam_lab_map`; it is not the
operational localization authority. Runtime source rejects pre-localization
callbacks and clears the map epoch before reusing a saved map.

The live overlay must show actual left rectified IR input with original stamp,
optical calibration and same-epoch corrected pose. It reports reprojected
current XYZ observations, not original native 2D tracks. Original source images
still render when the overlay cannot align. The existing tests cover stale,
LOST, clock reset, camera/calibration/pose mismatch, source time joining and
epoch fencing. Native image/feature/pose semantics in the installed environment
still need stage 41 measurement.

Global visualization is a replace snapshot, independent of camera view, with
bounded spatial LOD and same-snapshot region detail. It does not append points
across deleted/optimized generations. Static map age and runtime heartbeat are
separate. [MAP02_COMPLETENESS.md](MAP02_COMPLETENESS.md) records the verified
32,768 source cap and the missing retained-map guarantees; coverage stays
`unknown/subset`, engine total `null`.

## Native preservation and reuse

The current read-only catalogue contains the previously supplied 2026-10-14
occupancy map and corresponding pointcloud map; their revisions remain in the
private `catalogue.json`. They are LiDAR/occupancy artifacts, not a compatible
Isaac native package. The existing initial-coordinate record must be checked
against its recorded map revision/frame by the localization owner. It cannot be
renamed into a `vslam_lab_map` camera hint without a verified transform. No new
map or hint was requested from the user or invented for this preparation.

`MapPackageStore` requires an official save acknowledgement plus declared
nonempty native files, checks a quiet interval and file signatures around
hashing/copying, writes an immutable SHA256 manifest, and atomically publishes a
package. A preview is approximate unless it shares an explicitly matching native
snapshot ID. These checks detect file/package inconsistency; the official native
writer must actually finish before publication.

Read-only preview reads the immutable preview/manifest and starts no engine or
camera. Load verifies package revision, compatibility and native hashes, pins a
reference, and copies original native files to scratch. Failure, timeout and
unsaved-session replacement cannot authorize editing the original. Native
localize requires an explicit verified map-to-camera hint, preserves separate
official callback result, then waits for fresh corrected pose/tracking in the
owned new epoch after the service fence. Load-path acceptance alone is
insufficient. Stage 41 must additionally demonstrate geometric alignment with
that exact saved map; source-time/tracking confirmation is not an accuracy test.

Historical lab evidence remains distinct: `map-save.json` saved a 45,056-byte
native `data.mdb`, SHA256
`c8426f33dfa789c0a13eef9bcf101a6cbb8bcee3f8c60eecd2e0263982d933ce`.
Single-thread reuse timed out after 20 s; the later multithread recorded-sensor
trial returned false/code 3 in about 0.547 s while odometry continued. Neither is
product integrated reuse PASS. See preserved `docs/experiments/isaac-vslam/`
evidence. No native DB was parsed, rewritten or represented as PCD.

## Acceptance status and minimum next action

| Row | Status | Exact remaining condition |
| --- | --- | --- |
| Pure feature/projection/global completeness contract | PASS, synthetic | 42 feature tests; rejects unsupported complete claims and filtered snapshots |
| Adapter/package safety regressions | PASS, synthetic | 26 fake-runtime tests and 17 native-file fixture tests; installed runtime unmeasured |
| Product native lifecycle / actual stereo observations | NOT_RUN | Stage 40 candidate+service/environment+shared camera-lock installation, then stage 41 approved stationary window |
| Native save and offline readback | NOT_RUN | New product run; official completion, immutable native manifest/hash and preview readback after stop |
| Product native reuse and map alignment | NOT_RUN / BLOCKED | Compatible original package, private verified hint, approved reuse window, fresh owned corrected output and geometric alignment evidence |
| MAP-02 full retained landmarks | PARTIAL / BLOCKED | Qualified supported full API or frozen paging contract, independent total/exhaustion proof and installed validation |
| Operational pose/initialpose/goal/movement | NOT_RUN | Separate stages 42–43 current conditions and authorization |

Focused commands used the repository `.venv/bin/python`: unittest discovery for
`test_slam_features.py`, `test_slam_ros_runtime.py` and `test_slam_packages.py`.
Syntax compilation and scoped diff checks pass. An initial system-Python broad
SLAM attempt was invalid for complete acceptance due to missing FastAPI and
sandbox Unix-socket permissions. Ruff was unavailable in that interpreter/venv;
the integration owner must use the established complete verification environment.
No device runtime or performance test was run.

The next safe implementation step is to finish the exact stage 40 fixed install
manifest (candidate/config/helper/library hashes, UID/modes, mount and shared
lock identity, rollback), without applying it. Then evaluate the separately
approved live conditions. Existing lab bags, maps, image, checkout and services
remain preserved.
