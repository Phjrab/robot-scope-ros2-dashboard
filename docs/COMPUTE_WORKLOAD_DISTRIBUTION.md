# Competition compute workload distribution

## Decision summary

The robot-side Jetson performs work that must stay close to the sensors and
Go2 DDS. The external Orin validates, coordinates, presents and stores results.
The laptop labels and trains offline. This split reduces Wi-Fi load without
creating a second Mission or motion owner.

See [COMPETITION_SYSTEM_ARCHITECTURE.md](COMPETITION_SYSTEM_ARCHITECTURE.md)
for physical flow and
[ADR-001_DUAL_JETSON_WORKLOAD_SPLIT.md](ADR-001_DUAL_JETSON_WORKLOAD_SPLIT.md)
for the accepted decision.

## Workload ownership

### Robot-side Jetson — required

- own exactly one D435i color device and source timestamp/sequence;
- run the bounded, on-demand RealSense preview producer;
- observe Go2-local DDS on the dedicated interface;
- run the standalone signed control watchdog bridge;
- run only fixed sensor-specific relays that have an explicit packet/client
  allowlist.

### Robot-side Jetson — gated candidates

- one latest-frame hub shared by preview and inference;
- Lane, YOLO and depth/obstacle summary in `SHADOW` mode;
- bounded health and typed perception-result publication;
- decimated PointCloud only for a supervised diagnostic purpose.

These candidates must not be installed into the system Python or activated as
a side effect of documentation work. Target-specific TensorRT engines are
built and verified on the target Jetson after an ONNX/model package is
approved.

### Robot-side Jetson — prohibited ownership

- model training;
- the complete Robot Scope application;
- Dataset or model-registry authority;
- Mission/Navigation state authority;
- direct browser or AI ownership of the Go2 command path;
- arbitrary shell, URL, topic, service or forwarding input;
- permanent raw cloud streaming without a reviewed diagnostic gate.

### External Orin — required

- one-worker Robot Scope web/API and ROS application container;
- perception schema/model/sequence/freshness validation;
- Cockpit, operator events and bounded diagnostics;
- manual/autonomous exclusion, Mission and Safety coordination;
- authoritative Dataset Capture, quota, reserve and finalization;
- model registry, activation decision and rollback record;
- camera receiver and same-origin browser streams.

### External Orin — conditional

- comparison inference during replay or shadow validation;
- FAST-LIO/Nav2 only when a verified sensor-data path is available;
- bounded diagnostic point-cloud rendering;
- release packaging and offline artifact verification.

The current wireless deployment does not provide the external Orin with XT16
or Go2 ROS/DDS sensor data. Mapping and Nav2 remain blocked rather than being
declared operational from product capabilities alone.

### Laptop

- browser, SSH maintenance and report review;
- finalized Dataset export and backup;
- labeling, train/validation split, training and evaluation;
- ONNX export, manifest creation and deployment preparation.

The laptop does not run a competition command loop or provide a required
inference service.

## Sensor-local inference gates

Every model begins in `SHADOW`: it can compute, display and record results but
cannot influence motion. Promotion requires evidence for all rows.

| Gate | Required evidence |
| --- | --- |
| Identity | immutable model ID, schema version and cryptographic hash |
| Compatibility | target JetPack/TensorRT engine built and loaded on the target |
| Performance | FPS plus p50/p95 inference and end-to-end age |
| Backlog | latest-frame behavior and no unbounded queue |
| Memory | bounded RAM, no OOM and no unsafe swap pressure |
| Thermal | soak temperature and no throttling |
| Coexistence | camera, LowState and bridge freshness remain within existing limits |
| Failure isolation | inference crash does not stop relay or change motion ownership |
| Rollback | atomic return to the verified previous model/runtime |

Public benchmark numbers do not satisfy these gates. Power mode,
`jetson_clocks`, fan policy and OS packages are not changed automatically to
make a model pass.

## Point-cloud workload placement

| Need | Robot-side work | External work | Gate |
| --- | --- | --- | --- |
| obstacle/free-space summary | depth/cloud reduction | validate and display | preferred starting point |
| LaserScan/small grid | bounded conversion | mapping/mission consumer | measured freshness and bandwidth |
| decimated cloud | fixed points/rate/fields | diagnostic renderer | explicit session approval |
| raw cloud | capture/encode only if justified | diagnostic consumer | separate overload and safety test |

If a mapping worker is eventually colocated robot-side, it remains a sensor
compute worker: the external Orin still owns map identity, Mission/Safety
coordination and any motion decision. If mapping stays external, its transport
must be bounded and independently fail closed. WP00 selects neither
implementation without evidence.

## Resource priority

1. Go2 stop/control status and LowState freshness;
2. small perception result and health;
3. bounded camera preview;
4. Dataset transfer outside active competition work;
5. decimated diagnostic cloud;
6. raw diagnostic data.

When contention appears, lower-priority work is disabled or reduced first.
Control/watchdog timeouts, graph cardinality, stale thresholds and disk reserve
are never loosened as a resource-management strategy.

## Dataset and model lifecycle

The external Orin remains the authoritative Dataset writer described in
[AI_DATASET.md](AI_DATASET.md). The robot-side host does not retain a second
unbounded copy. A future outage ring buffer requires its own capacity,
retention, privacy and recovery contract.

Training happens off-robot. A deployable model package must be immutable and
identify its schema, preprocessing, expected output, source model hash and
target engine hash. Unknown or partial packages cannot become `active`.

## Current evidence and unknowns

The robot-side hardware was previously observed as an Orin NX 16 GB-class
JetPack 5.1.1 system, as recorded in [AI_DATASET.md](AI_DATASET.md). That is a
useful baseline, not proof of available competition headroom. The following
must be remeasured with current camera, Go2 relay and control services:

- CPU/GPU/RAM and swap;
- temperature, power mode and throttling;
- camera source/receiver age and FPS;
- bridge/LowState age and restart behavior;
- per-model inference latency and combined-model load.
