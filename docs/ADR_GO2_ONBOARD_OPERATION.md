# ADR: Go2 onboard single-host operation

- Status: accepted and deployed; pre-UI stationary and post-UI functional acceptance PASS, recorded separately
- Date: 2026-10-13
- Scope: explicit `go2-onboard` profile on the Go2-mounted Orin NX 16GB
- Related: [migration contract and evidence](GO2_ONBOARD_MIGRATION.md)

## Context

The operator requests Ubuntu 22.04/ROS 2 Humble operation on the internal
Jetson, with no external Jetson runtime dependency. Authenticated target
inspection confirms Ubuntu 22.04.5/aarch64, kernel 5.15.199-tegra and L4T
36.5.2. Required NumPy 1.26.4, system OpenCV 4.5.4, `rclpy` and Unitree message
imports and pinned Humble builds passed. Installed TensorRT packages report
10.7; this is package inventory, not an engine/API import acceptance claim.
These facts were measured independently of Ubuntu. No used model engine was
found, and TensorRT engine compatibility was not established.

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

XT16 uses the inspected direct packet destination and the sensor-associated
private correction/manifest pair. The observed stale destination
`192.168.123.99` was changed only to the internal sensor NIC
`192.168.123.18`, with original configuration preserved for guarded rollback.
PTC remains off and the original correction/manifest identity remains private.
A bounded receive-buffer adjustment restored the required UDP receive path.
The onboard Hesai participant uses `AllowMulticast=spdp`: participant discovery
stays on the sensor NIC, while large raw cloud data uses unicast. This fixed an
observed freshness failure when an additional raw cloud reader joined; the
identical reader regression subsequently kept all four cloud/odometry streams
at about 10 Hz with zero bridge rejections. Other participants retain their
multicast configuration, and no safety or timestamp limit was relaxed.
The full C++ bridge produces `/imu/body`
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

Physical target preservation and normal-loader/API checks passed for 15 maps,
13 families, 6 annotation sidecars, settings/routes, one navigation preset and
12 completed Dataset sessions with 1225 samples. New filesystem identities
required explicit target family/annotation derivatives. A historical rounded-pi
annotation and obsolete schematic timing cache retain their source failure and
original byte evidence; current strict constructors validate the target
derivatives. Authored map/order/layout geometry and historical Dataset paths
remain preserved. Live guidance, capture, missions and control authority were
not resumed from imported data.

The old external code/data/configuration and prior unit copies stay available.
Rollback stops only the new Robot Scope owners and restores the recorded
configuration/unit/release set; it neither deletes new maps nor changes
manufacturer services. OS/BSP reflash, broad kernel/NVIDIA replacement and
management-network changes without a recovery route are outside this decision.

## Acceptance and limits

Software PASS is separate from hardware PASS. The internal server, live required
sensors, durable data, local mapping/navigation/control ownership, restart
recovery and resource headroom must be measured with the external Jetson off
or disconnected. The operator changed stationary observation to 10 minutes
(600 seconds) on 2026-10-13, with CPU/GPU/RAM/swap/temperature and frame/message
receipt ages recorded. Candidate `093600f` passed the corrected 600.016-second
window at 03:49:53–03:59:53 UTC with 58 resource samples: CPU maximum 54.76%,
sampled GPU maximum 0%, temperature maximum 69.531°C, minimum available RAM
12.55 GiB, zero swap/OOM/service restarts and no freshness failures. Cloud and
odometry stayed about 10 Hz; maximum cloud/odometry/TF receipt ages were
40.2/27.7/27.3 ms. Both cameras delivered continuously at 12.010/12.251 fps.
These are delivery/receipt measurements, not physical source-to-display
latency. The first failed run remains preserved separately. This establishes
the required pre-UI stationary internal-only acceptance, not longer-duration
thermal stability or experimental VSLAM coexistence capacity.
No watchdog, freshness or publisher gate is relaxed to achieve acceptance. Supervised motion
is a separate NOT_RUN item until the operator is ready. New Nav2 goal success,
competition completion and new model accuracy are not additional migration
completion conditions.

The operator explicitly authorized an authenticated external-host shutdown.
The SSH session closed and subsequent SSH/ping received no reply. This records
the executed shutdown and network absence; physical power was not independently
observed. Internal Go2 camera frames measured 1280x720 at about 13 fps,
RealSense frames measured 640x480 at 15 fps, and FAST-LIO published at about
10 Hz. Local Nav2 localization-only workers reached process readiness and
`waiting_initial_pose`, which is expected before a measured initial pose.
No physical map position or goal arrival is asserted. Signed bridge status
recorded one own named publisher, zero foreign named publishers, ten
manufacturer bare endpoints, zero motion/action and no lease.

Dashboard restart and actual browser reconnection recovered fresh data while
the independent bridge PID remained unchanged. Stopping/restoring the three
Robot Scope units and a stopped-state environment backup also passed; the
manufacturer `enable-typec-host` process/invocation remained unchanged.
This is application stop/configuration recovery evidence. A complete rollback
to the former external deployment, a migration-owned controlled reboot and
physical Wi-Fi interruption remain NOT_RUN. Those interruptions lack an independent recovery
route while the current management connection remains the sole connection.

Initial migration evidence belongs to pre-UI candidate `3ec4cc6`; the Hesai
fanout correction and repeated acceptance use `093600f`.
The operator separately authorized UI integration: historical UI
branch merge `5f4d211` and external deployed release `544e108` are distinct
provenance points. The migration phase made no frontend changes before the
separately authorized UI handoff. Only `95d13e2` was integrated as `c9c15f0`,
with two narrow observation-label/Inspector recovery fixes in `92ff609`.
Backend/API/ROS/control/deployment contracts were unchanged. Integrated source
checks and a distinct 30-second post-UI functional camera/API/browser check
passed; the runbook records exact counts and follow-up coverage. Pre-UI
performance evidence was not relabelled as a post-UI thermal test.

The operator confirmed a different chat rebooted the host at 04:15 UTC, after
pre-UI acceptance. Before the UI deployment, enabled Robot Scope services had
automatically recovered safely on `093600f`; the later dashboard-only restart
preserved the bridge/camera/manufacturer service PIDs and invocations.
This is observed external-reboot recovery, separate from a controlled reboot
test by the migration task.

After acceptance, normal lifecycle APIs stopped test mapping/localization;
preview, both cameras and the independent bridge remain active with no lease
or motion authority. A separate Isaac ROS VSLAM lab has no operational TF,
service or control role. D435i remains owned by the operational RGB service;
the lab must use bags until an explicit camera time window or safe sharing
contract is arranged. Experimental domain/frames remain separate, and later
integration requires review of measurements, ownership, resources and frames.
The runbook records the acceptance interval, current device owner and limits
of retrospective experimental-load evidence.

After acceptance, the operator explicitly released the D435i to the lab.
The operational RealSense unit was stopped at 04:51:30 UTC, with MainPID=0
and no readable video/hidraw device handles. Do not restart it until camera
handback; boot enablement is retained and any reboot requires ownership
coordination. This planned experiment window is separate from the successful
two-camera migration acceptance.
