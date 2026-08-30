# Hardware validation — 2026-08-30 wireless management transition

## Scope and safety boundary

This session covered the robot-side Jetson wireless management link, its
dedicated Go2 Ethernet link, Go2 DDS/LowState observation, and the external
dashboard/control preflight. The robot remained uncommanded. No control lease,
ARM, deadman press, action request, navigation goal, mapping launch, map
mutation, dataset capture, robot service restart, or motion command was issued.

The standalone Control Bridge was not started because the external Orin did
not own the dedicated Go2 interface required by the repository contract. Its
unit remained disabled and `inactive/dead`, with PID 0 and zero restarts.

## Validated host and network roles

| Role | Interface/address | Result |
|---|---|---|
| External dashboard Orin management | `eno1=192.168.50.10/24` | PASS; Ethernet carrier and management default route present |
| Robot-side Jetson management | `wlan0=192.168.50.30/24` | PASS; `RobotLab_5G`, DHCP address, management default route present |
| Robot-side Jetson Go2/sensor LAN | `eth0=192.168.123.18/24` | PASS; static address, no gateway, `never-default=yes` |
| Go2 body | `192.168.123.161/24` | PASS from robot-side Jetson; 0% loss, about 0.17 ms average RTT |
| External Orin Go2 interface | required `192.168.123.99/24` | BLOCKED; no dedicated interface/address is currently present |

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
DDS/LowState path. It is not a PASS for the external Orin path.

## Control Bridge lifecycle status

The external dashboard restored the configured Go2 target and projected the
Control Bridge lifecycle surface, but the host still lacked
`192.168.123.99/24`. Starting the service in this topology would only leave its
supervisor waiting for that exact interface; it would not exercise the signed
bridge, LowState freshness, graph cardinality, zero-command watchdog, or
authenticated status path. Therefore the requested no-motion lifecycle is
recorded as **BLOCKED / NOT RUN**, not as a false pass.

The remaining supervised acceptance sequence is:

1. provide the external Orin with the approved dedicated Go2 transport;
2. confirm the dashboard starts in `go2_interface` mode and sees fresh
   LowState;
3. confirm no lease, DISARMED state, released deadman, and zero linear/angular
   command;
4. start the fixed Control Bridge service through the dashboard;
5. require authenticated bridge-ready status, fresh LowState, expected graph
   cardinality, DISARMED state, and zero command;
6. stop through the dashboard and confirm `inactive/dead` with no motion.

## Required architecture decision before the remaining test

The currently implemented and previously accepted path is a second external
Orin NIC at `192.168.123.99/24` connected to the dedicated Go2 network. If the
competition configuration must be fully wireless between the moving robot and
the external Orin, that is a product-boundary change: a narrow authenticated
cross-host transport and its fail-closed behavior must be designed, reviewed,
implemented, and hardware-tested first. Moving the whole dashboard or Control
Bridge onto the Foxy relay host, exposing arbitrary DDS over management Wi-Fi,
or adding generic routing/bridging is not an approved shortcut.

## Rollback notes

- Revert the three RealSense host values only if the robot-side management
  address is deliberately moved away from `192.168.50.30`.
- Do not return robot-side `eth0` to DHCP while it remains the dedicated
  `192.168.123.0/24` Go2/sensor link.
- Both RealSense and Control Bridge services were left disabled and inactive;
  no service-state rollback is required.

## Repository verification

- `git diff --check`: PASS
- JavaScript unit suite: 239 passed, 0 failed
- frontend syntax check: 48 modules passed
- Python unit suite: 683 run; 682 passed and one existing macOS baseline error
  remained. `test_apply_os_release_override_must_match_running_host` attempts to
  read Linux-only `/etc/os-release`, which is absent on the macOS test host.
  No test or assertion was removed or weakened.
