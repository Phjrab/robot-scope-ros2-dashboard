# Wireless Navigation observation transport deployment plan

## Status and authorization boundary

Repository implementation is ready for review. This plan does not authorize
installation, firewall replacement, key creation, service start/restart,
Navigation launch, initial pose, goal or motion. The operator must explicitly
approve deployment after reviewing the exact files and rollback below.

The operator approved installation plus WNO-1/WNO-2 on 2026-09-01. The fixed
transport was installed and WNO-1 passed. WNO-2 failed closed because the
original controller-odometry stamp was more than 220 seconds behind robot
realtime, beyond the unchanged 500 ms source-age bound. See the hardware
validation record for the measured evidence and final safe state. WNO-3 and
WNO-4 remain unauthorized.

The fail-closed sender source-clock guard and its guard-only deployment token
are specified separately in
`docs/CONTROLLER_ODOMETRY_CLOCK_RECOVERY_PLAN.md`. The earlier odometry token
does not authorize that follow-up replacement or any clock mutation.

Fixed topology:

| Role | Address | Responsibility |
|---|---|---|
| robot-side Jetson | `wlan0=192.168.50.30/24` | fixed odometry sender; direct Go2 DDS remains on `eth0=192.168.123.18/24` |
| external Orin | `eno1=192.168.50.10/24` | authenticated receiver, Robot Scope and Nav2 |
| Go2 body | `192.168.123.161` | unchanged; never replaced by a management address |
| transport | `.50.30:46030 -> .50.10:46030/udp` | connected fixed peers, 784-byte HMAC envelope, maximum 100 Hz |

The deployment uses a new random 32-byte key on both hosts at
`/etc/robot-scope/wireless-odom.key`, owner matching the service user, mode
`0600`. It must differ from the Control Bridge and wireless IMU keys. The key
value, hash and path contents must never enter Git, logs, diagnostics or an
acceptance report.

## Exact repository files

Robot-side installation set:

- `scripts/wireless_odom_protocol.py`
- `scripts/wireless_odom_sender_foxy.py`
- `scripts/run_wireless_odom_sender_foxy.sh`
- `scripts/robot_scope_wireless_mapping_ssh_command.py`
- `deploy/robot-scope-wireless-odom-sender.service.example`
- `deploy/robot-scope-wireless-mapping-remote.sudoers.example`

External installation set:

- `scripts/wireless_odom_protocol.py`
- `scripts/wireless_odom_receiver_humble.py`
- `scripts/run_wireless_odom_receiver_humble.sh`
- `scripts/check_wireless_odom_ready.py`
- `scripts/wireless_mapping_remote_lifecycle.py`
- `scripts/run_go2_navigation_humble.sh`
- `scripts/wireless_xt16_firewall.py`
- `deploy/robot-scope-wireless-odom-receiver.service.example`
- `deploy/robot-scope-wireless-firewall.service.example`

The receiver unit is supplied for bounded manual diagnostics but remains
disabled; the Navigation launcher normally owns the receiver child. The sender
also remains disabled and is started only through the restricted lifecycle.

## Transactional installation

1. Confirm both hosts are on the expected commit, clocks synchronized, robot
   stationary/DISARMED, no lease/deadman and all Mapping/Nav units inactive.
2. Stage every replacement as a root-owned temporary file on the same
   filesystem; validate Python, shell, systemd and sudoers syntax before rename.
3. Record mode, owner and SHA-256 for every previous installed file. Preserve
   backups with the pre-deployment commit suffix.
4. Generate one new odometry key without printing it. Install the same bytes as
   `unitree:unitree 0600` robot-side and `jetson_orin_nano:jetson_orin_nano 0600`
   externally. Verify only length, owner and mode.
5. Install the robot-side sender unit and updated forced command/sudoers policy;
   run `visudo -cf`; daemon-reload; verify the unit is `disabled` and `inactive`.
6. Install the external scripts/unit and updated firewall implementation;
   validate the currently installed firewall chain before replacement.
7. Replace the firewall unit transactionally, daemon-reload and restart only
   this oneshot boundary. Its exact inventory must contain the previous XT16
   and IMU rules plus the new 46030 allow/drop pair and one INPUT jump.
8. Do not start Robot Scope Navigation until the following gates pass.

No network address, route, gateway, forwarding sysctl, XT16 setting, Go2
setting, map, Dataset or control configuration changes in this deployment.

## Stationary hardware gates

### WNO-1 — source-only observation

- Robot stationary, Control Bridge stopped or DISARMED with no lease.
- Start only the robot-side odometry sender through the restricted command.
- PASS: unit active, one source publisher, synchronized clock, sent sequence
  advances, output rate does not exceed 100 Hz.
- Stop and confirm inactive. No external receiver and no robot motion.

### WNO-2 — authenticated receiver

- Start sender and one receiver manually without Nav2.
- PASS: exact UDP peer/port, 784-byte packets, five-sample readiness, exactly one
  external `/utlidar/robot_odom` publisher, `odom -> base_link`, original stamp
  freshness and strict advancement, finite values, bounded packet rate.
- Stop receiver then sender; confirm no process or UDP listener residue.

### WNO-3 — fail-closed transport

- With no Nav2/lease/goal, stop the sender and observe external topic staleness.
- PASS: no timestamp rebasing, no cached current sample, readiness lost within
  the fixed bound; restart requires five fresh samples and creates no authority.
- HMAC mismatch/replay injection uses only an offline socket fixture unless a
  separately supervised fault procedure is approved.

### WNO-4 — wireless Nav launcher, no goal

- Fresh NAV safety confirmation, fixed saved map/revision and `go2-safe`
  parameters; physical E-stop/remote and operator present.
- Start Control Bridge only to authenticated DISARMED/zero readiness.
- Start Navigation. PASS requires mapping readiness, WNO receiver readiness,
  fixed Nav2 children, fresh `/scan`, FAST-LIO `/Odometry` and independent
  `/utlidar/robot_odom`, with no lease, initial pose, goal or velocity command.
- Stop from the dashboard. Confirm launcher-owned receiver and sender are gone,
  Mapping is stopped only when Navigation owned it, and Control remains zero.

WNO-4 success does not authorize initial pose or a goal. Those remain later
supervised gates.

## Rollback

1. Stop Navigation through the dashboard and wait for exact job settlement.
2. Stop the fixed sender if still active. Confirm receiver, Nav2 and Mapping
   process groups and UDP 46030 listeners are absent.
3. Restore the previous external firewall implementation and service unit from
   recorded backups, daemon-reload and restart the oneshot firewall. Verify its
   exact pre-deployment inventory.
4. Restore the previous robot-side forced command and sudoers file; validate
   with `visudo -cf`; restore prior scripts/units or remove only newly added
   files when no predecessor existed.
5. Remove both private odometry key files only after all corresponding services
   are inactive. Do not touch Control Bridge or IMU keys.
6. Confirm both odometry units are absent or disabled/inactive, Control Bridge
   behavior is unchanged and no network profile or map changed.

Rollback never deletes runtime maps, PCD, datasets, ROS workspaces or unrelated
user files.

## Deployment approval token

After reviewing this exact plan, authorize installation and WNO-1/WNO-2 only
with:

```text
APPROVE_WIRELESS_ODOM_DEPLOY
```

WNO-3 and WNO-4 require their own fresh supervised confirmations.
