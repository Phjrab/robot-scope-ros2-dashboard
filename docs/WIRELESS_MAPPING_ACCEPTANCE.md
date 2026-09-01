# Wireless XT16, FAST-LIO and mapping acceptance

## Result vocabulary and evidence rule

Only these results are used:

- `PASS`: the exact stage was executed on the recorded commit and every bound
  was observed;
- `FAIL`: it was executed and any required bound failed;
- `BLOCKED`: a prerequisite or approved fixture was unavailable;
- `NOT_RUN`: it was deliberately not executed.

Lower-stage PASS never implies a higher-stage PASS. Hardware-free tests never
prove live XT16, IMU, PointCloud, FAST-LIO, mapping, Nav2 or physical stop
behavior. A cached frame, publisher count, running process or Wi-Fi association
is not a freshness pass.

## Current Gate record — 2026-09-01

| Gate | Result | Evidence |
| --- | --- | --- |
| Gate 0 dual-host audit | `PASS` | `.50.30/wlan0`, `.123.18/eth0`, `.50.10/eno1`, Go2 `.123.161`, XT16 `.123.20`, synchronized clocks, zero-loss bounded pings, fresh LowState, DISARMED/zero |
| Gate 0 legacy relay cleanup | `PASS` | former `.123.99:2368` relay is `inactive/dead`, disabled, PID 0; installed rollback files preserved |
| Gate 0 network boundary | `PASS` | both hosts `FORWARD DROP`, Docker-only `172.17.0.0/16` forwarding/NAT, no management/sensor forwarding; external nftables ruleset empty; no rules changed |
| Gate 1 architecture and acceptance documents | `PASS` after contract tests | this document and the wireless transport ADR; no runtime/deployment mutation |
| Gate 2 fixed XT16 relay implementation | `PASS` after hardware-free contract tests | separate fixed-address relay, disabled service example and strict regression tests; no host installation or live packet claim |
| Gate 3 Hesai wireless input and PTC decision | `PASS` after pinned-source and configuration contract tests | exact `.50.30:46236 -> .50.10:2368` profile; private PandarXT 16-channel CSV correction selected, optional firetime omitted from the proven baseline; PTC proxy not implemented and fallback remains blocked |
| Gate 4 minimum authenticated IMU | `PASS` after hardware-free contract tests | fixed 184-byte HMAC envelope, fixed connected UDP peers, fail-closed clock/order/freshness state and exact `/imu/body` QoS; no installation or live IMU claim |
| Gate 5 XT16 C++ role separation | `PASS` after hardware-free contract tests | explicit cloud-only C++ target and runner exclude LowState/IMU at compile time while the existing wired executable remains unchanged in behavior |
| Gate 6 wireless mapping profile | `PASS` after hardware-free contract tests | explicit opt-in profile, read-only preflight, restricted two-service lifecycle, transactional reverse cleanup and bounded UI failure reasons; no deployment or Mapping start |
| Gate 7 repository/C++ verification | `PASS` — `CODE_READY` | deployed `0d81a74`: 894 Python PASS, Node 257 PASS, Ruff and mypy PASS; Playwright 30 PASS on the tested `03b4d08` predecessor before service-only Jetson compatibility fixes; isolated Orin C++ Release build PASS with zero warnings and registered CTest PASS 1/1 |
| Deployment and HW-1 XT16 relay | `PASS` — `XT16_RELAY_PASS` | exact approval received; private PandarXT correction and disabled units installed; relay-only run received 53,328 exact packets in 12 s and cleaned up with no service residue |
| Firewall persistence and HW-2 workspace readiness | `PASS` | dedicated root oneshot owns only the exact INPUT chain and survived an external-Orin reboot; clean pinned Hesai source was built and resolved from the final `~/ws/hesai_ws` path without starting a sensor |
| HW-2 Hesai driver only | `PASS` — `LIDAR_PASS` | supervised stationary run produced exactly one reliable/volatile `/lidar_points` publisher at about 10 Hz with 64,000-point `hesai_lidar` clouds; bounded relay and UDP-drop checks passed and cleanup left no publisher or service residue |
| HW-3 IMU only | `PASS` — `IMU_PASS` | supervised stationary run produced exactly one reliable/volatile `/imu/body` publisher at about 502 Hz with authenticated, finite, fresh, increasing samples; zero external `/lowstate` publishers and cleanup left no sender, receiver or socket residue |
| HW-4 cloud bridge | `PASS` — `CLOUD_PASS` | supervised stationary run produced exactly one reliable/volatile `/velodyne_points` publisher at about 10 Hz with 16,000-point exact-layout clouds; age, jitter, relay and kernel-drop bounds passed and verified process-group cleanup left no topic, socket or service residue |
| HW-5 stationary FAST-LIO | `PASS` — `MAPPING_STATIONARY_PASS` | exact approval and fresh physical safety check recorded; all three FAST-LIO outputs were fresh, non-empty and single-publisher, shutdown-race correction `9bad38e` was deployed and retested, and reverse cleanup left no topic, socket, process or service residue |
| HW-6 compound load | `PASS` for 60 s and 10 min; 60 min `NOT_RUN` | simultaneous XT16, authenticated IMU, FAST-LIO, both cameras, signed Control Bridge status and LOW dashboard PointCloud remained bounded; 60-minute soak is still deferred and `SOAK_PASS` is not claimed |

After final HW-4 cleanup, current external topics remain truthfully unavailable:
`/lidar_points`, `/velodyne_points` and `/imu/body` have zero publishers.
Mapping, navigation and Dataset Capture are idle. The repository status is `CODE_READY`;
the current hardware status remains `MAPPING_STATIONARY_PASS` because the
60-minute soak is still `NOT_RUN`. No Nav2 or `SOAK_PASS` result is implied.

Three manageable 2D maps exist for later revision-pinned Nav2 work. The latest
audited candidate was `map_20260813_125411`, `120×169`, resolution `0.05 m`,
frame `map`, mode `trinary`. This is inventory only: it does not approve a map
load, initial pose or goal, and no map artifact is copied into Git.

### Gate 2 repository evidence

The new relay passively observes only `PACKET_HOST` IPv4 packets on `eth0` and
reuses the unchanged wired parser for the measured
`192.168.123.20:10000 -> 192.168.123.18:2368` contract. It additionally checks
a supplied IPv4 UDP checksum; checksum zero remains valid because IPv4 permits
the sender to omit it. Accepted 568-byte payloads become new ordinary UDP
datagrams from fixed `192.168.50.30:46236` to fixed
`192.168.50.10:2368`. There is no promiscuous capture, raw-IP spoofing, runtime
network override, route, NAT or bridge.

The service example runs as `unitree`, grants only `CAP_NET_RAW`, has a finite
restart limit and is explicitly left disabled. Gate 2 created no private
configuration and performed no installation, service start, mapping, Nav2,
Dataset Capture or robot operation. Live receipt and loss bounds therefore
remain `NOT_RUN` until the separately approved HW-1 stage.

### Gate 3 repository evidence

The pinned Hesai ROS revision
`e7e112f0809f0eed5e3c81c55a1a0376474db234` and SDK revision
`9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168` support binding the exact local
address and filtering point packets by the combined peer IPv4 address and
source port. The separate wireless profile fixes
`192.168.50.30:46236 -> 192.168.50.10:2368`, publishes only the bounded
`/lidar_points` output and leaves the wired profile unchanged.

The pinned SDK also has an offline path when PTC is disabled. The measured
`EE FF 06 01` packet header selects its PandarXT/UDP 6.1 (`XTM1`) parser, which
consumes a sensor-specific 16-channel CSV correction. A historic live wired
run of this exact unit loaded that correction and published at 10 Hz while the
optional firetime file was absent. Gate 3 therefore selects one fixed private
CSV correction, leaves `firetimes_path` empty and does not implement a PTC
proxy. The acquisition helper and private
manifest validator are repository-tested. The approved deployment later
installed and validated the private correction after a physical serial
cross-check; the contents, serial and hash remain outside Git and this report.
At Gate 3 completion, driver start and HW-2 were `NOT_RUN`. The later approved
HW-2 run is recorded below. A proxy fallback remains `BLOCKED` unless the
offline path fails in an approved hardware test and receives a new design
approval.

The helper was also compiled, but not executed, against the clean robot-side
pinned SDK using GNU C++ 9.4 in Release mode. Its target passed
`-Wall -Wextra -Wpedantic -Werror`. The executable was not installed, no PTC
connection was opened and the temporary source/build tree was removed.

### Gate 4 repository evidence

The robot-side sender subscribes only to `/lowstate` using best-effort,
volatile, keep-last depth 1 and extracts only quaternion, gyroscope,
accelerometer and an available integer source tick. The external receiver has
no `/lowstate` endpoint. It publishes only `sensor_msgs/Imu` on `/imu/body`,
frame `body_imu`, using reliable, volatile, keep-last depth 5, and refuses to
compete with another publisher.

The canonical 184-byte binary datagram fixes
`192.168.50.30:46020 -> 192.168.50.10:46020`, sender identity, version and
message type and authenticates every byte with HMAC-SHA256. Its exact 32-byte
mode-0600 file credential is distinct from Control Bridge authentication.
Receiver tests cover authentication, boot/sequence replay, duplicate/reorder,
finite and quaternion checks, stale/future time, clock fail-closed behavior,
receive jitter, fixed-peer sockets and five-sample loss recovery. See
`docs/WIRELESS_IMU_PROTOCOL.md` for the byte and clock-domain contract.

At Gate 4 completion, no key or service had been installed, neither Jetson had
been contacted, and HW-3 was `NOT_RUN`. The later separately supervised HW-3
deployment and `IMU_PASS` evidence are recorded below.

### Gate 5 repository evidence

The existing high-rate C++ source now builds two explicit executables. The
legacy `robot_scope_xt16_bridge_node` retains `/lidar_points` and `/lowstate`
inputs plus `/velodyne_points` and `/imu/body` outputs. The new
`robot_scope_xt16_cloud_bridge_node` is built with a fixed compile definition
that removes the Unitree header, LowState topic/subscription/callback and all
IMU message/publisher state from that binary.

Both targets use the same C++ conversion implementation, preserving exact
point fields, four-to-one decimation, reliable volatile QoS, frame, clock
residual, stale/future and monotonically increasing timestamp checks. The
wireless runner accepts no arguments and names only the cloud-only binary; it
does not substitute the Python reference converter or bypass the receive
buffer and network readiness contracts. See
`docs/WIRELESS_XT16_CLOUD_BRIDGE.md`.

The existing wired runner and preview remain bound to the legacy executable.
Gate 5 did not build on a Jetson, install an executable, start a ROS process or
publish a cloud. The targeted colcon build was deferred to Gate 7 and is
recorded below. At Gate 5 completion, HW-4 was `NOT_RUN`; the later supervised
deployment and `CLOUD_PASS` evidence are recorded below.

### Gate 6 repository evidence

The default `go2-xt16-wired` mode still selects the existing preview and
FAST-LIO launchers. Explicit `go2-xt16-wireless` selection instead chooses one
transactional launcher with the fixed relay, IMU receiver, wireless Hesai,
cloud-only C++ bridge and FAST-LIO order. Host, clock, receive-buffer,
conflicting-process, restricted lifecycle, advancing relay counters, IMU,
cloud and FAST-LIO readiness are fail-closed. The application additionally
rejects Mapping start while a control lease or Dataset Capture is active.

The robot-side forced command and sudoers example admit only the exact two
sensor service lifecycle. Already-active services are never claimed, and only
children started by the current transaction are removed in reverse order.
Exit codes map to the fixed public failure vocabulary documented in
`docs/WIRELESS_MAPPING_PROFILE.md`; raw child diagnostics cannot become the UI
error field.

Gate 6 did not install or start either service, change network state, start
Mapping, publish a cloud, save a map or operate the robot. HW-1 through HW-6
and all hardware status flags were `NOT_RUN` at Gate 6 completion.

### Gate 7 repository evidence

Gate 7 was executed against candidate runtime commit
`96428d7099fcdaf0827558815026b84cc0e1cff1`, with the fail-closed browser
follow-up at `ec87939a5dfd4c37056b6f351fdad995b69e47d1` and the registered C++
contract at `f9660793447982d17ee5c359409de731b3dd5b33`. The project virtual environment
completed all 871 tests present on that commit. After adding two deployment-plan
contract tests and two C++ registration/coverage contract tests, the final
Gate 7 tree completed all 875 Python tests. Node
completed all 257 JavaScript unit tests; frontend syntax checked 52 modules.
Ruff, strict configured mypy targets, the tracked-source secret scan and
`git diff --check` all passed.

The exact unqualified system-Python command ran 867 tests and had one import
collection error because the macOS Python 3.13 environment does not contain
`fastapi`. The repository-managed virtual environment contains the declared
dependency and completed the full 871-test suite. This is an unmanaged-host
dependency failure, not a changed assertion or product-code failure.

The full Playwright run completed 28 of 30 scenarios. It failed the offline
connection-label expectation (`연결 끊김` expected, `에이전트 오류` rendered)
and the perception-loss expectation (`STALE · lane-v2` expected, fail-closed
`OFFLINE` rendered). Both failures reproduced unchanged in a Git-archive
snapshot of pre-Gate-6 commit
`2ca30bc17ee47c7e40820ef59540bd20c072211f`. No test was removed or weakened,
and Gate 6 changed none of the Playwright, static frontend or configuration
files involved in those scenarios.

A follow-up corrected the direct-ROS disconnected label without changing the
separate authenticated Control Bridge projection. It also made the perception
fault scenario wait for a proven LIVE sample after reload and initialized the
two-waypoint Mission fixture before page load. Assertions for fail-closed KPI,
STALE perception, DISARMED state and Mission behavior remain intact. The
targeted scenarios and the complete Playwright suite now pass `30/30`.

On the external aarch64 Orin with ROS 2 Humble, an isolated `/tmp` source
archive built both `robot_scope_xt16_bridge_node` and
`robot_scope_xt16_cloud_bridge_node` in Release mode. The compiler emitted no
warnings. The package registered exactly one CTest,
`robot_scope_xt16_cloud_contract`. `colcon test` reported one test, zero errors,
zero failures and zero skips, and direct CTest independently passed `1/1`.
Nothing was installed into the operating checkout or system directories and no
ROS node or service was started.

The registered fail-closed contract test resolves the former zero-test gap, so
Gate 7 is `PASS` and the repository is `CODE_READY`. At Gate 7 completion,
deployment and every hardware status were `NOT_RUN`; private calibration,
firewall audit, the final dual-host/safety re-audit and the exact deployment
approval phrase were still required. The later approved deployment and HW-1
evidence are recorded below without changing that repository-only verdict.

### Pre-deployment read-only re-audit — 2026-08-31

No deployment approval was supplied, so this audit made no installation,
service, sensor, network, Mapping, Nav, Dataset, control-lease or robot-motion
mutation. The new wireless XT16 and IMU units report `LoadState=not-found` on
their intended hosts.

The robot-side Jetson was re-identified as Ubuntu 20.04 host `ubuntu`, with
`wlan0=192.168.50.30/24` and `eth0=192.168.123.18/24`. Its new management
address presented the same ED25519 host key previously recorded for
`192.168.123.18` and `192.168.50.103`. The external Ubuntu 22.04 Orin remained
`jetson-orin-nano` with `eno1=192.168.50.10/24`. Both clocks reported NTP
synchronized in `Asia/Seoul`; bounded pings in both management directions had
zero loss. Robot-side bounded pings to Go2 `192.168.123.161` and XT16
`192.168.123.20` also had zero loss. Wi-Fi reported `-38 dBm` and a negotiated
1,200.9 Mbit/s receive/transmit link during this short snapshot; this is not a
soak or payload-throughput result.

With the complete Foxy, Unitree-message and CycloneDDS `eth0` environment, the
robot-side graph showed exactly one `/lowstate` publisher and continuously
advancing samples. The external graph still had no `/lidar_points`,
`/velodyne_points` or `/imu/body` topic and zero `/Odometry` publishers. The
dashboard's public control projection reported no lease, deadman released,
exact zero command and an inactive Control Bridge service. Cached authenticated
bridge metadata was stale and was not treated as current readiness.

Both hosts currently report `net.ipv4.ip_forward=1`. Their unprivileged route
and link views showed no management-to-sensor route and no active carrier on
the Docker or Jetson USB bridges, but these observations cannot prove the
FORWARD/NAT policy. After explicit operator approval, a privileged robot-side
dump showed `iptables v1.8.4 (legacy)`, default `FORWARD DROP`, Docker-only
forward chains and a single `172.17.0.0/16` Docker MASQUERADE. There is no
`wlan0`/`eth0` forwarding or NAT rule; `nft` is not installed. The robot-side
privileged network boundary is `PASS` for this re-audit. The operator-provided
external dump showed `iptables v1.8.7 (legacy)`, default `FORWARD DROP`, the
same Docker-only `172.17.0.0/16` MASQUERADE boundary and no sensor or `eno1`
forwarding/NAT rule. Its installed `nft` tool returned an empty ruleset. The
external privileged network boundary is also `PASS`. Both dumps must still be
repeated against the final deployed commit; `ip_forward=1` alone is never
accepted as evidence.

The three fixed external calibration paths are absent, and a bounded filename
inventory found only ROS `Firetime.msg` source/generated files rather than an
XT16 correction or firetime artifact. No PTC connection was made. The external
operating checkout was clean at
`6dd569ea0367598f9230096f2bac423b7f1b2dc9`, behind the reviewed candidate,
while the robot-side exported tree records an older deployed commit and must be
preserved as rollback before complete-tree replacement. Code provenance and
the exact staged install paths must be recorded during deployment.

These were predeployment observations and preserved repository `CODE_READY` at
that point. The later approved transaction and HW-1 result are recorded below.

## Approved deployment and HW-1 evidence — 2026-08-31

The operator supplied `APPROVE_WIRELESS_XT16_DEPLOY`. Both hosts were deployed
to final commit `e22215af02ec43f6aee9b947ee5dad7fdca49529` with complete-tree or
fast-forward rollback preserved. The mounted sensor's measured `EE FF 06 01`
stream selected PandarXT/UDP 6.1. One approved generic read-only PTC query
returned a private 16-channel CSV correction; its physical-label association,
format, bounded length, owner/mode, revisions and hash passed the private
manifest validator. Neither its contents, serial nor hash entered Git or this
report.

The relay, IMU sender and IMU receiver units were installed disabled and left
inactive. Dedicated mode-0600 IMU and SSH material, a restricted forced SSH
command, exact sudoers commands and the 8 MiB receive-buffer ceiling were
installed. The external INPUT chain accepts only
`192.168.50.30:46236 -> 192.168.50.10:2368` and
`192.168.50.30:46020 -> 192.168.50.10:46020`, then drops other traffic to those
two destination ports. It was applied behind an automatic rollback window and
verified from a second SSH session without changing `FORWARD DROP`, NAT,
bridging or routes. The first approved HW-1 run used this chain as a
runtime-only rule while its persistence owner was still pending.

The follow-up persistence deployment assigns that exact chain to a separate
root oneshot unit ordered before the dashboard. It grants the unit only the
measured `CAP_NET_ADMIN` and `CAP_NET_RAW` requirements of Ubuntu's
iptables-legacy backend; the dashboard and sensor processes receive neither.
The helper adopted the already verified exact chain, rejected ambiguous or
extra rules, and made no FORWARD, NAT, route or bridge change. A second session
verified the owned chain before reboot. After an external-Orin reboot at the
same management address, the unit returned `active/exited`, `Result=success`
and `ExecMainStatus=0`, and the exact helper status passed again. The dashboard
remained stopped because its pre-existing manual-start unit is disabled, not
because of the firewall; it started normally when explicitly requested while
Mapping, Nav2 and Dataset Capture remained idle. No sensor unit was enabled or started.

Before HW-2, the missing Hesai runtime workspace was rebuilt without reusing a
dirty rollback tree. Source-only archives of the pinned wrapper and SDK
revisions were built first in isolation and then from the final
`~/ws/hesai_ws` path. Both Release builds completed successfully. The final
workspace resolves `hesai_ros_driver_node`, has no missing dynamic libraries,
and validates the private correction bundle. `colcon test-result --verbose`
reports zero registered tests, zero errors and zero failures; this is recorded
as workspace readiness, not as a hardware or pointcloud PASS. The original
dirty rollback workspace and the temporary staging workspace remain preserved.

The first relay-only attempt exposed unsupported systemd condition names and a
journal tail that could be displaced by manager warnings. Commits `5de2fa7`
and `e22215a` replaced them with supported unit conditions and strict bounded
filtering of the final two relay metric lines. All three deployed units then
passed targeted `systemd-analyze verify` checks without an unknown-key report.

The final HW-1 run opened a fixed external validator before starting only
`robot-scope-xt16-wireless-relay.service` for 12 seconds. It observed:

- 53,328 packets, 4,443.9 packets/s;
- zero wrong-peer, wrong-length or wrong-header payloads;
- zero relay send errors and equal advancing accepted/forwarded counters;
- 152 sequence gaps (about 0.285%) and two reordered packets, retained as the
  Wi-Fi baseline rather than hidden;
- Wi-Fi signal `-38 dBm`, 1,200.9 Mbit/s receive/transmit link rate;
- 20/20 management pings, zero loss, 2.156 ms average RTT.

Cleanup stopped the relay and confirmed disabled/inactive, PID 0, restart count
0. Both IMU units remained disabled/inactive; Hesai, cloud bridge, FAST-LIO and
Nav2 never started. Mapping and Dataset Capture remained idle, with no control
lease, deadman false and exact zero command. At HW-1 completion, HW-2–HW-6
remained `NOT_RUN`.

## HW-2 Hesai driver-only evidence — 2026-09-01

The operator reconfirmed the physical E-stop, safety supervision and clear
area, and reported the robot stationary in its seated posture. Machine
preflight independently showed DISARMED, no control lease, deadman released,
exact zero command, synchronized clocks, the fixed firewall active/successful,
the private correction manifest valid, and Mapping, Nav2 and Dataset Capture
idle. The robot-side Control Bridge and both IMU services remained disabled and
inactive. Only the XT16 relay and external Hesai driver were started.

The external operating checkout was `72e39c3`; the robot-side sensor export
remained the reviewed `e22215a` deployment. The later changes between those
revisions do not change the relay service, wireless Hesai runner/profile or
readiness contract used by this stage, except for the already recorded
external firewall preflight ownership update. The pinned Hesai wrapper and SDK
workspace and private calibration manifest both validated before launch.

The successful bounded run observed:

- exactly one `/lidar_points` publisher, node `hesai_ros_driver_node`;
- reliable, volatile, keep-last-depth-10 publisher QoS;
- frame `hesai_lidar`, height 1, width 64,000, `point_step=26` and
  `row_step=1,664,000`;
- five consecutive contract-valid fresh raw clouds, with final arrival age
  `0.001 s`;
- about `10.0 Hz` over repeated 30-frame windows, with `0.098–0.103 s`
  inter-arrival intervals and at most `1.07 ms` standard deviation in the
  sampled windows; the conservative interval spread was `5 ms`, below the
  `300 ms` jitter bound;
- offline private correction load success with PTC disabled as designed; the
  optional empty firetime path produced the pinned SDK's known non-terminal
  `load firetime` diagnostic while parsing continued at 64,000 points/frame;
- two consecutive steady-state relay reports advancing accepted and forwarded
  counters from `175,008/175,006` to `200,009/200,007`, with send errors fixed
  at 2 rather than increasing;
- external kernel UDP `InErrors=0`, `RcvbufErrors=0` and `SndbufErrors=0`
  before and after the measured interval.

Preparatory measurement-wrapper attempts failed closed before any driver start
when their local shell/environment ordering was incomplete. The first short
driver interval then exposed that relay health must compare two fully
post-bind statistics rather than a pre-bind/post-bind transition; it produced
valid 64,000-point frames but was not counted as PASS and was cleaned up. The
final run waited for two post-bind relay intervals and met every HW-2 bound.
No safety threshold, product runtime, test or assertion was changed.

Final cleanup stopped the exact Hesai child and relay it started. The robot-side
relay, IMU sender and Control Bridge were disabled/inactive with PID 0 and zero
restarts; the external IMU receiver was disabled/inactive; port 2368 had no
listener and `/lidar_points` was absent. The dashboard remained active but
showed no lease, deadman false, exact zero command, Mapping/Nav/Dataset idle and
no localization or goal. HW-2 is `PASS` as `LIDAR_PASS`.
HW-3–HW-6 remained `NOT_RUN` at HW-2 completion.

## HW-3 authenticated IMU-only evidence — 2026-09-01

The operator supplied a fresh `HW3 안전 확인 완료` confirmation. Machine
preflight independently showed DISARMED, no control lease, deadman released,
exact zero command, synchronized clocks, the fixed firewall active/successful,
and Mapping, Nav2 and Dataset Capture idle. The robot-side XT16 relay and
Control Bridge and the external Hesai path remained disabled/inactive. The
stage started only the fixed robot-side IMU sender and external IMU receiver.

The candidate and deployed runtime commit was `094186e`. The installed files
matched the repository with SHA-256 values
`1cc1600a1ea2c26a93570835e82d5c6bbef0fa63be953fd2933832e42f1fac29`
for the sender unit,
`ec70e5e04d47fc25bee83d69fd3e682f2fc8f685be2192eb3550bb18cdaf9831`
for the sender script,
`65df6b5b5bd6d96c7432ffa225563b5e4cf83bc168ac4356bb08d97c97cde114`
for the receiver unit and
`4d8899b40323d6d551d841d666af8e28a8631e62562601dcbc958449dfebff97`
for the receiver script. Both units stayed disabled and were started only for
the bounded test. Their previous installed files remain as rollback copies.

The successful run observed:

- exactly one `/imu/body` publisher, node
  `robot_scope_wireless_imu_receiver`, and zero external `/lowstate`
  publishers;
- reliable, volatile publisher QoS, frame `body_imu`, 50/50 contract-valid
  finite samples and strictly increasing timestamps;
- about `501.84 Hz`, maximum sampled message age `17.964 ms` and maximum
  arrival jitter `1.036 ms`;
- 4,152 received, authenticated, accepted and published envelopes, with zero
  loss, duplicate, reorder, receive, authentication, finite, quaternion,
  clock or rejection errors in the recorded receiver health report;
- sender health later showed input ready and clock synchronized, 7,192 fresh
  LowState samples received, 6,713 envelopes sent, and zero invalid samples,
  send errors or clock blocks;
- synchronized host clocks measured independently as external offset
  `-3.915 ms` with `10.729 ms` jitter and robot-side offset `+14.415 ms` with
  `6.524 ms` jitter. These per-host observations are not subtracted across
  clock domains.

Two preparatory attempts failed closed before a usable publisher. The first
showed that the unit sandbox needed unprivileged `AF_NETLINK` for its read-only
interface-address preflight; the second showed that ROS required a writable
log location while home remained read-only. Commit `094186e` admits only that
read-only address-family query, retains an empty capability bounding set, and
provides each unit a private mode-0700 runtime log directory under `/run`.
Idempotent ROS shutdown also prevents a duplicate cleanup exception. No
network mutation authority, safety threshold, publisher contract, test or
assertion was weakened.

Final cleanup left both IMU units disabled/inactive with PID 0 and restart
count 0, no listener on UDP 46020 and zero `/imu/body` publishers. The XT16
relay, Control Bridge and camera relay remained disabled/inactive. The
dashboard still showed no lease, deadman false, exact zero command, and
Mapping/Nav/Dataset idle with no localization or goal. HW-3 is `PASS` as
`IMU_PASS`; HW-4–HW-6 remain `NOT_RUN`.

## HW-4 cloud-only C++ bridge evidence — 2026-09-01

The operator supplied a fresh `HW4 안전 확인 완료` confirmation. Machine
preflight showed synchronized clocks, the fixed external firewall
active/successful, no conflicting sensor or navigation process, DISARMED, no
control lease, deadman released, exact zero command, and Mapping, Nav2 and
Dataset Capture idle. The test started only the robot-side XT16 relay and IMU
sender plus the external IMU receiver, Hesai driver and cloud-only C++ bridge.
FAST-LIO, map save, localization, Nav2 and robot motion were never started.

The external host had no production cloud binary before this stage. Commit
`c9873b7` added a fixed cloud-only Release build path that leaves the legacy
Unitree-dependent target enabled by default. The external build produced no
legacy executable, linked no `unitree_go`, completed successfully, and passed
the registered cloud contract through both colcon and direct CTest `1/1`.
The installed cloud binary SHA-256 was
`99a56c3ff62c9f9ece51b4da80f85e5590b41a663eddd52fd8fec1d86dd332ec`.
The selectively deployed CMake, build runner, preflight and final launcher
files matched commits `c9873b7`, `7f87c65` and `cb56b10`; every replaced file
has a separate rollback copy.

The final bounded run observed:

- exactly one `/velodyne_points` publisher, node
  `robot_scope_xt16_cloud_bridge`, offering reliable, volatile QoS;
- 50/50 contract-valid, finite, strictly increasing clouds at about
  `9.998 Hz`, maximum sampled header age `106.981 ms` and maximum arrival
  jitter `3.648 ms`;
- frame `hesai_lidar`, height 1, width 16,000, `point_step=22`,
  `row_step=352,000`, and exact fields `x`, `y`, `z`, `intensity`, `time`,
  `ring`; sampled output values had zero non-finite values;
- exactly one reliable/volatile `/lidar_points` publisher and one
  reliable/volatile authenticated `/imu/body` publisher while the stage was
  active, with zero external `/lowstate` publishers;
- zero `/Odometry` and `/Laser_map` publishers, proving FAST-LIO did not start;
- relay accepted/forwarded counters advancing from `75,003/74,996` to
  `100,004/99,997`, send errors stable at 7 and 137 measured sequence gaps;
- external UDP `InErrors=0`, `RcvbufErrors=0` and `SndbufErrors=0` before and
  after the interval;
- Wi-Fi signal `-35 dBm`, 1,080.6 Mbit/s receive and 1,200.9 Mbit/s transmit
  link rate, plus 5/5 management pings with zero loss and 1.864 ms average RTT;
- independently synchronized clocks with external offset `-5.255 ms` and
  `10.214 ms` jitter, and robot-side offset `+22.523 ms` and `10.387 ms`
  jitter. These host observations are not subtracted across clock domains.

Preparatory attempts failed closed without producing a cloud PASS. The first
showed that the external host intentionally lacks the legacy Unitree workspace,
which led to the separate cloud-only build path. The next exposed that strict
relay send-error health was evaluated before the fixed UDP 2368 consumer bound;
commit `7f87c65` preserves relay-first startup but moves the advancing,
error-stable gate after fresh raw clouds. Two temporary supervision-fixture
attempts then stopped before cloud launch because their ROS environment was not
yet sourced correctly; the product launcher already sourced it in the proper
order. No safety threshold or assertion was weakened.

The first successful measurement also exposed that signalling only a
`ros2 run` wrapper could leave its native Hesai child alive. That exact child
was identified by PID, start identity, executable and fixed config, stopped,
and the socket/topic graph returned to zero. Commit `cb56b10` places each local
runner in an owned process group and signals the group during reverse cleanup.
The complete HW-4 scenario was repeated with this fix and passed again. Final
automatic cleanup left both robot-side services disabled/inactive with PID 0
and zero restarts, no external UDP 2368/46020 listener, and zero publishers on
`/lidar_points`, `/velodyne_points`, `/imu/body`, `/lowstate`, `/Odometry` and
`/Laser_map`. The dashboard remained no-lease, deadman false, exact zero, with
Mapping/Nav/Dataset idle. At that checkpoint HW-4 was `PASS` as `CLOUD_PASS`
and the higher stages had not yet run; the later HW-5 result is recorded below.

On 2026-09-01, the read-only HW-5 preflight found that the active external
checkout no longer contained the Livox message or FAST-LIO overlays. The only
older install tree was inside the preserved `6dd569e` rollback checkout and
its generated setup files embedded the former `/home/jetson_orin_nano/ws`
paths, so it was not copied into service. The external Orin instead cloned the
manifest-pinned Livox-SDK2 `08f523c`, livox_ros_driver2 `4a1def9` and FAST-LIO
`2fffc57` sources into the active private workspace and rebuilt the two ROS
overlays there. The resulting `fastlio_mapping` executable has SHA-256
`b03fabb88b875115f2074da3934e47f0345c5218e82d1abe8ba993b722945fdc`,
resolves all shared libraries and is discoverable from the active overlay.
The external pinned projects had no tracked changes after the build. The
upstream builds completed with one livox_ros_driver2 unused-variable warning,
one FAST-LIO CMake policy warning and upstream compiler notes; none was hidden
or promoted to a repository PASS claim.

No relay, IMU, Hesai, cloud bridge, FAST-LIO, Mapping, Nav2, Dataset or control
process was started during that repair. The post-build host preflight passed,
all six relevant external ROS topics had zero publishers before the stage, the
dashboard still reported no lease, deadman false, exact zero and idle
Mapping/Nav/Dataset, and the robot-side sensor and control units remained
inactive. This was dependency recovery evidence only and did not itself promote
HW-5; the supervised result below records the later live observation.

## HW-5 supervised stationary FAST-LIO — 2026-09-01

The operator supplied exact `APPROVE_STATIONARY_MAPPING_TEST` authorization and
freshly confirmed physical E-stop readiness, an on-site safety operator, a
clear safety area and that the robot was seated. Immediately before launch the
dashboard reported no control lease, deadman false, exact zero on all three
velocity axes and idle Mapping/Nav/Dataset. The external host preflight passed,
all six sensor/mapping topics had zero publishers, the robot-side sensor units
were disabled/inactive and the robot-side `/lowstate` graph had exactly one
publisher. No control bridge, motion command, Nav2 process, goal or map-save
operation was started.

The fixed wireless launcher passed every ordered readiness gate. FAST-LIO then
published exactly one reliable/volatile publisher for each required output:

- `/Odometry` was `camera_init -> body`, passed three consecutive fresh samples
  at readiness and measured `10.007 Hz` over the final 50-sample window with
  `0.086-0.114 s` intervals and `0.00567 s` standard deviation;
- `/Laser_map` used frame `camera_init`, was non-empty at 11,574 points in the
  sampled message and measured approximately `0.997 Hz`;
- `/cloud_registered` used frame `camera_init`, was non-empty at 202 points in
  the sampled message and measured `9.983 Hz` with `0.086-0.117 s` intervals
  and `0.00777 s` standard deviation on the correction rerun.

During the first bounded run, UDP `InErrors`, `RcvbufErrors` and `SndbufErrors`
remained zero. The robot Wi-Fi link measured `-33 dBm` with 1,200.9 Mbit/s RX
and TX link rates. External RAM remained near 2.0 GiB of 7.6 GiB, swap stayed
at zero, GPU load was zero and the highest sampled SoC/CPU temperature was
about 40.6 degrees Celsius. The signed control state remained no-lease,
deadman false and exact zero throughout. The relay advanced continuously with
zero sequence loss/reorder/duplicate and a stable inherited send-error count;
the authenticated IMU receiver reported no loss, replay, invalid sample,
authentication, clock or transport errors.

TERM cleanup on the first run exposed a ROS Humble shutdown race: an already
running IMU timer could attempt one publish after the context became invalid.
There was no service, process, socket or topic residue, but the traceback was
not accepted as clean shutdown evidence. Commit `9bad38e` catches only
`RCLError` after `rclpy.ok()` becomes false; the same exception while the
context is live still propagates fail-closed. Targeted 19/19 and full 899/899
Python tests passed before deployment. The previous receiver was preserved as
`wireless_imu_receiver_humble.py.pre-9bad38e`, and the deployed replacement
SHA-256 was
`1e960fced0b4f2282466bc1d873a508c1d5ce57dbebba81db42674249831065f`.

The complete readiness sequence was repeated with the correction. All gates
passed again, `/cloud_registered` sustained approximately 10 Hz and TERM
cleanup produced no traceback. Final automatic cleanup left both robot-side
sensor units disabled/inactive with PID 0 and zero restarts, no external UDP
2368/46020 listener, and zero publishers on `/lidar_points`,
`/velodyne_points`, `/imu/body`, `/Odometry`, `/Laser_map` and
`/cloud_registered`. Mapping/Nav/Dataset returned to idle and control remained
no-lease, deadman false and exact zero. No new PCD, saved map or Dataset file
was created; the two-byte upstream `PCD/1` placeholder predated HW-5 and its
mtime did not change. HW-5 is therefore `PASS` as
`MAPPING_STATIONARY_PASS`. At that checkpoint HW-6 remained `NOT_RUN`; its
later short-gate evidence is recorded below.

## HW-6 supervised compound load — 2026-09-01

The operator freshly confirmed physical E-stop readiness, an on-site safety
operator, a clear safety area and a stationary robot. The compound fixture was
the exact prompt contract: XT16 relay, authenticated wireless IMU, FAST-LIO,
Go2 and RealSense cameras, signed Control Bridge status with no lease and the
Cockpit PointCloud renderer fixed to `LOW · 10K`. Mapping/Nav/Dataset remained
idle in the dashboard; no ARM, deadman, motion command, Nav2, goal, map save,
PCD save or Dataset capture was requested.

The first browser connection exposed a deployment-baseline omission rather
than a sensor failure: Uvicorn had no WebSocket implementation even though
`requirements.txt` requires `websockets>=12,<16`. The external Orin installed
the declared user-local `websockets 15.0.1`, the no-lease Control Bridge was
stopped, the dashboard was safely restarted, and then the bridge was started
again. Both camera panels became live before the mapping launcher ran. This
dependency repair did not change repository source, network configuration or
service enablement.

The 60-second gate and then the 10-minute gate both sustained the complete
compound load. Representative and final evidence was:

- `/lidar_points` and `/velodyne_points` remained approximately 10 Hz; the
  five-minute samples were `10.016 Hz` and `10.008 Hz` respectively;
- `/Odometry` finished at `10.017 Hz`, `/cloud_registered` at `10.021 Hz` and
  `/Laser_map` at `1.000 Hz`; the authenticated IMU remained near 500 Hz with
  zero loss, duplicate, reorder, authentication, finite-value, clock or
  transport errors;
- XT16 relay sequence loss/duplicate/reorder remained zero and its inherited
  send-error counter stayed fixed at 7. Kernel UDP receive/Rcvbuf errors rose
  from 0 to 6 during the first short gate, then remained exactly 6 through the
  remainder of that gate, the full 10-minute gate and the final regression;
  kernel send-buffer errors stayed zero;
- robot Wi-Fi RSSI ranged from approximately `-32` to `-40 dBm`, negotiated
  link rate remained at least `720.6 Mbit/s` in the sampled intervals, and the
  measured ping samples had zero loss with about `1.4-1.9 ms` average and at
  most `3.407 ms` observed RTT;
- Go2 camera delivery stayed about `11.0-12.5 FPS` and RealSense delivery about
  `15.0-18.6 FPS`, with backend ages below `0.08 s`, no source error and zero
  service restarts. The RealSense relay itself held about 15 FPS at 640x480;
- the signed bridge stayed authenticated/ready with status age at most about
  `0.252 s`, LowState age `0-1 ms`, exactly one LowState publisher, no lease,
  deadman false and exact zero on all three velocity axes;
- external used RAM changed from about 2.20 to 2.24 GiB during the 10-minute
  interval, swap remained zero, GPU was zero in sampled `tegrastats`, and the
  highest sampled thermal value was about 41.3 degrees Celsius. The LOW
  Cockpit renderer reported approximately 26-34 FPS. All sensor, camera,
  dashboard and control service restart counters stayed zero.

One Cockpit presentation mismatch was recorded during the gate: while the
backend source was continuously live with sub-second frame age, a camera panel
badge could briefly project `WAITING` before returning to `LIVE`. The cause was
the per-frame MJPEG metadata event demoting an already-live shared generation
to `connected` until its following binary frame. The post-gate correction now
preserves `live` across metadata refreshes while the received frame remains
fresh; generation reset, explicit close, reconnect, decode failure and stale
frame paths are unchanged. The focused unit, full JavaScript and Cockpit camera
E2E suites passed, and the corrected static module was deployed without a
dashboard or robot service restart. Because camera services remained in their
safe inactive state after HW-6, continuous live-hardware confirmation remains
part of the deferred 60-minute operator-facing soak.

The first 10-minute stop exposed a narrow shutdown diagnostic: SIGINT delivered
to the whole SSH foreground group could interrupt the launcher's in-flight
read-only remote-service check and print a Python `KeyboardInterrupt`
traceback. Cleanup still left no process, topic, port or service residue.
`check_wireless_mapping_preflight.py` now converts only that interrupt into
bounded exit code 130, with a regression test; timeout and all fail-closed
stage errors are unchanged. The deployed previous helper is preserved as
`check_wireless_mapping_preflight.py.pre-hw6-interrupt`.

An additional SSH-TTY-only stop attempt demonstrated that killing the client
before signalling the remote launcher can orphan its child groups. The exact
recorded PIDs, start identities and process groups were stopped in reverse
order and the robot relay was stopped through its restricted lifecycle. This
was not accepted as product cleanup evidence. The final correction run instead
sent SIGINT to the verified remote launcher PID, exited 130 with no traceback,
and automatically returned all six ROS publishers and both UDP listeners to
zero while leaving both mapping sensor units inactive. Final cleanup also
closed the browser viewers and returned Control Bridge, Go2 camera and
RealSense services to their original disabled/inactive, PID-0 state. No map,
PCD or Dataset artifact was created.

HW-6 is therefore `PASS` for its ordered 60-second and 10-minute gates. The
separately required 60-minute gate remains `NOT_RUN`, so the hardware status
does not advance to `SOAK_PASS` and remains `MAPPING_STATIONARY_PASS`.

## Safety prerequisites for every hardware stage

Before each stage, record all of the following again:

- physical remote/E-stop ready and a safety operator present;
- clear area and robot stationary;
- DISARMED, no control lease, deadman released and exact zero command;
- Mapping, Nav2 and Dataset Capture idle unless the selected stage explicitly
  requires one of them;
- exact service identities, commit and private deployment manifest;
- no route, NAT, Linux bridge, DDS Router or arbitrary relay between sensor and
  management networks.

Stop on the first unexpected motion, unknown publisher, stale timestamp,
sequence reset, authentication failure, clock failure, process residue,
unbounded resource growth or mismatch from the fixed peer contract.

## Repository and deployment gates

### Gate 2 — fixed XT16 payload relay

Tests must cover exact packet type, interface, source/destination IP and ports,
IPv4 checksum, fragmentation, UDP length, 568-byte payload, fixed header,
sequence loss/duplicate/reorder, wrong input rejection, send failure/recovery,
saturating counters, non-promiscuous capture and absence of arbitrary output.
The existing wired relay and its parser remain unchanged.

### Gate 3 — Hesai wireless input and PTC

The external receive path accepts only robot-side `192.168.50.30:46236` to
external `192.168.50.10:2368`. Use the private sensor-associated PandarXT
16-channel CSV correction and leave optional firetime empty. A fixed one-client PTC proxy is `BLOCKED`
until the pinned driver proves it is necessary and the operator separately
approves it. Actual correction data and identities never enter Git.

### Gate 4 — minimum authenticated IMU

Tests cover HMAC mismatch, wrong peer, replay, duplicate, reorder, boot change,
NaN/Inf, quaternion norm, stale/future timestamps, clock synchronization,
Wi-Fi loss/recovery, exact `/imu/body` QoS and proof that no external
`/lowstate` publisher is created. The IMU key is distinct from the Control
Bridge key and exists only in mode-0600 private files.

### Gate 5 — cloud-only C++ bridge

Verify no `/lowstate` dependency in wireless mode, exact
`/velodyne_points` layout, point bounds, frame, timestamp rejection,
freshness/QoS and the complete wired legacy-mode regression. Python is not an
accepted replacement for the high-rate C++ conversion path.

### Gate 6 — wireless mapping profile

The fixed startup order is robot-side XT16 relay, robot-side IMU sender,
external IMU receiver, Hesai driver, cloud-only bridge and FAST-LIO. Shutdown
is the reverse order. A failed transaction removes only children it started,
leaves no partial map and never retries into Mapping, Nav, Mission or ARM.

### Gate 7 — verification

Required evidence includes complete Python and JavaScript tests, frontend
syntax, Ruff, mypy, tracked-source secret scan, browser E2E, `git diff --check`,
targeted C++ colcon build and ament/ctest result with exact compiler warnings.
Baseline failures are reproduced at unmodified HEAD and are never hidden by
deleting tests or weakening assertions.

## Hardware stages

| Stage | Required observation | Pass bounds |
| --- | --- | --- |
| HW-1 XT16 relay only | accepted/forwarded sequence, loss, send errors, external UDP receipt, RSSI/link | advancing exact payload; no arbitrary traffic; no service residue |
| HW-2 Hesai driver only | `/lidar_points` publisher, rate, points, age, jitter, PTC state, socket drops | rate `>=4 Hz`, age `<=1.0 s`, jitter `<=300 ms`; target near 10 Hz/64K points |
| HW-3 IMU only | authenticated sequence, loss/reorder, packet age, clock, finite values, publisher graph | exactly one `/imu/body`; zero external `/lowstate`; fresh synchronized samples |
| HW-4 cloud bridge | `/velodyne_points` publisher, rate, age, jitter, layout and drops | rate `>=4 Hz`, age `<=0.5 s`, jitter `<=300 ms`; target near 10 Hz |
| HW-5 stationary FAST-LIO | `/Odometry`, `/Laser_map`, `/cloud_registered`, consecutive freshness | explicit `APPROVE_STATIONARY_MAPPING_TEST`; no map save, Nav2 or goal |
| HW-6 compound load | 60 s, then 10 min, then deferred 60 min coexistence | bounded loss/errors/restarts/resources; LOW renderer first; no lease |

HW-1 and HW-2 stop and report separately. HW-3 and HW-4 do not authorize
FAST-LIO. HW-5 does not authorize Nav2. The 60-second and 10-minute compound
checks do not imply `SOAK_PASS`; only the full accepted 60-minute run does.

## Fail-closed matrix

| Injected or observed failure | Required projection and cleanup |
| --- | --- |
| XT16 relay stale or sequence frozen | mapping readiness false; no cached cloud reuse |
| Wi-Fi disconnect | send/receive stale; no automatic Mapping/Nav/Mission resume |
| IMU auth/replay/clock failure | packet rejected; `/imu/body` readiness false |
| Hesai or cloud bridge loss | downstream freshness false; FAST-LIO not ready |
| FAST-LIO process loss | owned children cleaned; no partial map publication |
| dashboard restart | no ARM, lease, goal, Mapping, Nav or Mission restoration |

Recovery requires consecutive fresh samples and an explicit operator start.
It never grants a control lease, publishes a goal, saves a map or changes a
network profile.

## Evidence record

Every hardware report records:

- repository commit and per-host deployed hashes;
- host/interface/address roles and fixed ports;
- service active/enabled state, MainPID, invocation and restart count;
- packet/sample counts, rate, age, jitter, loss/reorder and socket drops;
- NTP state and clock offsets;
- Wi-Fi RSSI/link rate, ping loss/RTT and send errors;
- CPU/GPU/RAM/swap, temperature/throttling and camera/control coexistence;
- lease/deadman/command before, during and after;
- cleanup, rollback files and final process/topic graph.

Credentials, HMAC keys, private environment contents, calibration artifacts,
maps, PCD, rosbag, Dataset files and raw payloads are excluded.

## Deployment approval and rollback

Gate 7 produced `docs/WIRELESS_MAPPING_DEPLOYMENT_PLAN.md` and then stopped.
The plan is not deployment authorization. Installation on either Jetson
requires Gate 7 to be green and the exact operator phrase
`APPROVE_WIRELESS_XT16_DEPLOY`. Stationary FAST-LIO later requires
`APPROVE_STATIONARY_MAPPING_TEST`.

Rollback stops and disables only the newly installed XT16/IMU services,
restores the exact previous source/config manifest and preserves Control
Bridge, camera services, network profiles, maps, Dataset and private logs. It
does not reset networking, reboot automatically, delete shared secrets or
bundle unrelated service rollback.

## Status classification

Use exactly: `CODE_READY`, `XT16_RELAY_PASS`, `LIDAR_PASS`, `IMU_PASS`,
`CLOUD_PASS`, `MAPPING_STATIONARY_PASS`, `SOAK_PASS`, `BLOCKED` or `FAIL`.
Gates 2, 3, 4 and 5 are repository-only PASS. The repository gate is
`CODE_READY`; the current hardware status is `MAPPING_STATIONARY_PASS`.
`SOAK_PASS` is not claimed.
