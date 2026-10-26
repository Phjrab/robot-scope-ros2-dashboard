# C1 integration map — 2026-10-24 KST

Inspected baseline: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
This is a code-based integration design, not a native registration or a device qualification. D0/C2/C3/C4 branch submissions have not been reviewed or approved for integration by C1. Their implementations are not copied, imported or presumed complete. No public DTO, enum, runtime owner or device binding changes in this C1 patch.

## Canonical contracts and exact connection points

Paths below are relative to repository root. Method names describe current code, not proposed callable APIs.

| Boundary | Canonical location / signature | Integration constraint |
| --- | --- | --- |
| Definition/action | `robot_dashboard.mission_routes.models`: `DefinitionInput`, `CompetitionDefinition`, `CompetitionAction`, `Visit`, `Pose`; `docs/mission-competition/definition.schema.json` | Reuse `competition.v0.1` / `mission-action.v0.1`. Pose is map x/y in metres and yaw in radians. Preserve distinct visit/step IDs, map/annotation/route/revision pins and DRAFT/unplaced state. Optional serializers preserve legacy JSON shape/digest. |
| Observation | `robot_dashboard.mission_routes.competition_contract.Evidence`; `docs/mission-competition/evidence.schema.json` | Reuse `competition-evidence.v0.1`; producer epoch/sequence/config hash and owner/run/step/goal/generation must match. This trusted DTO has no public HTTP ingestion route. Never add a manual GREEN endpoint. |
| API gate | `robot_dashboard/api/routers/mission_routes.py`: `service(request)`, `write_gate(request)`, `require_same_origin` | Authoring, run and action HTTP handlers delegate to the existing service and competition gate. A UI label or received package cannot bypass these gates. |
| CAS/ledger | `MissionRoutes.write(body, identifier=None, copy_from=None)`, `_transaction(request_id, payload, operation, safety=False)` in `mission_routes/service.py` | Request replay returns the same receipt/run; changed payload conflicts. Uncertain outcome requires readback. Keep active-definition edit restriction, bounded ledger and immutable run snapshots. Stop remains available when durable audit writes fail. |
| Store | `robot_dashboard.mission_routes.store.PlanStore`, `application.mission_coordinator.MissionStateStore` | Existing private, bounded, atomic storage only. No duplicate native persistence owner; no implicit migration of legacy definitions. |
| Run admission | `MissionRoutes.create_run(identifier, RevisionRequest)`, `action(identifier, action, RunActionRequest)`, `preflight_dispatch(mission)`, `require_run_context(mission)` | `create_run` currently blocks competition actions. `_admission` is an opaque identity shared with the coordinator, not an HTTP token. Do not clear blockers just because adapter software exists. |
| Composition | `mission_routes/wiring.py:configure_mission_routes(runtime, state_root, native_planner_window=False, policy_provider=None)` | Current composition point. Reuses `runtime.mission`, navigation, maps and routes; sets guard/run-observer/preflight hooks. After actual C2 delivery, integrate a separate default-off boundary here without instantiating a competing coordinator. |
| Shared lock | `application.runtime.ApplicationRuntime.pipeline_coordination_lock`; `NavigationCoordinator.coordination_lock` | Same exact `asyncio.Lock` across pipeline transitions. Mission `_operation_lock` and service `_lock` have different purposes; do not hold a non-reentrant coordination lock while awaiting a navigation method that reacquires it. |
| Mission ownership | `MissionCoordinator.create`, `start(..., admission=...)`, `pause`, `resume`, `retry`, `abort`, `abort_active`, `blocks_navigation_goal` | One active owner and monitor generation. C2 must preserve admission, stop requests and dispatch preflight. Existing private hooks are integration seams, not a new public contract. |
| Navigation | `application.navigation_coordinator.NavigationCoordinator.send_goal(*, map_id, map_revision, x, y, yaw, confirmed)`; `send_annotation_goal`; `cancel_goal(*, goal_id)`; `view()` | Returns `navigation.goal` with lowercase state and actual goal ID. Translate to Evidence uppercase states explicitly. Goal response receipt is not completion or physical STOP. Never invent/reuse a goal ID. |
| Cancellation | `MissionCoordinator._cancel_current_locked(mission)` | Cancels only the matching owned ID, then polls `view()` for the same ID to become terminal. Timeout or ID mismatch retains the uncertain ownership fence. This terminal observation is not a hardware stop ACK; C2 must keep cancellation, arbiter HOLD ACK and measured STOP distinct. |
| Operational context | `mission_routes.context.NavigationContext.snapshot()` | Requires current map revision, operational pose/source/process generation, admission and enforced policy. Context revision intentionally excludes heartbeat changes. Maps observation candidates cannot substitute for operational pose. |
| Fixture execution | `mission_routes.competition_executor.ContractExecutor`, `FixtureRuns`; `MissionRoutes.create_fixture_run` | Fixture only; constructor rejects non-fixture adapter. Server monotonic timers continue after browser close, and restart interrupts runs. Keep this executor intact; no native rename or mode flip. |
| Existing camera owner | `ros_agent.RosAgent.camera_snapshot(source_id='go2_front')`, `camera_snapshots(source_ids)`; `ros/cameras.py:CameraHub` | C4 receives supplied bytes/metadata at an adapter boundary. Snapshots expose fixed source IDs, stream identity, frame data and freshness/clock diagnostics. Reading a snapshot does not prove synchronized capture time. Do not instantiate RosAgent, reopen streams, claim camera demand or start a camera from a replay package. |
| STOP/control | `app.py:control_stop` → `RosAgent.control_estop` → `control.ControlManager.emergency_stop`; navigation stop also calls `mission.abort_active(reason='navigation_stop')` | Preserve software stop latch, lease revocation and existing bridge. A native adapter must observe these interlocks, not send a competing velocity publisher or claim SDK acknowledgement is physical STOP. |
| VM provenance | `mission_routes.competition_assets.checked_file`, `arena_manifest`, `vm_evidence` | Keep source checksum verification, original snapshot publications, map-transform uncertainty and DRAFT course. D0 updates need actual new bytes/manifest/checksum review; never disable validation. |
| Per-action UI | `competition_contract.capabilities`, `readiness`; `static/features/mission_route/competition.js`, `workspace.js` | Every action stays `native_enabled=false`; each component has its own `UNCONNECTED` reason. Fixture/VM/replay/native simulation/robot evidence remain distinct. |

## Default-off native design for the later integration

1. After explicit integration approval, pin each approved review branch to its exact commit and inspect its merge base, allowed paths, all added/deleted files and reported tests. Compare against current main; reject unexpected ownership changes and model/private data in Git artifacts. Combine first on a separately authorized integration branch.
2. Review C2's concrete adapter API before adding imports at the composition point. Adapter code presence is a software fact only. Unconfigured binding keeps competition `create_run` blocked and does not create a task, ROS client, camera owner or bridge.
3. Bind observation provenance at the trusted receiver, not from browser fields. Preserve producer epoch/sequence and retire old epochs before assigning a local receipt sequence/time. Compute source age only in a known/synchronized clock domain. Preserve uncertainty; do not subtract remote monotonic clocks.
4. Source age, receiver constraint TTL and continuous observation gap are separate. Current VM integration default constraint TTL is **0.25 s**; fixture evidence freshness/gap is **0.5 s**. Neither value is a production qualification or permission to widen the other.
5. Hold transition waits for actual approach completion or matching cancellation acknowledgement, then current-generation arbiter HOLD acknowledgement and measured feet/STOP. Departure requires qualified fresh GREEN and a fresh exit goal. RELEASE does not replay a cached command. Signal wait must not run Nav2 progress recovery for the completed approach leg.
6. Preserve per-action requirements: adaptive navigation needs pose/body, collision and arbiter bindings; traffic additionally needs detector/state, feet and physical STOP; terrain needs gait execution; parking needs full-body containment/posture/STOP; OUT needs full-body crossing. Missing one blocks the applicable action even if other actions have software or simulation evidence.
7. C4 frame replay may validate loading/inference/DTOs, but not real-time onboard capture, time synchronization, foot geometry or Jetson latency. C3 native simulator evidence must retain exact ROS/version/config provenance and never activate robot capabilities. D0 planar/SIM_GT results do not qualify gait, terrain or physical stopping.
8. Before native enablement, test lost ACK/goal replacement, epoch/config/sequence replay, stale GREEN, STOP/cancel races, restart, active edits, ledger uncertainty, legacy shape/digest, owner conflicts and camera/Maps regressions with explicit no-hardware ports. Actual device binding and field qualification are separate work.

## Current integration status

| Role | Exact branch HEAD reviewed in C1 | Applied |
| --- | --- | --- |
| D0 | No | No |
| C2 | No | No |
| C3 | No | No |
| C4 | No | No |

The attached RGB dataset is an input for C4, not a C1 implementation. C1 does not alter or publish its images/labels. C1 submits only to `review/20261024-c1-ci-integration`; no main write, PR, merge or cross-role cherry-pick is authorized at this submission stage. Reading sibling chat context to identify C1 did not authorize messaging those chats or importing unfinished working trees.
