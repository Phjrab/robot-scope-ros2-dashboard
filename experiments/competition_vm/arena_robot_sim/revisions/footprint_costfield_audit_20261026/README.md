# D0 independent footprint / cost-field audit

Frozen, offline analysis of **one retained C3 B artifact**, not a new planner,
Nav2 run, route, camera takeover or hardware validation. All generated small cases
are **evaluation/regression only**. Never feed them into runtime as hidden obstacles
or a solution path. Original scene, witness, geometry and role-owned sources are unchanged.

## Reproduce

Python standard library only. Retrieve run `40168963222`, artifact `12590081484`
privately, verify ZIP SHA256
`43580b9a3ced0b6bba00211a14a6398650fb7018c2794243f2af092cc5c34c29`,
and extract outside the repository. Its `source-sha.txt` must be
`2a1b1f172f30d010fa33d9b7f247a9163f175e82`. `audit.py` independently checks the
five consumed input hashes against the pinned C3 receipt and environment source.
The archive, full maps, scans, logs and native binaries are not published here.

```sh
REV=experiments/competition_vm/arena_robot_sim/revisions/footprint_costfield_audit_20261026
RUN=/private/extracted/narrow/omni_lattice/mppi-d0_feasible1-0/run
python3 "$REV/audit.py" --run-dir "$RUN" --output /tmp/d0-costfield-check
python3 "$REV/coverage.py"
D0_B_RUN_DIR="$RUN" python3 -B -m unittest discover -s "$REV" -v
```

The second command deterministically regenerates the small committed synthetic
coverage JSON. Without private artifact, the focused suite skips only the explicit
artifact-reproduction test; it still checks all committed small-case geometry and
source-formula regressions. If inputs are absent or hashes mismatch, do not invent
raw evidence: mark that rerun INPUT_REQUIRED. Missing files fail closed.

## Outputs and limits

- `results/audit.json`: derived prior/first-failure corners and sparse lethal edge
  observations, map receipt/source times, frozen scene coordinates/provenance and
  one-event/64-sample semantics. No full costmap or native route is included.
- `results/checker_cases.json`: previous/current continuous-margin cases and a
  rectangle-valid/circle-invalid corridor. Saved map occupancy is explicitly
  distinguished from raw cost. A raw synthetic wall-field recipe is separate.
- `results/coverage.json`: condition equations, 4096 continuous-pose vertex
  placements, separately snapped primitive-heading placements, and a small
  single-lethal-cell quantization counterexample suitable for C3 native testing.

Continuous edge/cell clipping here is conservative and independent, **not Nav2
Bresenham**. A padded corner in a lethal raster cell can be rejected before the
continuous floor crossing. The previous sample demonstrates this distinction.
Published map snapshots bracket trace records but are not atomic TF/checker inputs.
The pinned simulation publisher supplies identity map→odom; this is source-supported
alignment, not a newly observed TF-buffer snapshot. Native checker results remain
null / NATIVE_NOT_RUN. Exact internal branch evidence is INPUT_REQUIRED.

See [ROUND5](../../../../../docs/parallel-review/20261024/D0/ROUND5.md)
for judgments, formula references, verification and the one bounded C3 handoff.
