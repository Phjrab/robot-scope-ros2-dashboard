# Hardware validation — 2026-08-30 wireless management transition

## Scope and safety boundary

This session covered the robot-side Jetson wireless management link, its
dedicated Go2 Ethernet link, Go2 DDS/LowState observation, and the external
dashboard/control preflight. It later deployed and exercised the accepted
wireless Control Bridge boundary from commit `b38dc25`. No control lease, ARM,
deadman press, drive, action request, navigation goal, mapping launch, map
mutation, or dataset capture was issued. The only Go2 requests allowed during
the lifecycle check were the Bridge watchdog and shutdown StopMove requests.

The standalone Control Bridge was started once from the dashboard, observed
without acquiring a lease, and stopped immediately after its readiness fields
were captured. The robot-side unit ended disabled and `inactive/dead`, with
zero restarts.

## Validated host and network roles

| Role | Interface/address | Result |
|---|---|---|
| External dashboard Orin management | `eno1=192.168.50.10/24` | PASS; Ethernet carrier and management default route present |
| Robot-side Jetson management | `wlan0=192.168.50.30/24` | PASS; `RobotLab_5G`, DHCP address, management default route present |
| Robot-side Jetson Go2/sensor LAN | `eth0=192.168.123.18/24` | PASS; static address, no gateway, `never-default=yes` |
| Go2 body | `192.168.123.161/24` | PASS from robot-side Jetson; 0% loss, about 0.17 ms average RTT |
| External Orin Go2 interface | no `192.168.123.99/24` | N/A for accepted wireless command/status transport; DDS remains robot-side |

The robot-side wireless adapter was identified as a USB `mt7921u` device using
the Jetson 5.10.104-tegra driver. It associated to the 5 GHz `RobotLab_5G` SSID
at -37 dBm and reported 1200.9 Mbit/s transmit and receive link rates during the
check. Ten management-LAN pings in each direction had 0% loss: external to
robot-side averaged 2.49 ms, and robot-side to external averaged 1.88 ms. These
short checks validate installation and basic link stability, not a competition
soak or interference margin.

The robot-side NetworkManager Ethernet profile was changed from an unresolved
DHCP profile to the fixed dedicated-LAN address. Wi-Fi remains the only default
route, so the Go2/sensor subnet is not used as an Internet or management
gateway. The external Orin reaches the robot-side Jetson management address,
but cannot reach `192.168.123.161`; its current route attempts the management
router and the bounded ping test had 100% loss.

No route, NAT, Linux bridge, multicast forwarder, arbitrary ROS topic relay, or
DDS router was added between the two subnets.

The active Wi-Fi profile obtains `192.168.50.30` by DHCP. The router-side
reservation was configured by the operator but was not independently queried
from the router in this session; a reconnect/reboot retention check remains
part of final field acceptance.

## Deployment configuration aligned to the wireless address

Without starting either camera service, the private host configuration was
updated as follows:

- external dashboard `ROBOT_SCOPE_REALSENSE_RELAY_HOST=192.168.50.30`
- robot-side relay `ROBOT_SCOPE_REALSENSE_BIND_HOST=192.168.50.30`
- robot-side relay `ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST=192.168.50.10`

The RealSense relay remained disabled and inactive. The dashboard is disabled
at boot but was already active under the manual-start operating policy. Its
fixed lifecycle API was used once, after mapping, Nav2, and Dataset Capture were
confirmed idle, to clear an incorrect runtime selection of the relay address as
the robot address. After restart the robot target was again
`192.168.123.161`, matched the startup profile, and had no restart-required
flag. The dashboard correctly stayed in `offline_viewer` mode because the
dedicated interface is absent.

## Go2 DDS and LowState result

On the robot-side Jetson, ROS 2 Foxy, the Unitree message workspace, and
CycloneDDS were explicitly bound to `eth0`. Discovery showed one reliable bare
DDS publisher for each of `/lowstate` and `/lf/lowstate`. Both topics produced
live, increasing samples. A bounded three-second CSV observation counted:

- `/lowstate`: 280 data lines, approximately 93 Hz
- `/lf/lowstate`: 28 data lines, approximately 9 Hz

The observed LowState payload included increasing ticks and finite battery,
power, and temperature fields. This is a PASS for the robot-side Jetson to Go2
DDS/LowState path. DDS itself does not cross Wi-Fi; the external Orin receives
only authenticated Bridge status derived from this local observation.

## Control Bridge lifecycle status

The implementation and hardware result are **PASS** for the bounded no-motion
lifecycle:

1. Initial external Orin commit and robot-side archive both resolved to
   `b38dc255fb4c331760af1b9d95dfa91c890529dd`. The fault-recovery correction
   was then deployed from `97dd0fbc313404dd91e48418e08c0bc80cb81245`.
2. The external dashboard bound a connected UDP socket from
   `192.168.50.10:46010` to `192.168.50.30:46010`; the Bridge bound the exact
   reverse peer while active.
3. Lifecycle SSH used a dedicated ED25519 key, strict host-key matching, a
   forced command with only `status`/`start`/`stop`, and exact-command sudoers.
4. Before START, Nav2, mapping, and Dataset Capture were idle; control had no
   lease, released deadman, and zero linear/angular command.
5. Dashboard START reached the disabled robot-side unit without enabling it at
   boot. The unit became `active/running` with a new invocation and zero
   restarts.
6. Signed status became authenticated and ready over UDP. LowState age was
   1–2 ms, with one LowState publisher, one sport subscriber, one Bridge-owned
   sport publisher, no foreign named sport publishers, and nine expected bare
   Unitree publishers. Total sport publishers were ten.
7. Control remained lease-free with deadman false and all three commanded
   velocities at `0.0`. No ARM, drive, action, or autonomous command was sent.
8. Dashboard STOP succeeded. The robot-side unit returned to
   `disabled`, `inactive/dead`, `Result=success`, and `NRestarts=0`; signed
   status then became stale as required.

The implemented boundary is documented in
[ADR — Authenticated wireless Control Bridge transport](ADR_WIRELESS_CONTROL_TRANSPORT.md).
No route, NAT, bridge, generic DDS router, or arbitrary ROS relay was added.
The full dashboard/Nav2 stack remains on the external Orin, while the minimal
Foxy Bridge and Go2 DDS participant remain on the robot-side Jetson.

## Wireless fault injection and reboot retention

All fault tests were performed with no lease, deadman false, and all three
command velocities at `0.0`. No ARM, drive, action, mapping, navigation, or
Dataset Capture request was used.

### Wi-Fi interruption

The first eight-second scheduled Wi-Fi disconnect exposed an unhandled
`ENETUNREACH` on Bridge status publication. The Bridge exited once while the
address was absent, failed one bind during the systemd retry, and then
recovered, reaching `NRestarts=2`. This initial result was **FAIL** against the
intended local-watchdog continuity contract; it was not hidden or accepted as
the final result. A runtime robot-target change was also observed before the
subsequent STOP, without a corresponding bounded operator-event record. A
dashboard restart restored the startup Go2 target. That target change did not
recur during the isolated repeat, so its trigger remains unassigned.

Commit `97dd0fb` changed both connected-UDP receive loops to survive transient
socket errors and made Bridge status-send failure force a local StopMove while
retaining the ROS watchdog and fixed socket. After deployment, the same
scheduled Wi-Fi disconnect was repeated:

- dashboard readiness changed from ready to unavailable and then stale about
  0.3 seconds after status ceased;
- lease remained absent, deadman false, and command velocities zero;
- Bridge logged one status-transport failure and one recovery;
- the same Bridge invocation remained active with `NRestarts=0`;
- authenticated status recovered automatically with LowState age 1 ms and
  publisher cardinality `1 owned / 0 foreign named / 9 Unitree bare`.

This repeat is **PASS** for no-motion Wi-Fi loss and automatic signed-status
recovery. The observed interval between the Bridge's failure and recovery logs
was about 16 seconds, including NetworkManager reassociation and DHCP.

### Bridge process loss

The active Bridge main process was then sent `SIGKILL` to model abrupt process
loss. Dashboard status became unavailable/stale in about 0.3 seconds. Systemd
created one restart after its configured three-second delay, the Bridge epoch
and invocation changed, and authenticated ready status returned about 4.3
seconds after the first unavailable observation. `NRestarts=1`, LowState age
was 1 ms, cardinality remained `1/0/9`, and no lease or non-zero command
appeared. This is **PASS** for no-motion detection and service recovery.

Because `SIGKILL` cannot execute the Bridge's three shutdown StopMove
publications, this result does not authorize an abrupt-process-loss test while
the robot is moving. Such a test requires a separate supervised motion-risk
plan and an independent physical stop boundary.

### DHCP reservation across reboot

The Bridge and RealSense units were stopped, disabled, and inactive before the
robot-side Jetson reboot. Its boot ID changed from
`50a4cc40-b8d6-4fd2-ae3a-15feb44448bd` to
`98a95905-6f6f-4dbd-980d-c77102a7f09b`. SSH returned after approximately 37
seconds with:

- `wlan0=192.168.50.30/24` from the DHCP profile and gateway
  `192.168.50.1`;
- `eth0=192.168.123.18/24` retained for the Go2 LAN;
- NetworkManager autoconnect `yes`, IPv4 method `auto`, and no Wi-Fi
  `never-default` restriction;
- NTP synchronized in `Asia/Seoul` before signed-control reuse;
- 0% loss to the Go2 at `192.168.123.161`, about 0.19 ms average RTT;
- Bridge and RealSense both still `disabled/inactive/dead`;
- dashboard restricted lifecycle status recovered and reported START
  available without starting the unit.

This is **PASS** for the configured `.50.30` DHCP reservation across one
intentional reboot. Router configuration itself was not queried; the observed
lease retention is the acceptance evidence.

## Wireless dual-camera dashboard validation

Commit `903b57a` added the fixed, camera-only Go2 RTP relay and was deployed to
the external dashboard Orin. The robot-side Jetson received the exact relay
script and systemd unit from that commit. Their deployed SHA-256 hashes were:

- `go2_camera_rtp_relay.py`:
  `defc4723c13696ed704a2590e39ecb54f404e3543a8bf8eee6a4b2dac18c6044`
- `robot-scope-go2-camera-relay.service`:
  `20b73b0860ce92cfdc190e57fd14ef7aae8beda2bd2d290e01234a46f77c6619`

The relay accepted only H.264 RTP payload type 96 from Go2 source
`192.168.123.161` at the fixed multicast endpoint `230.1.1.1:1720` on
robot-side `eth0`. It forwarded unchanged, validated datagrams from the fixed
robot-side source `192.168.50.30:46120` to the external dashboard Orin at
`192.168.50.10:1720`. It did not add a route, NAT rule, Linux bridge, DDS/ROS
relay, control transport, or runtime-configurable forwarding destination.

The robot-side service was deliberately left `disabled` at boot and manually
started for the camera check. It remained `active/running`, with one process,
one invocation, and `NRestarts=0`. The Control Bridge remained inactive on
both hosts throughout; no control lease, ARM, deadman, motion command,
navigation, mapping, or Dataset Capture operation was used.

### Dashboard and decoder result

The existing dashboard receiver decoded the relayed Go2 stream without a
dashboard code change. The Sensors view showed:

- Go2 front camera: **LIVE**, about 11.1 FPS, `1280x720`, `FRAME READY`
- RealSense color camera: **LIVE**, 15.0 FPS, `640x480`, `FRAME READY`

Cockpit was then configured with both camera panels in a 50:50 layout. With
both panels open at the same time, the UI reported:

- Go2 front camera: **LIVE**, 12.4 FPS, age 0.1 s, `1280x720`, `CONNECTED`
- RealSense color camera: **LIVE**, 15.0 FPS, age 0.0 s, `640x480`,
  `CONNECTED`

At that point the camera API reported `active_sources=2` and `viewers=2`, with
exactly one viewer for each source. The Go2 side had one external GStreamer
decoder, and the RealSense side had one relay process and one GStreamer
producer. No duplicate viewer or producer was present. RealSense briefly
showed `WAITING` during initial panel stabilization and automatically returned
to `LIVE` within five seconds without operator action.

After the Cockpit browser tab was closed and the disconnect grace period
elapsed, the API returned `active_sources=0`, `viewers=0`, and zero viewers for
both sources. The external Go2 GStreamer decoder exited. RealSense health
returned `status=idle`, `viewers=0`, `process_running=false`, and
`producer_thread_running=false`, with no last error. This is **PASS** for
demand-scoped startup and cleanup of both camera producers.

The Go2 relay itself remains active so that a future dashboard viewer can
attach without a robot-side login. Its final sampled counters were 81,030
captured and accepted packets, 80,833 forwarded packets, zero sequence loss,
duplicates, reordering, SSRC changes, or rejected packets. The 197 send errors
accumulated only while no dashboard UDP listener existed; they resumed after
the browser viewer closed and did not occur during the continuous dual-camera
LIVE observation. This is expected for the connected UDP no-listener interval,
not evidence of RTP corruption.

The first Sensors-page check found that the `2 화면` control did not switch from
its single-camera layout even though it appeared enabled. At a 1280-pixel
browser viewport, the half-width camera panel was about 410 pixels wide while
the three-column toolbar required about 490 pixels. The primary-camera select
therefore covered the center of the dual-view button.

Commit `317bbb3` changed the toolbar to two bounded control columns plus a
separate capacity row and gave the view toggle a 130-pixel minimum width. The
deployed button center then resolved to `cameraDualMode`, not the overlapping
select. A real click changed `aria-pressed` to `true`, changed the grid to
`dual`, exposed the secondary slot, and reported `2 CONNECTED / 2 REQUESTED`.
Sensors simultaneously showed RealSense **LIVE** at 15.0 FPS and Go2 front
**LIVE** at 11.3 FPS. This follow-up is **PASS** for the Sensors dual-view fix.

## External-dashboard point-cloud and mapping check

The external dashboard Orin remained in its intentional `offline_viewer` ROS
transport mode. Its selected `/velodyne_points` descriptor had zero publishers,
zero samples, and `available=false`; the point-cloud snapshot contained zero
source and sent points. The Live Mapping page therefore showed `NO POINTCLOUD
TOPIC`, `0 POINTS`, and ROS data `WAITING`.

A single operator-requested, no-motion `새 맵 시작` check was made after
confirming no control lease, released deadman, zero velocity command, inactive
Control Bridge, idle Nav2, and idle Dataset Capture. The allowlisted launcher
failed closed in less than one second because external-Orin `eno1` does not own
the required sensor-LAN address `192.168.123.99/24`. Pipeline state became
`failed` with exit status 1. No FAST-LIO, XT16 bridge, or LiDAR driver process
remained, no map was saved, and no robot command was sent.

This result is **FAIL** for point-cloud display and mapping on the current
external wireless dashboard, but **PASS** for the launcher's network preflight
and cleanup boundary. The narrow wireless transports currently carry camera
and authenticated control status/commands only; they deliberately do not
carry arbitrary ROS/DDS or XT16 point-cloud traffic. Restoring mapping requires
a separately reviewed sensor-data architecture. It must not be worked around
by silently adding a broad route, NAT, bridge, or DDS router.

## WP01/WP02 RealSense follow-up — 2026-08-31

The external dashboard Orin was fast-forwarded to commit `d3c1f71` before this
check. The robot-side relay script was installed from the same source at SHA-256
`5d4ef09a92b6ccfadaf99eeaadd3b05ac7fe2c5aed203c02062301836e8a0475`.
The configured relay profile was 640x480 at 15 FPS and JPEG quality 72.

The source-address boundary behaved as designed: requests from the management
Mac (`192.168.50.104`) received HTTP 403 for both `/health` and `/stream`, while
the external dashboard Orin and the relay host received HTTP 200. An external
dashboard WebSocket observation received 110 valid 640x480 JPEG frames in
8.036 seconds (13.69 observed FPS). While open, the dashboard reported one
viewer, 15.01 receive FPS, 6.454 Mbps, 35 successful decodes, and zero decode
failures. The relay reported one viewer and one producer, 15.16 FPS, 5.356
Mbps, and zero invalid frames. After closure, both layers returned to zero
viewers and the relay producer stopped. This is **PASS** for WP01 bounded
access, profile reporting, decode, single-producer behavior, and cleanup.

The first WP02 sample exposed a real observability defect: the relay returned
`wifi.state=UNVERIFIED` and `iw link probe failed` even though the same
unprivileged `iw dev wlan0 link` command worked outside the unit. The unit's
address-family sandbox omitted generic netlink. The service definition now
allows `AF_NETLINK` for that fixed-argument read-only probe while retaining an
empty `CapabilityBoundingSet` and no interface, route, or wireless mutation
authority. A contract test locks this boundary.

The corrected installed unit matched SHA-256
`37fc89f03fce61148a6cf1a0333f9afc394a6d4f7b7f75f87ee5e4fd97071ad0`.
Runtime properties confirmed an empty capability bounding set,
`RestrictAddressFamilies=AF_INET AF_INET6 AF_NETLINK AF_UNIX`, zero service
restarts, and the required manual-only `disabled` boot policy. Relay health
then reported Wi-Fi `LIVE` at -34 dBm and 1200.9 Mbps. A six-second stream from
the external Orin transferred 4,198,376 bytes; the in-stream sample showed one
viewer, one producer, 15.55 FPS, and zero invalid frames. After the disconnect
grace period, health returned to `idle`, zero viewers, and stopped producer and
producer thread. This is **PASS** for WP02 read-only link observability,
least-privilege confinement, bounded stream operation, and cleanup.

No control lease, deadman input, motion command, navigation, mapping, dataset
capture, or service auto-enable was used during these checks. The Control
Bridge remained inactive, the command projection remained zero, and the
RealSense relay was left manually active but disabled at boot.

Follow-up repository verification for this correction:

- targeted RealSense Python tests: 28 passed, 0 failed;
- camera-media JavaScript tests: 21 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- complete JavaScript suite: 252 passed, 0 failed;
- browser E2E: 29 passed and one timing-sensitive mission-restoration case
  failed in the full 30-case run; that exact case passed when rerun alone;
- complete Python suite: 793 run, 792 passed, with the unchanged macOS-only
  `/etc/os-release` baseline error in the Ubuntu installer test;
- mypy configured targets: PASS;
- Ruff: the correction itself is clean; the repository-wide targeted scan
  retains the existing `mission_coordinator.py:691` E701 finding;
- secret scan and `git diff --check`: PASS.

## WP03 shadow-runtime inventory and fail-closed gate — 2026-08-31

Read-only inventory on the Go2-mounted Jetson reconfirmed `aarch64`, Python
3.8.10, L4T 35.3.1, CUDA 11.4, TensorRT 8.5.2.2, OpenCV 4.2.0, NumPy 1.17.4,
and Pillow 7.0.0. ROS Noetic and Foxy are installed, but the standalone shadow
runtime imports neither. ONNX Runtime remains unavailable. No package or
system-Python dependency was installed.

The WP03 unit and executable were not installed, the model root was absent,
and no approved Lane or Object manifest or target-built TensorRT engine was
available. Hardware inference, resource comparison, and soak therefore remain
**BLOCKED** rather than being inferred from software tests.

Source review found that the relay's exact `source_sequence` and
`source_epoch` reached the sidecar frame but were omitted from the result
contract. The runtime and external validator now require and preserve both
fields while retaining a separate sidecar-monotonic result `sequence`. Frames
with missing/non-positive source identity fail before entering the depth-one
hub, and malformed remote results fail atomically. Tests now cover a relay
process restart where source epoch changes and source sequence returns to one
while result sequence continues increasing.

The corrected sidecar was copied only to a temporary unprivileged path on the
robot for Python 3.8 compatibility and fail-closed checks; no systemd unit was
installed or started, and the temporary copy was removed afterward. The staged SHA-256 was
`92e277ae25db8bb38d604f034cb1776fc97b2d06505291ebb09355cb251fb66f`.
An unexpected argument returned exit status 2. A fixed host configuration with
deliberately missing model names returned exit status 2 with
`INVALID_MANIFEST` before opening health or result listeners. Ports 8091 and
8092 remained closed, Control Bridge remained inactive, and the independent
RealSense relay remained active/disabled and idle with zero viewers and no
capture producer.

This is **PASS** for target-Python compatibility, invalid-model fail-closed
behavior, zero motion/control ownership, and exact source-frame traceability.
It is **BLOCKED** for relay + Lane + YOLO coexistence, per-model/combined
performance, CPU/GPU/RAM/swap/thermal measurements, preview comparison,
robot-service freshness under inference load, and the required 30-minute soak.

WP03 follow-up verification results:

- shadow runtime Python tests: 11 passed, 0 failed;
- external perception contract Python tests: 9 passed, 0 failed;
- perception/Cockpit JavaScript tests: 8 passed, 0 failed;
- complete JavaScript suite: 252 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- browser E2E: 30 passed, 0 failed;
- complete Python suite: 793 run, 792 passed, with the unchanged macOS-only
  `/etc/os-release` baseline error in the Ubuntu installer test;
- mypy configured targets: PASS;
- Ruff: all WP03 files passed; the repository-wide scan retains only the
  existing `mission_coordinator.py:691` E701 finding;
- `git diff --check`: PASS.

## WP04 result contract and dashboard integration — 2026-08-31

The existing narrow server-to-server HTTP pull transport remains unchanged.
The external dashboard now validates source-frame freshness in the robot
monotonic clock domain, rejects an input older than the fixed 1.5-second limit
even when inference completed recently, and projects that input age forward
only with external receive-domain elapsed time. It never subtracts timestamps
from different hosts.

Sensors, Cockpit camera panels, and Competition status now expose the exact
relay `source_sequence`, `source_epoch`, and input age. Missing or malformed
source identity fails closed to a stale/degraded presentation. Bounded dataset
metadata references preserve the same source identity and input age without
capturing or starting a dataset. No control, motion, navigation, mapping, or
service lifecycle behavior was changed.

The live inference portion remains **BLOCKED**: the robot-side shadow service
is intentionally not installed or running because no approved Lane/YOLO model
manifests and target-built TensorRT engines exist. Consequently the external
receiver policy is not configured and the dashboard correctly returns the
fail-closed unavailable state. Software contract, projection, stale cleanup,
and dashboard integration are **PASS**; actual Lane/YOLO overlay and record
verification must wait for approved model artifacts.

WP04 verification results:

- perception contract Python tests: 9 passed, 0 failed;
- perception/Cockpit JavaScript tests: 8 passed, 0 failed;
- complete JavaScript suite: 252 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- browser E2E: 30 passed, 0 failed;
- complete Python suite: 793 run, 792 passed, with the unchanged macOS-only
  `/etc/os-release` baseline error in the Ubuntu installer test;
- mypy configured targets: PASS;
- Ruff: the WP04 files pass targeted checks; the repository-wide scan retains
  only the existing `mission_coordinator.py:691` E701 finding;
- `git diff --check`: PASS.

## WP05 dataset and model lifecycle follow-up — 2026-08-31

The original WP05 implementation from `3703f27` was re-audited against the
current repository after WP04. Dataset Capture remained idle on the external
Orin, with the configured 20 GiB session quota and 5 GiB filesystem reserve.
The dashboard model registry was empty, reported no active or previous model,
and retained the `LOCAL_OPERATOR_ONLY` activation surface. No Dataset session,
export archive, package stage, model activation, rollback or service restart
was performed during this follow-up.

The audit found two model-registry persistence gaps. A third activation could
leave an older record marked `previous` after the task's single previous
pointer moved, causing the next registry load to fail closed. Activation now
atomically demotes that older rollback candidate to `validated`, preserves
exactly one `previous` model, and prevents rejection of that candidate. An
existing engine SHA directory was also accepted without rechecking all stored
artifacts. It must now contain exactly the engine, bounded build log and
validation evidence with matching hashes and content; any collision leaves the
model staged and the active registry unchanged. A new cross-component Dataset
test also confirms that WP04 relay sequence, relay epoch, input age and
unverified clock state reach the bounded sample perception reference.

The Go2-mounted Jetson remained stationary with Control Bridge and shadow
perception inactive. Its model registry root was absent and no `model.onnx` or
`engine.plan` existed in the project tree. The target was reconfirmed as L4T
35.3.1 with TensorRT 8.5.2 and CUDA 11.4. Actual package staging, TensorRT
generation, shadow/resource validation, activation and rollback therefore
remain **BLOCKED** pending an approved model package and supervised evidence;
software Dataset/export and registry contracts are **PASS**.

WP05 follow-up verification results:

- Dataset/perception/model targeted Python tests: 40 passed, 0 failed;
- model registry and application-contract tests: 12 passed, 0 failed;
- complete JavaScript suite: 252 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- browser E2E: 30 passed, 0 failed;
- complete Python suite: 796 run, 795 passed, with the unchanged macOS-only
  `/etc/os-release` baseline error in the Ubuntu installer test;
- mypy configured targets: PASS;
- tracked-source secret scan: PASS;
- Ruff: all WP05 files passed; the repository-wide scan retains only the
  existing `mission_coordinator.py:691` E701 finding;
- `git diff --check`: PASS.

## macOS installer baseline resolution — 2026-08-31

The remaining repository-wide Python failure was in the test fixture, not the
installer. The fixture read Linux-only `/etc/os-release` before invoking the
installer. It now selects a mismatched Ubuntu fixture when the host file exists
and accepts only the installer’s earlier Ubuntu-only apply rejection on macOS.
Linux still must produce the exact host-mismatch rejection. Both paths require
exit status 2 and verify that no configuration directory was created, so the
fail-closed assertion is unchanged. The complete Python suite now passes all
796 tests on the macOS development host. The unrelated pre-existing Ruff E701
finding in Mission abort handling was also expanded to an equivalent block;
the repository-wide `robot_dashboard` and `scripts` Ruff scan now passes.

## WP06 Competition Cockpit hardware follow-up — 2026-08-31

The external Orin checkout was cleanly fast-forwarded from `61a9131` to
`ba799bc`, then the dashboard-only lifecycle endpoint restarted
`robot-scope.service` with no active lifecycle blockers. The new dashboard
instance was `eaeb9b986298467a85b627929cfadbfb`. No ARM, deadman, motion command,
robot action, Navigation, Mapping or Dataset mutation was issued.

The receiver restart briefly projected `command datagram failed`, then the
existing authenticated Bridge recovered without operator motion input. The
steady state was Bridge `READY`, connected and authenticated, with LowState age
0–1 ms, one expected Bridge publisher, all nine expected bare Sport publishers,
no lease, deadman released and all three command axes exactly zero. The
robot-side Bridge service remained active but disabled at boot.

Before the HUD correction, the live Cockpit showed Control Bridge `READY` while
GO2 LINK remained `OFFLINE` and LOWSTATE remained `WAITING`, because the
external Orin deliberately has no direct Go2 DDS route. After deployment, the
same in-app browser showed the distinct split-topology state `CONTROL LIVE` and
the bounded Bridge LowState age while preserving `DISARMED`, lease `NONE`,
authority `NONE`, MANUAL mode and zero command axes. Direct ROS telemetry is
still offline and is not relabelled as live.

Competition Lock was enabled with explicit `LOCK` confirmation. The Cockpit
showed `LOCKED · PHYSICAL SAFETY: NO`, disabled mode controls and retained the
always-visible Dashboard SOFTWARE STOP. A dashboard restart request was
rejected with HTTP 423 and `Competition Lock blocks dashboard service restart`.
The lock was then released with explicit `UNLOCK`, stationary confirmation and
server-authoritative idle blockers; the final state was unlocked, MANUAL,
motion authority `NONE`, lease absent, deadman released and command axes zero.

The camera panels were not opened during this narrow follow-up, so the Network
and Camera fields correctly remained `UNAVAILABLE`/`WAITING`. Perception stayed
SHADOW with authority `NONE`; Lane, YOLO and Depth remained `OFFLINE`,
PointCloud diagnostic mode remained `OFF`, and both active and previous model
fields remained `NONE`. These are truthful unavailable states, not WP06 display
failures. Actual model overlay evidence remains blocked by the missing approved
model artifacts recorded in the WP04/WP05 sections.

WP06 follow-up verification results:

- Safety HUD targeted JavaScript tests: 11 passed, 0 failed;
- Cockpit JavaScript suite: 78 passed, 0 failed;
- complete JavaScript suite: 253 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- complete Python suite: 796 passed, 0 failed;
- Ruff configured repository targets: PASS;
- tracked-source secret scan: PASS;
- browser E2E: 30 passed, 0 failed after making the two mission tests refresh
  their injected annotation fixture explicitly; their waypoint and mission
  assertions were not removed or weakened;
- `git diff --check`: PASS.

WP06 is **PASS** for the currently available software, split-topology Bridge
status, fail-closed display and Competition Lock behavior. Live camera overlay
and model rollback display hardware evidence remain pending approved model
artifacts, while their software contracts are covered by the passing suites.

## WP07 read-only acceptance follow-up — 2026-08-31

The first robot-connected `go2-control` recorder run at commit `e357bdb`
reported `PASS=25 FAIL=2 BLOCKED=22 NOT_RUN=24`. The fixed failure rows exposed
two distinct causes: the observation was intentionally unlocked, and the
recorder incorrectly required the external Orin's direct ROS interface even in
the accepted signed-Bridge control topology. No failure was reclassified by
weakening a timeout or assertion.

Commit `758e274` makes the link contract mode-specific. `go2-control` now
requires the agent, pinned target, authenticated and connected Bridge, Bridge
status age at most 0.75 s and LowState age at most 750 ms. `go2-nav` and XT16
modes retain their direct ROS-interface requirement, and the separate exact
publisher-cardinality check remains unchanged. Regression tests prove both the
split-control PASS path and the unchanged direct-ROS failure path.

The patched recorder was deployed without a dashboard restart. During the
second read-only observation Competition Lock was explicitly enabled and the
robot remained stationary, DISARMED, deadman released, without a lease and with
all command axes zero. The resulting private report was
`acceptance-20260831T010027.420870Z` with `PASS=27 FAIL=0 BLOCKED=22 NOT_RUN=24`.
Lock was then explicitly released; the final Bridge remained authenticated,
connected and ready with LowState age 0 ms and exact publisher cardinality.

The 22 BLOCKED rows are retained for unavailable direct ROS/Nav/XT16 evidence,
inactive local-only Bridge systemd ownership on the external host, unavailable
RealSense/network quality, missing perception/model/compute evidence and
robot-side PointCloud mode. All 24 supervised rows remain NOT_RUN because the
recorder's five field confirmations were not supplied. The separately observed
dashboard receiver recovery and Competition Lock rejection were not promoted
to formal supervised PASS records.

WP07 recorder verification results:

- targeted acceptance and WP07 contract tests: 25 passed, 0 failed;
- complete Python suite: 798 passed, 0 failed;
- complete JavaScript suite: 253 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- mypy configured targets: PASS;
- Ruff configured repository targets: PASS;
- tracked-source secret scan: PASS;
- browser E2E: 30 passed, 0 failed;
- `git diff --check`: PASS.

## RealSense immediate restart recovery — 2026-08-31

The robot-side RealSense and fixed Go2 camera relay services were manually
started while their boot policy remained disabled. Sensors dual view showed
RealSense LIVE at 640×480 and 15.0 FPS and Go2 LIVE at 1280×720 and about
11.9 FPS. RealSense Wi-Fi was -37 to -39 dBm at 1080.6–1200.9 Mbps, transport
was about 6.8–7.6 Mbps, and browser decode reported zero failures and drops.
The dashboard owned exactly one viewer per source; the robot relay owned one
viewer and one producer process/thread with zero invalid frames.

Stopping the RealSense relay while the dual panel remained open changed only
the RealSense panel and transport/decode fields to STALE; Go2 remained LIVE and
the old RealSense frame was not presented as live. Immediate restart then
failed: the cleanly replaced process could not bind fixed port 8090 while the
prior MJPEG TCP connection was still tearing down. Systemd made five bounded
attempts and entered failed with `Address already in use`.

Commit `f48ef07` enables only `SO_REUSEADDR` on the single fixed HTTP listener.
`SO_REUSEPORT` remains disabled, so parallel listeners are not permitted. The
dashboard/relay IP allowlist, fixed port, viewer/client caps, capture profile,
frame bounds and service hardening are unchanged. The root-owned deployed file
has SHA-256 `36c0a0676a47eea48e0eb4cc0618270ed15f6c23e9f3a226ad81324db0f1b916`;
the pre-fix file is retained as
`/usr/local/libexec/robot-scope/realsense_mjpeg_relay.py.pre-f48ef07`.

With a viewer open, an immediate `systemctl restart` then returned active with
`NRestarts=0`. The existing dashboard receiver automatically returned to
RealSense LIVE at 640×480 while Go2 remained LIVE. Viewer/producer cardinality
was still one per layer and invalid/decode failure/drop counts remained zero.
After leaving Sensors, both dashboard viewers were zero and the robot-side
RealSense relay returned to idle with no producer process or thread. Both
camera services remained manually active and disabled at boot.

Verification results for this correction:

- RealSense relay tests: 29 passed, 0 failed;
- camera JavaScript tests: 28 passed, 0 failed;
- complete JavaScript suite: 253 passed, 0 failed;
- complete Python suite: 799 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- Ruff configured repository targets: PASS;
- tracked-source secret scan: PASS;
- `git diff --check`: PASS.

## Go2 relay recovery and preview demand lifecycle — 2026-08-31

With Sensors already in dual-camera mode, the fixed Go2 relay was restarted
once while the robot remained stationary. The service MainPID changed from
3898 to 5277 and returned `active/running` with `NRestarts=0`; its boot policy
remained `disabled`. The dashboard receiver reconnected without operator
action. The browser showed Go2 LIVE at 1280x720 and about 11.6 FPS after
stabilization, while the RealSense primary stayed LIVE at 640x480 and about
15–19 FPS. The interruption was shorter than the UI observation interval, so
no transient STALE/WAITING label was claimed. Post-recovery API state was
`active_sources=2`, `viewers=2`, with exactly one viewer per source and zero
RealSense decode failures.

The Sensors layout was then changed from dual view to single view and back.
Dual view reported one RealSense viewer and one Go2 viewer. Single view kept
the RealSense primary LIVE with one viewer and released Go2 to `stopped` with
zero viewers, yielding `active_sources=1` and `viewers=1`. Returning to dual
view restored exactly one viewer for each source, with no duplicate consumer.
After leaving Sensors for Overview, both sources were `stopped`,
`active_sources=0`, and `viewers=0`. Robot-side RealSense health was `idle`
with zero viewers and both producer process and producer thread stopped.

The final control projection still had no lease, deadman false, and all linear
and angular commands at zero. No ARM, motion, action, Dataset, Navigation, or
Mapping request was issued. Both camera services were left manually active and
disabled at boot. This is a separate non-motion observation; it does not
promote `supervised.preview_consumer_disconnect` or any other formal WP07
scenario to PASS without the recorder's five required field confirmations.

Repository verification for this observation-only update:

- complete Python suite: 799 passed, 0 failed;
- complete JavaScript suite: 253 passed, 0 failed;
- frontend syntax check: 51 modules passed;
- Ruff configured repository targets: PASS;
- tracked-source secret scan: PASS;
- `git diff --check`: PASS.

### Formal supervised preview-consumer record

Later on 2026-08-31 the operator explicitly supplied all five supervised field
confirmations: supervised execution approval, physical remote/E-stop ready,
clear area, low-speed limits confirmed, and a present safety operator. The
same preview lifecycle was therefore rerun while the robot remained stationary.
The external dashboard checkout was commit `07e58a7`; the two relay scripts and
two installed camera service units on the robot-side Jetson matched the files
from that commit by SHA-256.

The first immutable recorder output,
`acceptance-20260831T014104.873048Z`, retained the selected preview scenario as
PASS but had overall `PASS=27 FAIL=2 BLOCKED=21 NOT_RUN=23`. It was collected
after closing Sensors, so the dashboard's demand-scoped Wi-Fi cache was STALE,
and Competition Lock had not been enabled. The robot relay's direct health was
LIVE; the failed report was preserved instead of deleted or edited.

The fixed procedure kept Sensors LIVE during collection and enabled the
non-physical Competition Lock only for that read-only interval. Report
`acceptance-20260831T014254.689479Z` recorded
`PASS=31 FAIL=0 BLOCKED=19 NOT_RUN=23`. It specifically recorded
`network.robot_wifi=PASS`, `competition.lock_and_authority=PASS`, and
`supervised.preview_consumer_disconnect=PASS`. The selected scenario observed
viewer counts `2 -> 1 -> 2 -> 0`, zero Go2 receivers after disconnect, exactly
one after reconnect, and an idle RealSense producer after final panel close.

Competition Lock was explicitly released after collection. Final state was
MANUAL with motion authority NONE, no control lease, deadman false, all command
axes zero, both dashboard camera viewers zero, and both camera services still
manually active but disabled at boot. No ARM, motion, action, Dataset,
Navigation, or Mapping operation occurred.

## Remaining supervised scenarios and dashboard connectivity — 2026-08-31

The operator again confirmed the physical remote/E-stop, clear area, reviewed
low-speed limits, supervised execution approval and an on-site safety operator.
The robot remained stationary for every lifecycle and fault-prerequisite row.
Each formal recorder invocation selected exactly one fixed supervised scenario.
Competition Lock was enabled only while each report was collected and was
explicitly released afterwards.

The dashboard header continued to show the robot offline even while the signed
control path was healthy. This is a projection mismatch in the intentional
split wireless topology, not a Control Bridge disconnect. The external Jetson
has no route to the Go2 body at `192.168.123.161`; `/api/v1/state` therefore
reported `robot_target_connected=true`, `robot_online=false`, and ROS transport
`offline_viewer`. The robot-side Jetson retained the dedicated body interface
and the dashboard control projection simultaneously reported authenticated and
connected Bridge readiness, one expected LowState publisher, exact Sport graph
cardinality and 0--2 ms LowState age. Adding an external route, NAT or DDS
router was deliberately not attempted because it would change the reviewed
network and control boundary. A future UI change should distinguish direct
ROS/ICMP observability from signed remote-control readiness.

The following rows passed:

| Scenario | Report | Result and bounded evidence |
| --- | --- | --- |
| `supervised.manual_short_stop` | `acceptance-20260831T021545.648708Z` | `PASS`; after an allowlisted Stand up action, 40 public dashboard control frames held the existing 35% server limit for 2 seconds. The operator observed forward motion and complete stop; final lease and command were zero. |
| `supervised.browser_disconnect_watchdog` | `acceptance-20260831T021754.601247Z` | `PASS`; the control socket was aborted after 16 frames and the dashboard reported lease release, deadman false and exact zero in 63.6 ms. The operator observed motion and complete stop, with no automatic ARM/AUTO return. |
| `supervised.competition_lock_mutation_rejection` | `acceptance-20260831T015229.515673Z` | `PASS`; a harmless PointCloud setting mutation returned HTTP 423 while cleanup remained available. |
| `supervised.realsense_relay_restart` | `acceptance-20260831T015440.454194Z` | `PASS`; both cameras returned LIVE, one viewer per source, one producer process/thread and zero decode failures. |
| `supervised.dataset_shutdown_blocker` | `acceptance-20260831T015538.566325Z` | `PASS`; 17 RealSense samples (1,129,860 bytes) finalized and dashboard stop was rejected with HTTP 409 and `dataset_capture_active` while capture was active. |
| `supervised.control_bridge_stop` | `acceptance-20260831T015635.416852Z` | `PASS`; stop revoked signed readiness with no lease and zero command, then manual start recovered authenticated readiness without ARM. |
| `supervised.dashboard_process_stop` | `acceptance-20260831T015809.586916Z` | `PASS`; dashboard reached inactive/dead, robot-side Bridge stayed active, and manual dashboard start recovered DISARMED with boot policy still disabled. |
| `supervised.dashboard_receiver_restart` | `acceptance-20260831T020026.055773Z` | `PASS`; both source stream IDs were replaced once, viewers returned to exactly one per source, and no ARM/AUTO state returned. The relay counter advances once for invalidation and once for replacement, so one normal producer stop/start is a `+2` counter change, not two live producers. |

Every PASS report above had `FAIL=0` and the accepted baseline summary
`PASS=31 BLOCKED=19 NOT_RUN=23`. Runtime Dataset files, temporary supervised
clients and immutable acceptance reports remain private deployment artifacts
and were not added to Git.

The remaining fault rows were recorded as `BLOCKED`, not simulated or promoted
from software tests:

| Scenario | Report | Blocking prerequisite |
| --- | --- | --- |
| `supervised.stale_lowstate` | `acceptance-20260831T020311.767414Z` | No approved isolated LowState interruption fixture. |
| `supervised.foreign_sport_publisher` | `acceptance-20260831T020314.503235Z` | No fixed lab foreign-publisher fixture. |
| `supervised.navigation_start_stop` | `acceptance-20260831T020318.537818Z` | No ready map, scan, odometry, TF, localization, planner or controller. |
| `supervised.mapping_warmup_cancel` | `acceptance-20260831T020321.492619Z` | The external dashboard is an offline ROS viewer and has no active mapping pipeline. |
| `supervised.nav2_child_crash` | `acceptance-20260831T020324.464303Z` | Nav2 is inactive and its required inputs are absent. |
| `supervised.xt16_interruption` | `acceptance-20260831T020328.475841Z` | Dashboard PointCloud contained zero points and no trusted XT16 freshness source. |
| `supervised.low_disk_rejection` | `acceptance-20260831T020331.507003Z` | No bounded approved test volume; the live dataset filesystem had about 51.7 GiB free. |
| `supervised.robot_wifi_disconnect` | `acceptance-20260831T020335.504804Z` | The deployment was fully wireless with no reviewed out-of-band recovery path. |
| `supervised.realsense_source_stall` | `acceptance-20260831T020338.555785Z` | No fixed source-stall fixture or separately supervised cable-fault procedure. |
| `supervised.perception_process_stop` | `acceptance-20260831T020342.489411Z` | Shadow perception receiver returned HTTP 503 because it was not configured. |
| `supervised.perception_result_freeze` | `acceptance-20260831T020345.510841Z` | No configured perception receiver or fixed freeze fixture. |
| `supervised.model_hash_mismatch` | `acceptance-20260831T020348.514358Z` | Model registry was empty and no reviewed invalid fixture was installed. |
| `supervised.model_activation_rollback` | `acceptance-20260831T020352.519592Z` | No validated active/previous model pair existed. |
| `supervised.decimated_pointcloud_load` | `acceptance-20260831T020355.475459Z` | No live trusted PointCloud source was available to the external dashboard. |
| `supervised.raw_pointcloud_overload_abort` | `acceptance-20260831T020358.552137Z` | Separate overload approval and a live trusted PointCloud source were absent; an overload can never be PASS. |

All 15 BLOCKED reports had `FAIL=0` and summary
`PASS=30 BLOCKED=20 NOT_RUN=23`.

The first manual short-stop attempt produced no visible motion because the robot
was sitting. The allowlisted Stand up action consumed its lease, completed its
fixed safety guard and returned DISARMED before the retry. The in-app automation
surface could issue press/release but could not sustain a key-down interval.
Inspection also found that the current browser path scales the normalized input
to `0.105` at 35% and sends both that scaled value and `speed_scale=0.35`; the
server then correctly applies its own limit and scale again. This makes the UI
path's effective Bridge command much smaller than the displayed `0.105 m/s`.
No safety-sensitive control code was changed during field acceptance. The
accepted bounded retry used the same public arm/bind/twist/disarm API with
normalized `linear_x=1.0` and the unchanged server scale of 0.35, never the
private signed Bridge protocol.

During the manual retry the bounded client sent zero and release, did not receive
the expected release acknowledgement before the socket ended, and executed the
same HTTP disarm fallback used by the UI. The physical robot stopped and the
server then showed no lease, deadman false and exact zero. This acknowledgement
race and the browser double-scaling issue remain follow-up items even though the
stop criteria passed. The separate disconnect scenario intentionally sent no
zero or release before aborting its socket; server-side fail-closed behavior was
therefore observed independently.

Final runtime state after all executed rows was MANUAL, Competition Lock off,
motion authority NONE, no control lease, deadman false, all command axes zero,
signed Bridge READY/authenticated/connected and LowState age 0--1 ms. The
dashboard, robot-side Bridge and both camera relay services were active after
manual starts; their boot policy remained disabled. Dashboard camera demand was
then released, leaving zero viewers and the RealSense producer idle. No
route/NAT/DDS configuration, Nav2, mapping, model activation, raw cloud load or
destructive disk manipulation was applied.

## P0 control-contract correction and supervised fault follow-up — 2026-08-31

Commits `5461dee` and `6dd569e` corrected the two control-client contract
defects and the split-topology header projection without weakening the server
clamp, 200 ms Bridge watchdog, lease gate, fixed signed UDP transport, Sport
publisher cardinality gate or LowState freshness gate.

- The browser now sends normalized axes and a single `speed_scale`; the
  displayed velocity is derived from the server limit and scale but is not fed
  back as an already-scaled wire axis.
- Explicit release sends zero first, clears browser authority immediately and
  waits at most 180 ms for the WebSocket `released` acknowledgement. HTTP
  disarm remains the fail-closed fallback only when that acknowledgement is
  absent.
- The header now reports `direct ROS` and the authenticated remote Control
  Bridge independently. In the accepted wireless split topology it truthfully
  showed direct ROS offline and remote Control Bridge connected at the same
  time. Offline Overview sensor projections remain fail-closed.

A dedicated stationary WebSocket check observed the normal `bound` then
`released` sequence with the release acknowledgement in 6.8 ms, followed by
an HTTP cleanup check. No motion frame was sent. The supervised low-speed
physical check was then repeated with normalized `linear_x=1.0`,
`speed_scale=0.35` and the unchanged server maximum of 0.30 m/s, yielding the
single-scaled 0.105 m/s bound. Twenty-two frames were sent over about 1.25
seconds, followed by explicit zero and an acknowledged release. The operator
confirmed both forward movement and complete stop. Final state was DISARMED,
lease-free and exact zero.

The remaining control fault scenarios were executed one at a time with the
operator's physical E-stop ready, a clear area, the low-speed limit confirmed
and an on-site safety operator:

| Scenario | Result and bounded evidence |
| --- | --- |
| Dashboard Software STOP during low-speed motion | **PASS**; after 13 frames over 0.76 s, the STOP response arrived in 28.6 ms. The server latched E-stop, revoked the lease and projected exact zero. The operator confirmed complete physical stop before the latch was explicitly cleared. |
| Abnormal Control Bridge main-process loss | **PASS for stationary detection/recovery**; the robot was DISARMED and exact zero. `SIGKILL` ended the service main process at 12:03:00, systemd recorded `status=9/KILL`, scheduled one restart, and started new PID 50138 at 12:03:04 with `NRestarts=1`. Authenticated readiness, fresh LowState and exact graph cardinality recovered. This does not authorize `SIGKILL` during motion because that signal cannot execute shutdown StopMove. |
| Stale LowState | **PASS**; while management Wi-Fi remained available, robot-side `eth0` was isolated for five seconds. Bridge readiness became unavailable once LowState age crossed about 0.5 s and remained unavailable as age rose to about 11.9 s. Lease, deadman and command remained `false`, `false` and `0.0` throughout. Ethernet carrier and fresh LowState recovered automatically and the Bridge returned to idle/ready. |
| Fixed foreign named Sport publisher | **PASS**; a ROS 2 node named `robot_scope_foreign_sport_fixture` created a typed `/api/sport/request` publisher for eight seconds but never called `publish`. The graph changed from `0 foreign / 10 total` to `1 foreign / 11 total`; Bridge readiness became unavailable with no lease, deadman or non-zero command. Fixture exit restored `0/10` and idle/ready automatically. |

The older immutable acceptance reports that recorded stale LowState and foreign
publisher as BLOCKED remain unchanged: the fixed supervised fixtures did not
exist when those reports were collected. This direct follow-up supplies the
later hardware evidence and does not rewrite those historical artifacts.

Post-change repository verification was complete Python 799/799, complete
JavaScript 257/257, frontend syntax 52/52 and `git diff --check` PASS. The
deployed external dashboard resolved to `6dd569e`; the robot-side Bridge
remained manually started and disabled at boot. Final control state was
DISARMED with no lease, deadman false, exact zero, authenticated Bridge ready,
fresh LowState, `0` foreign named Sport publishers and the expected total of
ten Sport publishers.

## Remaining wireless acceptance

### Go2 v1.1.15 publisher-baseline follow-up — 2026-09-02

After the operator updated the Go2 body from v1.1.11 to v1.1.15, a stationary
robot-side Foxy graph audit observed one named Robot Scope publisher, zero
foreign named publishers and ten anonymous Unitree publishers on
`/api/sport/request` (eleven total). Five consecutive samples retained the
same ten anonymous endpoint GIDs. The repository profile still expected nine,
so the Bridge correctly stayed fail-closed and emitted only its periodic API
1003 `StopMove`; no API 1008 `Move` or action was observed.

The `go2` profile is therefore updated to the exact v1.1.15 baseline of ten.
The equality check, named-publisher rejection, LowState gate, watchdog and
velocity limits are unchanged. Regression coverage proves exact ten is ready
and nine, eleven, missing-own, named-foreign and inconsistent-total cases are
not ready. Deployment and stationary lifecycle revalidation remain separate
hardware gates before C4 or any motion.

- Run the deferred 60-minute Wi-Fi soak and interference test.
- Design and validate a bounded wireless XT16/FAST-LIO data path, or explicitly
  colocate the mapping stack with the sensor, before external-dashboard mapping
  can be accepted.
- Resolve or reproduce the one non-recurring runtime robot-target change from
  the first Wi-Fi fault attempt before relying on unattended fault recovery.
- Keep abrupt Bridge-process-loss testing motion-free until a separately
  reviewed physical-stop test plan exists.
- The Overview ICMP KPI still reports the Go2 body offline because the external
  Orin deliberately has no route to `192.168.123.161`. The Controls readiness
  comes from authenticated Bridge/LowState status and passed. UI wording should
  continue to distinguish these two signals rather than treating remote ICMP
  as the motion-safety source.
- External-Orin Nav2 remains deferred because its ROS/DDS sensor and command
  dependencies are not carried by this narrow control transport.
- The browser/server speed-scale and normal release-acknowledgement follow-up is
  complete at `5461dee`; retain the HTTP disarm fallback and repeat the bounded
  check after any future control-session protocol change.

## Rollback notes

- Revert the three RealSense host values only if the robot-side management
  address is deliberately moved away from `192.168.50.30`.
- Do not return robot-side `eth0` to DHCP while it remains the dedicated
  `192.168.123.0/24` Go2/sensor link.
- The robot-side Control Bridge was left disabled and inactive. RealSense and
  the fixed Go2 camera relay were left disabled at boot but manually active;
  stop those two camera services before rollback if camera availability is no
  longer required.
- External dashboard private configuration was backed up as
  `~/.config/robot-scope/control.env.pre-b38dc25`. Restore that mode-0600 copy
  and restart only the dashboard to roll back the wireless control settings.
- Robot-side source is `/home/unitree/project/robot-scope`; its private Bridge
  environment, lifecycle key authorization, forced-command helper, exact
  sudoers file, and systemd unit must be rolled back as one reviewed set. Do
  not delete or overwrite the shared key during an unrelated source rollback.
- The pre-fix robot-side source was retained temporarily as
  `/home/unitree/project/robot-scope.pre-97dd0fb` for exact rollback review.

## Repository verification

- `git diff --check`: PASS
- JavaScript unit suite: 239 passed, 0 failed
- frontend syntax check: 48 modules passed
- Python unit suite after the camera-relay change: 712 run; 711 passed and one
  existing macOS baseline error
  remained. `test_apply_os_release_override_must_match_running_host` attempts to
  read Linux-only `/etc/os-release`, which is absent on the macOS test host.
  No test or assertion was removed or weakened.
- Targeted fixed Go2 RTP relay tests: 17 passed, 0 failed.
- Targeted camera media/layout tests after the Sensors fix: 18 passed, 0
  failed.
- Targeted wireless control tests: 69 passed across datagram, dashboard
  transport, lifecycle, Bridge core, Foxy boot scripts, and public API
  projection.
- Ruff 0.6.9: all new and directly changed wireless-control files passed. The
  repository-wide run still reports ten pre-existing findings; four were
  reproduced directly from the corresponding HEAD version of
  `test_ros_control_transport.py`.
- mypy 1.13.0 strict configured targets: PASS.
- Browser E2E: 27 passed outside the macOS sandbox. The first sandboxed attempt
  failed before test execution because Chromium Mach port registration was
  denied; rerunning in the approved browser environment passed all tests.
