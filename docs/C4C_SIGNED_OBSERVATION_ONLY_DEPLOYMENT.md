# C4C Signed Observation-Only Deployment Gate

Status: `STATIONARY_SIGNED_PATH_PASS / DYNAMIC_NOT_RUN / MOTION_NOT_APPROVED`

This document defines the deployment gate for the C4C signed dynamic
observation comparison. It is not approval for MP-030, a navigation goal, a
lease, ARM, deadman, or any non-zero command.

## Implemented boundary

The existing Go2 Bridge executable now has an explicit `--observation-only`
role guarded by `ROBOT_SCOPE_C4C_OBSERVATION_ONLY=1`. In that role it:

- subscribes only to the allowlisted LowState and SportModeState sources;
- creates the existing signed status sender;
- creates no command receiver;
- creates no `/api/sport/request` publisher;
- never calls the command core tick or shutdown StopMove publisher;
- reports `bridge_role=motion_observer`, `ready=false`, exact-zero accepted
  command and zero request evidence.

The dashboard accepts this role only when the same local opt-in is set. It
authenticates and validates the signed evidence but always keeps control
unavailable. Observation status never participates in UDP command handoff.
Normal Bridge status without the role field retains the existing control
contract for rolling compatibility.

The dedicated example service has no installation section and therefore
cannot be enabled at boot. Its runner and the normal Bridge use the same
process lock, so they cannot run concurrently.

## Pre-deployment state and identity checks

Before any change, record separately on both hosts:

- repository and active release full SHA;
- process cwd and loaded-file fingerprints;
- dashboard and normal Bridge service state;
- Mapping, Localization, Navigation and Mission state;
- lease, ARM, deadman, manager command and accepted command;
- active `/api/sport/request` publisher classification;
- strict odometry sender/receiver state.

The release must be a clean immutable directory for the focused commit. A Git
push is not deployment approval.

## Proposed deployment sequence

This sequence requires a fresh operator approval before execution.

1. Stage the same exact release on external Jetson `192.168.50.10` and robot
   Jetson `192.168.50.30`; do not update either dirty development checkout.
2. Install the manual observer runner and unit only on the robot Jetson. Do
   not enable the unit.
3. Add `ROBOT_SCOPE_C4C_OBSERVATION_ONLY=1` to the external dashboard's
   runtime environment and restart only the dashboard so the strict receiver
   accepts the diagnostic role.
4. Confirm normal Bridge exact-zero cleanup, no lease, no deadman and physical
   stop, then stop the normal Bridge.
5. Start the manual observation-only unit. Shared locking must reject startup
   if the normal Bridge still owns the process lock.
6. Verify the observer owns zero Sport request publishers, advertises no
   command endpoint, retains zero request counters and exposes a progressing
   signed motion observation at the dashboard.
7. Run the fixed 300-second stationary checker. Do not proceed after any
   generation, source, stamp, freshness, cardinality, drift or request-evidence
   failure.
8. Only after a separate supervised approval, run the fixed 20-second dynamic
   checker while the operator moves the stock controller exactly once within
   the approved range.

The checker only reads `http://127.0.0.1:8088/api/v1/control`. It creates no ROS
endpoint and no motion command. Evidence is written mode `0600` below the
operator's fixed `~/.robot-scope/c4c-observations` directory.

## Resource and graph expectation

The observer adds two best-effort DDS subscriptions and one signed UDP status
producer. It adds no restricted command-topic endpoint. Expected incremental
load is one Python ROS process, two bounded latest-sample subscriptions and a
4 Hz signed status envelope. CPU, RAM and network values remain `UNKNOWN`
until the stationary deployment run measures them.

## Rollback

1. Stop only the observation-only unit started by this work.
2. Confirm no observer process, UDP owner or DDS subscription remains.
3. Remove the external opt-in and restore the previous immutable dashboard
   release, restarting only the dashboard.
4. Restore the previous immutable robot release.
5. Start the normal Bridge only when operationally required, then reverify its
   exact-zero status, one-owner graph, signed epoch and no lease.

Rollback does not change clocks, firmware, strict odometry guards, maps or
Navigation state.

## Gate state

```text
SOFTWARE_VALIDATED=PASS
STATIONARY_OBSERVATION_VALIDATED=PASS_SIGNED_OBSERVER
DYNAMIC_OBSERVATION_VALIDATED=PARTIAL_SOURCE_ONLY
SIGNED_OBSERVATION_ONLY_END_TO_END=PASS_STATIONARY
MOTION_USE_APPROVED=NO
MP030_MOTION=NOT_RUN
HIGHER_PROBES=NOT_RUN
NAV2_GOAL=NOT_RUN
```

## 2026-09-05 stationary deployment result

The operator approved the exact observer deployment and a five-minute
stationary run with the robot stopped and the physical remote/E-stop ready.
No motion approval was granted or inferred.

The exact commit
`a09264c1d36bad1993a33f685b5348b20239d3c7` was exported as a Git archive
with SHA-256
`ae5d8cd51fac33c6f6ab0207e56d7c64dabe3de6df60e48cc08e6ae86896885f`.
Both hosts independently verified the archive before extracting it into:

- external Jetson:
  `/home/jetson_orin_nano/releases/robot-scope/a09264c1d36bad1993a33f685b5348b20239d3c7`;
- robot Jetson:
  `/home/unitree/releases/robot-scope/a09264c1d36bad1993a33f685b5348b20239d3c7`.

The selected Bridge, receiver and checker file hashes matched the repository
on both hosts. The pre-transition release was
`a8b88b80a66d5173914c4a3b21754f1155b222e1`, preserved by the two
`robot-scope.pre-a09264c` links. The external private environment was preserved
as `control.env.pre-a09264c` before adding the explicit observation opt-in.
Neither development checkout was pulled, reset, cleaned or modified.

The external dashboard was switched first. It accepted the previous normal
Bridge through the documented absent-role compatibility path while lease,
deadman, dashboard command and accepted command remained exact zero. The
normal Bridge was then stopped and reached `inactive/dead` before the robot
release pointer was switched. The reviewed observer runner was launched
directly as user `unitree` from the exact release; the example system unit was
not installed or enabled. The process used the existing lock and UDP status
configuration, reported release `a09264c1d36bad1993a33f685b5348b20239d3c7`,
and exposed no command endpoint or Sport request publisher.

The initial and final signed dashboard snapshots both reported:

- control unavailable, no lease, deadman false and exact-zero manager and
  accepted commands;
- authenticated role `motion_observer`, observation connected, but Bridge
  `ready/connected/available=false`;
- zero Robot Scope and foreign named Sport publishers with exactly ten trusted
  bare Unitree publishers;
- request evidence `published/move/nonzero/action=0`;
- source `unitree_go.sport_mode_state.position`, one fixed producer generation,
  quality `READY` and no origin reset.

The fixed checker completed in `300.053049` seconds with `2,764` samples and
`1,075` progressing dashboard observations. Source sequence advanced from
`12,234` to `97,290`. Maximum planar displacement from the first sample was
`0.000970 m`, below the unchanged `0.005 m` stationary limit. Maximum callback
receive age was `15 ms` and maximum dashboard receiver-status age was `301 ms`.
The checker recorded `motion_command_created=false`.

Private evidence remains on the external host at
`/home/jetson_orin_nano/.robot-scope/c4c-observations/c4c-signed-stationary-20260905T052807.201057Z.json`
with SHA-256
`b15af9098d5cb36d0c6fcc8dfc7645b31c90681e00713d1f185afa0bd65674c8`.
It contains no command or secret material.

Resource snapshots were observational, not isolated benchmarks. External
dashboard RSS changed from `88,544 KiB` to `89,320 KiB`; robot observer RSS
changed from `60,748 KiB` to `63,180 KiB`. During the bracket the external
interface received `1,104,052,861` bytes and transmitted `6,192,244` bytes;
the robot wireless interface received `699,037` bytes and transmitted
`1,050,205,760` bytes. The already-running XT16 relay dominated this traffic,
so it must not be attributed to the signed observer.

After the PASS, the manually started observer was stopped and no observer or
normal Bridge process remained. The normal Bridge service remains
`inactive/enabled`; both release pointers remain on `a09264c...`; the external
dashboard remains active with the explicit opt-in and fails closed on stale
Bridge status. Navigation, localization and goals remain idle. The robot
systemd manager reports `NeedDaemonReload=yes`; no passwordless daemon-reload
authority was available, so that administrative maintenance remains explicit
and does not change the completed manual-process evidence.

This result qualifies only stationary signed delivery. It does not establish
dynamic accuracy, approve this source for motion, resolve the earlier 59-Move
non-motion cause, or authorize MP-030. A signed dynamic stock-controller
comparison still requires a new supervised approval and must stop after that
comparison without sending a Robot Scope motion command.
