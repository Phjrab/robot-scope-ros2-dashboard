# Bounded observation continuation contract (D0 ROUND9)

This includes an executable **pure lifecycle specification** and a minimal pinned
C3 runner patch, not a new simulator or deployed runtime change. It has no actuator, DDS, network, goal submission, or cancellation
API. It separates observer lifetime from predictive stop/control and supplies
small regression cases for the existing C3 owner.

Run: `python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/observation_continuation_20261027 -v`

`Observer(max_observation_s)` receives elapsed time from **one monotonic clock**.
No default budget is prescribed; reuse the existing finite fixture budget in C3.
`ABORTED`/`CANCELED` are recorded and observation continues; the native action is
never restarted. Predictive collision and zero velocity continue observation,
without making the controller move. Goal success must also pass independent goal
geometry checks. Contact uses raw-body geometry, not padded footprint contact or
published-grid proxy. Unavailable contact evidence stays unknown. Padding breaches
remain evaluation failures even though they are not raw-contact terminal events.
Infrastructure faults and explicit operator cancellation terminate separately;
this contract does not clear or weaken any safety latch.

Speed is sampled and reported by trapezoidal integration over received observation
intervals, not ground-truth traveled distance or a new minimum speed controller.
No numeric minimum was supplied by the user. Even verified goal reach is not
whole-navigation acceptance here; slow/stalled behavior cannot become PASS merely
because the observer remained alive. Sparse samples cannot establish continuous
contact absence, and no physical qualification follows.

Omitted raw contact defaults to unknown. At or after the exact observation deadline,
timeout wins over goal success; raw contact, infrastructure fault and explicit
operator cancellation retain their distinct higher-priority reasons.

## Exact-source patch and mocked runner checks

Pinned base and expected patched hashes are in source_pin.json. On an explicit
isolated C3 source checkout, run `python3 apply_patch.py /absolute/checkout`.
Application fails on source drift or existing helper; do not force it. It applies
only native_runner.py and installs native_observation.py beside it. This does
NOT start ROS, resubmit a goal, run native evaluation, or deploy anything.

Run all 26 cases with `C3_SOURCE_CHECKOUT=/absolute/pinned/source python3 -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/observation_continuation_20261027 -v`.
Without the source checkout, 12 patch cases skip explicitly. The source must contain
unchanged C3 dependencies for the raw geometry case. Mock tests apply the patch in
temporary copies, execute the patched loop text, and inspect unchanged safety blocks.
They do not substitute for a native post-stop observation run.
