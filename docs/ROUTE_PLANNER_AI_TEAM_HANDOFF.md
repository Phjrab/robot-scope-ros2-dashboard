# Route Planner AI Team Handoff

This packet defines the software boundary between perception producers and the advisory-only Competition Route Planner. It does not define a ROS topic, transport, or deployment target. Those integration names remain intentionally unspecified until the teams agree them.

## Contract files

- Canonical schema: `docs/contracts/route_planner/perception-envelope-v1.schema.json`
- Valid READY example: `docs/contracts/route_planner/examples/perception-success.json`
- Valid FAILED example: `docs/contracts/route_planner/examples/perception-failed.json`
- Intentionally rejected example: `docs/contracts/route_planner/examples/perception-invalid-unknown-field.json`
- Offline scenario schema: `docs/contracts/route_planner/scenario-v1.schema.json`

The envelope is JSON Schema Draft 2020-12. Unknown envelope and item fields are rejected. JSON numbers must be finite; `NaN` and `Infinity` are not JSON and are rejected by the fixture loader and Python contract.

## Common envelope

| Field | Contract |
|---|---|
| `schema_version` | Integer constant `1` |
| `source` | Producer identifier from 1 through 64 characters |
| `frame_id` | Fixed allowlist: `base_link` only |
| `observed_at_ns` | Unsigned 64-bit-compatible integer; live integration uses Unix-epoch nanoseconds |
| `sequence` | Unsigned 64-bit-compatible integer, strictly increasing within one provider stream |
| `state` | `READY`, `UNKNOWN`, or `FAILED` |
| `confidence` | Finite number from `0.0` through `1.0` |
| detection lists | `traffic`, `crosswalks`, `people`, and `aruco`; at most 32 items each |
| `underpass_blocked` | `true`, `false`, or `null` |

`observed_at_ns` is compared with the consumer's current nanosecond time. A READY snapshot is fresh through exactly 1.000 seconds of age and stale after that. A future timestamp is invalid rather than clamped to age zero. Offline scenarios use a fixed synthetic nanosecond origin and never read wall time.

## Model-output enums and interpretation

- Traffic `signal`: `RED`, `GREEN`, `UNKNOWN`. If `consecutive_frames` is supplied, stable GREEN requires at least two frames. Omitting it preserves the v1 producer-compatible READY behavior.
- Person `occupancy`: `CLEAR`, `OCCUPIED`, `UNKNOWN`. `OCCUPIED` blocks the relevant crosswalk requirement.
- Crosswalk/lane: `visible`, lateral offset, heading error, and both non-negative boundary distances are validated. Alignment readiness requires absolute lateral offset at most 0.15 m and absolute heading error at most 0.2 rad.
- ArUco: `docking_ready` is the only readiness decision exposed to the planner. Marker IDs and target pose are bounded supporting observations.
- Underpass: `underpass_blocked` reports scene state only. `SPECIAL_GAIT` remains operator-owned and is never converted into a control command.

Confidence does not override enum state, freshness, sequence, or any blocking result. It is metadata for operator and diagnostics use.

## UNKNOWN, FAILED, stale, and restart policy

- `UNKNOWN`, `FAILED`, stale, invalid, or missing perception projects safety requirements to `UNKNOWN`.
- RED and OCCUPIED project their matching requirement to `BLOCKED`.
- Sequence rollback is rejected, and the last accepted snapshot is not replaced.
- A producer restart requires a newly established sequence stream at the integration boundary. Offline `SERVER_RESTART` deliberately clears replay state and never auto-resumes a plan.
- Revision changes invalidate the recommendation. The replay does not load maps or trigger replanning side effects.
- None of these states authorize navigation, mission start, lease, ARM, deadman, or motion.

## Producer checklist

1. Generate all 12 envelope fields on every message; do not add transport- or command-specific fields.
2. Emit only `base_link` coordinates and nanosecond integer timestamps.
3. Keep one strictly increasing `sequence` per provider stream and document restart behavior before live integration.
4. Use `UNKNOWN` when the model cannot establish a result; do not synthesize permissive defaults.
5. Validate representative output against the schema and both boundary tests before handing it to Route Planner.
6. Agree topic/message/transport naming separately; this packet intentionally does not guess those values.

## Integration coordination checklist

- Record the perception-team owner/contact before transport integration: **TBD**.
- Record the Route Planner owner/contact before transport integration: **TBD**.
- Agree the provider restart/sequence reset handshake.
- Agree the shared timestamp basis and maximum clock-skew monitoring.
- Attach schema validation output and the relevant offline replay scenario IDs to the handoff.
- Keep live transport, ROS topic/message, and deployment decisions outside this software-only GP1 packet.

## Offline verification

```bash
python3 -m unittest tests.test_route_planner_scenario_replay -v
python3 scripts/replay_route_planner_scenario.py \
  --scenario tests/fixtures/route_planner/scenarios/traffic-red-to-green.json
```

The CLI reads only allowlisted fixtures, uses a deterministic virtual clock, and reports `side_effect_count: 0` plus individual zero counters.
