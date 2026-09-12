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

## Deployment result

Deployed application release `3a91dd6bb13d1f9a4a32e8ab582b25af13c7754c`.
Archive SHA-256: `36e1bfe19ad8f2703396d94567de49d23aa7c19d6cd161a6f2dba7d6beea195b`.
External Jetson focused Python tests passed 29/29 before activation.
The fixed dashboard restart helper reported active/running, PID 260814,
`NRestarts=0`; process cwd resolved to the new full-commit release.
Previous release `bd9b9416ae455ea6e31fbdf2f8e6276d518ef813` is retained.

Before and after: Navigation/Mission/Mapping idle, no control lease, deadman
false, exact-zero command, Bridge move_count=0 and action_count=0. Bridge
release remained `2c5eeb3ed394b566ac89dc03fdf1c133729fdd06`. Preview recovered
to running. No robot-side service restart or robot command was issued.

HTTP hashes of the Mission panel, spatial editor and polish stylesheet matched
the deployed files. Live browser inspection listed ten occupancy maps and loaded
`map_20260912_165206_crop_edited_crop_edited_edited` with its image/annotations.
No live route or Mission was saved during that inspection.

The first Linux CI run passed 49 browser tests and failed only when saving the
new screenshot to a macOS-only `/private/tmp` path. The follow-up test-only fix
uses Playwright's per-test output directory; the focused browser rerun passed.
It changes no deployed application files and requires no service restart.
