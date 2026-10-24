# Continuous path-progress experiment

VM-only follow-on to immutable `curved_slalom_20261024`. No hardware, deployment or publication. Same fixed OPEN and tight layouts; full body ±0.405/0.280m and additional 0.03m guard are unchanged. Existing adopted candidate remains authoritative unless this experiment passes all gates.

## Hypothesis
Nearest path vertices quantize the lookahead and contribute to target velocity changes. Project onto polyline segments and interpolate lookahead by arc length, without removing full rotated swept-footprint guards.

## Candidate history
- Candidate01: continuous projection, speed error gain 2.5 rather than 1.5. OPEN SAFE_WAIT at 6.1s; tight SAFE_WAIT at 15.9s, zero contacts. Rejected. No geometry or clearance adjustment.
- Candidate02: continuous projection with original speed error gain 1.5. Qualified only for fixed-OPEN planar smoothness; tight unresolved.

Compute timings are measured on this shared VM, not realtime guarantees or a Raspberry Pi/Jetson benchmark. No candidate is sent for costly rendering until goal-stop, clearance, normal acceleration, and sensor-fault regressions pass and motion metrics improve.

## Candidate02 preliminary motion evidence

Same OPEN layout: goal with zero command at 57.4s vs previous 51.7s. Recorded RMS linear jerk 0.150522 vs 1.248742 m/s³, maximum jerk 1.49933 vs 3.21827, velocity total variation 0.440989 vs 3.142048 m/s. Conservative footprint minimum clearance 0.0457054 vs 0.0453037m; full-body audit has zero violations. Normal maximum command acceleration remains 0.20m/s². This trades 11% longer duration for less target jitter, not a universal improvement.

Original tight layout still SAFE_WAIT after 24.1s; full-body minimum clearance 0.0360324m and zero contact. Stop override is intentionally exempt from normal slew and must not be counted as passing normal acceleration. No impossibility claim.

29 planning calls in OPEN, 33.53s aggregate planning wall time and 2.115s p95; total wall time 67.06s for 57.4s simulated. This synchronous offline loop does not demonstrate real-time feasibility. Shared VM timing is noisy, but the planning cost is a real engineering limitation. Sensor acquisition time is synthetic and does not model wall-clock stalls.

## Regression status

22 tests pass (5 target interpolation and 17 scenario tests). Dropout and 0.4s delayed observations stop with SAFE_WAIT at 7.2s; 14 stale samples rejected in delayed case. Blocked case SAFE_WAIT at 3.1s with zero movement. A repeated OPEN run has identical complete data excluding three wall-clock timing measurements. Repeated wall time was 60.80s, still not a real-time guarantee.

No articulated-envelope audit or rendering has been run for this new candidate. The previous rendered revision remains unchanged. Independent code/trace review passed; see review/REVIEW.md and review/independent_results.json. The independent edge-intersection audit and interpolation-motion bound establish >30mm between-sample clearance for all saved traces, not general hardware safety. Global nearest segment is not a stateful monotonic progress tracker: nearby branches and self-intersections remain untested.
