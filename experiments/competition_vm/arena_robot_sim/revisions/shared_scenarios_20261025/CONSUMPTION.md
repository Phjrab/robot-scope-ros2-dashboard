# C3 consumption boundary and exact adapter request

Read-only reference: C3 `16c63e08be5a7c10887e9e05cae94e94788e990f`:

- `experiments/competition_nav2/fixtures.py`: `cases`, `World`, `World.scan`.
- `execute.py`: fixture selected exclusively from `cases()+diagnostic_cases()`.
- `native_runner.py`: `Plant`, live `World.scan(pose, elapsed)` and scan scheduling.
- `container/manage.py`: CLI and isolated runner argument forwarding.
- `docs/parallel-review/20261024/C3/FOLLOWUP.md`.

**There is no external fixture flag at that revision.** Passing a D0 scenario name
or replacing `fixture.json` after start is not supported. `World` hardcodes its
geometry, grid and global footprint; its laser ray marches a 2D occupancy grid,
which is not D0's four-height triangle sensor. The existing native eight-case
result therefore does not establish consumption of these D0 inputs.

## Runnable checks now

In the D0 checkout, from repository root:

```sh
D0=experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025
python3 "$D0/export_fixtures.py" --check
python3 -m unittest discover -s "$D0" -p test_export_fixtures.py -v
python3 -c 'import json,pathlib; p=pathlib.Path("experiments/competition_vm/arena_robot_sim/revisions/shared_scenarios_20261025/fixtures"); m=json.loads((p/"manifest.json").read_text()); print(json.dumps(m,indent=2))'
```

For comparison only, these existing pinned C3 commands run its **own**, different
fixtures on an already available isolated Docker host; they do not accept D0:

```sh
python3 experiments/competition_nav2/container/manage.py build --lock work/c3-image-lock.json
python3 experiments/competition_nav2/container/manage.py run --lock work/c3-image-lock.json --output work/c3-empty --controller rpp --scenario empty --variant baseline --seed 20261024 --repeat 0
python3 experiments/competition_nav2/validate.py work/c3-empty/run
```

Those commands were inspected, not executed in this D0 round. Preserve C3's
package lock, runtime network-none isolation, DDS graph checks, watchdog,
raw-versus-final command evidence and final zero tail.

## Minimal request to C3 owner (not implemented here)

1. Add an explicit `--fixture PATH` to `container/manage.py` and `execute.py`,
   mutually exclusive with the built-in `--scenario` selection. Forward a read-only
   repository-relative path into the container. Resolve its adjacent manifest,
   geometry and observation file; verify their canonical hashes and schema before
   native launch. Record the unchanged D0 truth/geometry/observation hashes in the
   resulting run artifacts. Existing built-in fixtures must remain byte-identical.
2. Add an opt-in `World` adapter for `d0-scene-truth.v1`: use the declared route
   boundary and explicit forbidden polygons; keep full original geometry/provenance
   in artifacts. Derive static occupied cells only from that geometry, never hidden
   cones. Use exact square cone bases for independent collision evaluation and
   `appears_s` against the documented simulation epoch. Use the declared simulation
   transform; reject unknown real registration rather than interpreting GLTF axes.
3. Parameterize body polygon consistently in native costmaps **and** independent
   `World.collision/boundary_violation/clearance` checks. Record effective grid
   resolution, occupied-cell conservatism, footprint padding and inflation. Apply
   the D0 .03 m margin once for independent full-polygon sweep. Do not silently use
   the global C3 smaller footprint or stack .03 padding twice. A grid-blocked
   candidate is a discretization result, not proof of geometric impossibility.
4. Add a live D0 sensor option to `World.scan(pose,t)` using the existing D0
   `export_fixtures.observe(scene,pose,t)` / original triangle implementation (no
   copied sensor code). The output carries acquisition/source stamps. Native
   `Plant` must honor the declared .2 s schedule, .25 s freshness limit and dropout
   at elapsed 4 s, with its safety gates unchanged. If C3 retains its 2D ray march,
   label that a different sensor experiment, not identical-observation consumption.
   The small observation files are fixed-pose conformance vectors, not replay data
   to send at unrelated live poses. Compare all 360 ranges at the probe poses.
5. Make goal status and independent sensor/footprint/keepout checks retain original
   scenario expectations. Feasibility witnesses are audit-only: do not hand them
   to NavFn/RPP/MPPI, move the plant along them, or use them as reference commands.
   Start with a geometrically verified empty/feasible1 input, then feasible2,
   original_tight5, blocked and dropout. OPEN remains a separate diagnostic.

Expected adapter input: the exact `fixtures/SCENARIO.truth.json` plus adjacent
`geometry.json`, `SCENARIO.observations.json`, and `manifest.json`. Expected output:
actual native result and audit artifacts carrying all input hashes, live source/
receipt stamps, native path/command evidence, collision sweep and final zero.
No speculative future CLI command is presented as currently executable.

The single remaining integration action is **C3 owner implements this narrow input
adapter and runs actual native Nav2 against the unchanged hashed D0 fixtures**.
This D0 submission neither changes C3 files nor claims those native runs happened.
