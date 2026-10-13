# Go2 onboard migration contract and runbook

Decision: [onboard ADR](ADR_GO2_ONBOARD_OPERATION.md). This document is the
single execution/status record for the internal-only migration. Historical
dual-host records remain historical evidence. PASS means the named check ran
and passed; NOT_RUN means it has not been measured. Do not infer hardware
success from source tests or an HTTP health response alone.

## Scope and current evidence — 2026-10-13

Required candidate: dashboard/Cockpit, currently used Go2/XT16/IMU and both
camera paths, saved-map/settings/route preservation, local mapping and existing
navigation integration, independent safe control bridge, restart recovery and
stationary coexistence. Dataset history is preserved because actual collection
is recorded. New perception models, goal arrival and competition completion
are outside the migration completion criteria. Optional features remain
optional unless current target inventory shows they are used.

Initial migration evidence below belongs to pre-UI candidate `3ec4cc6`;
the subsequent Hesai fanout fix and repeated acceptance use `093600f`.
The operator separately authorized UI integration. Historical UI branch merge
`5f4d211` and external deployed release `544e108` are distinct provenance
points. The original migration phase made no frontend changes; the subsequently
authorized `95d13e2` integration and post-UI verification are recorded below.
Pre-UI tests and measurements do not establish acceptance of the candidate
after that handoff.

For that integration, verify the delivered base SHA and ordered new commits
against the latest migration main and `INTEGRATION_HANDOFF.md`. Review only the
needed UI changes; do not copy the whole static directory or merge an old UI
branch without review. Preserve current API payloads, stream ownership and
control gates, run both the migration and UI checks, then record deployment
and post-integration browser/device checks separately. The UI checkout,
branch and processes belong to the separate UI task.

The final runtime candidate suite ran 1551 Python tests with 1550 passing and 1 skipped
(`OK (skipped=1)`), plus 340 passing JavaScript tests. Neither migration commit
`36554f5` nor `3ec4cc6` changed frontend files. Existing UI branch `42c6cce` and
the external release `544e108` are verified ancestors of the current history.
These source-history facts are separate from the later UI integration checks.

| Fact/check | Source and result |
| --- | --- |
| Target module | Operator: Go2 internal Orin NX 16GB; historical 2026-08-12 inventory agrees (P3767-0000/P3768-0000) |
| Target current platform | Authenticated inspection: Ubuntu 22.04.5 `aarch64`, kernel 5.15.199-tegra, L4T 36.5.2; required native imports and pinned Humble builds PASS |
| Target native runtime | Fresh NumPy 1.26.4/system OpenCV 4.5.4, `rclpy` and Unitree message imports PASS. Installed TensorRT packages report 10.7; engine/API compatibility was not established, and no used model engine was found |
| Historical platform | Ubuntu 20.04.5, kernel 5.10.104-tegra, JP5.1.1/L4T R35.3.1, CUDA11.4.315, TensorRT8.5.2.2; not a current compatibility claim |
| Historical resources | 15W, 4/8 CPU online, roughly 12GB available RAM and 386GB free NVMe; historical values only |
| Target initial resource baseline | RAM15642MiB, used1565MiB, available13783MiB; swap7821MiB unused; NVMe467G/free378G. Final 600-second stationary compound acceptance PASS below |
| Management contact | Supplied internal address `192.168.50.30`, account `unitree`; credentials are never stored here |
| Local management link | Initial development Mac observation: `en0=192.168.50.140`; not a target NIC assignment |
| Internal SSH | Initial attempt timed out before authentication; later authenticated `unitree` access succeeded. Hostname `ubuntu`; deployment/acceptance not implied |
| Target network | Actual sensor NIC `enP8p1s0=192.168.123.18/24`; management Wi-Fi `wlx289401c9eb9b=192.168.50.30/24`, default via `.50.1`. Historical `eth0` is not the current NIC |
| Target service inventory | Three Robot Scope units enabled/active, NRestarts=0 after recovery; manufacturer `enable-typec-host` PID/invocation unchanged through dashboard restart and complete Robot Scope stop/restore |
| External host | Authenticated read-only inventory: Ubuntu 22.04.5, kernel5.15.148-tegra, L4T36.4.7; active Robot Scope release `544e108`, service user `jetson_orin_nano`, Python `/usr/bin/python3.10` |
| External resources | RAM7608MB, swap20188MB, available RAM2713MiB, reported filesystem free40G at inspection; external-host values only |
| External placement | Process cwd `/home/jetson_orin_nano/releases/robot-scope/544e…`; workspace `/home/jetson_orin_nano/project/robot-scope/workspaces`; runtime `/home/jetson_orin_nano/project/robot-scope/runtime` with `maps` and `state` subdirectories |
| External runtime config | Wireless competition FAST-LIO, UDP control, `ROS_LOCALHOST_ONLY=1`, Go2 NIC `eno1`, relay `.50.30`; target onboard selects direct NIC/ROS/local lifecycle |
| Historical sensor packets | Go2 `.123.161`, XT16 `.123.20:10000 -> .123.18:2368`; historical tuple, not a claim about the current packet source |
| XT16 current destination and calibration | Inspected stale DestIp `.123.99` changed only to actual sensor NIC `.123.18`, with private original configuration/rollback preserved; private correction/manifest retained and PTC off |
| XT16 receive buffer | `net.core.rmem_max` 212992→8388608 via `/etc/sysctl.d/90-robot-scope-xt16-buffer.conf`; original value preserved privately for rollback |
| Current sensor/camera operation | FAST-LIO about 10 Hz; Go2 actual 1280x720/about 13 fps and RealSense actual 640x480/15 fps. Required LiDAR/IMU/Go2 state and advancing camera observations PASS |
| Current durable data | Source/target preservation SHA-256 and normal-loader/live API PASS: maps47files/43,115,380bytes; datasets3459files/365,073,866bytes, 12 completed sessions/1225 recorded samples; maps/settings/routes/gallery accessible internally |
| Operator-event provenance | Project runtime one file/2428bytes; active release runtime separate file/1250bytes. Preserve with separate source labels |
| External transition and shutdown | Fresh capture/navgoal idle, signed command zero/no lease before retiring old authority. Operator explicitly authorized authenticated sudo shutdown; SSH closed and subsequent SSH/ping had no reply. Physical power was not independently observed |
| Current bridge safety | Signed own named publisher 1/foreign named 0/manufacturer bare 10; zero motion/action and no lease. Manufacturer bare endpoints remain distinct from bridge cardinality |
| Local Nav2 observation | All localization-only processes ready; `waiting_initial_pose` expected. No estimated physical map location or goal arrival asserted |
| Used data history | 2026-09-11 Dataset capture: 212 samples/26,064,528 bytes; map and stationary Nav2 records exist; these counts describe that past session |
| Model scope | External registry only `registry.json`88bytes; engines/packages empty. Historical approved artifacts absent; new model deployment is not required |

Current kernel/L4T and native imports/builds were measured separately from the
Ubuntu version. Missing `nvidia-jetpack` alone is not a platform failure, and
installed TensorRT does not establish compatibility of an untested engine.
Read selected safe environment keys rather than dumping whole service
environments; private calibration identity/content stays outside this record.

## Feature and data transition

The current-host column describes documented deployments, not a newly inspected
live installation. Resolve every runtime path from the active service/arguments
before copying. Default paths below are discovery hints.

| Feature | Documented current host | New host/data | Peers and required change | Verification |
| --- | --- | --- | --- | --- |
| Dashboard/API/WS, Cockpit | External `.50.10` | Internal `.50.30`, `:8088` | Management browsers; `go2-onboard`, persistent paths, local service | Internal PID/cwd/commit, health and real browser frames |
| Go2 state/control | Internal `.50.30` Foxy bridge, external coordinator | Internal Humble ROS bridge + dashboard | Actual sensor NIC to Go2 `.123.161`; local lifecycle, signed ROS transport | Fresh `/lowstate`, signed zero/no-lease status, exact graph ownership; no ARM |
| XT16 preview/mapping | Internal packet relay; external Hesai/C++/FAST-LIO | Internal direct driver/C++/FAST-LIO; private `/etc/robot-scope/hesai/` correction pair | Inspected XT16 destination to actual internal sensor NIC; no relay/driver port duplication | Actual packets, one fresh `/lidar_points` and `/velodyne_points`, fields/ring/stamp/frame, FAST-LIO outputs |
| IMU | Internal `/lowstate` sender, external authenticated receiver | Internal full C++ `/lowstate -> /imu/body` | Local ROS; no wireless IMU owner | One finite fresh ordered `/imu/body`, consistent time/frame/extrinsics |
| Existing navigation | External map/Nav2/runtime | Internal local workers | Saved map and selected validated odometry; no wireless lifecycle | Stationary readiness, TF/publisher identity and owned-child cleanup; goal arrival not required |
| Go2 camera | Internal fixed RTP relay, external decoder | Internal direct multicast decoder | Go2 `230.1.1.1:1720` via actual sensor NIC | Live JPEG sequence/age and NIC, no duplicate RTP receiver/capture |
| RealSense RGB/profile | Internal single RGB capture, external HTTP/SSH client | Internal one by-id capture, explicit same-host HTTP/local profile helper | D435i RGB; preserve one device owner, avoid self-SSH | Actual advancing JPEGs, profile read/apply recovery when capture idle |
| Saved maps/annotations/families | External maps root, default `~/ws/go2_3d/maps` | Internal persistent maps root | PCD, PGM/YAML pairs, `*.annotations.json`, `*.map-family.json`; preserve relative references/revisions | SHA-256/bytes, map listing/preview, YAML images and family/route reference resolution |
| Source selection/presets/authored routes | External state and user state paths | Internal persistent state/spatial-route roots | Only durable settings and authoring files; never whole navigation job state | SHA-256, source identity, presets/routes and map revision compatibility |
| Dataset and operator history | External `runtime/datasets`, `runtime/operator-events` unless overridden | Internal persistent roots | Select needed completed/history sessions/events; original provenance unchanged | Session/sample/byte counts, manifest hashes, gallery JPEGs; capture idle before copy |
| Models/calibration | External model registry, private calibration; model use unconfirmed | Internal only actually used artifacts | Preserve source/ONNX/manifest/calibration hashes; target-built engine if required | Artifact identity, native backend import/API and load; optional if unused |
| Browser settings/food estimates | Client localStorage at old origin | Same browser, new origin | Layout/scene/theme/camera/food state does not cross IP origins automatically | Back up needed records on old origin, restore preferences explicitly; no control state replay |

## Prepare the target

1. Inspect target services/users/cwd/ports, network/routes and ROS publishers
   without changing the robot. Identify manufacturer processes before touching
   any similarly named unit. Record stationary/disarmed/no-lease state.
2. Inspect Python executable, `rclpy`, NumPy, OpenCV/native ABI, ROS/RMW/domain/
   CycloneDDS overlays, GStreamer plugins, cameras and free disk/RAM/swap.
   Preserve current units, config/key files and release pointers privately.
3. Use a separate checkout/workspace/runtime root. Build a new system-site-packages
   virtualenv and pinned Humble dependencies with bounded build jobs. Do not copy
   old `.venv`, ROS build/install/log or reset the vendor workspace.
4. Review installer dry-run, then install only the application dependencies and
   Robot Scope service configuration needed for this profile. No blanket apt
   upgrade, CUDA replacement, OS/BSP reflash or network reconfiguration.

The installer dependency mode remains `go2-nav`; the runtime profile is
`ROBOT_SCOPE_MAPPING_PROFILE=go2-onboard` in an explicit private environment.
Create/review that file from `deploy/robot-scope-onboard.env.example` before
running the installer. Its mode and profile select different responsibilities,
and doctor reads the same environment. The installer preserves an existing file.

```bash
./scripts/install_ubuntu.sh --mode go2-nav --env-file /absolute/private/onboard.env --build-jobs 2 --dry-run
./scripts/install_ubuntu.sh --mode go2-nav --env-file /absolute/private/onboard.env --build-jobs 2 \
  --apply --install-system-packages --install-service
python3 scripts/robot_scope_doctor.py --mode go2-nav --env-file /absolute/private/onboard.env
```

Use literal absolute persistent paths in the host configuration.
The profile selects `config/go2-onboard.json` and
`config/hesai_xt16_onboard.yaml`; set actual sensor NIC/CIDR after inspection.
Control transport is `ros`, control lifecycle is `local`, and mapping lifecycle
is local. Historical `.50.10`, `eno1`, Foxy release symlinks and self-SSH keys
must not remain necessary dependencies. Browser entry after verified deployment
is `http://192.168.50.30:8088`; actual browser/API access and advancing frames
have been measured there.

RealSense uses a separate private capture environment: explicit local access
mode permits the same private bind/dashboard address and only that host may
consume `/stream`. The default remote mode still rejects equal addresses.
Use actual camera by-id identity and sensor NIC; do not select `eth0` merely
because it appears in a historical relay record.

## Preserve and verify data

First finalize Dataset capture and stop active map/save/convert/goal jobs. Copy
needed data into an absent private staging directory and verify before choosing
that directory in the target configuration. Keep the source unchanged.

`scripts/onboard_data_migration.py` supports explicit `maps`, `datasets`,
`settings`, `routes`, `models`, `calibration`, `events` and `mission-history` bundles. Each inventory
contains relative names, size and SHA-256; keep it private outside Git. It rejects
symlinks/hardlinks/special files, unsupported files, whole control/job trees,
credentials and any existing destination. A failed partial destination remains
for diagnosis and must not be activated. The tool neither transfers across SSH
nor installs files into a live service root.

```bash
# Example: replace names/paths with the inspected actual map bundle.
python3 scripts/onboard_data_migration.py inventory --kind maps \
  --root /absolute/source/maps --include map.pcd --include map.yaml --include map.pgm \
  --include map.map-family.json --manifest /absolute/private/maps.inventory.json
python3 scripts/onboard_data_migration.py verify --root /absolute/source/maps \
  --manifest /absolute/private/maps.inventory.json
python3 scripts/onboard_data_migration.py copy --root /absolute/source/maps \
  --manifest /absolute/private/maps.inventory.json --destination /absolute/new/maps
python3 scripts/onboard_data_migration.py verify --exact --root /absolute/new/maps \
  --manifest /absolute/private/maps.inventory.json
```

For datasets select known `sessions/<id>` directories; retain completed and
needed interrupted history without relabeling its source. Existing server-produced
`exports/<32-hex-id>.json` and `.zip` are preserved opaquely; the utility never
extracts ZIP members. For settings select
only `source-selection.json` and `presets.json`. Route authoring permits
revisioned spatial-route JSON/current files and the existing `route-planner.json`
whose normal loader disables resumed guidance. Never copy a complete navigation
runtime directory, competition state, leases, ARM/session/queued commands or
temporary goals. `mission-history` preserves `missions.json` in a separate
history directory, because the observed source document contains
`active_mission_id`; it must not become the new runtime mission store.
Model inventory supports source/engine/manifest artifacts;
handle additional needed validation logs as separate private evidence.

Verify PGM/YAML image references and map-family/route revisions separately from
byte checksums. Absolute old-host references need an explicit reviewed change;
do not fabricate old evidence or silently rewrite manifests. Service-user
ownership and private permissions must match the new installation. Browser
localStorage is separate from the server data inventory.

Actual preserved data is under `/home/unitree/robot-scope-data/`: `maps`,
`datasets`, selected `runtime/state` settings/routes, separately labelled
operator history, historical missions and calibration. Initial source/target
copy and an independent target preservation root verified every selected file
byte-for-byte before explicit runtime derivatives were applied. The
selected state consists of two settings files, two route documents and one
history-only mission document. Both original event sources remain distinct.
The source spatial-route directory was empty. Dataset manifests retain their
12 original source `output_path` values as historical provenance; the loader
uses the managed dataset root. Opaque export ZIPs were not extracted. Private
calibration identity evidence stays outside Git.

Saved-map IDs include the absolute map path, and revisions include filesystem
device/inode/mtime signatures. Therefore a byte-exact copy changes both IDs and
revisions. `scripts/onboard_map_identity_migration.py` captures actual source
catalog identities and hashes, then derives target identities from the actual
target catalog. It rebuilds only target family/annotation sidecars using the
existing constructors and strict parsers, preserves family/session lineage
and authoring geometry, and records old/new identity and SHA-256 provenance
outside Git. The original source and an independent target preservation root
remain unchanged. A failed final validation restores copied original sidecars.

```bash
# Capture on the source using its active Robot Scope Python/package path.
python3 scripts/onboard_map_identity_migration.py capture \
  --maps-root /absolute/source/maps --output /absolute/private/source-identity.json
# Preview first; add --apply only for the copied target maps.
python3 scripts/onboard_map_identity_migration.py adapt \
  --source-capture /absolute/private/source-identity.json \
  --original-maps /absolute/private/byte-exact-preservation/maps \
  --maps-root /absolute/persistent/maps --report /absolute/private/identity-provenance.json
```

The actual source has 15 maps, 13 valid families and 6 annotation sidecars. One
existing annotation has an authentic original content hash but a historical
rounded-pi yaw (`3.141593`) that the current normalizer clamps to pi, causing
strict content-revision validation to fail. Explicit capture option
`--canonicalize-rounded-pi` recognizes only that authenticated rounding case,
records the original source validation FAIL, and prepares a canonical target
derivative. All other authoring fields, source map pins and original bytes must
match; arbitrary corrupt hashes or authoring changes still fail. No runtime
validation is relaxed. Source identity capture and all 47 preserved artifact
hashes passed. Physical target adaptation passed for all 15 maps and 19
sidecars; current strict catalog checks validated 13 families and 6 annotation
sidecars. All 15 map previews were read on the target, including both PCDs.

The stored pointcloud choice was scoped to the former `Unitree Go2` profile.
Only its target profile scope was explicitly derived for `Unitree Go2 onboard
Jetson`, with private original/new SHA-256 provenance. Normal `SourceRegistry`
loading and the running dashboard restore the persisted `/velodyne_points`
pin. A live API snapshot measured PointCloud2 at 10.01 Hz, age 0.034 seconds,
one publisher and sample state `ok`.

Both imported route documents contain zero saved-map pins and inactive
guidance. Their strict loaders passed after an explicit target schematic cache
derivative: the authentic historical FIELD order used an obsolete restaurant
timing/catalog cache that the current source/target normalizers rejected.
Current `normalize_order` rebuilt only computed timing/catalog/revision fields;
authored grouped orders, IDs, labels, timestamps and layouts remain unchanged.
The historical source failure and original bytes are recorded rather than
relabelled as a successful source validation. The normal loader fences the
runtime to STALE with no guidance or motion/control authority.

One imported navigation preset passed the current parameter validator.
The Dataset manager listed all 12 completed sessions/1225 samples, and 22 gallery
JPEGs across those sessions were read and decoded without starting capture.
The running dashboard then returned HTTP 200 for all eight data/settings/status
inventory endpoints, five representative map/family/annotation/Dataset detail
endpoints and a gallery JPEG that decoded at 1280x720. This is real API/data
access evidence, separate from current live camera frames. Original manifests,
events, calibration and history-only missions retain their preservation checks.

## Cutover, recovery and rollback

Record old service enable/active/PID/restart states, release/config/unit/helper
copies and sensor port owners. Verify external control is idle and command zero;
retire only its Robot Scope authority before starting the new bridge. Keep
manufacturer services and physical robot state intact. Retire unnecessary
Robot Scope relay/capture owners in a recorded order to avoid UDP/device conflicts.

The actual cutover verified old capture/navigation idle, command zero and no
lease before retiring external Robot Scope authority. After the operator's
explicit request, authenticated sudo shutdown of the external host completed
with SSH closing; subsequent SSH/ping had no reply. Physical power has not been
independently observed. Internal API/sensor/camera operation continued without
that host; historical Dataset paths remain provenance rather than live reads.

Start the internal dashboard in safe observation state. Start the independent
bridge only after stationary/zero/cardinality checks. Confirm one required
sensor/camera owner and fresh outputs before mapping/navigation workers. No
automatic ARM, goal, prior session resume or browser reconnect command replay.
Restart only Robot Scope services; then inspect no lease/zero state and recovery.
Reboot is measured only after robot state and an independent reconnection route
are verified. Lack of that prerequisite leaves boot validation NOT_RUN.

Actual dashboard restart passed with the independent bridge PID unchanged,
no resumed lease/goal, real browser reconnection and fresh data recovery.
Separate stop/restore testing passed for all three Robot Scope units: stopped
units were inactive with MainPID=0, a stopped-state environment was restored
from its backup and hash-verified, then the final environment was reapplied
and all three units returned enabled/active with NRestarts=0. Manufacturer
`enable-typec-host` PID 536 and its invocation remained unchanged throughout.
The private report is
`/home/unitree/robot-scope-migration-evidence/service-stop-restore.json`.
These tests establish application stop/configuration recovery; a complete
external-deployment rollback was not executed. Physical Wi-Fi interruption
and a migration-owned controlled reboot remain NOT_RUN because the current
management connection is the sole connection and an independent recovery
route is absent. A subsequent reboot performed by another chat and observed
service recovery are recorded in the post-UI section below.

Rollback: stop new Robot Scope workers in reverse owned-child order, verify
zero/no-lease state and released ports, restore the recorded previous
unit/config/helper/release set, syntax-check sudoers/units, daemon-reload and
restore each recorded enable/active policy. Recheck old health/sensors/data.
Do not delete new/source maps, reset source Git, alter manufacturer workspaces,
or restore transient control state. Activate the external authority only after
the internal authority is confirmed stopped. Reboot/rollback PASS requires
actual execution evidence, not merely the existence of this procedure.

## Fixed acceptance matrix

Capture candidate commit/profile/dependency revisions and actual platform once
prepared. Failures retain evidence and trigger related fixes; do not repeat an
unchanged full suite without cause. The operator changed the compound test to
10 stationary minutes (600 seconds) on 2026-10-13, with necessary cameras/preview/
mapping/navigation observation and bridge status, no lease/goal/ARM. This
measures coexistence over the requested 10 minutes; it does not establish
longer-duration thermal stability.

The read-only diagnostics utility records current platform/network/services/
resources without starting workloads. Invoke it on the actual target with new
private output paths after preparing the required stationary workloads:

```bash
python3 scripts/robot_scope_onboard_diagnostics.py snapshot \
  --disk-path /absolute/persistent/runtime --output /absolute/private/baseline.json
python3 scripts/robot_scope_onboard_diagnostics.py sample \
  --duration-seconds 600 --interval-seconds 10 --output /absolute/private/soak.jsonl
```

A sampler running by itself does not prove simultaneous workloads, sensor
freshness, external power state, reboot or rollback. Preserve those observations
with the acceptance record; diagnostic output never promotes NOT_RUN to PASS.

### Preserved first compound-test failure

The first 600-second camera window began at 03:25:59 UTC on 2026-10-13.
Both camera streams completed it without a stale interval over three seconds,
API errors, OOM or service restart. However, a concurrent diagnostic reader
of the 1,664,000-byte raw cloud coincided with a real pipeline stall. At
03:31:41 UTC, native navigation reported cloud age 8.019 seconds and
`FRESHNESS_THRESHOLD_EXCEEDED`. The C++ bridge rejected growing callback
backlog rather than rebasing timestamps or bypassing its 250 ms limit.
Normal 10 Hz operation returned after that reader exited.

This window is a freshness FAIL, not a clean acceptance PASS. Its original
camera/resource JSONL, bridge log and diagnostic-reader evidence are preserved
privately. The sensor NIC reports 1000 Mbps/full duplex; a 100 Mbps link limit
was not established. Callback timing excludes DDS take/deserialization, and
the exact transport bottleneck is not inferred from that timing alone.

### Hesai fanout correction and identical-reader regression

Runtime candidate `093600f` sets `General/AllowMulticast=spdp` only in the
onboard Hesai driver participant. Participant discovery remains multicast on
the inspected sensor NIC; endpoint discovery and cloud data use unicast.
Other ROS participants and wired/wireless profiles retain their configuration.
Calibration validation, cloud fields, sensor clock conversion, publisher
cardinality, watchdog and freshness limits are unchanged.

At 03:48:13–03:48:25 UTC, the identical diagnostic script observed 100 raw,
100 converted, 100 FAST-LIO odometry and 100 registered clouds, all about
10 Hz. Native API observations before/during/after it had maximum cloud,
odometry and TF receipt ages of 40.2/27.7/26.8 ms, with no freshness failure.
Six native bridge counter windows recorded 300 clouds and zero rejections.
Both dynamic TF pairs advanced; the one static sensor transform was observed.
Signed request evidence added 51 Stop requests, zero Move and zero actions.
This establishes the correction's measured effect without claiming the
unprofiled middleware/socket mechanism is fully explained.

ROS receipt ages and callback durations are not physical source-to-display
latency. Raw XT16 timestamps remain in their device epoch and use the existing
strict C++ calibration contract. Unitree's clock led the host by about 5 ms
in the regression sample; a negative source age is not negative latency.
Humble/CycloneDDS RMW receive timestamps were unavailable and remain null.

### Final pre-UI compound acceptance — PASS

Candidate `093600fc002006fba3ba520c7c58f2f202c85111` ran the corrected
stationary window on 2026-10-13 at 03:49:53–03:59:53 UTC (12:49:53–12:59:53
KST). Both camera collectors covered the same 600.016 seconds; the resource
sampler completed its requested duration with 58 samples. Dashboard, both
cameras, direct Hesai/C++ conversion, FAST-LIO, localization-only Nav2 and the
independent bridge ran concurrently with the external host shut down.

| Final measurement | Result |
| --- | --- |
| Aggregate interval-average CPU / sampled GPU maximum | 54.76% / 0.0% |
| Sampled temperature maximum / available RAM minimum | 69.531°C / 13,474,213,888 bytes (12.55 GiB) |
| Swap used / OOM increase / service restarts / API errors | 0 / 0 / 0 / 0 |
| Cloud / FAST-LIO odometry rate | 9.944–10.047 / 9.939–10.047 Hz; about 10 Hz, not a strict minimum-rate certification |
| Cloud / odometry / TF receipt age maximum | 40.2 / 27.7 / 27.3 ms |
| Cloud / odometry callback p95 maximum | 11.345 / 3.283 ms; excludes physical transport latency |
| Go2 WebSocket delivery | 7,205 JPEGs, 1280×720, 12.010 fps, maximum arrival gap 267.6 ms |
| RealSense WebSocket delivery | 7,350 JPEGs, 640×480, 12.251 fps, maximum arrival gap 270.8 ms |
| Camera stale intervals over 3 seconds / backwards sequences | 0 / 0 for both streams |

Service PIDs/invocations remained unchanged. No freshness error, active lease,
deadman, nonzero Move or action was observed. Nav2 process readiness passed;
localization remained `waiting_initial_pose`/`INITIAL_POSE_REQUIRED`, with no
measured map pose or `map→odom` assertion. Camera delivery rates above are
measured WebSocket rates, distinct from source/decoder rates. Thermal throttling
and longer-duration stability were not measured.

Private evidence: `combined-soak-20261013T034952Z.jsonl`, its `.summary.json`,
`final-acceptance-summary.json`, `final-runtime-ownership.json` and
`xt16-after-dds-fix.log` under `/home/unitree/robot-scope-migration-evidence/`.
The first failed window remains preserved. After acceptance, normal lifecycle
APIs stopped localization and mapping; at 04:06:19 UTC mapping was `stopped`,
navigation/goal `idle`, preview `running`, bridge authenticated/ready and no
lease. The three Robot Scope units and manufacturer PID/invocation remained
unchanged. `final-observation-cleanup.json` records this observation state.

### Independent Isaac ROS VSLAM resource handoff

The separate lab owns release-3.2 environment validation and an isolated
container/workspace. It may not modify operational main/UI/API, FAST-LIO,
Nav2, bridge, services or TF. Use a separate ROS domain and output frames;
do not connect experimental odometry to driving. CUDA, Docker and camera
firmware replacement or arbitrary operational service stops are not authorized
by that experiment. Its measurements require a separate later integration
review; successful experimentation does not automatically change this ADR.

The operational D435i is occupied: at 04:05:40 UTC the accessible device owner
was `gst-launch-1.0` PID 63457, a child of
`robot-scope-realsense-camera.service` PID 39909, holding `/dev/video4` via the
configured stable by-id RGB device. That service provides the 640×480@15 RGB
stream on the internal private address at port 8090. The HTTP RGB preview is
not a synchronized stereo/IMU VSLAM input contract. Keep bag validation first
until a camera time window or reviewed sharing contract is explicitly arranged.
No exclusive camera window or camera release has been granted by this migration.

The final acceptance interval is recorded above. The lab chat's first turn
started at 04:02:25 UTC, after that interval; its observed initial state was
SSH authentication pending. The 58 resource samples contain no retrospective
process/container/build/bag trace, so absence of unrelated experimental load
throughout the interval is not independently certified. The 04:05:40 UTC
read-only process-name/accessible-device snapshot is a current observation,
not a retrospective proof. Future performance/thermal acceptance must record
lab build/run/record activity and exclude those workloads during its window.
Neither this acceptance nor sampled 0% GPU certifies concurrent VSLAM capacity.

| Required check | Current result | Evidence and limits |
| --- | --- | --- |
| Offline durable-data utility | PASS | Eleven focused tests: hash integrity, private permissions, no overwrite, source changes, symlinks/hardlinks, explicit selection, transient-state/traversal rejection, exact-copy, nested datasets, fixed opaque exports and mission-history separation |
| Offline map identity adapter | PASS | Ten focused tests: actual catalog identity changes, family/geometry preservation, byte/source checks, no overwrite, catalog/provenance-write rollback, stale-family refusal, explicit rounded-pi canonicalization and rejection of corrupt hashes/other authoring changes |
| Physical source/target byte preservation | PASS | Private inventories and independent target preservation verified selected maps, datasets, settings/routes, history and calibration; explicit runtime derivatives have separate original/new provenance |
| Internal platform, native ABI and pinned dependencies | PASS | Actual Ubuntu 22.04.5/aarch64/L4T 36.5.2; NumPy 1.26.4/system OpenCV 4.5.4/`rclpy`/Unitree message imports and pinned Humble builds. TensorRT 10.7 is installed package inventory; used model engine absent |
| External shutdown/network absence | PASS | Operator-authorized authenticated sudo shutdown, SSH close and no subsequent SSH/ping reply; internal operation continues. Independent physical power observation NOT_RUN |
| Internal server/browser | PASS | Pre-UI runtime candidate `093600f` runs internally; real browser/API access and reconnect with fresh data at management `.50.30:8088` |
| Required LiDAR, IMU, Go2 state and cameras update | PASS | Fresh sensor observations; FAST-LIO about 10 Hz; Go2 actual 1280x720/about 13 fps and RealSense actual 640x480/15 fps |
| Internal durable data and references | PASS | 15 map previews/13 families/6 annotations, zero-pin route loaders and 1 preset; 12 completed Dataset sessions/1225 samples/22 decoded history JPEGs; real data/settings/gallery APIs HTTP 200 |
| Local mapping/navigation stationary integration | PASS | Internal FAST-LIO outputs about 10 Hz and local Nav2 localization-only workers all ready; `waiting_initial_pose` expected. No estimated physical map location or goal arrival asserted |
| Independent bridge safety contracts | PASS | Signed own named 1/foreign named 0/manufacturer bare 10, zero motion/action, no lease; existing cardinality/signature/watchdog contracts retained |
| Dashboard restart/browser reconnect | PASS | Bridge PID unchanged; no resumed authority/goal; actual browser reconnect and fresh data recovery |
| Robot Scope stop/configuration restore | PASS | Three units inactive/MainPID=0; stopped-state environment backup restored/hash-verified, final environment reapplied; three enabled/active units, NRestarts=0; manufacturer PID/invocation unchanged |
| Physical Wi-Fi reconnect recovery | NOT_RUN | Sole management connection retained; no independent recovery route to safely interrupt it |
| 10-minute compound stationary resource test (operator requested) | PASS | Corrected candidate `093600f`, 600.016-second camera window/58 resource samples, fresh ~10 Hz cloud/odometry, both advancing videos, no OOM/restarts/freshness errors; limits and original failed window retained above |
| Migration-owned controlled reboot and complete external-deployment rollback | NOT_RUN | Independent reboot recovery route absent; later other-chat reboot recovery is separately observed below. Robot Scope stop/configuration restore does not establish full external failback |
| Supervised motion | NOT_RUN | Operator-prepared environment only; not implied by software or stationary PASS |

The required pre-UI stationary internal-only migration acceptance is achieved.
Software and device evidence remain separate. Actual motion, reboot, physical
Wi-Fi interruption, complete external failback and later UI/VSLAM integration
are not implied by this PASS.

## Reviewed UI integration and post-UI functional acceptance — PASS

The operator selected only UI implementation
`95d13e214746f4c866cb71b249b9c5dc9b3d0c00` from
`codex/ui-readability-refinement`, based on `42c6cce986029548e5cc7e0f6f9bd830144cabe3`.
The separate handoff document at `badd801` was reviewed but its commit was not
integrated. The base was already an ancestor of migration main and its static
tree matched the pre-UI migration tree. The selected commit applied without
conflict as `c9c15f0`; both have stable patch ID
`bebb260a7a486d21eab7b93c9d7a2a1bb397bef1`. No old branch merge or whole static
directory replacement was performed. The UI task's checkout, branch and
processes were not changed.

Review found two necessary integration corrections, separately committed as
`92ff609`:

- `safety_hud_view.js`: `safetyStatusLabel()` and `render()` use neutral
  pipeline/lock wording. Localization-only `waiting_initial_pose` must not be
  labelled active autonomous driving. Conservative locking stays unchanged.
- `workspace.js`: the Inspector toggle calls the existing `resize()` recovery
  path. The prior camera geometry could cover Inspector fields/links after
  the content area narrowed. Stream ownership and saved layout are preserved.

Focused regressions cover both fixes. The source integration and these fixes
change no Python backend, API endpoint/payload, ROS, frame, QoS, control gate,
network, dependency or deployment configuration relative to `093600f`.

| Integrated source check | Result |
| --- | --- |
| Full Python unittest | PASS: 1551 run, 1550 passed, 1 skipped |
| Final full JavaScript unit | PASS: 347/347 |
| Existing browser regression | PASS: 67/67 in one run before the two narrow follow-up fixes |
| Readability matrix/fonts/contrast/disclosure/DPR | PASS: 4/4, with 12 capture conditions; after the HUD wording correction |
| Mock STOP/failure/stale/legacy-layout/font lifecycle | PASS: 8/8 |
| Final existing/new Inspector disclosure regression | PASS: 2/2 after the viewport recovery fix; focused HUD view tests also PASS |

Browser checks ran against a separate index-exported temporary candidate with
isolated loopback ports and output paths. The UI task's historical captures
were preserved. The two narrow fixes received affected checks rather than
another unrelated full-suite repetition. Physical iPad/Safari and actual OS
200% zoom remain unmeasured.

Runtime `92ff6092ba8a64c687aa56b122bbce2e53670268` was fast-forward deployed
and the dashboard restarted at 04:21 UTC. Deployment guards checked idle
mapping/navigation, zero command and no lease first. Dashboard PID became
11988; independent bridge PID 947, RealSense service PID 955 and manufacturer
PID 573/invocations remained unchanged across this restart. All three Robot
Scope units remained enabled/active, with NRestarts=0. Served HTML and both
reviewed status modules matched deployed file SHA-256 hashes.

The post-UI functional camera window at 04:21:58–04:22:28 UTC covered
30.014 seconds: Go2 366 valid JPEGs (1280×720, 12.211 delivered fps), RealSense
374 (640×480, 12.488 delivered fps), no protocol error, backwards sequence or
stale interval over 3 seconds. Six API observations kept the bridge ready and
authenticated, no lease/deadman/motion/action, mapping idle and preview running.
Actual browser reload showed both live videos, live LiDAR and the disarmed HUD;
saved Dataset history remained available. This is post-UI functional acceptance,
not a repeat of the pre-UI 600-second performance/thermal measurement.

During local UI tests, another chat rebooted the Jetson (operator confirmed).
Host boot records show shutdown at 04:14 and boot at 04:15 UTC, after the
pre-UI acceptance window. Before migration's UI deployment, all three enabled
Robot Scope services had automatically recovered on original runtime `093600f`
with idle mapping/navigation and safe control state. This is observed recovery
after that external reboot; it is not a migration-owned controlled power-cycle
test or a claim about physical Wi-Fi interruption. Subsequent external-host
TCP22 still timed out. Original pre-reboot PID records retain their own dates.

The separate `vslam-lab-setup-20261013-0410` container was running during this
30-second post-UI smoke and was recorded. This task performed no experimental
integration into operational driving/TF. These observations do not certify
VSLAM coexistence performance. The 04:05 D435i owner above is historical;
after reboot its service owner is PID 955. Camera time-sharing still requires
a separate agreement.

Private source/deployment/boot/smoke evidence is preserved in
`/home/unitree/robot-scope-migration-evidence/` and the development host's
`migration-archives/onboard-20261013-99201d8a/deployment-evidence/` outside Git.
Final source/documentation and remote SHAs belong in that independent record,
avoiding a self-referential documentation commit loop. UI rollback reverts the
integration/follow-up UI commits only, preserving onboard migration, data and
browser settings; it was not executed during acceptance.

### Subsequent camera handoff and parallel checkout state

After all migration/UI acceptance above, the operator explicitly requested
RealSense release for the separate experiment. At 04:51:30 UTC (13:51:30 KST),
`robot-scope-realsense-camera.service` was manually stopped: inactive/dead,
MainPID=0, and no video/hidraw owner was found in readable `/proc` entries.
This is the latest intentional camera state; it does not invalidate the earlier
two-camera acceptance. The VSLAM chat received the camera window and must
recheck ownership before use. Migration will not restart this service until
camera handback. Boot enablement remains enabled, so a later reboot may
reacquire the camera and requires coordination. The dashboard/Go2 camera and
independent control bridge remain operational. Evidence is
`realsense-experiment-handoff.json`.

At final documentation synchronization, the target checkout also contained
parallel uncommitted resource-monitor work in `robot_dashboard/app.py`,
`application/runtime.py`, new resource API/server modules and resource frontend
files. Those changes are outside this migration/UI acceptance and were
preserved; they were not included in this task's Git publication or certified
by the `92ff609` measurements. Documentation-only synchronization must preserve
their hashes and must not restart services to activate them. The final private
record identifies this checkout drift separately from the verified runtime
commit and Git HEAD.
