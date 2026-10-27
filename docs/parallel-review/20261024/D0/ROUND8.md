# D0 ROUND8 — retained command/progress/timing audit

## Decision: offline diagnosis complete; no navigation adoption or tuning

User explicitly requested another D0 task after ROUND7. This bounded follow-up
uses existing C3 ROUND7 logs to separate command receipt, virtual actuation,
progress failure and timing. It does not repeat collision audit/native execution.

- Starting D0 remote: `2a2d3bb30b67b363ce98d7fbec2537b4d8108b60`.
- C3 report HEAD: `8aef2fb972af1358929774b85b642b6fc5f6c06b`.
- Executed C3 source: `cf7662123bf13c9c38d565c03a978a4b9ae357a2`.
- [C3 ROUND7](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/8aef2fb972af1358929774b85b642b6fc5f6c06b/docs/parallel-review/20261024/C3/ROUND7.md)
- Retained native run40296598053, artifact12638597871. ZIP SHA256:
  `91a7d37428dc838e324de82152ff7f84082a0cd618546376e559dfb73fead404`.
- Exact submitted/tested D0 SHA and terminal CI are in the delivery receipt. Review
  source and report are one commit, not a docs-only inheritance of old CI.

AGENTS and status were inspected; explicit role branch overrides default main-only.
Existing d0-round7 checkout has equivalent-tree local/API commit divergence and was
preserved without reset. A clean d0-round8 clone starts at actual remote HEAD.
Only five new owned files; no prior geometry/inputs/common code/C3 changes, native
run, main/PR, robot/camera access, services, deployment or automatic monitoring.

## Evidence and clocks

[Audit](../../../../experiments/competition_vm/arena_robot_sim/revisions/progress_timing_audit_20261027/audit.py)
reads original628 trace records and119 received native commands, verifies pinned
source/file hashes and produces a small derived result.json. It does not use C3's
aggregate timing verdict as an oracle. Original logs, raw commands and grids remain
private. No original replay is committed.

| Clock | Appropriate use | Not established |
|---|---|---|
| sim_t / odom / TF | fixed.05s plant steps, sampled motion windows | actual controller execution duration |
| monotonic | same-process command receipts / plant tick gaps | subtraction from realtime or sim_t |
| DDS source/received and native log realtime | same-container emission intervals, transport timestamp deltas, event order | independent clock synchronization or absent-message proof |

Sim span31.350s and monotonic span31.334432s cover the first-to-last trace records,
not identical endpoints to the C3 total-run wall timer. All checked streams are
monotone. Plant uses the PREVIOUS actuator for the current pose increment, then
computes/publishes the next output. This off-by-one relationship is preserved.

## OBSERVED: movement stalls despite continuing accepted commands

Controller104 received,103 accepted; behavior15 received,14 accepted. One initial
command per owner is rejected at the epoch transition. All command records have
fault=null and held=false. Source logic rejects the first transition command when
its source precedes the newly set release instant; this is source-supported
interpretation, not a captured native rejection-reason field.

The receipt-bounded active controller interval contains456 plant samples, all
**RELEASE**. There are no HOLD, COMMAND_TTL or latched sensor/actuator-fault samples
inside that interval. Whole-run COMMAND_TTL104 records are contiguous initial,
post-controller and post-recovery gaps, NOT104 repeated drive interruptions.
RELEASE itself does not guarantee nonzero motion; an accepted native zero also uses
RELEASE and bypasses slew.

Absolute simulation windows (not elapsed-from-goal time):

| Window | Median raw translation | Median next actuator translation | Sampled path length |
|---|---:|---:|---:|
|4–10s|.066338m/s|.066369m/s|.381439m|
|10–16s|.074868m/s|.074214m/s|.432343m|
|16–20s|.019237m/s|.020060m/s|.108475m|
|20–26.5s|.001791m/s|.001867m/s|.013816m|

Half-open window floating-point selection and endpoint omission are explicit in
code; these lengths must not be summed as a continuous partition of the whole run.
Raw medians use accepted command samples; actuator medians use plant samples.

The last receipt-anchored ~10s window spans sim16.55–26.50s (9.95s of sampled poses):
path length.089441m, net/max-from-first displacement.084400m. Configured progress
radius is.1m with10s allowance. This supports stagnation consistency but is NOT a
reconstruction of the checker's unrecorded internal baseline pose/time, reset events
or invocation moments. Do not claim the threshold firing time was independently
proved, and do not increase allowance just to pass.

## INDEPENDENT_RECONSTRUCTION: virtual actuator is actually integrated

A midpoint-heading/sinc SE(2) exponential, different from the runner's endpoint
sin/cos-difference formula, reproduces all627 pose increments using applied_previous
and fixed sim dt. Maximum coordinate/yaw residual is1.99e-13; previous actuator to
next applied_previous error is0. This tests retained virtual-plant arithmetic, not
hardware tracking, slip, gait or Safe-mode behavior.

Recomputed sampled path length.953508738m, remaining goal distance3.161727160m,
final actuator[0,0,0]. Retained contact/boundary counters stay0. These counters and
sampled paths are not a physical or continuous collision guarantee.

Therefore the visible stagnation is accompanied by progressively smaller accepted
native translation commands and correspondingly small simulated movement. It is
not supported to explain this run as repeated safety-gate TTL suppression or a
virtual plant ignoring otherwise sustained large commands. Why MPPI selects these
small commands remains **INPUT_REQUIRED** (critic/rollout/progress internals absent).

## Timing is slow, but causality is not isolated

Controller103 receipt intervals: median.222365s, max.258713s; all exceed75ms.
Source-emission timestamp intervals independently have median.222810s, max.258724s.
Thus the ~.22s cadence is already visible in received messages' source stamps, not
merely a subscriber callback backlog. This is not proof that no messages were lost.
Controller source-to-DDS-receive deltas max2.574ms; callback source age max25.521ms.
Neither is the time spent computing a command.

Behavior14 intervals have receipt median.050000s, source median.050008s. Plant tick
median.049999s, p95.050081s, one>75ms gap (startup max92.065ms). Native log contains
104 missed20Hz warnings. Do not turn these counts into104 independent stalls or
claim the plant/controller use the same scheduling mechanism.

Diagnostic JSON/file IO under the planner's GLOBAL costmap lock can perturb the
experiment. The controller uses its own LOCAL costmap. A direct global-lock-causes-
controller-blocking chain is not established; CPU scheduling, local lock waits,
MPPI scoring/checker workload and diagnostics need distinct spans. No clean
uninstrumented baseline or per-cycle compute duration is recorded. This run cannot
quantify an overlay performance regression or prove slow cadence caused stagnation.

## Terminal sequence, not one generic collision failure

Native realtime log orders:
1. Failed to make progress (1793005739.763273281).
2. Recovery wait begins and completes.
3. Recovery spin begins.
4. Collision Ahead - Exiting Spin (1793005741.514520272).
5. Navigate goal fails.

Controller accepted exact-zero source timestamp1793005739.763306122 follows the
progress error in the same-container realtime domain. Recovery commands rotate the
virtual plant, then a zero stops it. The spin warning is predictive recovery failure,
not an observed body contact and not the original progress failure. action_events
is empty; exact internal action/progress/critic packets are not invented.

## Checks, scope, and one next task

New focused tests **13 PASS**, including retained-source/hash reproduction,
independent arithmetic, clock-reset/duplicate and step-size guards, changed previous-
command detection. New compile/diff PASS. Required repository Python2691: existing
manifest failure1, VM socket permission errors25, skip1. JS660 PASS. Exact remote
CI is finalized in delivery; no new native or hardware run. Prior passing checker
cases are not counted again.

**One proposed C3 diagnostic:** a single bounded isolated run at unchanged settings,
with an in-memory per-control-cycle record linking selected raw command, selected
rollout/critic costs, local costmap/compute wait spans, progress baseline/reset/time
and source publish time, flushed after the run. The purpose is to distinguish
small-command selection from execution-budget starvation, not raise timeouts,
reduce footprint/inflation or launch broad tuning. This document does NOT run or
schedule that test. Current authority ends with this D0 offline review and publication.
