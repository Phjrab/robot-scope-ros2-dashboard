# Track G2 — Route Planner / Nav2 No-Motion Integration Prompt

Use a new isolated session after the Track G feature is integrated. Read `AGENTS.md` and `docs/ADR_COMPETITION_ROUTE_PLANNER.md` first. Confirm a clean checkout, exact `main`/`origin/main`, no concurrent checkout writer, and successful CI.

Goal: connect real saved-map annotations and a competition Route Graph to live read-only localization and a proven Nav2 planner-only preview, then export a Mission draft. This remains a no-motion task.

Required sequence:

1. Audit the exact saved 2D map ID/revision and annotation revision without altering runtime map data.
2. With the field team, create/verify named annotations for starts, intersections, safe holds, restaurant/destination approaches and docks, crosswalk waits/exits, and UNDERPASS entry/exit. Do not guess coordinates.
3. Build and import one bounded Route Graph pinned to those revisions. Validate every polyline on known-free 2D cells.
4. Start no robot service. Read current localization only if an already-running validated session exposes it; otherwise mark live guidance blocked. Do not publish `/initialpose`.
5. Connect live guidance to the existing pose snapshot and perception adapter contracts. Verify freshness and revision invalidation.
6. Add or enable Nav2 preview only if code audit proves a planner-only API cannot execute `NavigateToPose`, acquire a lease, activate a controller, or publish velocity. Otherwise retain the explicit blocked reason.
7. Export the selected route to a ready Mission draft and verify its route/revision link. Do not call Mission start.
8. Run focused and full Python/JavaScript/E2E tests, check no-motion evidence, commit, push and confirm CI.

Absolute prohibitions: Jetson deployment, robot service restart, runtime map mutation, `/initialpose`, Nav2 goal, Mission start, control lease, ARM, deadman, `/cmd_vel`, `/api/sport/request`, sit/stand, or any robot movement. AI model training/inference and control behavior remain out of scope.

Report exact map/annotation/graph revisions, guidance freshness evidence, planner-only status, Mission draft ID, zero command/action evidence, test counts, commit SHA and CI URL.
