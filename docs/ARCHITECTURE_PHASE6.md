# Phase 6 Autonomy Application Coordinators

This document records the Phase 6 application-coordinator extraction. It
supplements the Phase 0 baseline, the Phase 3 runtime-container boundary, and
the Phase 4/5 ROS-plane decompositions. Phase 6 moves application ownership;
it does not redesign the mapping, navigation, map-filesystem, control, or ROS
safety mechanisms beneath that ownership.

## Resulting application boundary

Robot Scope remains a single-process, one-worker application. The explicit
`ApplicationRuntime` holds one shared pipeline coordination lock and the three
focused autonomy coordinators:

```text
HTTP transport
      |
      v
ApplicationRuntime
  |-- MappingCoordinator
  |-- NavigationCoordinator
  `-- LifecycleCoordinator
      |
      v
Domain managers and fixed adapters
  |-- MappingJobManager
  |-- NavigationJobManager
  |-- SavedMapCatalog
  |-- ServiceLifecycleManager
  |-- ControlBridgeLifecycleManager
  `-- RosAgent compatibility facade
          |-- ControlTransport
          `-- NavigationRosGateway
```

The coordinators are application components. They do not import FastAPI and
do not expose browser-selected executables, commands, ROS names, raw paths, or
arbitrary parameters. HTTP code remains responsible for same-origin checks,
request-model validation, runtime dependency lookup, application/domain error
translation, and stable response serialization.

## Coordinator ownership

| Component | Application responsibility moved in Phase 6 | Responsibility deliberately retained below it |
| --- | --- | --- |
| `MappingCoordinator` | Shared mapping/navigation interlocks, the single bounded map-operation task, operator start/stop/save sequencing, saved-PCD conversion reservation, saved-map mutation sequencing, mapping activity projection, and the narrow localization dependency port used by navigation. | Trusted command specifications, process groups, timeouts, logs, staging, suffix validation, and compare-and-stop remain in `MappingJobManager`. Configured roots, opaque IDs, revisions, symlink/traversal defense, size/point/grid limits, and atomic map publication remain in `SavedMapCatalog`. |
| `NavigationCoordinator` | Navigation startup state and task, private token fencing, shared-versus-navigation-owned localization selection, readiness waits, process/ROS activation ordering, stop and cancellation settlement, terminal callback ownership, rollback, cleanup, and the stable application navigation view. | Fixed Nav2 commands, process groups, private map/parameter snapshots, parameter allowlists, known-free pose validation, and job logs remain in `NavigationJobManager`. ROS topics, freshness receipts, graph cardinality, autonomous lease, map/goal generations, stop-before-cancel behavior, and costmap calls remain behind `RosAgent`/`NavigationRosGateway`. |
| `LifecycleCoordinator` | Fail-closed cross-subsystem snapshot collection, dashboard-service blockers, action-specific control-bridge blockers, authenticated bridge-status freshness projection, the new-work idle gate, and lifecycle observer shutdown. | Fixed service identities and commands, confirmation, bounded dispatch, dispatch-time blocker rechecks, and worker state remain in `ServiceLifecycleManager` and `ControlBridgeLifecycleManager`. Closing the coordinator does not itself start, stop, or restart a service. |

These are coordinators around existing safety-owning managers, not replacement
implementations. There is still exactly one mapping manager, one navigation
manager, one saved-map catalog, and one ROS/control path.

## Shared coordination lock and interlocks

Mapping, navigation, manual-control acquisition, dataset start/stop, and local
service lifecycle mutations continue to use the exact same
`asyncio.Lock` owned by `ApplicationRuntime`. The coordinator method, or the
thin lifecycle/dataset/control transport entrypoint, acquires this lock around
the application decision and its corresponding reservation or manager call.
Moving code out of HTTP does not split the serialization boundary.

Important preserved interlocks are:

- new mapping work checks that lifecycle transitions are idle, navigation is
  idle, and no prior map task is active before it starts or reserves work;
- mapping stop intentionally remains a cleanup operation during a lifecycle
  transition, while still rejecting active navigation and unfinished map work;
- a stable running FAST-LIO pipeline is shared localization infrastructure,
  not a mapping conflict; only pipeline transitions and map operations block
  navigation startup;
- the externally observed clean mapping state `stopped` is normalized to
  `idle`, while unknown states fail closed as `failed`;
- manual and autonomous motion remain mutually exclusive through the single
  `ControlManager`; the application lock does not replace the control lease;
- lifecycle state providers treat missing, invalid, or failed snapshots as
  unavailable or active as appropriate, so a service transition cannot race
  work whose ownership is unknown.

The lower-level manager locks are unchanged. The application lock is never a
substitute for mapping process tokens, navigation job tokens, map revisions,
or ROS/control operation locks.

## Mapping task and filesystem transaction safety

`MappingCoordinator` retains one background task for map saving or local PCD
conversion. Task state is reported fail closed if it cannot be inspected. A
new save, conversion, edit, rename, or delete cannot pass while that task is
active.

Map saving still selects only the fixed `pointcloud3d` or
`pointcloud3d_2d` recipe after the manager validates the bounded map name. PCD
conversion preserves the following order:

1. validate the opaque source map and conversion values through the catalog;
2. capture the source revision;
3. reserve the manager's single local-operation job and exact job ID;
4. schedule the worker associated with that reservation;
5. pass the exact job ID to cancellation and final-publication guards;
6. publish only if the source revision and reservation remain valid.

If the conversion worker cannot be scheduled, the exact reservation is failed
and released. The coordinator never accepts or constructs a filesystem path.
All saved-map conversion, edit, rename, delete, rollback, and publication work
remains a catalog transaction inside configured roots.

## Navigation startup and ownership fencing

The navigation startup record retains a monotonically changing public
sequence and a private random token. It records the phase, pending and cancel
flags, exact mapping and navigation job IDs, whether localization was started
by navigation, terminal-cleanup ownership, and a bounded public error. The
private token is never returned through the browser contract.

A navigation start preserves this transaction order:

1. under the shared coordination lock, reject lifecycle activity, mapping
   operations or transitions, another navigation owner, stale parameter
   revision, and an invalid or stale opaque map revision;
2. run the ROS/control preflight before a cold localization launch can create a
   process side effect;
3. reserve one startup token and either pin the exact already-running shared
   mapping job or start a new localization dependency;
4. when navigation started localization, capture a fresh exact mapping job ID
   and mark it navigation-owned; never infer ownership from pipeline state;
5. wait boundedly for that exact localization job, then start the fixed
   navigation manager with its private map and parameter snapshots;
6. wait for the fixed runtime inputs and ROS readiness receipts, then repeat
   the ROS/control preflight immediately before motion can be armed;
7. activate the ROS navigation gateway and its autonomous lease, then project
   the stable public view;
8. commit only if the same token has not been fenced by stop or terminal
   cleanup.

The mapping coordinator's navigation port exposes only bounded activity/state,
manager snapshots, trusted mapping start, and exact
`stop_mapping_if_job_id`. It does not expose an unconditional stale-cleanup
path. A mapping pipeline that was already running remains shared and is never
stopped merely because one navigation session ends.

## Readiness, cancellation, and terminal cleanup

Readiness is not derived from UI telemetry. Navigation still requires the
configured manager prerequisites, pinned map and parameter revisions, the exact
localization job, bounded pipeline readiness, fixed fresh cloud/odometry and
runtime-health inputs, graph cardinality, localization/runtime readiness, and
the ROS gateway's autonomous-control safety gates.

Cancellation and rollback keep the existing settlement rules:

- STOP fences the startup token before cancelling its background task;
- an uncancellable `to_thread` manager or ROS operation is shielded and settled
  before rollback proceeds;
- navigation deactivation closes the velocity gate and signed autonomous lease
  before process cleanup;
- the fixed navigation process group is stopped even if ROS transport is
  already unavailable;
- navigation-owned localization is compare-and-stopped only by its exact
  mapping job ID;
- cleanup failure retains bounded ownership and a retry-visible failed state
  instead of reporting a false idle state;
- a terminal callback is accepted only for the exact navigation job currently
  owned by the startup record;
- terminal cleanup takes exclusive ownership of that record, and a ROS
  deactivation failure cannot skip process or localization cleanup;
- stale completion, cancellation, activation, goal, and terminal callbacks
  cannot mutate a newer transaction.

Goal cancellation still sends and flushes zero motion before the asynchronous
Nav2 cancellation request. Phase 6 does not move that ROS-level ordering out of
`NavigationRosGateway`.

## Lifecycle coordination

`LifecycleCoordinator` builds fail-closed blocker views from control,
navigation runtime, navigation process, mapping process/task, dataset capture,
and navigation-start ownership. Dashboard restart/stop remains blocked by
active robot work or an unknown required status. Control-bridge lifecycle
preflight retains its action-specific cleanup semantics, including the ability
to stop the local bridge when robot reachability itself is unavailable while
motion leases, actions, navigation, and conflicting dashboard lifecycle work
still block as required. Mapping and dataset capture are inspected but remain
independent of the signed motion bridge, so they deliberately do not block
bridge start or stop.

Authenticated bridge status retains the fixed 0.75 second stale boundary.
Lifecycle scheduling still requires explicit confirmation and the managers'
dispatch-time recheck. No coordinator changes systemd enablement or introduces
an arbitrary unit or shell interface.

## Application shutdown order

Shutdown remains fail closed and keeps motion cleanup ahead of potentially slow
data or mapping cleanup:

1. fence and cancel a pending navigation startup, then shield and settle it;
2. close lifecycle observers so no delayed service mutation can begin during
   application teardown;
3. deactivate the navigation ROS gate and autonomous lease while ROS is alive,
   then close the fixed navigation process manager;
4. compare-and-stop any exact navigation-owned localization dependency and
   retain ownership if that cleanup cannot be confirmed;
5. close/drain control and publish its final signed stop;
6. close the dataset writer after motion is closed so its bounded queue can be
   flushed safely;
7. close mapping-owned process groups and boundedly settle the retained mapping
   task;
8. stop the ROS facade and executor.

Repeated lower-level shutdown remains idempotent. Mapping preview, mapping,
navigation, lifecycle, and ROS cleanup continue to affect only resources owned
by their respective managers.

## Compatibility and HTTP boundary

The existing `/api/v1/*` paths, request fields, status semantics, bounded error
messages, and response projections remain the compatibility contract. Mutation
routes retain same-origin enforcement and explicit navigation-goal
confirmation. HTTP handlers delegate application decisions to the
coordinators; they do not rebuild transaction state, process ownership, shell
arguments, map paths, or ROS endpoints.

Go2 remains the full reference path. TurtleBot and Generic ROS2 mobile-robot
profiles retain their existing actual capabilities. Phase 6 does not add a
plugin framework, multi-worker coordination, a generic actuator interface, an
arbitrary ROS API, or a remote terminal.

## Preserved lower-level safety boundaries

- `MappingJobManager`: absolute trusted executables, fixed argv, `shell=False`,
  private process groups, bounded timeouts and logs, safe termination, map-name
  validation, known suffixes, private staging, and controlled publication.
- `NavigationJobManager`: fixed Nav2 launcher, private job directories and
  snapshots, map/parameter revision pinning, allowlisted values, known-free and
  robot-radius pose validation, bounded progress logs, and terminal job IDs.
- `SavedMapCatalog`: configured and managed roots, opaque IDs, symlink and path
  traversal protection, revision checks, file/point/grid limits, atomic pair
  transactions, and safe rename/delete/edit/conversion.
- `RosAgent`, `ControlTransport`, and `NavigationRosGateway`: fixed ROS
  endpoints, freshness and graph checks, exclusive lease, signed bridge,
  watchdog boundary, E-stop, goal and map generations, and stop-before-cancel.
- Dataset and discovery boundaries are unchanged.

## Verification policy and deferred work

Phase 6 is verified with local fake-backed coordinator tests, existing domain
manager and contract tests, full Python and JavaScript suites, syntax checks,
and source/diff review. Verification must not start or stop a real service,
launch mapping or Nav2, mutate a real map or dataset, publish a motion command,
send a navigation goal, or require connected robot hardware.

Phase 7 frontend modularization has not started. The current Vanilla JavaScript
UI and its public API usage are preserved; no framework migration, broad
`app.js` rewrite, or frontend state redesign belongs to this phase.
