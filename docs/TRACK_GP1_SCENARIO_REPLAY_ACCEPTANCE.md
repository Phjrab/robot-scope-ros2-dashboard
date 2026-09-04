# Track GP1 Scenario & Perception Replay Acceptance

## Scope and baseline

- Branch: `feature/competition-route-planner`
- Feature baseline before GP1: `0a8fc53ee845f0586befa547275a747465943f6f`
- `origin/main` was fetched and inspected read-only. Its two newer commits affected control transport and deployment documentation, with no overlap in the GP1 Route Planner allowlist.
- No merge, rebase, cherry-pick, main push, Jetson access, ROS access, service action, map runtime, initial pose, goal, Mission start, lease, ARM, deadman, or motion action was performed.

## Contract audit

| Contract | Previous implementation | Gap found | GP1 change |
|---|---|---|---|
| common envelope | Exact-key schema v1, bounded source/frame text, finite confidence, four bounded lists | No fixed frame or uint64 upper bound | Added Draft 2020-12 schema, `base_link` allowlist, source length, uint64 bounds |
| traffic | Fixed RED/GREEN/UNKNOWN enum and optional confidence/frame count | Explicit single-frame GREEN policy absent | Added stable-GREEN projection when frame count is present |
| crosswalk/lane | Visibility, offsets, heading, and boundary distances normalized | No language-neutral schema | Schema now mirrors all numeric and item bounds |
| person | CLEAR/OCCUPIED/UNKNOWN with optional distance/risk/confidence | No language-neutral schema/examples | Added schema, examples, and replay coverage |
| ArUco | Docking readiness, marker IDs, target pose, confidence | No language-neutral schema/examples | Added bounded schema, not-visible/partial/ready/stale scenarios |
| underpass | Nullable blocked observation; SPECIAL_GAIT remains operator-owned | Replay semantic not exposed | Added BLOCKED/UNKNOWN/OPERATOR_REQUIRED golden projection |
| freshness | READY and age at most 1 second | Future time was clamped to zero age; tests used wall time | Future timestamps now reject; replay uses deterministic clock |
| sequence | Mock provider required strictly increasing sequence | No uint64 ceiling or rollback scenario | Added uint64 ceiling and rollback golden test |
| mock provider | In-memory validated snapshots, no inference | No event replay, path boundary, or restart behavior | Added fixture-only replay with restart non-resume |

No duplicate perception model was introduced. Replay calls the existing order, graph, optimizer, perception, and guidance contracts.

## Deliverables and safety properties

- Perception and scenario JSON schemas plus AI-team success/failure/rejection examples
- Deterministic uint64-bounded virtual monotonic clock
- 33 competition scenarios across order, traffic, people, crosswalk/lane, ArUco, and composite cases
- Fixture-root-confined CLI and public-semantic golden comparison
- Restart and map/graph revision invalidation without automatic resume
- Explicit counters for control manager, navigation coordinator, ROS gateway, mission start, HTTP, ROS, socket, service, and motion; every counter remains zero
- Static test verifies that the replay module imports none of the runtime/control adapters

## Verification

Focused command:

```bash
python3 -m unittest tests.test_route_planner_scenario_replay -v
```

Result: 12 tests passed, including 33/33 deterministic golden scenarios.

Full software-only verification:

| Suite | Result |
|---|---|
| Route Planner focused regression | 39 passed |
| Complete Python unittest discovery | 1,057 passed |
| Complete JavaScript unit suite | 274 passed |
| Playwright browser E2E against local mock server | 33 passed |
| Ruff correctness scan | PASS |
| Repository configured strict mypy targets | PASS |
| New replay/clock/CLI strict mypy check | PASS |
| Frontend syntax | 55 modules passed |
| Tracked-source secret scan | PASS |
| Python dependency consistency | PASS |
| `git diff --check` | PASS |

The first Playwright launch was blocked before tests by the workspace sandbox's local-port policy. It was rerun with permission for the MacBook-only `127.0.0.1:4173` mock server and passed 33/33. No remote endpoint was contacted.

## Acceptance state

```text
SCHEMA_PASS
SCENARIO_FIXTURES_PASS
REPLAY_PASS
DETERMINISTIC_PASS
AI_HANDOFF_PASS
ROS_NOT_USED
JETSON_NOT_ACCESSED
MOTION_SIDE_EFFECTS=0
```

GP2 was not started.
