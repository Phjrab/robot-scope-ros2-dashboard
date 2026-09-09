# Track C4 new-map supervised goal preparation

Date: 2026-09-08

Status: `C4_PREGOAL_BLOCKED_ODOMETRY_GAP_CLEANUP_PASS`

Motion status: `NOT_RUN`

This record prepares the new operator-selected map for the existing supervised
Track C4 sequence. It does not authorize a navigation session, navigation
lease, initial pose, goal, deadman, non-zero command, Mission, or robot motion.

## Repository and live identity

- Repository commit at preparation start:
  `3e0a9aa109cde1b90c31311e948ef49a5809b79a`.
- `main` and `origin/main` matched and the working tree was clean before this
  focused change.
- External dashboard symlink and process release:
  `5bf184d63247186faa23dc5197e1c21a470a7d41`.
- Signed robot-side Control Bridge release:
  `10a7fa9cec2c329f2c50edc9ad98de13a22689da`.
- No service, release symlink, map, navigation session, lease, or command was
  changed during this preparation.

The mixed deployed releases are recorded facts, not an accepted C4 release
pair. A clean exact release and rollback plan must be shown before deployment.

## New pinned route

| Item | Exact value |
| --- | --- |
| Map | `map_20260908_072712_edited` |
| Map ID | `8050fff44b44ce106dc5a210` |
| Map revision | `9e72787f2443b714ed3045fda62c08c53e85294c7d02e26b8e74ce0cc30fc8ac` |
| Map geometry | 295 x 205 at 0.05 m/cell |
| Map origin | `[-10.5254297256, -4.29361486435, 0.0]` |
| Start pose | `(0.00, 0.00, 0.00)` |
| Proposed goal | `(0.25, 0.00, 0.00)` |
| Direction and distance | straight forward `+X`, 0.250 m |
| Robot-radius corridor | 0.220 m radius |
| Stopping buffer | 0.150 m beyond the goal |
| Checked corridor | start through `x=0.40`, sampled every 0.01 m |
| Minimum occupied/unknown/map-boundary clearance | 0.793614864 m |
| Net clearance beyond robot radius | 0.573614864 m |

The route calculation decoded the exact revision-pinned occupancy payload.
Every non-free value, including unknown cells, was treated as an obstacle. The
calculation permits only the fixed 0.25 m straight goal; it does not prove the
physical floor is clear or that the robot is still at the proposed start pose.

## Live read-only preflight

The external dashboard was active and the robot target was reachable. The
signed Bridge was ready, authenticated, connected, and reported fresh
LowState. Graph cardinality was one owned Sport publisher, one Sport
subscriber, zero foreign named publishers, ten expected bare Unitree
publishers, and eleven total publishers. Battery was 90 percent in this
snapshot. The control lease was inactive, deadman was released, and both the
manager and accepted command were exact zero. Bridge request evidence showed
zero Move, non-zero Move, action, other, and active motion-run requests.

Navigation, localization-only, Mapping, and goal state were idle. The prior C3
initial-pose count remained historical evidence only and is not reusable in a
new normal navigation session.

## Focused checker change

`scripts/check_track_c4_navigation_ready.py` now accepts explicit `--map-id`
and `--map-revision` pins. Both values remain strict opaque hexadecimal
identities and are cross-checked against the live navigation session and the
downloaded map payload. The historical map remains the default for retained
runbooks, while a new map must be supplied explicitly.

The fixed start, 0.25 m goal, 0.15 m stopping buffer, 0.22 m robot radius,
35-percent speed scale, 0.30 m/s server clamp, C4 parameters, stabilized READY
dwell, odometry maximum gap, lifecycle, topic cardinality, TF, signed Bridge,
LowState, lease ownership, deadman, raw-command, watchdog, and exact-zero
requirements were not relaxed.

## Software validation

- Focused C2/C3/C4: 45 tests passed.
- Full Python repository suite: 1,369 tests passed.
- JavaScript unit suite: passed.
- Cockpit JavaScript suite: 94 tests passed.
- Playwright hardware-free browser suite: 36 tests passed.
- Ruff and `git diff --check`: passed.

The first Playwright invocation was blocked by the local sandbox from binding
its test port. The identical suite passed outside that restriction; this was
an environment failure, not a product-test failure.

## Original mandatory gates at preparation time

1. Publish the focused commit and wait for CI.
2. Show the exact clean release, both-host compatibility, deployment order,
   and rollback release; obtain explicit deployment approval.
3. Reconfirm the robot is standing and completely stationary at
   `(0,0,0)`, facing the mapping-start direction, with at least 0.40 m of
   clear physical space ahead and a physical remote/E-stop in hand.
4. Obtain a new approval for one normal navigation no-goal session. Starting
   that session is allowed to acquire only the Navigation lease.
5. Show the exact map/revision/parameter revision again and obtain a separate
   initial-pose approval before publishing it exactly once.
6. Require stable C4 READY for at least 10 seconds with an idle goal and exact
   zero command, then stop and obtain a separate one-shot goal approval.

No prior C3, C4, C4A, C4B, or general approval can be reused for the motion
step. Any mismatch or loss of health requires reverse cleanup and a new
session; no goal may be retried automatically.

## Approved external deployment result

The operator approved only the external dashboard exact-release transition
and dashboard restart. The onboard Bridge, map contents, Navigation session,
initial pose, goal, and motion were explicitly outside the approved change.

The first external transition exposed a fail-closed packaging dependency: the
Git archive did not contain the generated PCL NDT2D executable required by the
already enabled D2 relocalization runtime. The dashboard failed during startup
with the executable missing from the exact release. The production symlink was
immediately returned to
`5bf184d63247186faa23dc5197e1c21a470a7d41`, and the dashboard recovered before
any Navigation or control operation. This failed transition did not start a
Navigation session, publish an initial pose, submit a goal, acquire a lease,
engage deadman, or publish a non-zero command.

The native registration tree was then configured and built inside the exact
`6f0a99b62e22f9f96ecf3561a451ce7426d6b1fe` release with the PCL backends and
tests enabled. Its native CTest passed 1/1. The resulting NDT2D executable has
SHA-256
`ec761c181fe8ecdae0c31522a9cf2edca9cb3d7150696414f29a41af72cf94f3`.
After this prerequisite existed, the external dashboard alone was switched
and restarted successfully.

Final deployed state:

- External production symlink and live process cwd:
  `6f0a99b62e22f9f96ecf3561a451ce7426d6b1fe`.
- External service: active, PID 96608, restart count 0 for the successful
  invocation.
- Rollback symlink:
  `5bf184d63247186faa23dc5197e1c21a470a7d41`.
- Onboard signed Control Bridge release, unchanged:
  `10a7fa9cec2c329f2c50edc9ad98de13a22689da`.
- Bridge: connected, authenticated, ready, fresh LowState, one owned Sport
  publisher, one Sport subscriber, zero foreign named Sport publishers.
- Control: no lease, deadman released, accepted command exact zero, Move 0,
  non-zero Move 0, action 0, other 0, active motion run false.
- Navigation pipeline and shared localization pipeline: idle; localization
  uninitialized; localization-only session inactive with initial-pose count 0;
  goal idle and goal submission disabled.
- Selected map remains `map_20260908_072712_edited`, ID
  `8050fff44b44ce106dc5a210`, revision
  `9e72787f2443b714ed3045fda62c08c53e85294c7d02e26b8e74ce0cc30fc8ac`.
- No map, onboard service, Navigation session, initial pose, goal, lease,
  deadman, action, or motion command was changed by this deployment.

The deployment incident also confirms that a source archive alone is not a
complete release artifact while the D2 PCL backend is enabled. Future release
preflight must either build and test this exact native target before switching
the production symlink or carry a verified compatible artifact produced from
the same exact source release.

## Gates completed during the supervised attempt

1. Physical stationary state, clear space, remote/E-stop, and safety operator
   were reconfirmed.
2. A normal Navigation no-goal session was separately approved and started.
3. The exact map/revision/parameter revision and `(0,0,0)` pose were separately
   approved; the initial pose was submitted once.
4. The formal pre-goal checker remained mandatory and blocked the attempt; no
   one-shot goal approval was requested or reused.

## Supervised no-goal and initial-pose result

The operator separately confirmed the physical safety conditions and approved
one normal Navigation no-goal session. The exact map and parameter revisions
above were pinned. The session acquired the Navigation-only lease and reached
`pipeline=running` with no initial pose, idle goal, released deadman, exact-zero
command, and zero Bridge Move/action evidence.

After a second exact-map confirmation, `(x=0, y=0, yaw=0)` was submitted once
through the existing normal Navigation initial-pose endpoint. The request was
accepted once. Localization converged within a few millimetres of the approved
pose, all required readiness booleans became true, and health completed its
10-second enter dwell. Live polling observed `READY / HEALTHY_STABLE` for more
than 24 seconds while the goal remained idle and both dashboard and accepted
commands remained exact zero.

The formal C4 checker subsequently failed closed because localization health
was no longer READY. Read-only diagnostics identified
`ODOMETRY_MAX_GAP_EXCEEDED`: the raw odometry frequency remained approximately
10 Hz, but the recent window contained a 0.297107-second maximum gap, exceeding
the unchanged 0.25-second limit. Once that sample rolled out, health recovered
to READY for 18.61 seconds with a 0.207711-second maximum gap. A fresh formal
checker invocation again found health non-READY, so the transient recovery was
not accepted as durable pre-goal evidence. The threshold and checker were not
relaxed or bypassed.

The goal was not submitted. The Navigation session was stopped and reverse
cleanup was verified:

- Navigation pipeline, shared localization pipeline, and goal: idle.
- Navigation lease: released.
- Deadman: released.
- Dashboard and Bridge accepted command: exact zero.
- Bridge non-zero Move count: 0.
- Bridge action count: 0.
- Active motion run: false.

This result does not invalidate the accepted initial-pose path. It blocks C4
goal readiness on intermittent controller-odometry delivery gaps. A new
session and a new one-time initial-pose approval will be required after the gap
source is diagnosed and the unchanged readiness contract can be satisfied
reliably.

## Follow-up gap diagnosis and instrumentation

Read-only host inspection after cleanup found no Navigation child crash, thermal
pressure, memory exhaustion, NIC error or active UDP receive-buffer-drop
increase. The external Jetson remained in its maximum-performance power mode.
These observations exclude those conditions for the inspected interval, but do
not prove where the earlier 0.297107-second gap originated.

The existing maximum-gap metric measures monotonic callback-handling timestamps
inside `robot_scope_navigation_runtime`; it does not measure the FAST-LIO source
header interval. The same single-threaded runtime also parses and projects each
16,000-point cloud before servicing the next callback. Therefore the prior
evidence cannot distinguish an upstream FAST-LIO publication gap from DDS or
executor delay. Callback contention is a supported hypothesis, not a confirmed
root cause.

The focused follow-up adds bounded, read-only timing evidence without changing
the C4 policy or command path:

- FAST-LIO source-stamp frequency, periods and maximum gap;
- PointCloud callback latest, p95 and maximum execution duration;
- odometry callback latest, p95 and maximum execution duration;
- bounded sample counts for every new window.

The gateway accepts either the complete timing diagnostic set or none for
rolling compatibility, rejects partial, non-finite or out-of-range diagnostic
payloads, and exposes the sanitized values in localization-health metrics. The
existing arrival-based `odometry_max_gap_s` remains the only maximum-gap input
to the unchanged 0.25-second C4 readiness gate. No automatic source fallback,
threshold increase, executor change or motion authorization is introduced.

On the next separately approved stationary run, the evidence is interpreted as
follows:

- source and arrival gaps both exceed 0.25 seconds: investigate FAST-LIO or its
  upstream sensor scheduling;
- source gap stays within 0.25 seconds while arrival gap exceeds it and a
  callback duration spikes: investigate single-executor callback contention;
- source gap stays within 0.25 seconds and callbacks remain short while arrival
  gap exceeds it: investigate DDS delivery or host scheduling.

Instrumentation alone does not authorize a new Navigation session, initial
pose, goal or motion.

## Remaining gates after the blocked attempt

1. Diagnose the intermittent controller-odometry gap without increasing the
   0.25-second maximum-gap threshold or weakening the stable-READY checker.
2. Re-run hardware-free regressions for any focused correction, then commit,
   push, pass CI, and deploy the exact corrected external release under a new
   approval.
3. Reconfirm physical safety and obtain a new approval for a fresh normal
   Navigation no-goal session.
4. Obtain a new exact-map initial-pose approval and publish it once in that new
   session.
5. Pass the formal C4 checker while READY remains stable, the goal is idle,
   command is exact zero, and all existing cardinality/freshness constraints
   remain satisfied.
6. Only then present the fixed 0.25 m goal and request a new one-shot motion
   approval.
