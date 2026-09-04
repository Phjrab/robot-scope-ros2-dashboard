# Dedicated Appliance Boot Autostart — 2026-09-04

## Scope and decision

This change makes the already-established wireless Robot Scope topology eligible
for deliberate appliance-style boot startup. It does not change the default
installer policy: ordinary and development installations remain disabled and
manual-start. The dedicated allowlist contains exactly these units:

| Host | Unit | Boot responsibility |
| --- | --- | --- |
| External Orin `192.168.50.10` | `robot-scope.service` | Dashboard and fail-closed observers |
| Robot Jetson `192.168.50.30` | `robot-scope-control-bridge.service` | Signed Stop-first control bridge |
| Robot Jetson `192.168.50.30` | `robot-scope-xt16-wireless-relay.service` | Fixed XT16 sensor payload relay |

No camera, IMU/odometry, FAST-LIO, Mapping, Navigation, localization, Mission or
Dataset Capture unit was added to the boot allowlist. The external legacy local
Control Bridge is explicitly outside the policy because the robot-side signed
Bridge is the sole authority for this topology.

## Pre-change live baseline

The read-only baseline was captured at `2026-09-04T08:22:31Z` while the robot was
stationary. Both active release symlinks resolved to commit `0921b4f`.

- External dashboard: active, MainPID `918112`, restart count `0`, boot state
  `disabled`.
- Robot Control Bridge: active, MainPID `3398`, restart count `0`, boot state
  `disabled`.
- Robot XT16 relay: active, MainPID `3769`, restart count `0`, boot state
  `disabled`.
- Control remained DISARMED: no lease, deadman released, command exactly
  `(0.0, 0.0, 0.0)`, authenticated Bridge ready, fresh LowState, and expected
  publisher cardinality `1 / 0 / 10 / 11`.
- Bridge-owned request evidence was Stop-only: `stop=4922`, `Move=0`,
  `nonzero Move=0`, malformed Move `0`, action `0`.
- Navigation and localization sessions were idle and no goal was active.
- XT16 accepted/forwarded counters advanced continuously. The accumulated
  `send_errors=20` value stayed unchanged over the sampled reports.

Starting, enabling or testing this policy does not authorize ARM, deadman,
lease acquisition, initial pose, goal publication, nonzero command or motion.

## Boot readiness implementation

The two hosts now have separate, fixed readiness examples. Both are passive
Linux socket/ioctl probes. They cannot invoke a shell, NetworkManager, `ip` or
`systemctl`, and cannot add an address, change a route or alter link state.

- External gate: require `eno1` UP/RUNNING with `192.168.50.10/24`.
- Robot gate: require both `eth0` UP/RUNNING with `192.168.123.18/24` and
  `wlan0` UP/RUNNING with `192.168.50.30/24`.
- Each activation attempt is bounded to 60 seconds.
- The opt-in drop-ins directly order after
  `NetworkManager-wait-online.service`; that service can remain globally
  disabled.
- Existing `Restart=on-failure`, restart delay and start-limit values are not
  removed or relaxed.

The external release drop-in also replaces the stale absolute
`releases/robot-scope/1164553` service path with the reviewed stable
`/home/jetson_orin_nano/robot-scope` symlink. Release selection and appliance
readiness remain separate drop-ins.

## Robot-only reboot preview recovery

An external dashboard that remains running used to leave the XT16 preview in a
terminal failed state after only the robot Jetson rebooted. The dedicated
dashboard appliance drop-in now supplies the exact opt-in
`ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER=1`. Absence of the variable and every
other value keep recovery disabled; wired and direct profiles ignore it.

Only one observation-preview monitor may run. It checks after bounded
`5 → 10 → 20 → 30` second delays and retries the existing fixed preview launcher
only when all of the following are safely idle:

- lifecycle transition;
- Navigation/localization;
- control lease;
- Dataset Capture;
- Mapping coordinator task and map operation;
- Mapping pipeline (`idle`, `stopped` or terminal `failed`).

A failed Mapping pipeline remains failed. Recovery starts no Mapping, IMU,
FAST-LIO, Nav2, Mission, Dataset, Control, lease, ARM, deadman, goal or motion
path. If the relay already exists because systemd started it, preview cleanup
does not claim or stop that pre-existing service.

Shutdown uses cooperative cancellation and explicitly settles an in-flight
threaded preview start before manager/process cleanup. Tests cover ordinary
shutdown, external monitor cancellation and cancellation of `close()` itself.

## Repository verification

The final hardware-free repository verification produced these results:

- `python3 -m unittest discover -s tests -v`: **1044/1044 PASS**;
- `npm test`: **270/270 PASS**;
- `node scripts/check_frontend_syntax.mjs`: **53 modules PASS**;
- Ruff on `robot_dashboard`, `scripts`, and every changed/new test: **PASS**;
- configured Mypy target set: **PASS (4 source files)**;
- tracked-source credential scan and `git diff --check`: **PASS**;
- both fixed readiness helpers: **PASS** when run read-only with the system
  Python on their intended live hosts (`eno1=192.168.50.10/24` externally;
  `eth0=192.168.123.18/24` and `wlan0=192.168.50.30/24` robot-side).

An additional repository-wide Ruff invocation including every historical test
still reports 11 pre-existing diagnostics in unchanged test files. The normal
source/script lint target and every test touched by this change are clean; no
unrelated lint cleanup was included.

## Deployment and acceptance state

The repository implementation and root-owned installation examples are ready.
Permanent host policy still requires an administrator to install the reviewed
helpers/drop-ins and enable the exact three units using the commands in
[INSTALL.md](INSTALL.md#전용-appliance-부팅-자동-시작-opt-in). No `--now` command
is used, so applying boot policy does not change the currently running robot.

Until those administrator steps and one separately approved cold reboot are
complete, the result must be recorded as `IMPLEMENTED / NOT YET COLD-BOOT
ACCEPTED`. Acceptance requires:

1. this change newly enables and activates exactly its three allowlisted
   units; independently approved pre-existing enablement, such as camera
   units, is recorded and preserved rather than disabled;
2. both readiness gates pass with one MainPID per unit and stable restart
   counts;
3. the signed Bridge returns fresh/ready while control remains no-lease,
   deadman-released and exact-zero;
4. request evidence remains Move/action/nonzero-free;
5. the XT16 relay and external PointCloud sequence advance, and the actual
   dashboard MainPID (not only merged unit configuration) has the exact
   preview-recovery opt-in without exposing the rest of its environment;
6. Mapping, Navigation, localization, Mission, Dataset and goal remain idle;
7. a robot-only reboot produces `LIVE → WAITING → LIVE` without restarting the
   external dashboard or creating duplicate relay/Hesai/cloud processes.

The exact rollback and evidence procedure is in
[UPDATE_ROLLBACK.md](UPDATE_ROLLBACK.md#전용-appliance-enable-상태와-cold-boot-검증).
