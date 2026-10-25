# One native feasible1 failure audit

Frozen offline audit, not another navigation harness. No original fixture, model,
witness, production controller or C3 source is modified. See [ROUND4 report](../../../../../docs/parallel-review/20261024/D0/ROUND4.md),
[source contract](source_contract.md), [judgment](results/judgment.json),
[one topdown figure](results/first_failure_topdown.png), and [independent review](review/REVIEW.md).

## Reproduce

Obtain artifact **12588085458** from the authenticated repository's
[run 40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349).
Keep the ZIP and extracted native logs outside the Git checkout. Expected ZIP:
1,813,021 bytes; SHA256
`c2d20937c7e2d7d2d20527994e8eaa116d2fab1d556638562ce688972317d8cb`.
The analyzer rejects a different archive. Existing Python requirements are NumPy,
PyYAML and matplotlib; this audit does not install or start ROS.

```sh
REV=experiments/competition_vm/arena_robot_sim/revisions/native_feasible1_audit_20261025
python -B "$REV/analyze_failure.py" --artifact-zip /private/path/artifact.zip --output /tmp/d0-round4-reproduced
D0_NATIVE_ARTIFACT=/private/path/artifact.zip python -B -m unittest discover -s "$REV" -p 'test_*.py' -v
python -B "$REV/review/independent_geometry.py" /private/path/extracted/d0/rpp-d0_feasible1-0/run
```

Without `D0_NATIVE_ARTIFACT`, the private-archive integration test is explicitly
skipped, not passed. The other six tests check geometry, cost encoding,
constant-twist integration, archive rejection and evidence qualifiers.

## Limits

The point is a saved simulation pose bracketing the first warning, not the
unrecorded exact RPP TF pose. Path yaws were discarded: the red footprint uses
an outgoing-segment heading. A central-chord heading changes raw-body contact
(clearance 9.294 mm), although the padded body overlaps for both. The purple
projection holds the last accepted command, not the rejected candidate.
Global OccupancyGrid is older and is not the missing local checker input.
Exact native causal replay is NOT_RUN_MISSING_SIGNALS. The original holonomic
witness was neither promoted to a differential-drive proof nor injected into Nav2.
