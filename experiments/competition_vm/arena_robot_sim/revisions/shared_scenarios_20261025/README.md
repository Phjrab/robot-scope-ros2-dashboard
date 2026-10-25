# D0 shared scene inputs, 2026-10-25

Offline compact input contract, not another simulator, renderer or driving harness.
All six required cases plus a separately marked OPEN diagnostic are exported.
Existing D0 cone meshes and first-hit raycast are imported, not reimplemented;
C3 source is neither copied nor modified. Native consumption is **ADAPTER_REQUIRED /
NOT_RUN**, not native Nav2 evidence. See [CONSUMPTION.md](CONSUMPTION.md).

## Reproduce from repository root

```sh
D0=experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025
python3 "$D0/export_fixtures.py"
python3 "$D0/export_fixtures.py" --check
python3 -m unittest discover -s "$D0" -p test_export_fixtures.py -v
```

Existing NumPy/SciPy environment suffices. No ROS, robot, network or generated map
is needed. `--output DIR` changes only the output location. `--check` rebuilds the
expected values in memory and fails on any mismatch. `manifest.json` hashes each
JSON value using sorted-key, compact, UTF-8 canonical JSON, not pretty-print bytes.
The geometry source and virtual-fence files have separate exact byte SHA256s.
Each truth wrapper also records `scene_sha256`: this hashes the stable `scenes()`
input alone and matches the independent feasibility `input_sha256`. Expectations
and provenance are outside that scene hash but protected by the full truth hash.

## Contract and frames

- `fixtures/geometry.json` preserves the complete original rulebook outer boundary,
  holes, floors and semantic zones, plus the approved corridor-parallel revision
  with its own source hash/provenance. Neither is a field-measured navigation map.
- Every scenario uses the **original rulebook left slalom polygon** as its route
  boundary. That polygon is identical in the approved corridor revision. All
  original holes, parking, central platform, ramps and stairs are forbidden.
  Physical fence observations and semantic route restrictions are separate:
  semantic keepouts do not magically become laser returns.
- SI metres/radians; right-handed Z-up, lower-left ground origin. The declared
  `arena_design -> d0_sim_map` transform is identity **in simulation only**.
  GLTF `(x,y,z)->(x,z,-y)` is viewer-only. All real `map_transform` values stay null.
- Collision body is the conservative proposed .81 x .56 m rectangle, not the
  smaller standing visual FK envelope. Add .03 m once to each body half-extent
  for the conservative .87 x .62 m clearance sweep. This is not a gait envelope
  or physical collision qualification.
- Cones retain .26 m square base, .04 m base height, .12 m cone radius and .32 m
  total height. Square bases, not smaller circular disks, define planar collision.
- `SCENARIO.truth.json` is hidden truth: unchanged cone definitions, their square
  base polygons, spawn times, start/goal, sensor parameters, expected outcome and
  provenance. No hidden obstacle may be preloaded into the static prior.
- `SCENARIO.observations.json` is a separate **sensor conformance probe stream**:
  explicit acquisition poses, source/receipt simulation stamps, seed, epoch and
  360 ranges. Probes include a 3.2 cm pose displacement but are not a controller
  trajectory. Native runs must generate scans at their actual evolving poses.
- D0 sensor: .025/.10/.20/.35 m ground-relative horizontal planes; full 360-degree
  FOV; first exact triangle hit per beam/height, then minimum across heights;
  valid range (.02,8) m and 8 m no-hit sentinel. No calibrated noise assumption.
  Dropout removes observations from 4 s onward, never restamps old returns or
  substitutes clear scans. Freshness limit is .25 s, independent of planning.

## Cases and interpretation

`empty`, `feasible1` and `feasible2` have independently certified original-geometry witnesses. The latter
use full-size cones on the same side at (.18,2.5) and (.18,2)/(.18,3.5) respectively.
See the independent `FEASIBILITY.md` and its witness/sweep results. Geometric feasibility is not native goal reach.

`original_tight5` preserves the original alternating five-cone arrangement and
prior NOT_ADOPTED/SAFE_WAIT result. The new independent geometric witness does not retroactively
turn that previous planner trial into a success. Failure of bounded SE(2) search
is not proof of continuous-space impossibility.

`blocked` preserves the original five-cone blocking arrangement. `sensor_dropout`
uses the same empty route with scan loss from 4 s. The expectation is stale HOLD,
not automatic recovery, physical braking, or a claim that this probe stream drove.

`open_diagnostic` reproduces the existing OPEN cone spacing. Source inspection
shows the **same floor boundary**, with expanded longitudinal obstacle spacing
and therefore more turning room, not a widened physical arena. It remains a
separate diagnostic and cannot certify original tight5.

No planning loop, signal/lifecycle behavior, production code or UI was changed.
No map grids, bags, mesh duplication, videos, calibration or robot evidence are
included. Witnesses are feasibility-only and must never be fed as Nav2 paths.
