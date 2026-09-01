# Nav2 Track B parallel-path decision and no-goal plan

- Status: repository analysis complete; hardware execution blocked
- Date: 2026-09-01
- Selected path: `A_EXISTING_WIRED_CANDIDATE`
- Current readiness: `BLOCKED_BY_PHYSICAL_TOPOLOGY_AND_WORKSPACE`
- Related deferred path: Track A controller-odometry source-clock recovery

## Scope and invariant boundary

Track B separates Nav2's runtime prerequisites from the strict wireless
controller-odometry clock problem. It does not replace or weaken Track A.
The original `/utlidar/robot_odom` stamp, the 500 ms maximum source age, the
100 ms future-skew limit, the fixed peer/topic/frame contract and the ban on
using FAST-LIO `/Odometry` as controller odometry remain unchanged.

The following firmware metadata is support evidence, not a Nav2 runtime gate:

- Unitree Go application: `v2.0.0-8031e`
- Go2 model: `Go2 EDU`
- Go2 body software: initially observed as `v1.1.11`; the operator later
  reported completing the update to `v1.1.15`
- Go2 hardware: `v2.0`
- L1 firmware: `MISSING_FROM_HANDOFF`

The body update was operator-performed outside this task. This work did not
request, install or validate an OTA update. The new version is not evidence
that the producer clock changed.

Track A remains `DEFERRED / BLOCKED PENDING UNITREE SUPPORT`. In particular,
this plan does not authorize WNO-2, clock changes, firmware changes or an
undocumented Unitree API.

## Architecture comparison

| Item | PDF direct single-PC | Robot Scope `go2-xt16-wired` | Robot Scope `go2-xt16-wireless` |
|---|---|---|---|
| OS / ROS | Ubuntu 24.04 / Jazzy examples | Ubuntu 22.04 / Humble | robot Foxy 20.04 + external Humble 22.04 |
| Go2 DDS owner | development PC | external Humble host | robot-side Foxy host |
| Go2 dedicated NIC | direct `192.168.123.x` | external host owns `192.168.123.99/24` | robot host owns `192.168.123.18/24` |
| XT16 receiver | development PC | external host fixed XT16 path | robot relay plus bounded external receiver |
| Body IMU source | direct bridge, host restamped | direct Unitree graph | authenticated bounded IMU transport |
| FAST-LIO owner | development PC | external Humble host | external Humble host |
| `/Odometry` owner | FAST-LIO | FAST-LIO | FAST-LIO |
| `/utlidar/robot_odom` path | direct Unitree graph | direct Unitree graph | authenticated fixed UDP transport |
| `/scan` owner | local projection | Robot Scope navigation runtime | Robot Scope navigation runtime |
| TF owner | PDF launch/`go2_tf`, details unavailable | Robot Scope navigation runtime | Robot Scope navigation runtime |
| Nav2 owner | development PC | external Humble host | external Humble host |
| Command bridge | local `/cmd_vel` to sport bridge | fixed Robot Scope navigation ingress and signed watchdog | same fixed ingress plus remote signed Control Bridge |
| Clock policy | XT16/body IMU host restamp; controller-odom behavior not shown | host-current FAST-LIO and runtime TF; controller stamp must advance | original controller stamp plus strict sender/receiver clock fences |
| Additional transport guard | not shown | none for controller odometry | HMAC, fixed peers, sequence/replay and 500/100 ms clock bounds |

The PDF demonstrates one useful architecture, not the current production
contract. Its Jazzy commands and uninspected `go2_tf`/launch internals are not
copied into Robot Scope.

## Gate B1 conclusions

```text
NAV2_RUNTIME_REQUIRES_FIRMWARE_VERSION=false
WIRED_PROFILE_REQUIRES_WIRELESS_ODOM_GUARD=false
WIRELESS_PROFILE_REQUIRES_CONTROLLER_ODOM_TRANSPORT=true
ROBOT_SIDE_FOXY_MAY_HOST_FULL_NAV2=false
```

Evidence:

- `run_go2_navigation_humble.sh` defaults to `go2-xt16-wired` and sources
  `setup_go2_ros2_humble.sh` for that profile.
- Only the explicit wireless branch starts the remote odometry sender, local
  receiver and `check_wireless_odom_ready.py`.
- `config/nav2_params_go2_humble.yaml` fixes both `bt_navigator` and
  `controller_server` to `/utlidar/robot_odom`, while the Robot Scope
  localization runtime consumes FAST-LIO `/Odometry`.
- The supported full Go2/XT16/Nav2 target remains Humble on Ubuntu 22.04.
  Nav2 binaries observed on the robot Foxy host do not change that support
  boundary.

## Read-only topology observed on 2026-09-01

### External/dashboard Jetson

- `aarch64`, Ubuntu 22.04.5, ROS 2 Humble
- management/Wi-Fi: `wlP1p1s0=192.168.0.26/24`, carrier up
- robot management LAN: `eno1=192.168.50.10/24`, carrier up
- no interface owns `192.168.123.99/24`
- Go2 body `192.168.123.161` and XT16 `192.168.123.20` route through the
  `.50.1` default gateway and both bounded pings failed
- Humble and required Nav2 executables are present
- `/home/jetson_orin_nano/unitree_ros2/cyclonedds_ws/install/setup.bash` is
  missing

### Robot-side Jetson

- `aarch64`, Ubuntu 20.04.6, ROS 2 Foxy (and ROS 1 Noetic present)
- Go2 sensor LAN: `eth0=192.168.123.18/24`, carrier up
- management Wi-Fi: `wlan0=192.168.50.30/24`, carrier up
- direct routes exist to Go2 `192.168.123.161` and XT16 `192.168.123.20`
- the Unitree Foxy workspace and repository setup helper are present
- robot-side Robot Scope dashboard unit is absent; bounded sensor/control
  units are installed, disabled and inactive
- Nav2 binaries are present but full Nav2 on this Foxy host is rejected by the
  repository support contract

Immediately after the operator-performed body update, the robot Jetson booted
with a transient 1970 clock. Without any mutation by Robot Scope, its existing
NTP service then synchronized to 2026-09-01 and reported
`NTPSynchronized=yes`. This host-clock recovery does not prove that the Go2
bare-DDS producer timestamp was repaired.

## Gate B2 conclusions

| Candidate | Result | Evidence |
|---|---|---|
| Direct wired Humble | `BLOCKED` | no `.123.99/24` NIC, no direct body/XT16 reachability, missing Unitree workspace |
| Existing strict wireless | `BLOCKED` | topology is installed but Track A source clock failed the unchanged sender fence |
| Robot-side full Nav2 | `REJECTED` | Foxy host is outside the supported full-stack deployment contract |
| PDF Jazzy commands unchanged | `REJECTED` | different OS/ROS, launch and TF details are not established |

## Timestamp and readiness code audit

| Time kind | Definition | Repository use | Failure condition |
|---|---|---|---|
| Source header stamp | producer-provided message time | original `/utlidar/robot_odom`; FAST-LIO `/Odometry` | zero/malformed/non-advancing; FAST-LIO also wall-clock stale/future |
| Sender realtime | robot Jetson wall clock | wireless sender envelope and source-age comparison | source older than 500 ms or over 100 ms future |
| Receiver realtime | external Jetson wall clock | sender packet age and source/sender delta | older than 500 ms or over 100 ms future |
| Monotonic arrival | process-local liveness | receiver readiness, gateway validated receipts, runtime source age | transport gap or freshness timeout |
| TF stamp | current external ROS clock | runtime `odom -> base_link` and `map -> odom` broadcast | no fresh FAST-LIO odometry or no accepted initial pose |
| Nav2 ROS time | external ROS time, `use_sim_time=false` | all fixed Nav2 children | host-time/TF/input incompatibility, determined at no-goal acceptance |

### Fixed role separation

- Navigation runtime consumes `/velodyne_points` and FAST-LIO `/Odometry`.
  It requires current host-clock stamps, projects `/scan`, and creates dynamic
  TF with its current ROS clock.
- Nav2 controller and BT navigator consume independent
  `/utlidar/robot_odom` for controller feedback.
- Navigation gateway applies absolute wall-clock freshness to FAST-LIO
  `/Odometry`. For controller odometry it validates shape, finite/bounded
  values, strict advancement and monotonic arrival recency, but does not apply
  the FAST-LIO absolute-age check.
- Wireless sender and receiver independently apply the stricter original-stamp
  500 ms source-age and 100 ms future-skew fences. The receiver republishes the
  original stamp without rebasing.
- Runtime TF freshness is based on host-current broadcasts and monotonic
  observation age. It is not evidence that the independent controller source
  shares the same clock domain.

### Gate B3 conclusions

```text
WIRED_ABSOLUTE_SOURCE_AGE_BLOCKER=NOT_ENFORCED_BY_WIRELESS_TRANSPORT; NAV2_RUNTIME_ACCEPTANCE_REQUIRED
WIRELESS_ABSOLUTE_SOURCE_AGE_BLOCKER=YES_500MS_PAST_100MS_FUTURE
TF_DOMAIN_COMPATIBILITY=PARTIAL_UNPROVEN_FOR_DIRECT_CONTROLLER_ODOMETRY
CURRENT_PRIMARY_BLOCKER=E_PHYSICAL_TOPOLOGY_FOR_A_PLUS_C_STRICT_TRANSPORT_CLOCK_FOR_B
PDF_EVIDENCE_LIMIT=GO2_TF_AND_CONTROLLER_ODOMETRY_CLOCK_BEHAVIOR_NOT_SHOWN
```

An advancing controller stamp with a fixed absolute offset passes the current
gateway's controller-specific validation. That is not promoted to a hardware
PASS: Nav2 and TF compatibility still require a stationary no-goal run on the
direct wired topology. The PDF's XT16/body-IMU restamping does not establish
that controller odometry was restamped or safe.

## Hardware-free Track B experiment

The experiment is implemented in
`tests/test_nav2_track_b_boundaries.py`. It uses synthetic messages and the
existing pure validation functions; it opens no ROS graph or network socket.

| Scenario | Expected | Actual | Code path | Wired relevance | Wireless relevance | Remaining uncertainty |
|---|---|---|---|---|---|---|
| T1 current source | accepted inside fixed bounds | `PASS` | sender/receiver validation | current direct source remains required | passes strict clock fence | live rate/QoS not proven |
| T2 advancing fixed past offset | controller gateway advances; wireless rejects | `PASS` | gateway controller validation vs sender source clock | not rejected by gateway absolute-age logic | rejected as stale | Nav2 binary behavior needs no-goal run |
| T3 non-advancing source | fail closed | `PASS` | gateway commit and receiver replay state | advancement still required | replay rejected | live producer reset behavior |
| T4 future source | fail closed | `PASS` | sender future fence | FAST-LIO host-clock path rejects future stamps | strict 100 ms fence | live source behavior |
| T5 transport arrival stale | readiness closes | `PASS` | receiver monotonic freshness | not applicable to direct DDS transport | no cached current sample | live Wi-Fi loss deferred |
| T6 TF/frame mismatch | reject incompatible frames | `PASS` | FAST-LIO frame contract | direct path must supply expected TF inputs | same external runtime contract | vendor/PDF `go2_tf` unknown |
| T7 PDF-style sensor restamp boundary | sensor/TF clock handling must not rebase controller odom | `PASS` | scan stamp, host TF stamp, receiver original stamp | roles remain separate | strict original stamp preserved | hardware timestamps not remeasured |

## Candidate evaluation and selected path

### Candidate A — existing direct wired Humble

`SELECTED_PATH=A_EXISTING_WIRED_CANDIDATE`

This is the preferred Track B route because it reuses the existing profile and
does not weaken Track A. It is not executable in the current wiring.

Required preparation in a separately approved task:

1. Connect a dedicated external-host NIC to the Go2/XT16 sensor LAN without
   changing the management Wi-Fi/LAN.
2. Assign the repository contract address `192.168.123.99/24` to that dedicated
   interface, with no default route, forwarding, NAT or bridge.
3. Install/verify the pinned Unitree Humble workspace at the existing helper's
   expected absolute path.
4. Verify carrier, exact address ownership and bounded direct reachability to
   Go2 `192.168.123.161` and XT16 `192.168.123.20`.
5. Verify the fixed wired XT16 configuration and packet destination without
   changing the sensor in this Track B repository task.
6. Run the repository doctor and static preflight before any ROS child is
   started.

Rollback for that future physical task is to remove only the added sensor-LAN
cable/NIC configuration and restore its recorded prior network profile. It
must not change `.50.10`, `.50.30`, Track A files, the wireless keys or any
robot-side service.

### Candidate B — strict wireless

`DEFERRED / BLOCKED PENDING UNITREE SUPPORT`. The original stamp and all
transport guards remain unchanged. Go2 body `v1.1.15` is a Track A resume
trigger, not proof of repair; source timestamps must be remeasured in that
separate track before WNO-2 is reconsidered.

### Candidate C — future explicit adaptation

`NOT_SELECTED`. No production relay or restamping implementation is authorized.
Any future design requires a separate ADR, fixed new topic/profile, audit of
the original stamp and measured offset, fail-closed drift/jump/replay handling,
a threat model, hardware acceptance and explicit approval.

## No-goal validation plan — not authorized by this document

The following is a future supervised plan only. It does not create an approval
token and must not be run as part of Track B repository work.

1. Record the exact repository and deployed commit on every participating host.
2. Select exactly `go2-xt16-wired`; do not fall back to wireless.
3. Use only the external Ubuntu 22.04/Humble host for the full stack.
4. Record the dedicated interface name, carrier and exact
   `192.168.123.99/24` ownership.
5. Select one immutable saved map ID and revision without modifying map data.
6. Record SHA-256 of the generated map and parameter snapshots.
7. Confirm sender/receiver, Mapping, FAST-LIO, Nav2 and Control Bridge starting
   states before any lifecycle action.
8. Confirm control lease inactive.
9. Confirm DISARMED; if armed state cannot be read, stop.
10. Confirm deadman false.
11. Confirm vx, vy and wz are exact zero.
12. Require a physical remote/E-stop, stationary robot, cleared area and an
    on-site safety observer.
13. Do not publish `/initialpose`.
14. Do not send a navigation goal.
15. Do not use browser manual control during the run.
16. Observe every Nav2 lifecycle node and require deterministic activation or
    fail-closed cleanup.
17. Require exactly one fresh `/map`, `/scan`, `/Odometry`,
    `/utlidar/robot_odom` and the expected TF chain.
18. Require `/robot_scope/nav/cmd_vel_raw` to be absent or exact zero.
19. Prove that no new `/api/sport/request` command is published.
20. Stop through the owning dashboard transaction and wait for settlement.
21. Confirm no owned child, UDP 46030 listener or process-group residue.
22. Stop immediately on publisher conflict, stale/future/non-advancing input,
    TF mismatch, lifecycle child exit, lease/deadman change or nonzero command.
23. Roll back only the selected run's owned processes and snapshots; preserve
    maps, Track A artifacts and unrelated services.
24. Produce a timestamped report with exact inputs, lifecycle transitions,
    topic/frame/QoS/rate/freshness evidence, command absence and final state.

No-goal success would authorize neither an initial pose nor a navigation goal.

## Track A resume conditions

Reopen Track A separately when any of the following is available:

- authoritative source timestamp remeasurement after the operator-reported
  Go2 `v1.1.15` update;
- an official Unitree support response or supported producer-clock workflow;
- applicable body/L1 firmware range and persistence behavior;
- calibration, locomotion, saved-map and rollback/downgrade impact;
- expected timestamp domain and maximum error after the official procedure.

Track A evidence is appended, never replaced by this Track B decision.
