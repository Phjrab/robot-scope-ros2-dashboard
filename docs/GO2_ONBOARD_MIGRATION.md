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
is recorded. New perception models, UI improvements, goal arrival and competition
completion are outside the completion criteria. Optional features remain
optional unless current target inventory shows they are used.

| Fact/check | Source and result |
| --- | --- |
| Target module | Operator: Go2 internal Orin NX 16GB; historical 2026-08-12 inventory agrees (P3767-0000/P3768-0000) |
| Target current platform | Authenticated read-only inspection: Ubuntu22.04.5 `aarch64`, kernel5.15.199-tegra, L4T36.5.2; NVIDIA/native compatibility inspection continues |
| Historical platform | Ubuntu 20.04.5, kernel 5.10.104-tegra, JP5.1.1/L4T R35.3.1, CUDA11.4.315, TensorRT8.5.2.2; not a current compatibility claim |
| Historical resources | 15W, 4/8 CPU online, roughly 12GB available RAM and 386GB free NVMe; historical values only |
| Target current resources | RAM15642MiB, used1565MiB, available13783MiB; swap7821MiB unused; NVMe467G/free378G. Compound-load/thermal acceptance NOT_RUN |
| Management contact | Supplied internal address `192.168.50.30`, account `unitree`; credentials are never stored here |
| Local management link | Initial development Mac observation: `en0=192.168.50.140`; not a target NIC assignment |
| Internal SSH | Initial attempt timed out before authentication; later authenticated `unitree` access succeeded. Hostname `ubuntu`; deployment/acceptance not implied |
| Target network | Actual sensor NIC `enP8p1s0=192.168.123.18/24`; management Wi-Fi `wlx289401c9eb9b=192.168.50.30/24`, default via `.50.1`. Historical `eth0` is not the current NIC |
| Target service inventory | Initial `robot-scope*`/`unitree*` systemd list empty; manufacturer process/port ownership inspection continues |
| External host | Authenticated read-only inventory: Ubuntu22.04.5, kernel5.15.148-tegra, L4T36.4.7; active Robot Scope release `544e108`, service user `jetson_orin_nano`, Python `/usr/bin/python3.10` |
| External resources | RAM7608MB, swap20188MB, available RAM2713MiB, reported filesystem free40G at inspection; external-host values only |
| External placement | Process cwd `/home/jetson_orin_nano/releases/robot-scope/544e…`; workspace `/home/jetson_orin_nano/project/robot-scope/workspaces`; runtime `/home/jetson_orin_nano/project/robot-scope/runtime` with `maps` and `state` subdirectories |
| External runtime config | Wireless competition FAST-LIO, UDP control, `ROS_LOCALHOST_ONLY=1`, Go2 NIC `eno1`, relay `.50.30`; target onboard selects direct NIC/ROS/local lifecycle |
| Historical sensor packets | Go2 `.123.161`, XT16 `.123.20:10000 -> .123.18:2368`; current packet/port consumers remain to be measured |
| Current durable data | Source and internal target preservation SHA-256 PASS: maps47files/43,115,380bytes; datasets3459files/365,073,866bytes with 12 completed sessions/1225 recorded samples. Runtime use requires separate map/gallery/settings checks |
| Operator-event provenance | Project runtime one file/2428bytes; active release runtime separate file/1250bytes. Preserve with separate source labels |
| External activity | Dataset capture idle and navigation goal idle during read-only inspection; transition still requires fresh zero/no-lease checks |
| Used data history | 2026-09-11 Dataset capture: 212 samples/26,064,528 bytes; map and stationary Nav2 records exist; these counts describe that past session |
| Model scope | External registry only `registry.json`88bytes; engines/packages empty. Historical approved artifacts absent; new model deployment is not required |

Current kernel/L4T above were measured separately from the Ubuntu version;
JetPack/native ABI/ROS overlay and driver checks still need their own evidence. Missing `nvidia-jetpack`
alone is not a platform failure. Recheck OS/architecture/kernel/L4T, installed
NVIDIA packages and relevant native imports independently. Read selected safe
environment keys rather than dumping whole service environments.

## Feature and data transition

The current-host column describes documented deployments, not a newly inspected
live installation. Resolve every runtime path from the active service/arguments
before copying. Default paths below are discovery hints.

| Feature | Documented current host | New host/data | Peers and required change | Verification |
| --- | --- | --- | --- | --- |
| Dashboard/API/WS, Cockpit | External `.50.10` | Internal `.50.30`, `:8088` | Management browsers; `go2-onboard`, persistent paths, local service | Internal PID/cwd/commit, health and real browser frames |
| Go2 state/control | Internal `.50.30` Foxy bridge, external coordinator | Internal Humble ROS bridge + dashboard | Actual sensor NIC to Go2 `.123.161`; local lifecycle, signed ROS transport | Fresh `/lowstate`, signed zero/no-lease status, exact graph ownership; no ARM |
| XT16 preview/mapping | Internal packet relay; external Hesai/C++/FAST-LIO | Internal direct driver/C++/FAST-LIO; private `/etc/robot-scope/hesai/` correction pair | XT16 `.123.20` original UDP; no relay/driver port duplication | Actual packets, one fresh `/lidar_points` and `/velodyne_points`, fields/ring/stamp/frame, FAST-LIO outputs |
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
is `http://192.168.50.30:8088`; it is an intended address until measured.

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
operator history, historical missions and staged calibration. Source and
target private inventories verified every selected file byte-for-byte. The
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
hashes passed; physical target adaptation remains NOT_RUN until executed.
Both imported route documents contain no saved-map pins and inactive guidance;
their normal schemas can be validated without restoring transient guidance.

## Cutover, recovery and rollback

Record old service enable/active/PID/restart states, release/config/unit/helper
copies and sensor port owners. Verify external control is idle and command zero;
retire only its Robot Scope authority before starting the new bridge. Keep
manufacturer services and physical robot state intact. Retire unnecessary
Robot Scope relay/capture owners in a recorded order to avoid UDP/device conflicts.

Start the internal dashboard in safe observation state. Start the independent
bridge only after stationary/zero/cardinality checks. Confirm one required
sensor/camera owner and fresh outputs before mapping/navigation workers. No
automatic ARM, goal, prior session resume or browser reconnect command replay.
Restart only Robot Scope services; then inspect no lease/zero state and recovery.
Reboot is measured only after robot state and an independent reconnection route
are verified. Lack of that prerequisite leaves boot validation NOT_RUN.

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

| Required check | Current result | Evidence needed |
| --- | --- | --- |
| Offline durable-data utility | PASS | Eleven focused tests: hash integrity, private permissions, no overwrite, source changes, symlinks/hardlinks, explicit selection, transient-state/traversal rejection, exact-copy, nested datasets, fixed opaque exports and mission-history separation |
| Offline map identity adapter | PASS | Ten focused tests: actual catalog identity changes, family/geometry preservation, byte/source checks, no overwrite, catalog/provenance-write rollback, stale-family refusal, explicit rounded-pi canonicalization and rejection of corrupt hashes/other authoring changes |
| Physical source/target byte preservation | PASS | Private inventories and independent target preservation verified selected maps, datasets, settings/routes, history and calibration; target runtime use is a separate check |
| Internal platform, native ABI and pinned dependencies | NOT_RUN | Actual target inventory/imports/builds; selected env keys |
| External Jetson OFF/disconnected | NOT_RUN | Physical/operator observation plus no required live peer/file dependency |
| Internal server/browser | NOT_RUN | PID/cwd/commit, management address, real UI/API/WS |
| Required LiDAR, IMU, Go2 state and cameras update | NOT_RUN | Publisher identities, fresh messages and actual advancing frames |
| Internal durable data and references | NOT_RUN | Inventories/checksums/counts, map/gallery/route/settings checks |
| Local mapping/navigation integration and cleanup | NOT_RUN | Process owners, topic/TF/readiness and clean stop; no goal required |
| Independent bridge safety contracts | NOT_RUN | Signed zero/no-lease state, preserved named/bare graph checks and watchdog tests |
| Restart and Wi-Fi reconnect recovery | NOT_RUN | No auto authority, no duplicated processes/ports/capture, fresh data recovery |
| 10-minute compound stationary resource test (operator requested) | NOT_RUN | 600 seconds; CPU/GPU/RAM/swap/temperature, frame ages/message delays, no OOM/repeated crash; longer-duration thermal stability unmeasured |
| Reboot and rollback | NOT_RUN | Safe reconnection prerequisite, actual post-boot recovery and previous-set restore |
| Supervised motion | NOT_RUN | Operator-prepared environment only; not implied by software or stationary PASS |

Record software validation and target validation separately. The overall
internal-only migration remains unachieved until the required live rows pass.
Do not call an inaccessible target BLOCKED merely because one connection timed
out; prepare source, installation, diagnostics and recovery while retrying
meaningful access checks.
