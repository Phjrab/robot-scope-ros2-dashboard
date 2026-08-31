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

## Current Gate record — 2026-08-31

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
| HW-2–HW-6 | `NOT_RUN` | HW-2 awaits a fresh physical safety check; no Hesai driver, IMU publisher, cloud bridge, FAST-LIO, map write or Nav2 start |

Current external topics remain truthfully unavailable: `/lidar_points`,
`/velodyne_points` and `/imu/body` have zero publishers. Mapping, navigation
and Dataset Capture are idle. The repository status is `CODE_READY`; the
current hardware status is `XT16_RELAY_PASS`. No LiDAR pointcloud, IMU, cloud,
mapping or navigation PASS is implied.

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
Driver start and HW-2 remain `NOT_RUN`. A proxy fallback remains
`BLOCKED` unless the offline path fails in an approved hardware test and
receives a new design approval.

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

Gate 4 did not install a key or service, contact either Jetson, start a ROS
process, create a topic, or operate the robot. HW-3 and `IMU_PASS` therefore
remain `NOT_RUN`.

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
recorded below; HW-4 plus `CLOUD_PASS` remain `NOT_RUN`.

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
lease, deadman false and exact zero command. HW-2–HW-6 remain `NOT_RUN`.

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
`CODE_READY`; the current hardware status is `XT16_RELAY_PASS`. `LIDAR_PASS`,
`IMU_PASS`, `CLOUD_PASS`, `MAPPING_STATIONARY_PASS` and `SOAK_PASS` are not
claimed.
