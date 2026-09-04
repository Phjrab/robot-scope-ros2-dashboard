# Track GP3 Rehearsal UI and Mission Dry-Run Acceptance

## Scope

- Branch: `feature/competition-route-planner`
- Prerequisites: GP1 `f5c94a8`, GP2 `8332214`
- Rehearsal is server-flagged, in-memory, fixture-backed, and software-only.
- No Jetson, ROS, service, map runtime, initial pose, navigation goal, Mission start, lease, ARM/deadman, Sport, or motion operation was performed.
- No main merge, rebase, cherry-pick, or push was performed.

## Delivered

- Server-authoritative scenario catalog and one active rehearsal session
- RESET, PLAY, PAUSE, STEP, fixed-speed selection, scrub, and deterministic off-route injection
- Distance-based virtual pose with tangent yaw and a 10 Hz declared ceiling
- Existing-SceneHost route/current-segment progress with no actual Nav2 path and no second renderer
- Deterministic recommendation metric breakdown and bounded alternative comparisons
- GP2-backed ordered cargo/pickup/drop-off rehearsal timeline
- Pure shared Mission waypoint compiler and revision-pinned dry-run endpoint
- Bounded JSON/Markdown rehearsal report
- Browser feature-flag hiding and explicit virtual-data banner
- Mock-backend counters for control, arm, deadman, velocity, navigation activation/goal, Mission create/start, Sport, and service restart

## Focused evidence

| Suite | Result |
|---|---|
| Python rehearsal/domain tests | 24 passed |
| Route Planner Python focused regression | 156 passed |
| Cockpit Route Planner JavaScript | 8 passed |
| Focused Playwright rehearsal flow | 1 passed |
| New Python strict mypy targets | PASS |
| Changed Python Ruff check | PASS |

The browser flow covers a LOW order, metric explanations, RED→GREEN, person occupied, ArUco docking ready, virtual pose, pause/step/scrub/speed/off-route, two pickups, delivery, Mission dry-run, report generation, one renderer, and all side-effect counters at zero.

## Full software-suite evidence

| Suite | Result |
|---|---|
| Python unittest discovery | 1,172 passed; 2 existing global route-count assertions failed |
| JavaScript unit | 278 passed |
| Playwright E2E | 34 passed |
| Repository Ruff | PASS |
| Configured mypy | PASS |
| Tracked-source secret scan | PASS |
| Python dependency check | PASS |

The two Python failures are deterministic inventory-count mismatches caused by the five new Route Planner endpoints: total HTTP routes changed from 99 to 104 and mutation routes from 57 to 60. Every mutation still passes the shared same-origin assertion. `tests/test_api_contract_phase8.py` is outside this track's change allowlist, so its fixed counts were not modified here. The allowed Route Planner API contract suite passes with all five endpoints explicitly inventoried.

## Latest main read-only audit

- Fetched `origin/main` at `6a3f510c759b71811f5c102372fc268c042f5a19`.
- The feature branch pre-GP3 head and its remote were both `83322147a0d7e514c2029eff85da4309266c6dc9`.
- Main-only commits are `0921b4f` (UDP dashboard handoff) and `6a3f510` (C4B retry deployment record).
- Their changed files are limited to wireless-control transport, Go2 bridge, related tests, and C4B documentation; none overlaps the GP3 changed paths.
- No main checkout, merge, rebase, cherry-pick, or push was performed.

## Core integration boundary

Active rehearsal disables all Route Planner mutations that could enter manual guidance or create a Mission draft. Entry also rejects active navigation, Mission, or mapping state. A system-wide fence for independent Control/Nav/Mission APIs requires an out-of-allowlist core dependency change and was not attempted:

```text
GLOBAL_REHEARSAL_INTERLOCK=BLOCKED_BY_CORE_INTEGRATION
```

This is a GP4 integration-readiness item, not authorization to change core runtime.

## Acceptance state

```text
REHEARSAL_MODE_PASS
SCENARIO_TIMELINE_PASS
VIRTUAL_POSE_PASS
3D_REPLAY_PASS
EXPLAINABILITY_PASS
CARGO_WORKFLOW_PASS
MISSION_DRYRUN_PASS
SIDE_EFFECTS=0
GLOBAL_REHEARSAL_INTERLOCK=BLOCKED_BY_CORE_INTEGRATION
```

GP4 was not started.
