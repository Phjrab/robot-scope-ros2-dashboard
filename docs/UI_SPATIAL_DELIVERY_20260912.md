# Delivery configuration, dashboard polish and E1 authoring release

Scope: visit-specific `sit_then_rise` configuration, repeated Mission visits,
order-sheet layout/readability refinements, and the E1 spatial route editor
inside the existing Route Planner. User authorized software verification and
external dashboard deployment on 2026-09-12.

The first verification found and fixed a missing function-closing brace in the
spatial editor and annotation rendering that needed the actual nested `pose`.
Visual inspection also found that the editor occupied only one Planner column;
it now spans the panel width. Existing Cockpit coverage now closes the sensor
launcher before operating Mission controls and initializes both annotation
fixtures before page load, avoiding asynchronous fixture replacement.

Software evidence:

- Python: 1,459 tests, OK, one skipped.
- JavaScript: 321 tests, all passed.
- Focused browser: arrival-action persistence/reordering and disabled execution;
  rotated-map drawing, point deletion/undo, corridor-policy persistence, final
  orientation, and preserved edits after a 409 revision conflict.
- Existing E0 tests retain map-family, footprint, segment and zone rejection.
- Application Ruff, configured mypy, frontend syntax and diff whitespace checks.
- Full browser suite: 50 passed. Exact deployed commit is recorded in the handoff.

Deployment plan: immutable full-commit release, reuse unchanged verified native
registration artifacts only after source comparison, preserve the existing
private schematic assets, and retain the previous release for rollback. Switch
only the external dashboard and restart only `robot-scope.service` after idle
Navigation/Mission and disarmed zero-command checks. Do not restart the onboard
Bridge or sensor services. Verify active process cwd, served source hashes and
read-only API state afterward.

Remaining feature limits: `sit_then_rise` is configuration only. Missions with
it remain blocked because no completion-aware posture executor is implemented.
CORRIDOR/STRICT remain authoring-only; no actual constrained Nav2 execution or
spatial-route Mission export is added. Software validation is not physical
posture, stopping-distance or constrained-driving acceptance.
