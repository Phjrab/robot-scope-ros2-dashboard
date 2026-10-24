# VM in-process constraint integration

Evidence: **SYNTHETIC_IN_PROCESS ONLY**. No ROS execution, publisher, native Nav2, robot, field performance or deployment claim.

## Contract mismatch resolved at this experimental boundary

Traffic core emits a dictionary with owner/run/step/generation, request ID, HOLD/RELEASE, zero or unset caps and receiver TTL. Avoidance core accepts only a `signal_hold` Boolean; its default False cannot safely consume traffic output directly. `adapter.py` now provides an explicit session-bound translation and invokes the actual avoidance arbiter. Tests use the actual traffic FSM rather than fabricated GREEN eligibility.

The original module APIs are unchanged. Avoidance's original standalone scenario does not automatically use this adapter. The integration smoke explicitly imports both cores. Traffic ROS domain 173 and avoidance ROS domain 183 remain separate; nothing here changes that or wires live topics.

## Rules enforced

- Expected owners are configured, nonempty and allowlisted. All must supply a fresh RELEASE before movement is permitted. Any HOLD, missing, expired, malformed or unknown-owner constraint fails closed.
- Run, step and generation must exactly match; generation must be an integer. Invalid known-owner input revokes that owner's earlier RELEASE. Unknown owner revokes all releases.
- Constraint sequence is strictly increasing per owner. TTL and local receipt time must be finite; TTL is positive and capped at 0.25 seconds by default. Future receipts and backwards receiver time fail closed.
- HOLD must contain three zero velocity caps; RELEASE must contain three null caps. Unsupported LIMIT_SPEED is refused rather than silently ignored.
- Commands have strictly increasing receiver sequence, finite/current local receipt time, and must be received no earlier than every active RELEASE. A consumed command cannot resume after HOLD clears. RELEASE is permission to evaluate a new command, not a command itself.
- Existing arbiter ESTOP, sensor/TF stale and collision gates retain precedence. Other owner holds cannot be released by traffic.
- No cached nonzero command, socket, ROS publisher or actuator interface exists here.

## Evidence and reproduction

Run from repository root with NumPy, SciPy and OpenCV installed (the current VM has the traffic dependencies under /tmp/traffic-deps):

```sh
PYTHONPATH=/tmp/traffic-deps:. python3 -m unittest discover -s experiments/competition_vm/integration/tests -v
PYTHONPATH=/tmp/traffic-deps:. python3 experiments/competition_vm/integration/smoke.py
```

`results/tests.txt`: 16 tests PASS. `results/trace.jsonl`: 24 synthetic frames. RED/UNKNOWN stay at zero on an otherwise clear path; eligible GREEN permits a fresh command; deliberate sequence-21 replay at time 2.2 seconds remains zero; fresh sequence 23 resumes. Synthetic velocities are return values only and are not published.

## Required future integration work

The transport receiver must authenticate/bind owner and session, assign receipt time and monotonic sequence itself, reject replay before stamping a packet fresh, and handle producer epochs. The traffic dictionary alone has no authoritative transport epoch/time envelope; owner allowlisting here is not authentication. A new session must use a new non-reused generation and adapter; a restarted receiver cannot safely reuse old identity or blindly restamp old messages. Localized approach-completion/cancel ACK determines when this traffic gate becomes active: its APPROACH HOLD must not prevent the approach leg itself. A controller/missions manager must request a new crossing leg on departure intent; RELEASE alone does not start a leg. Native ROS wiring, foot evidence, real perception, watchdog scheduling, synchronized integration and safety validation remain NOT_RUN.

## Git publication (2026-10-24)
This source snapshot is prepared for publication on main. Earlier no-publication statements describe the authoring stage. See experiments/competition_vm/PUBLICATION.md for included artifacts, exclusions and final test status. Module checksums describe the Git publication subset, not the separately delivered immutable ZIP. No real robot measurements are included.
