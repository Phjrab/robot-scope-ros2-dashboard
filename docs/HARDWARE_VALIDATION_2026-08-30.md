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

1. External Orin commit and robot-side archive both resolved to
   `b38dc255fb4c331760af1b9d95dfa91c890529dd`.
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

## Remaining wireless acceptance

- Run the deferred 60-minute Wi-Fi soak and interference test.
- Run supervised Wi-Fi/UDP interruption and Bridge-process-loss fault tests;
  neither was injected during this no-motion lifecycle.
- Verify the DHCP reservation retains `192.168.50.30` after an intentional
  reconnect or reboot.
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
- Both RealSense and robot-side Control Bridge services were left disabled and
  inactive; no service-state rollback is required.
- External dashboard private configuration was backed up as
  `~/.config/robot-scope/control.env.pre-b38dc25`. Restore that mode-0600 copy
  and restart only the dashboard to roll back the wireless control settings.
- Robot-side source is `/home/unitree/project/robot-scope`; its private Bridge
  environment, lifecycle key authorization, forced-command helper, exact
  sudoers file, and systemd unit must be rolled back as one reviewed set. Do
  not delete or overwrite the shared key during an unrelated source rollback.

## Repository verification

- `git diff --check`: PASS
- JavaScript unit suite: 239 passed, 0 failed
- frontend syntax check: 48 modules passed
- Python unit suite: 694 run; 693 passed and one existing macOS baseline error
  remained. `test_apply_os_release_override_must_match_running_host` attempts to
  read Linux-only `/etc/os-release`, which is absent on the macOS test host.
  No test or assertion was removed or weakened.
- Targeted wireless control tests: 68 passed across datagram, dashboard
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
