# D0 traffic lifecycle correction — 2026-10-24 UTC

Fixed baseline: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`. LOCAL-ONLY; no commit/push, robot access, camera acquisition, actuator transport or ROS launch. Historical results and checksums are unchanged.

## Executed and verified

- Actual fixed-base `StopGoFSM` returns HOLD while approach is active: self-block reproduced. Corrected integration boundary `TrafficLifecycle` emits traffic RELEASE during approach, but sensor, localization, collision and emergency gates still block movement. A RELEASE is only absence of this owner's restriction, not a command or proof of action completion.
- Strict event sequence: matching approach SUCCEEDED or CANCELED+cancel ACK → explicit HOLD request → matching, post-request HOLD ACK → fresh physical-stop/two-front-feet evidence → conservative continuous 2-second observed bound → connected fresh GREEN/pose/path → distinct increasing exit-goal generation → post-request exit ACK → goal-bound post-ACK observed movement. Sending a goal or releasing a constraint never commits departure. CANCELLED without ACK remains persistently held.
- Before departure, RED/UNKNOWN/stale/identity mismatch revokes exit eligibility. After observed commitment, red alone does not stop that crossing; safety/obstacle/localization remain authoritative. Full crossing completion also requires matching exit-goal identity and post-ACK observation.
- Fixed a real legacy TemporalFilter defect: stale source age called reset, erased sequence/stamp high-water marks, and allowed old frames to rebuild GREEN. Replay ledgers now survive freshness/evidence reset and track changes. Old producer epochs remain retired.
- Strict lifecycle action or observation producer restart closes the session. Native mission owner must choose a new, never-reused generation and rebuild both lifecycle and constraint adapter. In-memory ledgers do not replace durable mission generation ownership.
- 136 traffic unit tests PASS in this VM: existing 67 preserved, 69 new. `results/unit_tests.log` is the actual run, not CI. `results/before_after.json` records actual old/new behavior. Native ROS/real .pt/RGB/Jetson remain NOT_RUN or INPUT_REQUIRED.

## Time contracts and conservative stop bound

Receiver TTL = 0.25 seconds. Maximum current source age = 0.25 seconds. Stop continuity observation-gap limit = 0.5 seconds. These are separate checks; none was enlarged to hide latency.

Current source age = clock-aware age at local receipt + local receiver residence. No subtraction of monotonic timestamps from separate hosts occurs. The same bound applies to action ACKs and pose. Dispatch eligibility expires at the earliest receiver/source/pose deadline, not simply 0.25 seconds after the last call.

For stop dwell, first valid stopped observation starts the conservative bound at its local RECEIPT instant. Last supported physical instant is latest receipt minus trusted observation age. Bound = max(0, last supported instant − first receipt). Receiver residence is never credited as physical evidence; source-time regression or a gap over 0.5 seconds resets the bound. This assumes source age is trustworthy and correctly synchronized by the adapter. Unbounded clock/age uncertainty must fail closed. ACK and movement evidence acquisition must be after the relevant request or accepted ACK, respectively.

## Public-contract differences: proposals only

No canonical schema, production API, UI or runtime enum changed. `ActionEvent`, lifecycle_state and additional output diagnostics are VM-local Python records, not competition-evidence.v0.1 extensions.

- Legacy StopInput has only approach_ack and no hold-request correlation, action-terminal identity, exit-goal identity or action ACK chronology. It cannot safely express the lifecycle on its own.
- Canonical evidence has goal_id/generation/state, cancel_ack/hold_ack and producer metadata, but an actual native receiver must validate transport identity and correlate HOLD request IDs and request/ACK order at ONE adapter boundary. Do not infer ACKs from SDK call success or fill missing values with True.
- `observe(..., observed_goal_id=..., observed_goal_generation=...)` explicitly binds departure/crossing evidence to the accepted fresh exit goal. Boolean observed movement alone is insufficient. Exact native movement/velocity/displacement thresholds and two-front-foot estimator are INPUT_REQUIRED; this VM only tests the stated synthetic assumption (fresh non-stopped motion after ACK).
- Local motion constraints retain receipt_ttl_s. Mission fixture current_generation_only is not automatically wire-compatible. Use the revised integration adapter and its goal/sequence barriers; preserve canonical DTOs and C1/C2 normalize semantics explicitly.
- Legacy StopGoFSM remains a narrow zone/replay core for immutable comparison. Its standalone approach HOLD is not suitable for direct mission wiring. New strict integration smoke uses TrafficLifecycle; do not bypass the boundary by invoking the legacy boolean approach_ack API.

## C1 application order

1. Apply D0 tracked core.py changes and all new lifecycle/tests/revision files in the package; keep old results.
2. Apply the revised integration adapter and strict smoke together, not the wrapper alone. It must bind active_goal_id/active_goal_generation and retain fresh-command barriers.
3. Run traffic and integration tests plus strict smoke. Confirm both approach progress and persistent safe stop before matching ACK; inspect before/after evidence.
4. C1/C2 implement one native boundary for owner/run/step/goal/generation, source/receipt times, ACK correlation, epoch restart and actual observation evidence. This is a proposal, not an existing deployed adapter.
5. Only separately authorized native/sensor/hardware validation may qualify actual physical stop, foot containment, crossing or deployment.

Rollback: revert only D0 changes to traffic core and remove the new lifecycle/tests/revision paths if not adopted; coordinate integration removal. Do not reset another checkout or overwrite historical records.

## Reproduction

From repository root, using a project venv with NumPy, OpenCV, Pillow:

```
python -m unittest discover -s experiments/competition_vm/traffic_signals/tests -v
python experiments/competition_vm/traffic_signals/revisions/d0-20261024/reproduce_before_after.py
```

This VM used Python 3.12, NumPy 2.3.5, OpenCV 4.10.0, Pillow 12.3.0. This differs from historical traffic NumPy 2.5.4; the old environment/result claims are preserved, not rewritten.

Input provenance: immutable baseline core snapshot is `fixtures/base_core_7f2a707.txt`, exact SHA256 `5a3e786243662547588365982d9784293f1025922d0e0f90d28e23d0cedc8f17`. All new unit observations/ACKs are explicit synthetic fixtures; none is real robot evidence. No trained weights or user video were loaded.


## Submission update (2026-10-24 UTC)
The user subsequently approved publication ONLY on `review/20261024-d0-vm-offline`. Earlier LOCAL-ONLY/no-commit statements describe the implementation stage, not the final submission workflow. No main/PR/merge/device action is authorized. See `docs/parallel-review/20261024/D0/REVIEW.md` for source-tested commit, final submission status, selected artifacts and unresolved common-manifest integration failure. Historical publication manifests remain unchanged.
