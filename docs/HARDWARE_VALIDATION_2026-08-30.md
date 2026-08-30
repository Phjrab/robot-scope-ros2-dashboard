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

## Remaining wireless acceptance

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
