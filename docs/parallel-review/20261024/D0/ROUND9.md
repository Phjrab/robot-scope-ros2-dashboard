# D0 ROUND9 — keep observing after predictive stops

## Status: pinned C3 runner patch implemented/tested with mocks; live integration NOT_APPLIED

User clarified that “terminate only on actual contact” means **continue observing**
after a predicted-collision safety stop, not disable that stop or push the robot
until collision. Excessive slowdown is not a solution. This change does not grant
physical robot/camera/service/deployment/main/PR access.

D0 starting remote `ffd277a0ab8662c3b4b8547b7994bfabec228b95`.
Latest C3 remote `8aef2fb972af1358929774b85b642b6fc5f6c06b` unchanged at inspection.
AGENTS and status inspected. Prior d0-round8 local/API equivalent-tree divergence
was preserved; a clean independent d0-round9 clone starts at remote D0. Explicit
role-branch instruction overrides default main-only workflow.

## Source finding and ownership

Current C3 [native_runner.py](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/8aef2fb972af1358929774b85b642b6fc5f6c06b/experiments/competition_nav2/native_runner.py#L1097-L1158)
breaks its observation loop when the native result future is done (after the
recovery-probe condition). A non-success result then gets only a 2.6-second settling
observation. It also exits on a latched boundary fault. This is **not** a direct
“predicted collision callback terminates experiment” condition: a native abort can
end the loop after progress/recovery, and controller predictive stops must remain.

The user subsequently explicitly approved the narrow C3 runner edit, without
new native execution or real robot access. C3 source is absent from the D0 branch,
so this delivery carries a hash-guarded minimal patch and helper rather than
copying all C3 dependencies or merging another role branch. The patch was applied
to an isolated exact-source copy and its actual loop exercised with mocks. The
remote C3 branch and deployed/runtime code remain unchanged. The older D0 toy baseline has
a separate blocked-scene six-second exit, but changing that obsolete demo would not
change the current C3 native trial; it was preserved too.

## Implemented bounded deliverable

A small [pure lifecycle contract](../../../../experiments/competition_vm/arena_robot_sim/revisions/observation_continuation_20261027/observation.py)
and [14 regression cases](../../../../experiments/competition_vm/arena_robot_sim/revisions/observation_continuation_20261027/test_observation.py)
make the intended distinction executable. A [minimal runner patch](../../../../experiments/competition_vm/arena_robot_sim/revisions/observation_continuation_20261027/native_runner.patch) wires it into the actual pinned runner source in isolated test copies.
[Application helper](../../../../experiments/competition_vm/arena_robot_sim/revisions/observation_continuation_20261027/apply_patch.py) refuses source hash drift or an existing helper, checks patch applicability,
and verifies the resulting source hash. It does not launch ROS or native tests.
The original command handler and padded-contact safety-latch block are byte-preserved.

| Event | Observer | Motion authority / evaluation |
|---|---|---|
| Predicted collision / SAFE_WAIT / native zero | Continue within finite existing budget | Predictive stop unchanged; not success |
| Native ABORTED / CANCELED | Record terminal action; continue bounded observation | Never restart or resubmit goal |
| Raw-body actual geometry contact | Terminate RAW_CONTACT | Evaluation failure, not padded proxy |
| Padded margin violation only | Continue observation | FAIL_PADDED_ENVELOPE persists |
| Verified native success + goal geometry | Terminate GOAL_REACHED | Still not whole-navigation qualification |
| Infrastructure fault / explicit operator cancel | Terminate distinct reason | Do not clear fault or override shutdown |
| Observation time budget reached | Terminate OBSERVATION_TIMEOUT | Never count inactivity as goal success |

Unknown or omitted raw-contact evidence defaults to INPUT_REQUIRED. The finite
observation budget wins over success at or after its exact endpoint; raw contact,
infrastructure error and explicit cancellation retain distinct priority reasons. No force-minimum speed, changed
speed limit, removed collision gate, or fabricated nonzero command. Sampled mean
translation speed is reported, not enforced, and not substituted for traveled
path length. No numerical minimum has been chosen for the user.

## Runner changes implemented in patch; integration handoff

1. Separate `action_finished` from `observer_finished` in the existing runner.
   Capture terminal status once; do not keep querying/resubmitting/restarting it.
2. Continue spinning existing observations after non-success action completion
   until the existing bounded fixture/wall budget, raw contact, explicit cancel,
   or infrastructure fault. Leave command boundary, TTL, collision prediction,
   zero output, fault latches and shutdown semantics intact.
3. Existing collision counter uses effective/padded geometry. Do **not** relabel
   it raw contact. Use original raw body .81×.56 against original truth geometry
   for a separate contact observation, with continuous/sampled limitations explicit;
   retain .87×.62 padded envelope failures independently. Do not send truth to planner.
4. Log terminal action status/time, observer termination reason/time, post-stop
   observation duration, goal distance and speed/progress metrics. Merely extending
   the observation of an aborted goal cannot make it resume or finish. Terminal
   action status is cached once; action-observed/observer-end/post-action durations
   use one monotonic elapsed clock. Existing bounded cancellation/result waits,
   2.6-second settle and 0.5-second zero-output cleanup remain outside the main
   observation budget and are explicitly labeled; no hard end-to-end claim.
5. Supplied mocked tests execute the actual patched observation loop, plus raw-body
   geometry against the existing C3 geometry functions. A real native execution
   remains NOT_RUN; applying to the role owner checkout is still outstanding. A
   missing raw contact signal is INPUT_REQUIRED, not fabricated contact-free PASS.

## Verification and limitations

- D0 focused suite: 26 PASS: 14 pure lifecycle cases and 12 exact-patch/actual-loop
  mocked cases. These are synthetic/offline tests, NOT native Nav2 execution.
- Required whole-repository Python and relevant JS results are in the final receipt.
- Exact submitted/tested SHA and exact-head CI are in the delivery receipt; source
  and report are one focused commit, not a docs-only claim of old CI.
- Original geometry, audits, fixtures and command generation unchanged. The only
  C3 code change is the pinned patch, exercised in temporary copies; no C3 branch
  or installed runner was changed.
- No C3/native replay, robot, hardware, deployment, service, main or PR operation.

**Remaining one task:** C3 owner applies the reviewed hash-pinned runner patch to
its current checkout and, under separately scoped native-run authorization, verifies
actual post-stop observation records.
Until then the native behavior is unchanged. No automatic monitoring or extra phase.
