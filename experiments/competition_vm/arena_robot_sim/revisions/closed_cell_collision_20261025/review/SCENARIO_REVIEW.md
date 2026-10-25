# Independent fresh scenario review

Overall: PASS

- open_normal: PASS, GOAL_REACHED; continuous clearance lower bound 0.045281822 m; actual poses/commands/states equal to frozen: True; paths equal: True.
  Versus fresh generic implementation: actual poses/commands/states equal: True; planned paths equal: True; source SHA-256 values are recorded in the JSON report.
- tight_normal: PASS, SAFE_WAIT; continuous clearance lower bound 0.035506964 m; actual poses/commands/states equal to frozen: True; paths equal: False.
  Versus fresh generic implementation: actual poses/commands/states equal: True; planned paths equal: True; source SHA-256 values are recorded in the JSON report.
  Path differences begin at frame 160 and affect 20 common frames; XY equal: False, path yaw equal: True. A closed-cell guard can legitimately change planning candidates without changing the executed trajectory.
- open_dropout: PASS, SAFE_WAIT; continuous clearance lower bound 0.050610365 m; actual poses/commands/states equal to frozen: True; paths equal: True.
  Versus fresh generic implementation: actual poses/commands/states equal: True; planned paths equal: True; source SHA-256 values are recorded in the JSON report.
- open_delay: PASS, SAFE_WAIT; continuous clearance lower bound 0.050610365 m; actual poses/commands/states equal to frozen: True; paths equal: True.
  Versus fresh generic implementation: actual poses/commands/states equal: True; planned paths equal: True; source SHA-256 values are recorded in the JSON report.
- blocked_5: PASS, SAFE_WAIT; continuous clearance lower bound 0.054000000 m; actual poses/commands/states equal to frozen: True; paths equal: True.
  Versus fresh generic implementation: actual poses/commands/states equal: True; planned paths equal: True; source SHA-256 values are recorded in the JSON report.

Open normal must reach the goal; tight normal may safely wait (as the frozen baseline did) or reach the goal. Dropout, delay and blocked cases must terminate in SAFE_WAIT. Normal slew is tested separately from immediate emergency zero stops. Source and receiver age both gate freshness. Body, margin, cone and floor values are checked against the frozen source and explicit dimensions.

## Scope and comparison notes
- Only newly executed closed_cell_collision_20261025 traces are audited; frozen traces are comparison references, not fresh tests.
- Full body planar rectangle and exact cone base/floor polygons; not articulated-mesh, dynamics, real-robot or physical gait validation.
- Continuous bound uses commanded linear position/yaw integration and 11 samples per interval.
- Closed-cell corrections may change planned paths. Actual poses, commands and states are compared separately without assuming equivalence.
- Wall-clock/planning timing metrics excluded from deterministic comparison; concurrent scenario/test workload is not a performance benchmark.
- No real-time capability is inferred from this replay or its wall times.
- A tight-normal SAFE_WAIT is a safe unresolved case, not proof that the course is infeasible.
