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
| Gate 0 network boundary | `PASS` with recorded limitation | robot-side `FORWARD DROP`, Docker-only forwarding/NAT, no `wlan0↔eth0` rule; external has no sensor route/interface, but privileged external netfilter dump remains unverified |
| Gate 1 architecture and acceptance documents | `PASS` after contract tests | this document and the wireless transport ADR; no runtime/deployment mutation |
| Gate 2 fixed XT16 relay implementation | `PASS` after hardware-free contract tests | separate fixed-address relay, disabled service example and strict regression tests; no host installation or live packet claim |
| Gates 3–6 implementation | `NOT_RUN` | later work gates |
| Gate 7 repository/C++ verification | `NOT_RUN` | runs after implementation |
| Deployment and HW-1–HW-6 | `NOT_RUN` | `APPROVE_WIRELESS_XT16_DEPLOY` not supplied |

Current external topics remain truthfully unavailable: `/lidar_points`,
`/velodyne_points` and `/imu/body` have zero publishers. Mapping, navigation
and Dataset Capture are idle. The current repository status is not
`CODE_READY`; that classification requires Gates 2–7.

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
external `192.168.50.10:2368`. Prefer a private sensor-associated offline
correction/firetime artifact. A fixed one-client PTC proxy is `BLOCKED` until
the pinned driver proves it is necessary and the operator separately approves
it. Actual calibration artifacts and identities never enter Git.

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

Gate 7 completion produces `docs/WIRELESS_MAPPING_DEPLOYMENT_PLAN.md` and then
stops. Installation on either Jetson requires the exact operator phrase
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
Gate 2 is a repository-only PASS. No deployment or hardware status is claimed.
