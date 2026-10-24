# D0 integration handoff

2026-10-24 UTC. Base commit 7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a. LOCAL-ONLY, no commit/push. This revision supplements and does not overwrite original published result logs, traces or handoffs.

## Implemented and exercised

A retained RELEASE is bounded by the oldest supporting observation/pose/GREEN evidence before departure. Direct terminal, cancellation or fault events revoke cached permission at apply time without waiting for the next sensor tick.

The existing ConstraintAdapter now validates a separate source-age/epoch/sequence/stamp envelope, permanently closes a current session on epoch replacement or explicit cancellation, and binds command goal ID/generation with a fresh-command barrier. Historical receiver-local calls still work; they are not a substitute for a verified native transport envelope.

LifecycleConstraintAdapter wires the actual traffic module TrafficLifecycle to the actual avoidance CommandArbiter. The default integration/smoke.py now runs the strict action lifecycle, rather than bypassing approach with a boolean. No ACK is inferred from an emitted HOLD, a goal request, RELEASE or bind_goal. Synthetic ActionEvent inputs are explicit scenario data and labelled as such. The baseline smoke source is retained in fixtures.

`before_after.json` records replay of fixed-base adapter and traffic core snapshots, with hashes. Three defects are demonstrated: (1) approach blocked by its own signal HOLD, (2) same source packet accepted after new receiver sequence stamping, (3) source age 0.2 s plus receiver residence 0.06 s accepted by a receiver-only TTL check. Corrected result is approach motion only in the appropriate phase, and zero motion in both stale/replay cases.

`trace.jsonl` has 38 synthetic frames: fresh approach; real event boundary to HOLD; separately injected HOLD ACK; observed two-foot/body-stop dwell; new exit goal request and matching ACK; RELEASE but no departure latch; deliberately replayed command rejected; explicitly observed moving departure; RED after committed crossing; full crossing evidence. All claims are SYNTHETIC_IN_PROCESS only.

44 integration tests PASS: 16 original tests and 28 D0 tests. The trace covers 0.0–3.7 simulated seconds. These are return-value checks, not an actuator or ROS simulation. Original avoidance, traffic and whole-repository results are aggregated by the D0 package owner; this file makes no claim about tests run elsewhere.

## Reproduce from repository root

Use project-local environment with dependencies from the existing module requirements, then:

    python -m unittest discover -s experiments/competition_vm/integration/tests -v
    python experiments/competition_vm/integration/before_after.py
    python experiments/competition_vm/integration/smoke.py

Outputs go to stdout unless explicitly redirected to a new revision folder. No hardware access, sockets, service registration or network calls occur in these scripts.

## Contract and adoption

Read CONTRACT_DIFF.md for source age / receiver TTL / observation gap semantics, missing native DTO correlations and the exact C1/C2 adoption order. Never change fixture mode strings to activate native operation. An arbiter ACK is not physical stop; moving departure is a separately trusted observation. Native ROS, real RGB/weights, Jetson and robot evidence remain NOT_RUN/INPUT_REQUIRED.

Rollback is to omit/revert only the listed D0 integration files and dependent traffic lifecycle adoption. No production service/configuration was changed. Shared canonical schemas and public publication index are read-only and unchanged; C1 may add an index entry after applying and verifying the package.


## Submission update (2026-10-24 UTC)
The user subsequently approved publication ONLY on `review/20261024-d0-vm-offline`. Earlier LOCAL-ONLY/no-commit statements describe the implementation stage, not the final submission workflow. No main/PR/merge/device action is authorized. See `docs/parallel-review/20261024/D0/REVIEW.md` for source-tested commit, final submission status, selected artifacts and unresolved common-manifest integration failure. Historical publication manifests remain unchanged.
