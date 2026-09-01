# Track C — Competition PDF direct-wired Nav2 path

Status date: 2026-09-02

Repository baseline: `c7b5c0ea369f3674a79b08928a2a42852febfc64`

Track C profile: `competition-pdf-direct`

## Direction and preservation

- `DEFERRED`: Unitree support email submission, firmware investigation and
  source-clock correction work.
- No Gmail draft or sent message was found during the read-only C0 check. No
  support portal submission was made by this work.
- Track A and Track B remain source records. This change does not edit them.
- The strict wireless odometry protocol remains separate. Its 500 ms source
  age and 100 ms future-skew limits are not used by Track C and are not
  weakened.
- Track C never starts the wireless odometry sender or receiver. It consumes
  `/utlidar/robot_odom` from direct DDS on the Nav host.
- No firmware, clock, route, NAT, bridge, robot control, map data or navigation
  goal was changed during C0–C3.

Preserved-file fingerprints at the C0 baseline:

| Deferred record | SHA-256 |
|---|---|
| `docs/CONTROLLER_ODOMETRY_CLOCK_RECOVERY_PLAN.md` | `b7dcbe6dbeb06f7d3cfb282a73a74fcf8725e5a4c831c38ca05d7cd0b05860cd` |
| `docs/ADR_WIRELESS_CONTROLLER_ODOMETRY_TRANSPORT.md` | `1438c45b397e5e46d727da53db80d5ec97daf6c43c3bccfb245fbfa8e7184c1d` |
| `docs/NAV2_TRACK_B_PARALLEL_PATH_PLAN.md` | `a265bb192196afa3011ee9044cc5509bb342207d37759bfe4d2567ad9ae2fa28` |

## Evidence boundary

The named education PDF files were not present in the supplied prompt folder,
the repository, `Documents`, or `Desktop`. Therefore `PDF 원본` below means
only the contracts transcribed into the supplied Track C prompt; it is not a
claim that the original PDFs were independently inspected. Repository code,
host files and live read-only measurements are reported separately.

## Nav host decision

| Candidate | Direct Go2/XT16 network | Runtime | Decision |
|---|---|---|---|
| External Jetson `192.168.50.10` | No `192.168.123.0/24` NIC or route; direct pings fail | Ubuntu 22.04, ROS 2 Humble, 6 cores, 7.4 GiB | Rejected for Track C physical topology |
| Go2-mounted external Jetson `192.168.50.30` | `eth0=192.168.123.18/24`; Go2 and XT16 pings pass | Ubuntu 20.04, ROS 2 Foxy, 8 cores, 15 GiB | Only physically eligible host; runtime compatibility blocked |

`192.168.50.30` is the management address of the external Jetson mounted on
the Go2; it is not the Go2 internal computer. The off-robot dashboard Jetson is
`192.168.50.10`. The Go2-mounted external Jetson is the only current direct
host. It cannot run the
repository-owned Humble Track C stack without mixing ROS distributions, which
Track C explicitly forbids. Its installed Foxy graph has Nav2 and Unitree/Hesai
messages but no `fast_lio` package. No automatic OS/ROS upgrade or substitute
localization backend is authorized.

The external deployment also had pre-existing uncommitted files at inspection
time and runs the dashboard with `go2-xt16-wireless`. Those files were not
changed or cleaned by Track C.

Direct-host environment inventory:

| Item | Observed value |
|---|---|
| Ubuntu | 20.04.6 LTS (Focal), `aarch64` |
| ROS | Foxy, domain 0 |
| Python | 3.8.10 |
| RMW | `rmw_cyclonedds_cpp` 0.7.11 |
| CycloneDDS ROS package | 0.7.0 |
| Compute | 8 cores, 15 GiB RAM |
| Robot NIC | `eth0=192.168.123.18/24` |
| Management NIC | `wlan0=192.168.50.30/24` |

## PDF-to-current implementation inventory

| PDF 구성 | PDF 경로/명령 | Current equivalent | Status |
|---|---|---|---|
| Go2 ROS environment | `go2ros` | `scripts/setup_competition_pdf_direct_humble.sh` → pinned direct Humble setup | IMPLEMENTED, hardware host blocked |
| Unitree messages/DDS | `~/unitree_ros2` | pinned Humble dependency manifest; robot host has Foxy `autonomy_stack_go2` and `unitree_ros2` | FOUND, distro differs |
| Go2 URDF | `~/ws/unitree_ros` | Unitree source dependency; dashboard model path is separate | PATH DIFFERS |
| Hesai driver | `~/ws/hesai_ws` | `scripts/run_hesai_driver_competition_direct_humble.sh` plus pinned Hesai workspace | IMPLEMENTED; Foxy workspace also found |
| Livox dependency | `~/ws/livox` | pinned in `config/ros_dependencies_humble.json` for FAST-LIO build | DECLARED, not installed on direct host |
| FAST-LIO | `~/ws/fastlio_ws` | pinned `Ericsii/FAST_LIO` plus `scripts/run_hesai_fastlio_humble.sh` | MISSING on direct host |
| XT16/body IMU bridge | `xt16_fastlio_bridge.py` | repository C++ `robot_scope_xt16_bridge` and Python reference | FOUND; Humble build only |
| FAST-LIO launcher | `run_slam.sh` | `scripts/run_hesai_fastlio_humble.sh` | EQUIVALENT |
| PCD save | `save_map.py` | `scripts/save_map.py` and allowlisted `save_hesai_map_humble.sh` | FOUND |
| 3D→2D map | `pcd2pgm` | repository `save_map.py` path and Nav2 map saver | EQUIVALENT |
| Localization backend | `go2_navigation2.launch.py` | `robot_dashboard.navigation_runtime` and navigation coordinator | EQUIVALENT, Humble |
| Nav2 core | `go2_nav.launch.py` | `scripts/run_go2_navigation_humble.sh` with fixed executables | EQUIVALENT |
| Tuned parameters | `nav2_params_shim.yaml` | `config/nav2_params_go2_humble.yaml` plus runtime snapshot validation | PATH DIFFERS |
| Command bridge | `cmd_vel_to_sport.py` | signed Control Bridge/watchdog path; an unrelated Foxy copy exists under `go2-rgbd-obstacle-slam` | NOT USED in no-goal |
| RViz config | `go2_nav.rviz` | no exact repository file | MISSING; dashboard visualization exists |
| Go2 camera relay | H.264 multicast→MJPEG | existing Robot Scope Go2 camera relay | FOUND, outside C0–C8 core |

Exact PDF-named files were not found except the repository equivalents
`scripts/xt16_fastlio_bridge.py` and `scripts/save_map.py`. The robot host also
contains `/home/unitree/go2-rgbd-obstacle-slam/.../cmd_vel_to_sport.py`, but it
is not assumed to be the PDF source and is not integrated into Track C.

## Track C process and topic contract

The profile is explicit; the repository default remains `go2-xt16-wired`.

| Owner | Input | Output / responsibility |
|---|---|---|
| direct setup | dedicated `192.168.123.x/24` NIC | Humble + CycloneDDS bound to that NIC |
| direct preflight | NIC, process table, DDS graph | blocks wrong distro, missing direct links, wireless odometry processes, duplicate/missing publishers |
| Track C Hesai driver | XT16 `192.168.123.20:2368` | `/lidar_points`, frame `hesai_lidar` |
| existing fixed bridge | `/lidar_points`, `/lowstate` | `/velodyne_points`, `/imu/body`; sensor restamp only |
| existing FAST-LIO | `/velodyne_points`, `/imu/body` | `/Odometry`, `/Laser_map` |
| existing localization runtime | `/Odometry`, `/Laser_map`, selected static map | `/scan`, TF adapter and health |
| existing Nav2 owner | `/map`, `/scan`, direct `/utlidar/robot_odom`, TF | `/robot_scope/nav/cmd_vel_raw` only when a future goal exists |
| no-goal checker | active graph and motion topics | requires lifecycle/map/scan/TF and two seconds of quiet command topics |

The Track C preview and mapping wrappers `exec` the existing transactional
owners. They do not create a second Hesai, bridge, FAST-LIO or TF owner. The
Hesai runner selection is an exact repository allowlist, not a caller-supplied
command.

## Stationary hardware observations

The robot remained stationary and no control path was opened. Go2 DDS checks
were read-only subscriptions. The XT16 check added one bounded sensor-only
Hesai publisher, then stopped it without starting bridge, FAST-LIO or Nav2.

| Check | Result | State |
|---|---|---|
| Robot host → Go2 `192.168.123.161` | 3/3 replies, 0% loss, average 0.893 ms | PASS |
| Robot host → XT16 `192.168.123.20` | 3/3 replies, 0% loss, average 0.195 ms | PASS |
| `/lowstate` | one reliable/volatile `unitree_go/msg/LowState` publisher; samples advance | PASS |
| `/utlidar/robot_odom` | one reliable/volatile publisher; `odom → base_link`; samples advance | PASS |
| `/utlidar/imu` | one reliable/volatile publisher; frame `utlidar_imu`; samples advance | PASS |
| `/utlidar/cloud` | one graph publisher but no sample observed in a three-second window | BLOCKED |
| Hesai `/lidar_points` | bounded Foxy sensor-only probe decoded 64,000 points/frame at approximately 10 Hz; one reliable publisher | PASS (raw sensor only) |
| bridge, FAST-LIO, map, scan, TF, Nav2 no-goal | FAST-LIO absent and distro mismatch | BLOCKED |

The Foxy CLI rate helper produced no periodic output for the bare-DDS topics.
A bounded message count still proved progression: 248 `/lowstate`, 228 odometry
and 392 IMU samples were observed in separate three-second subscription
windows. These are observation-throughput counts, not claimed source rates.
The Hesai CLI subscriber did not receive a cloud even though the driver graph
and decoder log advanced, so the PASS above covers XT16 UDP decode and publisher
creation, not ROS subscriber delivery to the Humble Track C bridge. The first
probe also exposed that `ros2 run` could orphan the vendor child; the exact
child was cleaned and the Track C runner now `exec`s the validated installed
driver binary so its process owner tracks the real PID.

## No-goal and motion boundary

`scripts/check_competition_no_goal_ready.py` is intentionally read-only. It
requires the core lifecycle nodes to be active, `/map`, `/scan`, localization
and both costmaps to have publishers, `map → base_link` TF to resolve, and both
the Nav raw velocity topic and `/api/sport/request` to remain silent during the
monitoring window.

No Track C launcher starts `cmd_vel_to_sport`. C0–C4 did not publish an initial
pose, goal, `/cmd_vel`, sport request, lease, ARM or deadman event. Mapping
motion and autonomous motion remain outside the authorized scope.

## Minimum unblock requirement

One of the following must exist before C4 bridge/FAST-LIO and C8 no-goal can be
continued:

1. a direct-wired Ubuntu 22.04 / ROS 2 Humble host with Go2 and XT16 on its
   dedicated NIC, or
2. a separately reviewed Foxy Track C dependency/compatibility plan with the
   actual education sources, including an installed FAST-LIO package and
   verified Foxy bridge build.

The current external Humble Jetson cannot satisfy option 1 while Go2 and XT16
remain physically connected only to the Go2-mounted external Jetson. No route, NAT,
bridge, wireless relay or ROS distro mixing will be introduced as a shortcut.

After the host requirement is met, the next stationary sequence is: direct
preflight → Hesai preview → bridge readiness → FAST-LIO readiness → selected
map/localization → Nav2 startup without command bridge → no-goal checker →
owned-process cleanup. A real initial pose, goal or motion still requires a new
explicit safety confirmation.

## Final observed runtime state

- External Jetson: dashboard service active on TCP `0.0.0.0:8088`; wireless
  odometry receiver and Control Bridge inactive; no Track C sensor, FAST-LIO,
  Nav2 or command bridge process observed.
- Go2-mounted external Jetson: wireless odometry sender, Control Bridge and XT16
  wireless relay services inactive; the bounded Hesai probe was stopped; no
  Track C sensor, FAST-LIO, Nav2 or command bridge process or related listening
  UDP port observed.
