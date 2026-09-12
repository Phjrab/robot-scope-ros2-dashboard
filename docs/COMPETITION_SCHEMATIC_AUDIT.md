# Competition schematic integration audit

Local baseline: `78224f45c8ddec13ff5f99df6c476ccc292f9929`, clean main.
Instructions: supplied gangnam_manual_guidance_pack START_HERE and prompts 01–07.
User overrides repository publication policy: no commit/push. No Jetson/robot
connections, deployment, service changes, goal or Mission execution/export.

## Existing contracts and selected extension points

| Owner | Existing behavior | Extension |
|---|---|---|
| route_planner/graph.py | Exact SavedMap/annotation pins, metric coordinates and known-free clearance | Unchanged; separate schematic validator |
| route_planner/optimizer.py | Deterministic Dijkstra and venue permutations; metric time costs | Shared search with injected relative-cost provider |
| route_planner/orders.py | Catalog IDs, menus, quantity, order revisions | Reused without weakening validation |
| application/route_planner_coordinator.py | Shared lock, active-task gates, persistent planner state | Separate DEMO/FIELD schematic state, same coordination boundary |
| route_planner/state_store.py | Bounded private atomic storage | Reused with separate schema/store directory |
| cockpit/route_planner_client.js and panels/route_planner_panel.js | Common order/route UI, default AUTO_NAV2, map overlay | Explicit schematic context, MANUAL_GUIDANCE only, isolated schematic view |
| api/routers/route_catalogs.py | Composes route planner transports | Separate typed schematic endpoints |

No-motion call graph: common order UI → schematic transport → coordinator lock
and existing read-only activity gates → dedicated catalog/order/search/manual-event
state. No Mission, Navigation, Control or service mutation port is passed to the
schematic engine. Schematic identifiers cannot pass existing saved-map route IDs.

Static assets use local allowlisted files, not arbitrary SVG/URLs. Supplied original
images are local reference-only and must not be published until rights are confirmed.
No Sites, new web framework, CDN, second JavaScript route engine, synthetic occupancy
map, guessed field coordinates or metric calibration is introduced.

Baseline before edits: Python 1438 tests OK (skipped 1), JavaScript 301 passed.
Final combined worktree: Python 1452 OK (skipped 1), JavaScript 306 passed,
new real-backend browser suite 4 passed, existing Route Planner browser suite 8 passed.
Exact scope, historical test limitations, and handoff are recorded in
COMPETITION_SCHEMATIC_ACCEPTANCE.md. Unrelated concurrent mission/order edits
were preserved, including non-overlapping changes in the shared panel/CSS.
