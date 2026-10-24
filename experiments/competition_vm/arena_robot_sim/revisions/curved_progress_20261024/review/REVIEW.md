# Independent candidate02 review

Verdict: qualifies as a promising VM-only smoothness candidate for the fixed OPEN fixture. It does not qualify the tight fixture for completion, real-time control, or physical deployment. No implementation or baseline source was edited by this review; no rendering, hardware, network, or publication was used.

## Verified results

- All 22 target/scenario tests pass after the author added three narrowly missing regression assertions suggested by this review. See `tests.log`.
- Live candidate source and candidate02/source.py are byte-identical: SHA256 5258fc6697beedc02f4b44b3d9c5415640e74484a60df4429c4f7f8ec6942aff. Diff from prior curved source is continuous segment projection/interpolated arclength targeting plus timing instrumentation, not footprint or safety-gate relaxation.
- OPEN: GOAL_REACHED, 57.4 s versus 51.7 s; terminal command exactly zero and final position 4.18 mm from goal. Maximum linear acceleration 0.20 m/s² and yaw acceleration 0.35 rad/s², including startup/goal stop, no emergency override. Position/command integration agrees to floating-point precision.
- OPEN recorded linear-vector RMS jerk is 0.150522 versus 1.248742 m/s³ (87.9% lower). Velocity total variation is 0.440989 versus 3.142048 m/s (86.0% lower). Independent scalar-speed RMS jerk also improves, 0.079704 versus 1.240531 m/s³; yaw RMS jerk 0.793394 versus 0.921927 rad/s³. This supports reduced command jitter, not physical smoothness or faster traversal. Duration is 11.0% longer.
- Tight: SAFE_WAIT at 24.1 s, zero contacts, one emergency stop override. Peak linear acceleration 0.641392 m/s² therefore does not pass normal-slew limits; it is explicitly a safety exception and an unresolved traversal.
- Dropout and 0.4 s delayed input: SAFE_WAIT at 7.2 s. First stale command at t=4.1 s is zero; all 31 stale frames stay zero. Delayed case rejects 14 samples. Fault stop overrides reach 0.749768 m/s² and 0.517516 rad/s²; these are not normal-slew passes or demonstrated physical braking.
- Blocked fixture: SAFE_WAIT at 3.1 s, zero movement and zero contacts.
- Independently compared original and repeat OPEN complete JSON: identical after removing only wall_time_s, planning_wall_s, and planning_p95_s. The manifest states the reviewer's exact JSON serialization for its hash; hash equality should not be assumed across differing serialization formats.

## Independent geometric qualification

`review.py` uses separate polygon transforms, segment intersections, point-in-polygon checks, and distances in both vertex-to-edge directions. It does not call the existing geometric auditor. At 11 poses per 0.1 s interval it confirms zero polygon violations and the stated minima. It also subtracts a conservative half-sample rigid-body displacement bound, translation plus circumscribed body radius times yaw change, to lower-bound clearance between samples under this exact constant-command kinematic plant.

| Fixture | Sampled minimum | Continuous-time lower bound |
| --- | ---: | ---: |
| OPEN normal | 45.705 mm | 45.282 mm |
| Tight normal | 36.032 mm | 35.507 mm |
| OPEN dropout | 51.113 mm | 50.610 mm |
| OPEN delay | 51.113 mm | 50.610 mm |
| Blocked | 54.000 mm | 54.000 mm |

All exceed the required 30 mm for the full unchanged ±0.405/0.280 m rectangular body. These bounds certify only saved ideal planar traces and static fixtures, not articulated-envelope motion, perception errors, dynamics, tracking error, or hardware execution. Full numerical results and trace SHA256 hashes are in `independent_results.json`.

## Limitations and next bounded checks

1. Global nearest-segment projection is not a stateful monotonic progress tracker. It can jump among nearby branches or at self-intersections, and a new path can discontinuously move the target. Current fixed OPEN evidence is good; it does not establish general route continuity. Future broader layouts should include hairpins/nearby branches and replanning continuity tests before making that claim.
2. Existing geometric audit calls 11 substeps “continuous,” but sampling alone is not a continuous proof. Its floor clearance uses robot-vertex-to-floor-edge distances only, and all-vertex containment alone misses concave-floor edge crossings in general. The left floor polygon is non-convex. This review checked crossings and both distance directions independently and found no violation or changed minimum on these traces. The rigid-body interpolation bound supplies the missing between-sample qualification for these saved traces.
3. Existing comparison pass_geometry means no intersection, not necessarily 30 mm clearance. The author's added all-scenario assertions now enforce the numerical threshold and scenario presence, and explicitly cover tight and delayed-stale stop behavior.
4. Source snapshot alone is not standalone: relative imports and runner-set yaw limits matter. Keep run_candidate.py, base simulator/core/geometry inputs, trace hashes, and environment versions with the candidate. `manifest.json` records the relevant current files and Python/NumPy/SciPy versions.
5. No realtime readiness: OPEN planning p95 2.115 s exceeds the 0.1 s control tick; 67.06 s wall time for 57.4 s simulation. Synchronous computation does not advance simulated sensor age, so sensor freshness tests do not exercise real wall-clock planner stalls. Need separation of planning and a wall-clock watchdog before physical relevance.
6. Evidence is deterministic fixed-fixture evidence, not statistical robustness. No injected sensor noise, odometry drift, packet reordering, moving cones, gait dynamics, or articulated-envelope audit was performed. RMS jerk is a finite-difference command statistic on saved frames, not measured acceleration jerk of a physical robot.

No blocking defect found for accepting this as an explicitly limited VM-only smoothness experiment. Preserve previous authoritative rendered candidate until any later promotion gate is deliberately satisfied; no rendering was performed in this review.
