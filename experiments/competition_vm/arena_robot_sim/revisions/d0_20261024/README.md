# D0 planar regression revision — 2026-10-24

This revision changes no prior published source, results or videos. It extends the
existing arena simulator with repeatable policy/sensor stress tests; it does not
create a new planner, arena, native ROS runtime, or physical motion controller.

## Fixed inputs

- Base main: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
- Start `(5.99, 1.65, pi/2)`, goal `(5.99,4.35)` in provisional `arena_design`.
- Same outward-rounded model-derived body: ±0.358m × ±0.162m. No body reduction.
- Cones: square base0.26m, base height0.04m, cone radius0.12m/top0.32m.
- Seed20261024; deterministic explicit layouts, no seed search or geometry repair.
- Existing circumscribed-radius A* and rotate/follow controller unchanged.
- Cases include0/1/2/5/10 cones, centered and x5.75 historical failed conditions,
  boundary proximity, alternating narrow passage, collinear occlusion, complete
  blocked rows, actual queued0.4s scan latency, dropout, mapped static cone.
- Each scene has two policies and two repeat runs. Only parking allowance changes
  between policies. No cone/wall/body moves occur in a success-seeking retry.

## Corrected restriction

`strict_no_parking` forbids the entire parking polygon during a navigation stage,
not just the center. The legacy policy is retained for explicit comparison only.
The old x5.70 detour succeeded by entering the parking bay with part of its body;
that is not a strict navigation success. An unchanged strict scenario may and does
end SAFE_WAIT instead of inventing a route. SAFE_WAIT is a safety result, never
full-course completion or proven ability to negotiate all configurations.

## Geometry and sensor evidence

The online guard intersects the whole oriented rectangle with conservative occupied
cells, including static floor boundary/terrain, mapped cones, dynamic occupied and
unknown cells. It evaluates swept poses before each command. The evaluator separately
samples6 poses per0.1s interval against all truth cones and static cells. Exact cone
SAT and fence segment contacts are checked; intersection clearance is zero, not a
positive endpoint-distance artifact. A separate saved-trace audit subdivides every
recorded interval10 ways, without running the planner. These are finite planar
sampling checks, not continuous-time certification or gait/contact physics.

Every fence and terrain triangle from the existing revision participates in the
first-hit ideal virtual LiDAR. A rear cone cannot clear a nearer cone. Existing
static obstacles are never excluded from truth collision merely because the map
already knows them. Scanner acquisition time and pose are queued; a delivered old
sample has current receiver time but retains its old source age. Source age and
receiver TTL are separately bounded at0.25s here; no threshold is enlarged.
Unknown/expired returns do not become evidence of free space.

`min_grid_circumscribed_clearance_proxy_m` is a conservative raster/circle proxy.
`min_sampled_polygon_edge_clearance_m` is actual planar rectangle-to-cone/fence
edge distance sampled along motion, NOT a measured physical or 3D margin. The
latter does not include a semantic parking exclusion boundary in its numeric
clearance, although parking overlap is explicitly tested and counted separately.

## Reproduction

From repository root, with the existing pinned NumPy/SciPy and Pillow/ffmpeg:

```
python3 experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/regression.py
python3 experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/audit_trace.py
python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/d0_20261024 -p test_regression.py -v
python3 experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/render_replay.py
```

All new outputs stay in this revision. `results/summary.json` records deterministic
payload hashes for both repetitions; measured wall runtime is kept outside the
hashed trace. `results/independent_trace_audit.json` covers saved pose evidence.
Rendering shows exact saved frames and actual terminal reasons, labeled
SYNTHETIC/PLANAR with seed. The displayed rectangle is the Go2 model-derived body
footprint, not articulated walking. Source hashes/frame indices are retained.

## Full-course sequence: DRAFT only

User intent: IN → all required arena sections → P → OUT. The geometry's graph,
map registration and terrain attachment dimensions remain DRAFT/unconfirmed.

| Segment | Evidence status |
| --- | --- |
| Right straight, no parking during navigation | This finite planar regression only |
| IN approach / entire course visit order | DRAFT sequence, not executed here |
| Ramps, stairs and central raised platform | BLOCKED_TERRAIN_HANDOFF; native gait NOT_RUN |
| Two signal stops and departure | Separate D0 FSM/integration synthetic tests, not a live linked run |
| Full-body P containment, seated posture, ≥5s physical stop | NOT_RUN; standing rectangle is not sitting evidence |
| Whole-body OUT crossing | NOT_RUN in this local straight regression |

No full-course lap, terrain walk, sitting or physical departure is claimed. In
particular the previously delivered kinematic full-lap picture cannot establish
those missing capabilities. No robot was contacted and no commit/push was made.

## Compact Git publication subset

The later user-approved destination is the D0-only review branch; main, PR creation
and device work remain outside this task. The D0 coordinator owns Git publication.
The full48 local trace files are preserved but excluded from Git, as are transient
logs/caches and duplicated partial summaries. `RAW_TRACE_MANIFEST.json` records
all48 exact file hashes/sizes. `results/summary.json` retains both deterministic
payload hashes for every paired run; payload hashes exclude walltime and need not
match byte-for-byte file hashes due to JSON ordering/newline formatting.

`fixtures/` contains lossless projections of every delayed/dropout source frame,
retaining all fields asserted by unit tests (`t`, `v`, `w`, `sensor_fresh`) and the
entire metrics object. The full input file SHA256/frame count is included. Tests
use these compact fixtures without skipping their original behavioral assertions.
`compact_fixtures.py` reproduces them from locally regenerated traces. No source
trace is deleted or changed to produce the projection.

- Fast remote regression: run the unit-test command above; no large traces needed.
- Full reproduction/video rebuild: run `regression.py`, then `compact_fixtures.py`,
  `audit_trace.py` and `render_replay.py`. Missing audit traces cause INPUT_REQUIRED,
  never an empty successful audit.
- `PUBLICATION_FILES.txt` and `PUBLICATION_SHA256SUMS.txt` describe only the compact
  published subset. The local-only `SHA256SUMS.txt` describes the larger local set.
- The small comparison MP4/PNGs and their source-hash/frame-index manifest remain
  useful review evidence; rendering is not newly executed when viewing that video.

Projection equivalence can be checked without rewriting fixtures:
`python3 experiments/competition_vm/arena_robot_sim/revisions/d0_20261024/compact_fixtures.py --verify`.
The report `results/compact_projection_verification.json` confirms all289 source
frames (71 delayed +218 dropout), all tested values and complete metrics match
exactly, with no downsampling/rounding. A separate compact shadow checkout with
zero new raw traces passed all13 tests with0 skips. Running the audit there correctly
returned INPUT_REQUIRED rather than an empty PASS; see compact validation JSON.
