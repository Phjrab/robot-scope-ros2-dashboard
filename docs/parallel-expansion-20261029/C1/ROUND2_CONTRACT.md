# C1 round 2 canonical contract

MapSourceDescriptor/FusionRequest/FusionProposal remain **0.1**, preserving the
verified C2/D1 HTTP flow. Observation, ObstacleFrame, CollisionAssessment and
ScenePacket additionally support **0.2**. v0.1 parsing remains available.

The actual C1 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 interval uses
`host_clock_id/start_monotonic_ns/end_monotonic_ns`, not the follow-up prompt's
`clock_domain` spelling. Those three names remain canonical. v0.2 host receipt
and interval ns are decimal strings (0..2^63-1). v0.1 uses integers and cannot
safely be round-tripped through JS Number beyond 2^53-1. Source stamp_ns remains
a decimal string. Sequence/generation remain JS-safe integers.

`time_binding.normalize_collision_assessment` is the single compatibility
boundary. It accepts D3's clock_domain/from_ns/until_ns only with an explicit
ClockBinding(source clock, source epoch, host clock, signed offset, uncertainty,
binding ID). Uncertainty shrinks the interval; original expiry is never reset to
receipt time or now. Original interval and conversion provenance are retained.
Unknown clocks, mixed aliases, negative/reversed/oversized intervals are rejected.
No browser clock is assumed equal to a server clock. No UNKNOWN/CLEAR, coverage,
command permission or full observation reference is fabricated by conversion.

Executable small example: `tests.expansion_contracts.test_time_binding.assessment`
and the corresponding test converts across 2^53 without precision loss. Run:

```sh
python -m unittest tests.expansion_contracts.test_time_binding -v
```

## Exact current producer/consumer matrix

| Role / pinned SHA | Actual contract | Current compatibility |
|---|---|---|
| D1 cbedd05ba6f97dad5506e8003302f689ed8fcb4c | solve_contract, map 0.1 | retained; real composition next |
| C2 5eed1a9959ca25a4f30bd5b5712806a5ad660c51 | map HTTP 0.1 | retained; short compatibility check then frozen |
| D2 c0d266e290a2d29c173d3b83520f8c96efea9447 | Tracker.step()['obstacle_frame'], observation 0.1 | explicit envelope upgrade to 0.2 |
| D3 09b68b692fa4b7ccdea39b1a16e3ff150794e12d | source-clock string interval; full metadata refs | explicit clock-bound converter; refs retained |
| C4 b9d700d754f0d3d43b9afdcffcb86e9deb7b1020 | C1ObstacleProjection emits 0.1; C1SceneSink forwards obstacle only | service may opt in to 0.2 upgrade; assessment is not forwarded by this sink |
| C4 same SHA command.constraint_from_d3 | requires freshness.c4_binding, command ref, clock_id/valid_from_ns/valid_until_ns | FAIL closed with current D3; conversion is not authorization |
| C3 92658bccc253f31552415f9c9d667bbd28957a06 | only 0.1, requires sources.display profile and valid_until_ns | FAIL with actual C1 snapshot; consumer follow-up required |

No counterpart files are modified or copied into this branch. Scene locations,
actual composition results and measured byte limits will be added in ROUND2.md.

Round-2 implementation additionally migrates receipt ns inside provenance/full refs
losslessly, and defines actual scene locations/limits in [ROUND2.md](ROUND2.md).
No nested reference identity or original source expiry is discarded.
