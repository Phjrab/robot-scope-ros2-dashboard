# Track GP2 Advisory Behavior Acceptance

## Scope

- Branch: `feature/competition-route-planner`
- GP1 prerequisite: commit `f5c94a89a7c9f57db5ce32c483592a3622bce7b6`
- Work is software-only and reuses the GP1 Route Planner perception, guidance, route, order, virtual-clock, scenario, and replay contracts.
- No main integration, Jetson access, ROS/service action, map runtime, initial pose, navigation goal, Mission start, lease, ARM/deadman, sport request, or motion was performed.

## Delivered

- Exact common advisory snapshot contract with a closed advisory vocabulary and prohibited control-shaped output fields
- Crosswalk, docking, underpass, and delivery state machines
- One-active-behavior composite coordinator with fail-closed priority
- Stable-GREEN/person/alignment/boundary crosswalk checks, including the supplied three-feet-outside rule without FK
- Venue/zone/confidence/target-jump docking checks without visual servo
- Operator-owned underpass handling without gait/action calls
- Capacity-five ordered pickup/drop-off mock workflow with bounded confirmation audit and restart gate
- GP1 replay integration plus a 33-scenario advisory golden fixture

## Safety evidence

- The production behavior package exposes decisions only.
- A syntax-tree regression test rejects runtime control/navigation call symbols in the behavior/replay implementation.
- Every GP1 replay scenario asserts `side_effect_count == 0` and all named side-effect counters equal zero.
- Recovery tests require new evidence or renewed confirmation after stale data, rollback, readiness loss, revision change, pose loss, or restart as applicable.

## Verification

Focused behavior verification passes 93 tests, including more than the required 40 explicit transition tests and all 33 GP1 advisory golden projections.

| Suite | Result |
|---|---|
| Route Planner focused regression | 132 passed |
| Complete Python unittest discovery | 1,150 passed |
| Complete JavaScript unit suite | 274 passed |
| Playwright browser E2E against local mock server | 33 passed |
| Ruff production/scripts and GP2 paths | PASS |
| Repository configured strict mypy targets | PASS |
| GP2 behavior/replay strict mypy check | PASS |
| Frontend syntax | 55 modules passed |
| Tracked-source secret scan | PASS |
| Python dependency consistency | PASS |
| `git diff --check` | PASS |

Playwright used only the MacBook-local `127.0.0.1` mock server. No remote endpoint or hardware was contacted.

## Acceptance state

```text
CROSSWALK_ADVISORY_PASS
DOCKING_ADVISORY_PASS
UNDERPASS_ADVISORY_PASS
DELIVERY_WORKFLOW_PASS
COMPOSITE_DECISION_PASS
CONTROL_OUTPUTS=0
NAVIGATION_ACTIONS=0
```

GP3 is not started.
