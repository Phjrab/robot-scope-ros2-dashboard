# Robot Scope Current Architecture

Robot Scope is a **ROS2 Autonomous Mobile Robot Mapping, Navigation and Control Dashboard**.
This document is the current architecture authority for
the repository after the Phase 0–15 refactor. The per-phase architecture
documents remain historical design and verification records; when they
describe an older ownership boundary, this document takes precedence.

## Product boundary

The reference system is Unitree Go2 + Hesai XT16 + FAST-LIO + Nav2. TurtleBot
and Generic ROS2 mobile robots retain the capabilities that are explicitly
declared by the backend. Robot Scope does not provide SO-101, manipulator,
generic actuator, arbitrary ROS publisher/service, shell, filesystem-browser,
or remote-terminal products.

The application deliberately remains one process with one Uvicorn worker.
That constraint gives asynchronous tasks, ROS resources and child processes
one explicit owner; it does not make them global or collapse subsystem safety
boundaries.

## Before and after

The frozen Phase 0 implementation is commit
`48617c69033995c82d5d58d6ba1abe9f7808d187`. The current comparison was made
against the Phase 10 pre-change HEAD `17119dab7b58271ac3051fcd17e2ebc328e14801`.

| Hotspot | Phase 0 | Phase 15 | Responsibility reduction |
| --- | ---: | ---: | --- |
| `robot_dashboard/app.py` | 3,208 lines | 1,308 lines | Runtime globals, extracted routers and mapping/navigation/lifecycle transactions moved to explicit owners; annotation transport remains thin; 59.2% smaller. |
| `robot_dashboard/ros_agent.py` | 4,723 lines | 2,378 lines | ROS runtime, observability, control transport and navigation gateway moved to focused components; 49.6% smaller. |
| `robot_dashboard/static/app.js` | 8,404 lines | 6,890 lines | Shared utilities and seven vertical features moved to focused modules, including the Phase 15 static-map annotation editor; 18.0% smaller. |

Line count is evidence, not the goal. The important change is the dependency
and ownership direction:

```text
Phase 0

Browser
  -> app.js (most frontend state/network/render ownership)
  -> app.py (routes + globals + tasks + autonomy transactions)
  -> RosAgent (executor + every ROS plane)
  -> process/filesystem/control adapters

Current

Browser feature modules + app.js composition
  -> FastAPI routers / thin transport handlers
  -> ApplicationRuntime + focused coordinators
  -> domain managers and ROS components
  -> fixed process, filesystem and signed-control adapters
```

## Module layout and ownership

```text
robot_dashboard/
├── api/
│   ├── dependencies.py       runtime lookup for HTTP/WebSocket requests
│   ├── models.py             strict bounded request bodies
│   └── routers/              system, telemetry, cameras, dataset, discovery
├── application/
│   ├── runtime.py            one-worker ownership container and shared lock
│   ├── mapping_coordinator.py
│   ├── navigation_coordinator.py
│   └── lifecycle_coordinator.py
├── ros/
│   ├── runtime.py            ROS thread/executor lifetime
│   ├── graph.py              graph snapshot/cardinality observation
│   ├── sources.py            selected sources and sensor metadata authority
│   ├── telemetry.py          bounded sensor/joint/pose summaries
│   ├── cameras.py            fixed camera source ownership
│   ├── pointcloud.py         bounded cloud state
│   ├── control_transport.py  signed bridge transport and ControlManager owner
│   └── navigation_gateway.py fixed Nav2 ROS boundary and autonomous lease
├── app.py                    composition, lifespan, remaining thin routes
├── diagnostics.py            deterministic bounded public ZIP projection
├── localization_health.py    bounded explainable localization classifier
├── operator_events.py        rotated browser-intent JSONL timeline
├── ros_agent.py              compatibility facade and target orchestration
├── mapping_jobs.py           trusted mapping child-process manager
├── navigation_jobs.py        trusted Nav2 child-process manager
├── map_annotations.py        pure revisioned map-operation schema/geometry
├── saved_maps.py             opaque-ID map filesystem boundary
├── dataset_capture.py        bounded server-side dataset writer
└── static/
    ├── core/                 API, DOM, formatting and sticky-log utilities
    ├── features/             extracted feature-owned state and polling
    ├── map_annotations.js    bounded annotation projection and editor state
    └── app.js                remaining UI composition and features
```

### API and application plane

`ApplicationRuntime` owns the agent, saved-map catalog, dataset manager, three
coordinators, shared pipeline coordination lock, response caches, control
bindings, local discovery, one diagnostics service and one operator-event
timeline. There is one module-level `RUNTIME` container,
not separate manager/task globals. FastAPI handlers validate browser intent,
look up the runtime, invoke a coordinator or bounded manager and translate
domain errors to the existing HTTP contract.

`MappingCoordinator` owns the asynchronous mapping/map-operation task and the
cross-domain mapping gates. `NavigationCoordinator` owns the navigation-start
task, private token and exact mapping/navigation job fencing. Its state uses a
threading `RLock` because terminal callbacks originate from the process
monitor thread. `LifecycleCoordinator` owns dashboard and bridge lifecycle
manager composition and fail-closed blockers. All three use the same injected
pipeline coordination lock where new work must be serialized.

### ROS plane

`RosRuntime` owns the ROS thread, node and executor lifetime. `RosGraphMonitor`,
`SourceRegistry`, `TelemetryHub`, `CameraHub` and `PointCloudHub` own the
observation plane. `ControlTransport` owns exactly one `ControlManager`, the
shared control operation `RLock`, signed status/command transport and final
stop. `NavigationRosGateway` uses that same manager and operation lock through
a narrow port and owns autonomous ROS state, validated freshness receipts,
action clients and goal generations.

`RosAgent` remains the supported compatibility facade. Its forwarding
properties and private delegates were audited in Phase 10 and are retained
intentionally: tests and existing integrations use them while all mutable
truth lives in the extracted component. They must not become a second state
owner. Future removal requires an explicit deprecation and caller inventory,
not a line-count cleanup.

The fixed navigation runtime publishes additive bounded rate, age, TF,
discontinuity and frame telemetry. `NavigationRosGateway` validates and
projects it through the observation-only classifier in
`localization_health.py`. This classifier cannot arm control or replace the
existing navigation freshness interlock. Its seven explicit states, profile
thresholds and read-only calibration assistant are specified in
[ARCHITECTURE_PHASE14.md](ARCHITECTURE_PHASE14.md).

### Frontend plane

The browser remains vanilla JavaScript with native ES modules and no bundler.
The shared core owns same-origin/no-store API calls, DOM helpers, formatting
and user-scroll-wins log behavior. Extracted features own LiDAR identity,
navigation logs, control-bridge lifecycle, dashboard-service lifecycle,
server-side dataset UI lifecycle and the static-map annotation editor.
`app.js` composes those modules and still owns overview, camera media, mapping,
saved-map raster editing and most manual/navigation UI state. The hardware-free
browser contract is recorded in `docs/ARCHITECTURE_PHASE12.md`. This remaining
size is known debt, not hidden completion.

Cockpit has both the compatible embedded `#cockpit` composition and a strict
same-origin `?workspace=cockpit#cockpit` full-window composition. The supported
named-window launcher deactivates the embedded Cockpit after a successful open,
but each browser document still has its own JavaScript owners; no cross-window
sensor/control singleton or lease handoff is claimed. The server safety owners,
watchdogs and fail-closed authority remain unchanged. The detailed contract is
in [COCKPIT_WORKSPACE.md](COCKPIT_WORKSPACE.md).

Backend responses are authoritative for capability grants, sensor identity,
processing stage and freshness. Browser constants may format labels but may
not grant a capability or infer a physical sensor from a topic name.

## Runtime, thread, task and process ownership

| Resource | Single owner | Shutdown / fencing rule |
| --- | --- | --- |
| Uvicorn application state | `ApplicationRuntime` | One worker only; no cross-worker state claim. |
| ROS thread/node/executor | `RosRuntime` through `RosAgent` | Navigation/control stop while ROS transport is live, executor last. |
| Mapping async operation | `MappingCoordinator` | Shared coordination lock; exact manager operation/job ownership. |
| Navigation start task | `NavigationCoordinator` | Private token, cancellation settlement and exact job cleanup. |
| Mapping/preview/save children | `MappingJobManager` | Fixed absolute argv, `shell=False`, owned process groups and bounded termination. |
| Nav2 child | `NavigationJobManager` | One exact job/process group; terminal callbacks carry exact job identity. |
| Dataset sampler/writer threads | `DatasetCaptureManager` | Bounded queue/rate/size, quota and atomic finalization. |
| Dashboard/bridge lifecycle workers | focused lifecycle managers | Fixed units/argv only; close observes and fences but never dispatches a new mutation. |
| Camera workers/processes | fixed camera adapters | Source-bound demand tokens and bounded stale/close behavior. |
| Operator intent JSONL | `OperatorEventTimeline` | Fixed mutation catalog; 256 KiB rotation, four-file retention, no request bodies or verified identity claim. |
| Diagnostics ZIP | `DiagnosticsBundleService` | Read-only public projections, deterministic fixed entries and 2 MiB compressed limit. |

Application shutdown preserves this high-level order: settle a pending
navigation start, close lifecycle observers, deactivate/close navigation,
shut down signed control, close dataset capture, close mapping ownership, then
stop the ROS agent/executor. Cleanup endpoints remain available when new work
is blocked.

## Preserved safety contracts

### Motion control

```text
Browser
  -> ControlManager
  -> signed fixed-topic ControlTransport
  -> standalone Go2 watchdog bridge
  -> fixed /api/sport/request path
  -> Go2
```

The exclusive lease, manual/autonomous mutual exclusion, deadman, sequence and
age checks, LowState freshness, graph cardinality, foreign publisher blocking,
speed/motion limits, action allowlist, latched software E-stop, bridge epoch
fencing and final StopMove remain intact. Systemd `RUNNING` is never treated as
authenticated bridge readiness. The browser still cannot publish directly to
the Go2 sport request path.

### Navigation

Only opaque map IDs/revisions, parameter revisions, allowlisted parameter
values, validated poses, explicit confirmation and goal IDs cross the HTTP
boundary. Known-free pose validation, map revision pinning, fixed private
cmd_vel ingress, fresh sensor/runtime gates, the second pre-motion preflight,
exclusive autonomous lease, goal/costmap generation fencing, cancellation and
terminal cleanup are preserved.

The startup transaction retains a private token, pending/cancel flags, shared
versus navigation-owned mapping distinction, exact mapping and navigation job
IDs, compare-and-stop cleanup, worker settlement, readiness timeout and
terminal-cleanup ownership.

### Mapping, maps and datasets

Mapping uses trusted command specifications, absolute executables, fixed argv,
`shell=False`, private process groups, bounded timeouts/logs, validated names,
known result suffixes, private staging and controlled publication.

Maps remain confined to configured roots and opaque IDs. Managed/read-only
root separation, path/symlink checks, file/point/grid limits, revision compare,
pair-aware rename/delete and bounded conversion/editing remain unchanged.

Dataset capture remains server-side with fixed sources, bounded sampling,
queue and JPEG size, session quota, minimum free reserve, secured non-symlink
directories, atomic publication and interrupted-session recovery.

### Network and web boundary

Discovery is limited to server-derived directly connected RFC1918/link-local
networks with bounded subnet, host, worker and time budgets. Browser input
cannot select an arbitrary subnet.

All 30 HTTP mutations require the shared strict same-origin check. All six
browser WebSockets enforce the same origin before accept/runtime lookup.
Requests expose bounded intent rather than paths, commands or arbitrary ROS
names. Operational responses are no-store and public diagnostics are bounded
and redacted. This is a trusted-LAN boundary, not authentication; internet
exposure still requires external TLS and access control.

Settings can export the deterministic bounded Phase 13 diagnostics bundle
without taking the robot-work lock. It includes only allowlisted summaries and
redacted transitions; it excludes credentials, environment, raw argv/output,
absolute paths, IP addresses and raw ROS messages. The browser session and
request sequence stored in the rotated operator-event timeline are correlation
fields only and never establish a human identity. The full contract is in
[ARCHITECTURE_PHASE13.md](ARCHITECTURE_PHASE13.md).

## SO-101 extraction and assets

SO-101 runtime profiles, discovery aliases, UI choices, model metadata, build
specification and approximately 16 MiB of bundled arm assets were removed in
Phase 1. The complete pre-removal inventory and future standalone-project
handoff are retained in [SO101_EXTRACTION.md](SO101_EXTRACTION.md).

Phase 10 rechecked `config/`, `scripts/` and `robot_dashboard/`: no SO-101,
SO101 or LeRobot runtime/product residue remains. Deliberate references are
limited to the extraction/baseline history and negative tests proving that an
arm profile is rejected. Shared discovery, observability, profile, model-build
and asset-provenance utilities remain because Go2, TurtleBot or Generic mobile
robots use them.

The shipped model catalog contains only Go2 and TurtleBot. Their pinned source,
derivative notes and licenses remain in their asset directories and
`THIRD_PARTY_NOTICES.md`; external Unitree/Hesai/Livox/FAST-LIO/Nav2 workspaces
are not vendored.

## Cleanup and duplicate-authority audit

- Ruff correctness checks report no unused imports or undefined names in
  `robot_dashboard` and `scripts`.
- No former manager/task globals remain alongside `ApplicationRuntime`; the
  runtime and coordinator ownership tests reject reintroduction.
- No second ControlManager, navigation lease, mapping task or lifecycle state
  owner was found. Compatibility facade members delegate to the single owner.
- Backend capability and sensor metadata are authoritative. Frontend values
  left in feature modules are presentation labels and fail-closed fallbacks.
- Mapping/navigation log and public error projection share bounded diagnostic
  behavior; raw child argv/environment/stdout and private control fields are
  not public API contracts.
- The current model catalog, bundled files and third-party notices agree.
- [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) and
  `ARCHITECTURE_PHASE3.md` through
  `ARCHITECTURE_PHASE9.md`, `ARCHITECTURE_PHASE12.md` and
  `ARCHITECTURE_PHASE13.md` are historical records, not competing current
  ownership specifications.

No wrapper, module or asset was removed merely because it looked small or was
not imported by a production module. Script entrypoints, compatibility
surfaces, build tools and safety adapters have non-import callers and require
their own contract evidence before deletion.

## Compatibility and verification

The refactor preserves the existing `/api/v1/*` paths, fixed camera/source IDs,
single-worker deployment, Generic/TurtleBot observation support and Go2
reference path, except for the explicitly documented Phase 8 contract
hardening in [ARCHITECTURE_PHASE8.md](ARCHITECTURE_PHASE8.md). The removed
SO-101 product was an intentional Phase 1 boundary change.

Repository verification is side-effect free: unit and contract tests use
fakes/stubs and never start systemd units, launch mapping/Nav2, move a robot,
delete maps or capture a live dataset. The quality workflow and exact tool
scope are documented in [ARCHITECTURE_PHASE9.md](ARCHITECTURE_PHASE9.md).
Live ROS2/DDS, sensor timing, bridge watchdog and physical motion acceptance
remain deployment checks on a controlled host.

The Phase 10 documentation audit covered the required operator documents:

| Document | Current authority checked |
| --- | --- |
| `README.md` | Product scope, supported profiles, API overview, test commands, security warning and current module layout. |
| `docs/INSTALL.md` | Explicit install opt-ins, modes, service policy and side-effect-aware smoke tests. |
| `docs/DEPENDENCIES.md` | Supported ROS/system-site-packages boundary, distro-specific manifests and release-record strategy. |
| `docs/TOPOLOGY.md` | Management/robot/sensor network roles and single/two-host reference paths. |
| `docs/TROUBLESHOOTING.md` | Read-only-first diagnostics and fail-closed control/mapping/navigation recovery. |
| `THIRD_PARTY_NOTICES.md` | Only shipped Go2/TurtleBot assets plus external runtime redistribution obligations. |

## Phase 10 verification baseline

The final local, no-hardware verification completed with:

| Command / check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | PASS — 600 tests |
| `node --test tests/*.mjs` | PASS — 151 tests |
| `node scripts/check_frontend_syntax.mjs` | PASS — 17 dashboard modules |
| `python3 -m compileall -q robot_dashboard scripts` | PASS |
| `python3 scripts/check_repository_secrets.py` | PASS |
| `git diff --check` | PASS |

Expected synthetic exception logs from failure-containment tests do not
represent baseline failures; both test runners exited successfully. The exact
Ruff, Mypy, coverage and dependency-audit CI scope remains the Phase 9 contract.

## Remaining debt and future milestones

1. Continue frontend extraction one vertical feature at a time. `app.js` is
   still the largest ownership hotspot; cameras, mapping/maps, overview and
   main control/navigation UI state are the next candidates.
2. Retire `RosAgent` private forwarding properties only after repository and
   external caller deprecation, with direct component tests retained. Do not
   duplicate state during migration.
3. Expand strict typing only across isolated or ROS-stubbed boundaries. Do not
   replace Ubuntu/ROS system packages or hide control/navigation errors with
   broad ignores.
4. Record a hardware-aware coverage baseline before introducing a percentage
   gate. Hardware-free browser E2E now runs in CI from Phase 12 onward.
5. Perform the deferred Jetson/ROS/hardware acceptance when the robot, XT16 and
   safe test area are available. Validate sensor timestamp domains, signed
   bridge readiness, fail-stop behavior, mapping publication and Nav2 startup
   fencing without loosening timeouts.
6. Treat authentication/TLS for broader networks as a separately reviewed
   product milestone. Same-origin protection alone is not authorization.
