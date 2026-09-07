# Track E0 spatial route catalog acceptance

Status: `ROUTE_CATALOG_SOFTWARE_PASS`

```text
ROUTE_CATALOG_SOFTWARE_PASS
ROUTE_EDITOR_NOT_IMPLEMENTED
ROUTE_EXECUTION_NOT_RUN
MOTION_NOT_RUN
```

## Scope and architecture

Track E0 adds a non-executing, revisioned authoring catalog.  It does not
modify the existing annotation-based Mission queue or Route Planner
recommendations.  Runtime ownership is one `SpatialRouteCatalog` under the
single-process `ApplicationRuntime`; the default private root is
`~/.local/state/robot-scope/spatial-routes`.

| Contract | Result |
|---|---|
| Schema | `robot-scope.spatial-route.v1`, strict unknown-field rejection |
| Identity | 24-hex opaque route ID and content-derived 64-hex revision |
| Map pin | exact family, PCD member, and occupancy member IDs/revisions |
| Storage | immutable mode-0600 revision + atomic mode-0600 current pointer |
| Update | copy-on-write with current-revision CAS |
| Limits | 4,096 raw poses, 1 MiB semantic document, 1,000 m, 100,000 validation samples |
| Execution projection | deterministic, corner-preserving, at most 32 poses |
| Motion authority | `NONE` |

## Validator acceptance

| Check | Result |
|---|---|
| Exact family/revision mismatch | PASS: fail closed |
| Finite/bounded poses and optional visual-only z | PASS |
| Known-free circular 0.25 m footprint | PASS |
| Unknown/occupied/map boundary | PASS: rejected |
| Occupied segment between valid-looking endpoints | PASS: rejected |
| KEEP_OUT | PASS: rejected |
| SLOW_ZONE / WAIT_ZONE | PASS: tagged, not converted to commands |
| Bounded clearance evidence | PASS: conservative lower bound |
| Duplicate/yaw/RDP/max-segment utilities | PASS |
| 4,096-pose iterative simplification | PASS |
| Final yaw preservation | PASS |
| Simplified projection revalidation | PASS |
| FLEXIBLE eligibility | PASS: data-only; no Mission created |
| CORRIDOR / STRICT | PASS: execution ineligible |

## Filesystem and HTTP acceptance

| Check | Result |
|---|---|
| No caller-supplied path/topic/script/hook | PASS |
| Private root and files | PASS: root 0700; files 0600 |
| Direct root/current symlink | PASS: rejected |
| Immutable revision publication | PASS |
| Atomic pointer failure | PASS: prior current revision retained |
| Create/update/delete/copy CAS | PASS |
| Same-origin on every mutation | PASS |
| Competition Lock on every mutation | PASS |
| API inventory updated without weakening assertion | PASS |

## Safety state

No robot, ROS graph, Jetson service, sensor pipeline, map artifact, Mission,
Navigation session, initial pose, goal, lease, ARM, deadman, non-zero command,
or robot movement was used for software acceptance.  The new API cannot create
or start a Mission and cannot reach ControlManager or NavigationRosGateway.

## Test record

The focused E0 and API-contract suites passed.  The completed local validation
record is:

| Command | Result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -q` | PASS: 1,360 tests |
| `node --test --test-reporter=dot tests/*.mjs` | PASS: 281 tests |
| `npm run test:e2e:ci` | PASS: 35 tests |
| `.venv/bin/ruff check robot_dashboard scripts` | PASS |
| `.venv/bin/python -m mypy --config-file mypy.ini` | PASS: 4 configured files |
| `.venv/bin/python scripts/check_repository_secrets.py` | PASS |
| `node scripts/check_frontend_syntax.mjs` | PASS: 56 modules |
| `git diff --check` | PASS |

Remote CI is recorded after publication of the focused completion commits.

## Handoff

```text
PHASE=E0
SOFTWARE_STATUS=ROUTE_CATALOG_SOFTWARE_PASS
HARDWARE_STATUS=NOT_REQUIRED
ROUTE_SCHEMA=robot-scope.spatial-route.v1
STORAGE=PRIVATE_IMMUTABLE_REVISIONS_ATOMIC_CURRENT_CAS
MAX_RAW_POSES=4096
MAX_EXECUTION_WAYPOINTS=32
VALIDATOR=EXACT_D0_FAMILY_2D_FOOTPRINT_SEGMENT_ZONE
SUPPORTED_MODES=FLEXIBLE,CORRIDOR,STRICT
EXECUTABLE_MODES=NONE_IN_E0
ROUTE_EDITOR_NOT_IMPLEMENTED=true
ROUTE_EXECUTION_NOT_RUN=true
MOTION_NOT_RUN=true
E1_READY=true
```

Track H remains blocked by its independent actual short-goal PASS activation
gate.  D3 remains blocked until a stationary D2 live candidate exists.  E1 is
the next repository-only phase; it was not started in this phase.
