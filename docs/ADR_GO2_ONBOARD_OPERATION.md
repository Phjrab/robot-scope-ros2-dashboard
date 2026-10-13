# ADR: Go2 onboard single-host operation

- Status: accepted implementation direction; live migration acceptance pending
- Date: 2026-10-13
- Scope: explicit `go2-onboard` profile on the Go2-mounted Orin NX 16GB
- Related: [migration contract and evidence](GO2_ONBOARD_MIGRATION.md)

## Context

The operator requests Ubuntu 22.04/ROS 2 Humble operation on the internal
Jetson, with no external Jetson runtime dependency. The Ubuntu upgrade is
operator-reported until inspected. Ubuntu version alone establishes neither
JetPack/L4T compatibility nor working CUDA, TensorRT, kernel or camera drivers.

[ADR-001](ADR-001_DUAL_JETSON_WORKLOAD_SPLIT.md) remains the decision for the
historical dual-host competition deployment. Its prohibition on colocating
the complete product does not apply to this explicitly selected profile.
Existing wired/wireless configurations and evidence retain their original
host and date. This decision replaces the split only for onboard operation;
it creates one product and motion coordinator rather than duplicating them.

## Decision

The internal Jetson owns web/API/WebSocket, ROS observation, direct XT16
decode and C++ conversion, FAST-LIO and configured Nav2 workers, the independent
signed ROS control bridge/watchdog, camera processing and durable data.
PCs/tablets supply browsers and maintenance; the external Jetson is a preserved
rollback source and has no required live HTTP, SSH, UDP, ROS or file role.

`go2-onboard` must select the same topology in launcher, profile, mapping and
navigation factories, installer, doctor, systemd lifecycle and acceptance.
The implementation reuses the Humble direct-sensor and local lifecycle paths.
Go2 DDS and camera multicast remain on the actual sensor NIC. The browser
uses the management address. Colocation does not convert robot traffic to
loopback or widen existing network allowlists.

XT16 uses the actual original packet destination and the sensor-associated
private correction/manifest pair. The full C++ bridge produces `/imu/body`
from `/lowstate`; cloud fields/ring/time/frame and installed extrinsics retain
their contract. Wireless XT16/IMU/odometry and Go2 camera relays are unnecessary
for this profile and must not create duplicate owners. Direct controller
odometry still requires a valid original source clock. The existing validated
FAST-LIO controller-odometry projection can serve this profile without
replacing timestamps or relaxing readiness.

Control uses `ROBOT_SCOPE_CONTROL_TRANSPORT=ros` and local lifecycle, with one
independent watchdog process. Signature/session/sequence/expiry, ARM, deadman,
manual/autonomous exclusion and graph cardinality remain unchanged. Named
bridge publishers, foreign named publishers and manufacturer bare DDS
endpoints remain distinct. A new service starts DISARMED with no lease, goal
or replayed command. Transition first retires the old Robot Scope authority
after verifying idle/zero state, then starts the new authority.

RealSense retains one device owner selected by stable RGB by-id identity.
Same-host HTTP consumption has an explicit local contract; the historical
distinct-host relay contract remains strict. Camera profile changes use a
fixed local helper rather than self-SSH. Existing inference is included only
when a currently used artifact is found; absent approved models do not block
the migration. Any found TensorRT engine retains target identity checks and
must be rebuilt from its source model when incompatible.

## Data and recovery

Build Python/ROS environments on the target from pinned sources; preserve
manufacturer workspaces. Persistent maps, annotations/family revisions,
settings, authored routes, needed datasets/events and any used model/calibration
are inventoried and copied into new directories with SHA-256 verification.
Environment files/keys are handled privately. Live lease/ARM/command state,
temporary jobs and previous ROS builds are not restored. Browser localStorage
belongs to its original origin and requires a separate operator backup if used.

The old external code/data/configuration and prior unit copies stay available.
Rollback stops only the new Robot Scope owners and restores the recorded
configuration/unit/release set; it neither deletes new maps nor changes
manufacturer services. OS/BSP reflash, broad kernel/NVIDIA replacement and
management-network changes without a recovery route are outside this decision.

## Acceptance and limits

Software PASS is separate from hardware PASS. The internal server, live required
sensors, durable data, local mapping/navigation/control ownership, restart
recovery and resource headroom must be measured with the external Jetson off
or disconnected. Default compound stationary observation is 30 minutes, with
CPU/GPU/RAM/swap/temperature and frame/message latency recorded. No watchdog,
freshness or publisher gate is relaxed to achieve acceptance. Supervised motion
is a separate NOT_RUN item until the operator is ready. New Nav2 goal success,
competition completion and new model accuracy are not additional migration
completion conditions.
