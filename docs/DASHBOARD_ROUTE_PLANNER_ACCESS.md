# Dashboard Route Planner access

Status: implemented and hardware-free validated

## User-visible behavior

The main dashboard sidebar and Overview shortcuts now expose **Route Planner**
at `#route-planner`.  The page uses the same server-authoritative client and
panel view as the Cockpit panel, but provides a wide two-column workspace for
orders, recommendations, route selection, manual guidance, preview, and
Mission-draft export.

Only the currently visible Route Planner surface polls the backend.  Leaving
the standalone page, hiding the document, or unloading the page removes its
subscription and timer.  The Cockpit panel remains available and unchanged.

## Safety boundary

The standalone page does not add a renderer, WebSocket, ROS subscriber,
Navigation start, Navigation goal, Control lease, ARM, deadman, velocity, or
Sport request path.  Its visible banner retains the existing
`SERVER-AUTHORITATIVE · NO MOTION AUTHORITY` contract.  Mission export creates
only a draft through the existing bounded endpoint; it does not start it.

## Verification

- Node contract tests confirm the menu, page, shared client/view, responsive
  layout, page-scoped polling, and absence of control/navigation calls.
- Browser E2E opens the standalone page, saves an order, calculates and selects
  a recommendation, starts advisory guidance, then confirms polling is released
  on navigation away.
- The same E2E asserts zero Navigation start, Navigation goal, and Control ARM
  requests throughout the workflow.
- The repository-wide Python, JavaScript, browser, static, type, syntax, and
  secret-scan suites pass without robot hardware.
