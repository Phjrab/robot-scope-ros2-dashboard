# C4C Signed Observation-Only Deployment Gate

Status: `CODE_READY / NOT_DEPLOYED / NOT_RUN`

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
STATIONARY_OBSERVATION_VALIDATED=PREVIOUS_NORMAL_BRIDGE_ONLY
DYNAMIC_OBSERVATION_VALIDATED=PARTIAL_SOURCE_ONLY
SIGNED_OBSERVATION_ONLY_END_TO_END=NOT_RUN
MOTION_USE_APPROVED=NO
MP030_MOTION=NOT_RUN
HIGHER_PROBES=NOT_RUN
NAV2_GOAL=NOT_RUN
```
