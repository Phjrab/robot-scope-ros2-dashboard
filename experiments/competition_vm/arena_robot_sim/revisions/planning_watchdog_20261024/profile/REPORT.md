# Frozen initial-OPEN planning profile, 2026-10-24

## Result

The unchanged continuous-progress candidate's initial `build_path` takes a median **2.206 s** in this shared VM (five unprofiled calls: 2.130–2.272 s; sample p95 2.264 s). This is **22.1 times the 0.1 s controller tick** and **8.82 times the 0.25 s sensor-freshness window**. It cannot be treated as an in-tick real-time planner here.

An isolated, per-call exact-coordinate cache around the smoothing `allowed()` predicate produced **bit-for-bit identical float64 [x, y, yaw] output for all 411 waypoints** in this fixture. Median time fell to **1.306 s** (five calls: 1.286–1.388 s), a measured **1.69x speedup**, still **13.1 ticks / 5.22 freshness windows**. This is an experimental result, not adoption or real-time qualification.

## Provenance and scope

- Frozen source: `/workspace/scratch/b09eacf6919d/robot-scope-left-slalom-20261024/experiments/competition_vm/arena_robot_sim/revisions/curved_progress_20261024/simulate_curved.py` and `run_candidate.py`.
- Actual `run_candidate.OPEN` layout; `YAW_MAX = 0.12` as selected by the OPEN runner; pose is `base.START`.
- Actual `static_grid()`, ideal four-height `base.sim.raycast(base.sim.mesh(OPEN), pose)`, and `Occupancy.update(Scan(...), pose, 0)` construct the fixture. `grid = observed | unknown` comes from `Occupancy.masks(0, ttl=2)`.
- Hidden geometry was used only by the virtual sensor, as in the frozen simulator. No hidden-truth raster was constructed or supplied to planning.
- Grid is 600x800, with 425,784 static blocked cells, 425,903 observed blocked cells, and zero unknown cells at the initial scan. Zero unknown reflects the simulator's known-free map prior; it does not imply all cells were seen.
- Setup wall time is reported separately from planner time. Five unprofiled calls plus one cProfile call per variant. All calls in each variant reproduce the same path. Source SHA-256 hashes were checked unchanged at completion.
- Initial snapshot only. No complete trajectory, other pose/layout, real sensor, hardware, deadline-distribution, memory-pressure, watchdog, or concurrent-thread safety qualification. No renderer, device access, installation, network, publication, or source-repository edits.

## cProfile hotspots

Baseline instrumented call: 2.616 s, 1,452,273 calls. Inclusive times overlap and must not be added.

| Function | Calls | Inclusive seconds | Share of total |
|---|---:|---:|---:|
| Smoothing `allowed` | 73,620 | 2.192 | 83.77% |
| `polygon_collision` | 74,278 | 2.121 | 81.08% |
| `plan` (A*) | 1 | 0.141 | 5.39% |
| Both distance transforms | 2 | 0.041 | 1.57% |

The major cost is repeatedly checking the padded polygon during 45 smoothing passes, not the A* search. `polygon_collision` alone uses 1.371 s self time (52.4% of total); polygon construction and repeated scalar min/max calls contribute to its inclusive time.

## Isolated optimization

`memoized_build_path.py` is a copy in this separate experiment directory only. The sole algorithmic change is a function-local `lru_cache(maxsize=None)` keyed by the exact `(x, y)` tuple for `allowed()`. No coordinate rounding, removal of guards, changed footprint, changed grid, or inter-call cache occurs. The same grid and validity mask are fixed for the duration of each call. Cache info: 32,489 hits and 41,131 misses / live entries; 44.13% of predicate evaluations reused an exact prior result. Cache lifetime is one build call. General memory bounds/pressure were not benchmarked.

Output equality was asserted on uint64 views of all float64 entries, including yaw, against the frozen baseline; it was not tolerance-based. Baseline path JSON SHA-256: `5c6c7f607d9dd2beeeca22273a41ba2bada63083ff5b490d905c03dace947e97`.

This optimization does not justify relaxing the watchdog or accepting a plan after its observation/command deadline. It does not establish all-input semantic equivalence or authorize implementation in the frozen source.

## Timing interpretation and required boundary

Shared-VM measurements are noisy, these are five samples rather than a tail-latency bound, and cProfile adds overhead. Baseline and cached batches were sequential rather than randomized. Nonetheless every unprofiled sample exceeds both budgets by large margins.

The frozen run loop computes freshness from synthetic `t` before synchronous planning, and simulated time does not advance during the planning wall-clock stall. Therefore its sensor-fault trace does not demonstrate command expiry or freshness enforcement during a real planner stall. A separately ticking command deadline/watchdog must reject expired work and keep zero command when there is no current safe command. The parent's independent real-clock/watchdog harness should use this fixture and actual planner process; no such behavior is claimed tested by this profile.

## Reproduce

From `/workspace/scratch/b09eacf6919d`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 planning-profile-20261024/profile_planning.py --repeats 5
PYTHONDONTWRITEBYTECODE=1 python3 planning-profile-20261024/test_memoization.py
```

To reuse only the snapshot, load `initial_open_observed_fixture.npz` with NumPy. Keys: `pose`, `static`, `grid`, `observed`, `unknown`, `angles`, `ranges`. Use `pose` and `grid` with the actual frozen `build_path`, after setting `YAW_MAX = 0.12`. Fixture creation assertions and input/output hashes are in the scripts and JSON.

## Files

- `profile_planning.py`: actual sensor-to-observed-grid builder and frozen baseline profiler.
- `initial_open_observed_fixture.npz`: replayable observed snapshot.
- `results.json`: environment, source hashes, repeated timings, fixture stats, profile hotspots.
- `baseline.prof`, `baseline_profile.txt`: raw/text cProfile.
- `baseline_path.json`: exact frozen path.
- `test_memoization.py`, `memoized_build_path.py`: isolated experiment and exact-equivalence assertions.
- `memoization_results.json`, `memoized.prof`, `memoized_profile.txt`: optimization results/profile.
- `profile_run.log`, `memoization_run.log`: captured execution logs.
