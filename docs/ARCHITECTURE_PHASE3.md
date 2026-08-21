# Phase 3 Runtime Container and API Router Boundary

This document records the Phase 3 ownership move. It supplements the Phase 0
baseline and does not describe later RosAgent or coordinator extraction work.

## Runtime ownership

Before Phase 3, `robot_dashboard/app.py` independently owned module globals for
the ROS agent, six managers, two background tasks, navigation state, locks,
caches, browser control bindings, and discovery. Phase 3 replaces those mutable
owners with one `ApplicationRuntime` instance attached to `FastAPI.app.state`.

`ApplicationRuntime` explicitly owns:

- `RosAgent`, `SavedMapCatalog`, `MappingJobManager`, `NavigationJobManager`,
  both lifecycle managers, and `DatasetCaptureManager`;
- mapping and navigation-start asyncio tasks;
- the shared pipeline coordination lock and navigation-start state lock;
- fenced navigation-start state;
- point-cloud/JSON caches, browser control bindings, and bounded discovery.

The deployment remains `uvicorn workers=1`. The container does not introduce a
plugin registry, multi-worker coordination, dependency injection framework, or
new public configuration authority. Independent container instances have
independent mutable state, which permits isolated application tests later.

## Transport routers

The following route groups now live under `robot_dashboard/api/routers/` and
resolve the runtime from the current request/WebSocket application:

| Router | Preserved responsibility |
| --- | --- |
| `system.py` | Dashboard lifecycle and control-bridge lifecycle status/start/stop transport. |
| `telemetry.py` | Health, state, topics, sources, point-cloud/map/joint/pose HTTP and observation WebSockets. |
| `cameras.py` | Camera catalog and fixed-source WebSocket demand-token lifecycle. |
| `dataset.py` | Capture start/stop/status and bounded gallery/image transport. |
| `discovery.py` | Fixed product catalog, bounded local discovery, target selection and disconnect. |

All existing paths, status codes, strict request bodies, same-origin mutation
checks, stream cleanup, response bounds, and cache headers remain in place.
Request schemas moved without semantic changes to `robot_dashboard/api/models.py`.

## Deliberately retained in `app.py`

Control, mapping, saved-map mutation, and navigation routes remain beside their
current application orchestration for this phase. In particular, the complete
navigation startup transaction remains outside the new routers:

- startup token and cancellation fencing;
- shared versus navigation-owned mapping job identity;
- exact navigation job identity and stale terminal callback rejection;
- readiness waits, autonomous lease activation, rollback, and shutdown cleanup.

Moving that transaction into a transport router would violate the dependency
direction. Its later move belongs to the application-coordinator phase. The
current compatibility helpers remain temporarily so those safety paths are not
redesigned during this ownership-only phase.

## Safety invariants preserved

- No route accepts a shell command, executable, arbitrary ROS topic, or raw
  filesystem path.
- Control continues through `ControlManager`, signed transport, and the
  standalone watchdog bridge with the same exclusive lease and E-stop rules.
- Mapping command specifications, process-group ownership, output staging, and
  navigation compare-and-stop ownership are unchanged.
- Saved-map opaque IDs, revision checks, symlink/path boundaries, and output
  limits are unchanged.
- Dataset quotas, secured directories, atomic publication, camera tokens, and
  shutdown ordering are unchanged.
- Dashboard shutdown still closes navigation/control before dataset, mapping,
  camera/ROS teardown.
- No service start/restart, mapping launch, navigation goal, robot command, map
  mutation, or dataset operation was performed as part of this refactor.

## Remaining migration boundary

`app.py` is materially smaller than the Phase 0 baseline, but still contains
the intentional application coordination listed above. Phase 4 should address
the RosAgent observability plane only. Mapping/navigation coordinator extraction
must wait for its designated phase rather than being folded into transport
routers.
