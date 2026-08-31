# Wireless XT16 mapping deployment plan

- Plan date: 2026-08-31
- Candidate runtime baseline: final tested `main` HEAD, frozen at approval
- Deployment authorized: **no**
- Current status: repository `CODE_READY`; deployment and HW-1–HW-6 `NOT_RUN`

This document fixes the intended installation and hardware-test boundary. It
does not authorize installation, a service start, Mapping, FAST-LIO, Nav2, a
map write, a control lease or robot motion. Gate 7 is green, but deployment
still requires every blocker below to clear and the exact operator phrase
`APPROVE_WIRELESS_XT16_DEPLOY`.

## Measured topology and ownership

| Role | Host/interface/address | Owner |
| --- | --- | --- |
| Robot management | robot-side Jetson `wlan0=192.168.50.30/24` | Wi-Fi management only |
| Robot sensor LAN | robot-side Jetson `eth0=192.168.123.18/24` | Go2 and XT16 only; no default gateway |
| Dashboard and mapping | external Orin `eno1=192.168.50.10/24` | Robot Scope, Hesai, cloud bridge, FAST-LIO |
| Go2 body | `192.168.123.161` | unchanged |
| XT16 | `192.168.123.20` | unchanged |

Before installation, a new read-only audit must confirm these exact values,
both synchronized clocks, robot-side `FORWARD DROP`, no management-to-sensor
forwarding/NAT/bridge and the external host's privileged netfilter state. Any
address or ownership mismatch blocks deployment; source code and network
profiles are not adjusted opportunistically.

## Fixed transport and expected load

| Flow | Exact tuple and content | Planning load |
| --- | --- | --- |
| XT16 sensor input | `192.168.123.20:10000 -> 192.168.123.18:2368`, passively validated on `eth0` | observed near 5,000 packets/s |
| XT16 wireless output | `192.168.50.30:46236 -> 192.168.50.10:2368`, exact 568-byte payload | about 22.72 Mbit/s UDP payload at 5,000 packets/s; packet/link overhead measured in HW-1 |
| Minimum IMU | `192.168.50.30:46020 -> 192.168.50.10:46020`, authenticated 184-byte envelope | rate follows fresh `/lowstate`; exact Mbit/s measured in HW-3 |

No PointCloud2, full LowState, arbitrary ROS/DDS, route, NAT, Linux bridge,
multicast forwarder, generic proxy or browser-selected endpoint is deployed.
Control Bridge port `46010` and camera transport remain separate and unchanged.

## Exact repository and private files

### Robot-side Jetson

- install fixed relay sources as root-owned, non-writable executables:
  `/usr/local/libexec/robot-scope/xt16_udp_relay.py` and
  `/usr/local/libexec/robot-scope/xt16_wireless_udp_relay.py`;
- update the approved project checkout under
  `/home/unitree/project/robot-scope` for the fixed IMU sender and its runner,
  using the complete-tree staging and rollback procedure in
  `docs/ROBOT_SIDE_WIRELESS_CHECKOUT_STAGING.md`;
- install `robot-scope-xt16-wireless-relay.service` and
  `robot-scope-wireless-imu-sender.service` from their reviewed examples;
- install the fixed forced-command script and the exact
  `robot-scope-wireless-mapping-remote.sudoers` policy;
- add a dedicated SSH public key whose `authorized_keys` entry forces only
  `robot_scope_wireless_mapping_ssh_command.py` with no PTY, forwarding or
  agent forwarding;
- install `/etc/robot-scope/wireless-imu.key`, owned by `unitree`, mode `0600`.

### External Orin

- update the approved project checkout under
  `/home/jetson_orin_nano/project/robot-scope` and build the current
  `robot_scope_xt16_bridge` package plus pinned Hesai/FAST-LIO dependencies;
- keep `config/hesai_xt16_wireless.yaml` repository-owned and install private
  correction state at `/etc/robot-scope/hesai/xt16-correction.dat` and
  `/etc/robot-scope/hesai/xt16-calibration.manifest`;
- install `/etc/robot-scope/wireless-imu.key`, owned by
  `jetson_orin_nano`, mode `0600`;
- install dashboard-owned mode-`0600` SSH identity and known-hosts files, and
  set only their absolute paths in the private Robot Scope environment;
- set `ROBOT_SCOPE_MAPPING_PROFILE=go2-xt16-wireless` only after the wired
  default and rollback copy are recorded;
- the Mapping launcher owns the external IMU receiver, Hesai driver,
  cloud-only bridge and FAST-LIO as local children. The optional receiver unit
  may be installed disabled for isolated HW-3 work but must never be enabled or
  active concurrently with the launcher.

The deployment manifest records the final approved Git commit, every installed
file SHA-256, owner/mode, service enabled/active state, ROS dependency revisions
and the previous file hashes. Credentials, calibration contents, serial number,
maps, Dataset and raw payloads remain outside Git and public diagnostics.

## IMU key creation and handling

Generate one new 32-byte key from the operating system CSPRNG during the
approved deployment. Install the same bytes atomically on both hosts with the
service user's ownership and exact mode `0600`, then remove any staging copy.
The installer rejects symlinks, wrong size, wrong owner or any broader mode.
The key must not be printed, logged, passed as a command argument, placed in an
environment file or reused from Control Bridge. Rollback removes only this
dedicated key after both new IMU processes are stopped; it never removes a
shared control or camera credential.

## PTC and calibration decision

Use the pinned driver's offline JT16 binary-correction path with
`use_ptc_connected: false`. The pinned JT16 parser explicitly does not support
firetime loading, so `firetimes_path` is empty and no firetime artifact is
invented. After the exact deployment approval and before driver start, follow
`docs/HESAI_XT16_CALIBRATION_RUNBOOK.md`. The private manifest must bind the
installed XT16 model/physically cross-checked serial, parser identity,
acquisition method, driver revision
`e7e112f0809f0eed5e3c81c55a1a0376474db234`, SDK revision
`9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168`, fixed correction path, exact
64-byte length and SHA-256. The wireless driver runner validates ownership,
mode, schema and hash before sourcing ROS. Any mismatch blocks HW-2.

No PTC proxy is installed. It remains a separately approved fallback only if
the exact offline artifacts fail with the pinned driver during HW-2.

## Proposed firewall policy

The robot-side firewall owner is confirmed as `iptables v1.8.4 (legacy)` and
the external owner as `iptables v1.8.7 (legacy)`. Both have default
`FORWARD DROP`, Docker-only forwarding/NAT and no management/sensor forwarding
rule. The external installed `nft` tool returned an empty ruleset; robot-side
`nft` is absent. No rule was changed during the audit. The reviewed semantic
policy is:

1. on external `eno1`, allow UDP only from
   `192.168.50.30:46236` to `192.168.50.10:2368`;
2. on external `eno1`, allow UDP only from
   `192.168.50.30:46020` to `192.168.50.10:46020`;
3. reject or drop every other source tuple targeting external UDP 2368 or
   46020, without changing established control/camera management traffic;
4. add no `FORWARD`, NAT, MASQUERADE, bridge, route, multicast or DDS rule on
   either host.

Rules are staged with an automatic rollback window and verified from a second
management session before persistence. If the host firewall framework or
existing policy cannot express the two exact tuples without weakening another
boundary, deployment stops for a new review.

## Enable policy and transactional lifecycle

All three new service units are installed disabled. No unit is enabled at boot
and there is no automatic Mapping/Nav/Mission resume after boot or Wi-Fi
recovery. Robot Scope may start only the two robot-side units through the
restricted forced command after an explicit Mapping start and successful
preflight.

Startup is fixed:

1. robot-side XT16 wireless relay;
2. robot-side minimum IMU sender;
3. external authenticated IMU receiver;
4. external wireless Hesai driver;
5. external cloud-only C++ bridge;
6. external FAST-LIO;
7. Mapping ready only after consecutive freshness gates pass.

Stop and failure cleanup run in reverse order and remove only children or
services started by that transaction. An already-active service is observed
but never claimed. Failure leaves no partial map, does not retry into Mapping,
and never starts Nav2, Mission, ARM, a control lease or a goal.

## Approved deployment sequence after all blockers clear

1. record stationary/DISARMED/no-lease/zero-command state, idle
   Mapping/Nav/Dataset, host identities, current hashes and rollback copies;
2. install private calibration and IMU-key state without starting a service;
3. install code, service units, forced SSH command, sudoers and exact firewall
   rules; validate syntax and ownership; leave every unit disabled/inactive;
4. build the C++ package and rerun repository verification on the final commit;
5. run HW-1 relay only and stop for a result;
6. after HW-1 PASS, run HW-2 Hesai only and stop for a result;
7. after HW-2 PASS, run HW-3 IMU only and stop for a result;
8. after HW-3 PASS, run HW-4 cloud bridge and stop for a result;
9. request `APPROVE_STATIONARY_MAPPING_TEST` before HW-5 FAST-LIO;
10. after HW-5 PASS, run HW-6 for 60 seconds, then 10 minutes, and defer the
    60-minute soak until separately scheduled.

Each hardware stage rechecks E-stop readiness, safety operator presence,
stationary robot, DISARMED, no control lease, deadman released and zero command.
It stops at the first unexpected motion, peer, publisher, stale timestamp,
authentication/clock failure, packet-loss bound failure or process residue.

## Rollback

Robot-side rollback stops only the two new sensor units, disables them if
needed, restores or removes their exact unit/source/forced-command/sudoers
files from the manifest and removes only the dedicated IMU key. It preserves
the control and camera services plus `eth0`/`wlan0` NetworkManager profiles.

External rollback stops only launcher-owned local children and the optional
disabled receiver unit, restores the wired profile/environment and previous
C++/configuration hashes, and removes the two exact firewall additions. It
leaves maps, Dataset, private logs and calibration backups untouched. Neither
rollback resets networking, reboots, deletes shared credentials or changes
Go2/XT16 sensor configuration.

## Blocking items before deployment approval

- repository verification is cleared: Playwright is 30/30 PASS, the Orin
  Release build has zero compiler warnings and the registered cloud contract
  passes 1/1 through both colcon and direct CTest;
- privileged network verification is cleared on both hosts: `FORWARD DROP`,
  Docker-only `172.17.0.0/16` MASQUERADE and no management/sensor forwarding;
- the correction acquisition and checkout staging procedures are now
  repository-defined, but their actual approved execution remains pending:
  acquire the exact 64-byte XT16 correction, cross-check the private serial,
  and install/validate the manifest;
- the `/home/unitree/project/robot-scope` checkout is currently absent; create
  it from the final tested commit using the complete-tree staging procedure;
- update the clean external operating checkout from
  `6dd569ea0367598f9230096f2bac423b7f1b2dc9` to the reviewed deployment commit
  only after approval, preserving its current rollback identity;
- repeat both host addresses, clocks, interface ownership, privileged network
  policy and idle safety state against that final deployed commit;
- supply the exact phrase `APPROVE_WIRELESS_XT16_DEPLOY` only after reviewing
  this plan and the green Gate 7 rerun.

Until every deployment blocker clears, deployment remains unauthorized and all
hardware stages remain `NOT_RUN`; the repository status remains `CODE_READY`.
No relay, LiDAR, IMU, cloud, FAST-LIO or soak hardware PASS is claimed.
