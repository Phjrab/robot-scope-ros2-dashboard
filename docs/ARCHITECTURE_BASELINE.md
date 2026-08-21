# Robot Scope Architecture Baseline

> Phase 0 baseline only. This document records the implementation observed at
> commit `48617c69033995c82d5d58d6ba1abe9f7808d187`; it does not approve or
> introduce any behavioural, safety, process, filesystem, or API change.

## Scope and evidence

- Authoritative planning source read for this baseline:
  `ROBOT_SCOPE_CODEX_MASTER_SPEC.md`, SHA-256
  `5f48b9715e314893cac424baab1ca3ec8d5ddf8728e75f6db000f8d00477da22`.
  The supplied source is outside this checkout at
  `/Users/hajoonpark/Documents/자율설계/prompt/ROBOT_SCOPE_CODEX_MASTER_SPEC.md`.
  No copy existed at this repository root at baseline time, so this Phase does
  not create a second, potentially divergent copy.
- Baseline branch: `main`, clean and equal to `origin/main` before this
  documentation change.
- Code and test inspection covered the current source tree, not the target
  layout proposed by the Master Spec. In particular, no proposed `api/`,
  `application/`, `ros/`, or frontend feature-module tree exists yet.
- This file is the Phase 0 architecture freeze. `docs/SO101_EXTRACTION.md` is
  intentionally deferred to Phase 1, immediately before the extraction
  deletion work required by the Master Spec.

## Product boundary observed today

The implemented product already has a strong mobile-robot Go2 reference path:

```text
Browser
  -> FastAPI dashboard (single uvicorn worker)
  -> RosAgent + process managers on the ROS host
  -> signed Go2 bridge / mapping / Nav2 launchers
  -> Go2, Hesai XT16, FAST-LIO and Nav2
```

It also currently exposes Generic, TurtleBot, and SO-101 as selectable robot
types. SO-101 is an observation/display controller-host profile, not a Go2
motion path, but it is still a shipped runtime capability and therefore is an
explicit Phase 1 extraction target rather than dead metadata.

Current public messaging still calls the product "Robot Scope ROS 2 Dashboard"
in `README.md`. The autonomy-oriented description in the Master Spec is a
later product-language migration, not a Phase 0 behaviour change.

## Runtime and ownership topology

### Application construction and lifetime

`robot_dashboard.app.main()` constructs the long-lived managers, stores them
in module globals, and starts uvicorn with `workers=1`:

| Current owner | Constructed object / state | Lifecycle and responsibility |
| --- | --- | --- |
| `app.py` module globals | `AGENT`, `SAVED_MAPS`, `MAPPING_JOBS`, `NAVIGATION_JOBS`, `SERVICE_LIFECYCLE`, `CONTROL_BRIDGE_LIFECYCLE`, `DATASET_CAPTURE` | Application runtime dependencies; access is through module helper functions which emit HTTP 503 if unconfigured. |
| `app.py` module globals | `MAPPING_TASK`, `NAVIGATION_START_TASK`, `NAVIGATION_START_STATE` | Async one-shot map-save ownership and the fenced navigation-start transaction. |
| `app.py` locks/caches | `PIPELINE_COORDINATION_LOCK`, `NAVIGATION_START_STATE_LOCK`, pointcloud binary cache/lock, JSON cache, `CONTROL_BINDINGS` | Cross-subsystem interlocks, task state, bounded response reuse, and browser-control binding bookkeeping. |
| `lifespan()` | Starts `RosAgent`; optionally starts XT16 preview | On shutdown, settles pending navigation startup, prevents lifecycle dispatch, closes Nav motion first, then control, dataset, mapping, and ROS resources. |
| `RosAgent` | ROS node, executor, graph/telemetry/source/camera/control/navigation state | Compatibility facade that owns the ROS callback plane and routes bounded state to the rest of the application. |

The application is intentionally one process/one uvicorn worker. This is a
current safety and ownership assumption, not an invitation to add workers or
distributed coordination during the refactor.

### ROS executor ownership

`RosAgent.start()` starts one daemon thread named `robot-scope-ros`.
`RosAgent._run()` owns the ROS node and `MultiThreadedExecutor`, its fixed
subscriptions, publishers, callback groups, timers, and shutdown. HTTP routes
do not create arbitrary ROS publishers, subscribers, nodes, topics, services,
or parameter names.

The agent currently owns these significant planes:

| Plane | Current responsibility |
| --- | --- |
| Graph and telemetry | Topic discovery, publisher counts, rate/freshness metrics, bounded summaries, selected source state, joints, pose, occupancy/map and pointcloud snapshots. |
| Cameras | Fixed `go2_front` and `realsense_color` source adapters, per-source opaque demand tokens, maximum viewer/source limits, latest-frame state and stale handling. |
| Control transport | `ControlManager` calls, signed bridge status subscription/publisher, LowState freshness, fixed control timer, exclusive browser/navigation leases, and final signed stop flushing. |
| Navigation ROS gateway | Fixed navigation command ingress, runtime-health, scan, FAST-LIO odometry, controller odometry, `/amcl_pose`, initial-pose publisher, Nav2 action client and fixed costmap-clear clients. |
| Robot target/source persistence | Profile-derived source allowlists, local target selection, safe source-selection file read/write, and Go2 target-change lease revocation. |

`RosAgent` is therefore a facade with multiple responsibilities, not merely a
ROS executor wrapper. Future extraction must retain its public methods until
all current route and test callers migrate.

### Threads, processes, and background asyncio work

| Owner | Threads / child processes | Important ownership rule |
| --- | --- | --- |
| `RosAgent` | ROS executor daemon thread | Stops control/navigation before its executor stops. |
| `MappingJobManager` | Fixed preview, mapping-pipeline, and map-save process groups; stdout reader/monitor threads | Trusted absolute argv, `shell=False`, manager-owned process groups only, bounded stop and private staging publication. |
| `NavigationJobManager` | One Nav2 process group, reader thread, monitor thread | Private map/parameter snapshots; fixed launcher and private cmd_vel ingress; terminal callback reports exact job identity. |
| `DatasetCaptureManager` | Sampler and writer threads | Server-side camera demand tokens, bounded queue, atomic sample publication, quota/reserve checks, interrupted-session recovery. |
| `Go2MulticastCamera` / `CameraDecoder` | GStreamer child process plus reader/writer/stderr/watchdog threads | Source-specific on-demand start/stop; no browser-selected pipeline command. |
| `RemoteMjpegCamera` | One reader thread | Pulls only the configured RealSense endpoint; bounded JPEG parsing. |
| `ServiceLifecycleManager` | One bounded worker thread per fixed dashboard service transition | Only exact, shell-free sudo/systemctl restart or stop commands. |
| `ControlBridgeLifecycleManager` | One bounded worker thread per fixed bridge start/stop transition | Owns exactly the bridge unit and status polling; `RUNNING` is not treated as signed bridge readiness. |
| `app.py` | `MAPPING_TASK`, `NAVIGATION_START_TASK`, WebSocket disconnect/send tasks | Tasks are fenced/settled during cancellation and app shutdown; navigation startup has a token and exact job ownership. |

External systemd units remain outside the dashboard process. In particular,
the standalone Go2 control bridge is independently watchdog-protected and is
not merged into the FastAPI service.

## HTTP and WebSocket surface

### HTTP route groups

All mutating HTTP routes use strict Pydantic bodies where applicable and call
`require_same_origin()`. Their request models accept bounded intent, not
filesystem paths, shell fragments, arbitrary ROS names, or executable names.

| Group | Current `/api/v1/*` surface | Primary subsystem |
| --- | --- | --- |
| System / lifecycle | `system/service`, restart, stop; `control/bridge-service`, start, stop | Service lifecycle managers and app-level activity blockers. |
| Observability | `health`, `state`, `topics`, `sources`, `pointcloud`, `pointcloud.bin`, `pointcloud/settings`, `map`, `joints`, `pose` | `RosAgent`, bounded serializers, pointcloud frame encoder. |
| Robot discovery | `robots/types`, `robots/discover`, `robot` POST/DELETE | `LocalRobotDiscovery`, `RosAgent` target state. |
| Camera / dataset | `cameras`, dataset capture start/stop/status, session listing/detail, fixed JPEG sample route | `RosAgent` camera hubs and `DatasetCaptureManager`. |
| Manual control | `control`, arm, disarm, stop, E-stop clear | `RosAgent` facade over `ControlManager` and signed transport. |
| Navigation | status, logs, parameters GET/PATCH, start/stop, initial pose, goal, cancel, clear-costmaps | `NavigationJobManager`, app startup coordinator, `RosAgent` navigation gateway. |
| Mapping | `mapping/control`, start/stop/save | `MappingJobManager` plus app task/interlocks. |
| Saved maps | listing, conversion, edited copy, metadata, rename, delete, bounded data | `SavedMapCatalog`; opaque IDs and revision checks. |

### WebSocket routes and producers

| Route | Producer and cleanup | Baseline origin policy |
| --- | --- | --- |
| `/api/v1/ws/control` | Browser session binds an opaque ControlManager lease; inbound messages are sequence, age, deadman, source, and action validated; finalizer releases it. | Same-origin required. |
| `/api/v1/ws/pointcloud` | `RosAgent` latest pointcloud snapshot -> bounded binary encoder/cache -> disconnect-aware stream helper. | Same-origin required. |
| `/api/v1/ws/camera` and `/api/v1/ws/cameras/{source_id}` | Exact allowlisted source -> opaque camera demand token -> metadata plus JPEG latest frame; finalizer closes the exact token. | Same-origin required. |
| `/api/v1/ws/joints` | `RosAgent.joints_snapshot()` emits changed bounded JSON snapshots. | **No explicit same-origin check at baseline.** |
| `/api/v1/ws/pose` | `RosAgent.pose_snapshot()` emits changed bounded JSON snapshots. | **No explicit same-origin check at baseline.** |

The joint and pose routes are read-only, but their inconsistent origin policy
is an explicit Phase 8 audit item. It is documented here, not changed in
Phase 0.

## Major state machines and coordination

### Motion control

```text
disarmed / no lease
  -> explicit ARM (keyboard or gamepad)
  -> unbound lease
  -> browser WebSocket binds lease
  -> deadman + fresh sequence + fresh bridge/LowState
  -> bounded signed drive output
  -> release, stale input, stale bridge/LowState, E-stop, target change,
     navigation ownership, or shutdown
  -> signed StopMove and lease revocation
```

`ControlManager` remains ROS-independent. `RosAgent` transports already
bounded decisions using the signed internal bridge protocol; the standalone
bridge is the only dashboard-owned publisher path to `/api/sport/request`.
Manual and navigation control share one exclusive lease and cannot coexist.

### Mapping

```text
preview: disabled | idle | starting | running | stopping | failed
pipeline: idle | starting | running | stopping | failed
operation: idle | saving | stopping | succeeded | failed
```

The preview can remain available independent of FAST-LIO mapping. Pipeline and
save commands are trusted `CommandSpec` / `SaveCommandSpec` values with fixed
argv. Map saving writes to private staging and publishes only validated,
expected suffixes through a controlled result path.

### Navigation startup and execution

```text
idle
  -> token reserved / pending
  -> inspect safe control preflight
  -> use shared mapping or start and claim an exact mapping job
  -> start Nav2 process and claim exact navigation job
  -> wait for fixed fresh pre-localization inputs
  -> recheck control preflight and acquire autonomous lease
  -> initial pose -> localizing -> localized
  -> confirmed goal -> pending | active | canceling -> terminal
  -> exact token/job cleanup, including only navigation-owned mapping
```

`NAVIGATION_START_STATE` records token, cancellation flag, mapping ownership,
navigation job ID, terminal-cleanup state, phase, sequence and public error.
`PIPELINE_COORDINATION_LOCK` and the start-state lock protect the handoff.
Cancellation is settled before rollback; a stale terminal callback must not
cancel a replacement start. STOP/CANCEL cleanup remains available even while
new work is gated.

### Dashboard and bridge lifecycle

Dashboard restart/stop and control-bridge start/stop each require explicit
confirmation, operate on only fixed systemd argv, and collect fail-closed
blockers from control leases/actions, navigation, mapping, and relevant
transitions. Neither API changes systemd enablement. The service lifecycle
prevents a dashboard transition while robot work is active; bridge service
state is kept distinct from signed bridge readiness.

### Dataset capture

```text
idle -> starting -> capturing -> stopping -> finalizing -> completed | failed
```

The manager owns one generated session ID, fixed source IDs, bounded sampling
rate/queue/JPEG size, filesystem quotas, and server-side atomic sample writes.
Dataset capture is a lifecycle blocker so dashboard shutdown/restart does not
silently truncate a normal session; shutdown still closes motion gates first.

## Filesystem and configuration boundaries

| Domain | Authority and boundary |
| --- | --- |
| Source selection | Profile allowlist plus a mode-0600, regular, owned state file. Untrusted persisted topics are revalidated. |
| Maps | `SavedMapCatalog` discovers only configured roots and returns opaque IDs. Mutations require explicit managed roots, safe names, revision comparison, regular-file/symlink checks, and pair-aware rename/delete rollback. |
| Navigation maps | An opaque managed map ID/revision becomes a private, revision-pinned YAML/PGM snapshot for one job; paths are not serialized to the browser. |
| Mapping output | Configured real directory only; save process receives a private staging prefix, never a browser path. |
| Dataset storage | Absolute, non-root, real path with no symlink components; root/session directories are secured, writes are bounded and atomically published. |
| Runtime state/logs | Runner scripts pass project-local runtime/state/log paths explicitly; ROS logs, dataset data, maps, control environment, workspaces and generated artifacts are excluded from Git. |
| Robot models | Static read-only assets, with upstream provenance and licenses in the asset directories and `THIRD_PARTY_NOTICES.md`. |

## Frontend baseline

`robot_dashboard/static/app.js` is a single 8,404-line module. It owns DOM
references, global mutable state, polling, request generations, WebSockets,
camera decode/recording, pointcloud transport, mapping/map editor, datasets,
navigation, lifecycle controls, robot discovery, and manual control input.
It imports focused helpers such as `navigation.js`, `scene3d.js`,
`live_map2d.js`, `pointcloud_stream.js`, `control_input.js`,
`map_editor.js`, and `robot_profiles.js`, but feature-level ownership is still
primarily central.

Important current global state families include:

- REST snapshots and request generations for state, topics, source catalog,
  mapping, navigation, parameters, datasets, lifecycle, and bridge state.
- Per-stream sockets and reconnect state for camera, pointcloud, joints, pose,
  and control.
- Camera source, decoder, frame freshness, recording and dual-view state.
- Saved-map, editor, point budget, 3D/live-map renderer, robot-model and
  pose-trail state.
- Navigation map layout/selection/pose staging/log stream/parameter draft
  state.
- Manual-control lease, socket, heartbeat, deadman, action and gamepad state.

The frontend currently duplicates a small LiDAR topic identity allowlist for
presentation fallback. Backend metadata is already preferred where supplied.
The Master Spec's backend-authority and feature-module direction is therefore
a later incremental extraction target, not a Phase 0 rewrite.

## Safety invariants verified in code and test inventory

The following are current assets and must be preserved while responsibility is
moved in later phases.

| Boundary | Baseline evidence |
| --- | --- |
| Control transport | `control.py`, `control_protocol.py`, `go2_control_bridge.py`, `go2_bridge.py`, `ros_agent.py`, and control tests preserve signed bridge messages, independent watchdog, fixed action allowlist, low-state/bridge freshness, cardinality checks, one lease, deadman, age/sequence limits, latched E-stop, and shutdown StopMove. |
| Navigation | `navigation_jobs.py`, `navigation_runtime.py`, `ros_agent.py`, `app.py`, saved-map tests, navigation transaction tests preserve opaque map/revision inputs, private snapshots, fixed launcher argv, known-free pose validation, runtime/readiness gates, private cmd_vel ingress, autonomous lease, goal cancellation, and startup/terminal fencing. |
| Mapping | `mapping_jobs.py` and its tests preserve absolute trusted executables, `shell=False`, private process groups, bounded timeouts/logs, fixed save suffixes, safe names, staging and publication. |
| Maps/filesystem | `saved_maps.py` and tests preserve configured-root discovery, opaque IDs, managed/read-only separation, no traversal/symlink following, limits, pair transactions and revisions. |
| Dataset | `dataset_capture.py` and tests preserve server-side capture, fixed sources, bounded queue/rate/JPEG, quota/reserve, O_NOFOLLOW-style path safety, atomic publication and interrupted recovery. |
| Discovery | `discovery.py` derives bounded local RFC1918/link-local scope from host interfaces; browser input cannot choose a subnet, interface or arbitrary probe target. |
| HTTP/WS | Mutations enforce same-origin; control, camera and pointcloud WebSockets do likewise. The joints/pose inconsistency is recorded above for Phase 8 rather than weakened or hidden. |

## Architecture hotspots and Phase 1+ extraction inventory

| Hotspot | Baseline size / responsibility | Safe refactoring direction, not started in Phase 0 |
| --- | --- | --- |
| `robot_dashboard/app.py` | 3,208 lines; runtime globals, lifespan, HTTP/WS transport, request models, lifecycle blockers, navigation startup transaction, task ownership and manager wiring | Introduce an explicit runtime container first, then move transport routes to domain routers and move mapping/navigation transactions to application coordinators. Preserve paths and response contracts. |
| `robot_dashboard/ros_agent.py` | 4,723 lines; ROS executor, graph, source selection, telemetry, cameras, pointcloud, control transport and navigation gateway | Extract focused adapters behind the existing facade: runtime/graph/source/telemetry/camera/pointcloud/control/navigation. Keep callback and locking semantics intact during delegation. |
| `robot_dashboard/static/app.js` | 8,404 lines; global state, DOM, polling, WebSockets, render and input behaviour for every feature | Incrementally extract ES-module features and shared API/store/WS helpers. Do not replace the UI framework or rewrite all pages at once. |
| `MappingJobManager` / `NavigationJobManager` | Already focused domain/process managers, but app-level coordination is in `app.py` | Retain their command, process, snapshot, token, cleanup and log contracts; introduce coordinators around them rather than moving safety logic into route handlers. |
| Lifecycle managers | Focused fixed-command managers, app computes blockers | Keep shell-free fixed unit/argv contracts; move only the coordination/dependency ownership when a runtime container exists. |

## SO-101 integration inventory (Phase 0; no extraction yet)

### SO-101 dedicated implementation and assets

| Area | Files / role | Classification |
| --- | --- | --- |
| Startup profile | `config/so101.json`; `scripts/run_generic.sh` accepts `so-101`/`so101` and selects it | SO-101 dedicated runtime profile and launcher branch. |
| Robot metadata and discovery | `robot_dashboard/discovery.py` `ROBOT_TYPES["so-101"]`, aliases, type inference, hostname hints and controller-host discovery messaging | SO-101 dedicated catalogue/discovery integration. |
| Frontend type selection | `static/robot_profiles.js`, `static/index.html`, and `static/assets/robot-model-catalog.json` | SO-101 dedicated selectable UI/model metadata. |
| Static assets | `static/assets/so101/` (18 files, about 16 MiB): Apache-2.0 license, upstream manifest, URDF, 13 STL files and generated lite model | SO-101 dedicated asset payload. |
| Model build configuration | `scripts/build_official_robot_models.py` contains a SO-101 `ModelSpec`, mesh budgets and output paths | Mixed builder: remove only the SO-101 branch; retain generic builder infrastructure and TurtleBot branch. |
| Product/licensing docs | `README.md`, `THIRD_PARTY_NOTICES.md`, `static/assets/README.md`, `static/assets/so101/README.md` | SO-101 documentation/provenance metadata. |
| Tests | `test_discovery.py`, `test_robot_profiles.mjs`, `test_ros_agent_target.py`, `test_official_robot_assets.py`, and model-build output in `test_official_go2_asset.py` | SO-101 dedicated assertions or mixed catalog tests requiring Phase 1 surgical updates. |

### Shared reusable implementation to retain

| Shared item | Why it is not SO-101 dedicated |
| --- | --- |
| `LocalRobotDiscovery` bounds, interface filtering, RFC1918/link-local validation, worker/time caps | Used by Go2 and TurtleBot; only the SO-101 metadata/candidate branch is dedicated. |
| `RosAgent` generic target selection, source discovery, observability, target-change safety revocation | Go2/TurtleBot/Generic use the same target/profile plumbing. Remove SO-101 identifiers, not generic safety behaviour. |
| Robot model catalogue schema, lightweight model renderer and builder framework | Go2 and TurtleBot use the same schema and tooling. |
| `scripts/run_generic.sh` generic/TurtleBot launch path and project-local runtime path checks | The SO-101 case is removable while generic and TurtleBot remain. |
| Asset provenance/license pattern | Reuse for shipped Go2/TurtleBot assets; remove only SO-101 entries and files. |

### Extraction hand-off constraints

- Do not delete, rename, or move these integrations in Phase 0.
- Before Phase 1 deletion, create `docs/SO101_EXTRACTION.md` containing the
  dedicated/shared split, config schema, profile example, model provenance and
  license, tests, integration points, and a migration inventory for an
  independent project.
- Phase 1 must update product docs/notices and residual searches together with
  the code/assets. It must not remove generic discovery, model rendering, or
  non-Go2 observation support by accident.

## Baseline test inventory and result

The full baseline was executed without contacting robot hardware, restarting a
service, moving the robot, launching mapping/navigation, or changing map/data
files:

```text
python3 -m unittest discover -s tests -v
Ran 488 tests in 32.229s
OK

node --test tests/*.mjs
tests 145; pass 145; fail 0; skipped 0
```

The Python suite includes deliberate error-path fixtures that log simulated
mapping/navigation cleanup exceptions while their tests pass. Those log lines
are expected test evidence, not baseline failures.

Baseline test coverage is organized by safety/domain, including control and
bridge lifecycle, dataset capture, discovery, HTTP security, mapping
artifacts/jobs/control UI, navigation process/transaction/ROS/runtime/UI,
saved maps, serializers/source persistence, stream WebSockets, XT16
readiness/relay, frontend media/map/navigation/control/dataset/scene checks,
and robot asset provenance.

## Known risks and prerequisites for later phases

1. The Master Spec source was supplied outside the checkout and was absent at
   repository root. Keep its recorded hash/source location in future planning
   or explicitly add a governed in-repository copy in a separately approved
   documentation change; do not silently treat an untracked local copy as
   versioned specification.
2. `app.py`, `ros_agent.py`, and `app.js` have high responsibility density.
   Their globals, locks, callbacks and state transitions are safety-relevant;
   extraction must be delegation-first with compatibility tests at each step.
3. `/api/v1/ws/joints` and `/api/v1/ws/pose` lack the explicit same-origin
   check used by the other browser WebSockets. This is a Phase 8 security
   hardening item and is intentionally unchanged in Phase 0.
4. SO-101 is integrated across runtime, static UI and approximately 16 MiB of
   licensed assets. Its removal will require a coordinated configuration,
   discovery, frontend, asset, notice and test update, not an asset-only
   deletion.
5. The baseline has no failing test. Refactor work must distinguish future
   failures from this recorded green baseline and must not delete or weaken
   assertions merely to recover it.
6. Physical Go2/XT16/RealSense and systemd behaviour is intentionally not
   exercised here. Git publication and Jetson deployment remain separate.

## Phase 1 entry checklist

Before starting Phase 1, re-read `AGENTS.md`, capture a fresh `git status
--short --branch`, preserve this baseline document, and create the required
`docs/SO101_EXTRACTION.md` before deleting any SO-101 file or integration.
Run a fresh repository-wide SO-101/LeRobot residual search, classify every
match against this inventory, then update tests and third-party notices in the
same focused change. Do not begin runtime container, router, RosAgent, or
frontend modularization work until their respective later phases.
