# ADR-001: Dual-Jetson competition workload split

- Status: accepted for the WP00 architecture baseline
- Date: 2026-08-30
- Scope: competition Robot Scope deployment
- Supersedes: no current runtime ADR
- Related: [wireless control transport ADR](ADR_WIRELESS_CONTROL_TRANSPORT.md)

## Context

The competition system has a robot-side Jetson running Ubuntu 20.04 with the
RealSense and direct Go2/sensor network access, and an external Orin Nano
running Ubuntu 22.04/ROS 2 Humble with Robot Scope. They communicate over a
trusted BE5100M management LAN; the external Orin is wired and the moving
robot-side host uses Wi-Fi.

Sending every raw camera, depth and PointCloud stream to the external Orin
couples inference and mapping latency to Wi-Fi airtime, loss and TCP/DDS queue
behavior. Moving the complete application and Mission authority robot-side
would instead combine sensor, inference, web, storage and safety workloads on
one thermally constrained moving host.

The repository already has a third constraint: in the accepted wireless
topology, the Go2 DDS participant and standalone control watchdog are
robot-side, while the external Orin has no Go2/sensor-LAN interface. Camera and
signed control have narrow purpose-built transports; XT16/FAST-LIO does not.

## Decision

### Robot-side Jetson is the sensor-local compute and Go2 bridge host

It owns:

- RealSense device capture, timestamps and on-demand preview;
- Go2-local DDS observation needed by the signed watchdog bridge;
- fixed sensor-specific relays already accepted for the deployment;
- future Lane/YOLO/depth inference only after shadow and resource gates.

It does not own the complete Robot Scope product, authoritative Dataset/model
registry, final Mission/Safety state or an independent motion command path.

### External Orin is the product, validation and coordination host

It owns:

- Robot Scope web/API and browser transports;
- result schema/model/sequence/freshness validation;
- manual/autonomous exclusion, Mission and Safety coordination;
- Dataset, model registry, logs and diagnostics;
- final decision whether any validated perception capability is available.

Navigation remains an external-Orin product authority. FAST-LIO/Nav2 execution
is not declared competition-ready until the chosen bounded sensor-data path is
validated. Product capability metadata alone is not hardware readiness.

### Laptop is an offline development and operator client

It performs labeling, training, evaluation, ONNX export and deployment
preparation. It is not required for server runtime, inference or control-loop
continuity.

### Sensor-local inference is allowed and preferred for evaluation

Inference near the D435i can avoid Wi-Fi and JPEG decode latency. Every model
starts in `SHADOW`, publishes observation only and must pass identity,
TensorRT, freshness, performance, memory, thermal, coexistence and rollback
gates. Training does not run on either competition Jetson.

### Raw PointCloud is not the default operating path

Management-Wi-Fi modes are fixed conceptually to `OFF`, `SUMMARY`,
`DECIMATED_DIAGNOSTIC` and `RAW_DIAGNOSTIC`, with `OFF` as the default and
`SUMMARY` preferred. Diagnostic modes require bounded rate/points/fields,
queue and duration plus same-run evidence that camera, LowState, signed
control and watchdog behavior do not degrade.

### Existing safety authorities are unchanged

AI is an observation producer. The physical stop, Go2 firmware behavior,
robot-side watchdog, exact graph cardinality, external motion lease, deadman,
freshness and Mission/Navigation coordination remain authoritative. No later
work package may weaken them to make perception or network acceptance pass.

## Consequences

### Positive

- sensor input can be interpreted before crossing Wi-Fi;
- the management link can carry small typed results and bounded preview;
- one external product host retains UI, storage and Mission coordination;
- Ubuntu 20.04/Foxy and Ubuntu 22.04/Humble differences remain behind explicit
  process and result contracts;
- loss of inference cannot silently become loss of the control watchdog.

### Costs and risks

- two hosts require compatible schema/model manifests and clock/sequence
  handling;
- robot-side resource and thermal headroom must be measured;
- deployment and rollback become multi-host operations;
- external mapping is currently blocked without a sensor-data design;
- management Wi-Fi requires field capacity and fault testing.

## Rejected alternatives

### Continuous raw RGB/depth/cloud processing only on the external Orin

This is useful for bounded replay or diagnostics but is rejected as the default
because it makes sensor latency and compute availability depend on Wi-Fi.

### Complete Robot Scope and Mission duplication robot-side

Rejected because it duplicates authority, increases the moving host's failure
surface and competes with sensor/control workloads.

### Generic route, NAT, Linux bridge or DDS router

Rejected as an implicit solution. It widens the network boundary, exposes
unrelated traffic and bypasses the purpose-specific allowlists already used by
camera and signed control.

### Laptop-hosted live inference or motion coordination

Rejected because laptop, browser and Internet availability must not become
competition runtime dependencies.

## Follow-up gates

- WP01: replace eligible reference addresses with strict role-based deployment
  contracts without adding arbitrary relay destinations.
- WP02: expose and record link, camera and receiver health plus bandwidth.
- WP03: add robot-side perception shadow runtime with zero command ownership.
- WP04: validate typed results and stale/model contracts on the external Orin.
- Later mapping work: choose and accept a bounded XT16/FAST-LIO placement; it is
  not implied by this ADR.
- WP07: run fault and field acceptance before any active perception use.
