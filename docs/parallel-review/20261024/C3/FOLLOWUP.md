# C3 native Humble follow-up

Branch: `review/20261024-c3-nav2-benchmark`. Continues reviewed `d023131`.
At follow-up start remote main was `7ef47dc249e4dba83865e78dc283f40013ea92de`;
it was read, not integrated or changed. Independent C3 clone was clean.

## Completed minimum comparison

Tested source: **`afe02f38d8396d11d786d39452ac572f27d72c22`**.
Actual [Actions run 40099437117](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099437117)
recorded **8/8 native runs; 8/8 independent evidence/safety checks PASS; 7/8 scenario expectations met**.
The workflow is intentionally red because the MPPI diagnostic did not meet its goal expectation.
All eight downloaded runs also passed local independent replay. Each RPP/MPPI pair
has byte-equivalent fixture data and equal parameters after removing only FollowPath.
Every case used the same image and source, baseline, repeat 0 and fixture seed 20261024.

| Scenario | RPP | MPPI |
| --- | --- | --- |
| Empty arena path | GOAL_REACHED, error 0.118 m | GOAL_REACHED, error 0.115 m |
| Separate feasible obstacle diagnostic | GOAL_REACHED, error 0.115 m | SAFE_WAIT after 65 s goal timeout, error 0.260 m |
| Fully blocked arena | SAFE_WAIT, native ABORTED (6) | SAFE_WAIT, native ABORTED (6) |
| Sensor dropout while moving | SENSOR_STALE, canceled (5), latched ZERO | SENSOR_STALE, canceled (5), latched ZERO |

All eight had zero swept-footprint contacts, zero keepout violations, zero nonzero
output under HOLD, and zero final actuator output. MPPI diagnostic logs show a native
progress-checker failure, native Spin recovery, resumed FollowPath, then harness
cancellation when the 65 s simulation budget expired. It was not a setup failure.
The obstacle is feasible for the full body: 1,846 reference sweep samples and
0.307 m conservative minimum clearance. Nav2 generated its own path and commands.
Original arena obstacles/goals/body/forbidden regions and D0 strict-parking SAFE_WAIT
results were not changed to obtain this success.

Sensor cases moved 0.328 m (RPP) / 0.253 m (MPPI) before stopping. The trace records
source/receipt ages, epochs, actual DDS timestamps, TF/odom/clock stamps, scan age,
raw/final commands and the subsequent zero tail. A latched sensor fault requires a
fresh isolated run with fresh observations, active servers, a new goal and release;
HOLD/RELEASE alone cannot reset it. Physical stopping and restored-sensor autonomous
recovery are not claimed. Simulated ZERO is not Go2 braking evidence.

## Evidence and reproduction

- [Small native summary](../../../../experiments/competition_nav2/results/minimum_native_summary.json).
- [Actual artifact 12562342808](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099437117/artifacts/12562342808): logs, trace, action UUID/results, lifecycle/readback, binary hashes, full package lock, graph/isolation and cleanup. Retention 14 days; API expiry **2026-11-07 13:49:59 UTC** (22:49:59 KST), unless deleted earlier. Downloads require repository access. Generated PGM maps are excluded and reproducible from fixtures.
- Base image `ros@sha256:566b87e6dfc48392189a9c32e594e84060fa9948de93b04e536f39475a1f6963`.
- Actual local image `sha256:0efc243066ebe7f5c64723718886c15659fae2a67e2c05c8ffb7b5af57aa9cd3`; package-lock SHA256 `45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de`. Image ID was local to the hosted runner, not published to a registry. Rebuild uses the recorded base and package lock and rejects package drift; the image ID may change on rebuild.
- Installed Nav2 controller/planner/BT/RPP/MPPI **1.1.20**, rclpy **3.3.22**. Exact Debian versions and transitive dependencies are in the artifact.

On an existing Docker Linux host, from the tested source:

```bash
python3 experiments/competition_nav2/container/manage.py build --lock work/c3-image-lock.json
python3 experiments/competition_nav2/run_minimum.py --lock work/c3-image-lock.json --output work/c3-minimum
python3 experiments/competition_nav2/validate.py work/c3-minimum/mppi-diagnostic_single_obstacle/run
```

For exact package comparison, place the downloaded artifact's `image-lock.json` at
the chosen lock path before build. A rebuilt image is checked against the complete
lock. Each case starts a fresh `--network none` container after networked build.
The workflow uses only the C3 branch/path push trigger, contents:read, one hosted
job, a 35-minute timeout and cancellation of obsolete runs. No default-branch
workflow_dispatch, secrets, self-hosted runner, robot endpoint or host DDS is used.

## Validation and remaining limits

Focused tests **43 PASS**; repository Python **2,691 run, 2,689 PASS / 2 optional
dependency SKIP**; JavaScript **70 PASS**; Ruff, Python compilation, secret scan
and diff whitespace checks passed. Four orchestration smoke checks used mocked
subprocesses and are not native evidence. The downloaded eight runs passed all
independent validators and four pairwise fairness checks.

[Common CI at tested source](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099437116)
failed its browser E2E stage, as observed before this follow-up. Common ci.yml and
production code belong to C1 and were not modified. Latest remote main observed
before result publication: `104692fa0070ef085eee918913ea05fdb2d88c05`; it was not integrated.

This is one fixed baseline sample per controller/case. MPPI's optimizer RNG seed
is not exposed; performance superiority and deterministic replay are not claimed.
Original 144-run expansion, real sensors, full course, gait/slip, physical braking,
Jetson timing and robot deployment remain NOT_RUN. The goal failure is preserved;
no additional controller tuning was performed. The final publication commit adds
reports only; its exact source HEAD/run status is reported in the submission response.

## Runtime compatibility fixes and retained failed attempts

First actual hosted run: [40096839736](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40096839736), source `2495f7bdbad5ff83d1b4c8ff7171260618f4e5bd`.
Humble image built successfully; network-none container started real ROS servers.
Graph audit rejected the native `/diagnostics` topic before activation. This is
an environment/harness failure, not a controller result. Native completed comparisons: 0.
Fix: namespace diagnostics explicitly; keep graph rejection checks intact.
Also avoid duplicate SIGINT delivery from both launcher and descendant cleanup.

Second run [40097188846](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40097188846), source `c8e52b80df3cd4a0b48b79908be62957d5d325c2`, passed graph isolation and loaded the real RPP plugin.
Activation stopped because Humble also loads the default NavigateThroughPoses
tree, which requires the intentionally disabled Backup action. The fix supplies
a matching forward-only through-poses tree with native Spin/Wait. The normal
NavigateToPose tree and controller limits stay unchanged. Costmap footprint,
inflation and scan configuration now also receive runtime parameter readback.

Third run [40097544519](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40097544519), source `3f7abe20924a8da11493762095006d81306e2fa8`, activated all five native lifecycle nodes.
Graph audit then found two publishers belonging to the same behavior server:
Humble TimedBehavior creates one velocity publisher per plugin, including Wait.
The audit now requires the exact configured behavior-plugin count with the same
owner for every endpoint. Foreign owners and extra/missing endpoints still fail.

Fourth run [40098000263](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098000263), source `6d9b111b10ab4163cede32bf73ea151b1432b27c`, reached the native NavigateToPose/FollowPath goal and controller output.
Humble rclpy's default executor discards the DDS metadata returned by
`Subscription.handle.take_message`; its callback receives only the message.
The Humble-only executor adapter now retains the original metadata for the two
raw command subscriptions, while delegating all other subscriptions unchanged.
Source age still uses the actual DDS source timestamp, never a receipt restamp.
Shutdown callback exceptions now preserve a FAIL result instead of losing it.

Fifth run [40098521277](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098521277), source `4a7bfae8d1f88722a2faa81af5b6d291b53dd6ed`, reached the empty-path goal with real RPP commands (`Reached the goal!` / `Goal succeeded` in native.log).
Final report serialization rejected ROS's numpy uint8 UUID elements. The 16
original UUID bytes are now explicitly converted to JSON integers, with length
and range validation. This run is retained as a report-writing failure, not a
completed validated comparison; the eight-case gate correctly stopped at one.

Sixth run [40098944552](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40098944552), source `dd715db33617df00f69f944a6398ebe1d63bcbbd`, attempted all eight cases.
All four RPP cases passed independent validation: empty/diagnostic goal reached,
blocked/dropout SAFE_WAIT, no footprint contacts or keepout violations. MPPI's
four attempts activated its native plugin but stopped before goals because its
default `/trajectories` publisher escaped the namespace. This visualization topic
is now explicitly remapped into `/c3_nav2`; the outside-topic audit is preserved.
This is 4 validated native results, not an 8-case completed native comparison.
The original eight-attempt summary is retained in `results/minimum_attempt_40098944552.json`.

The workflow gates on one empty RPP case: only actual GOAL_REACHED plus
independent evidence PASS permits the remaining seven sequential cases. The separate synthetic obstacle
diagnostic has a full-footprint swept reference feasibility check. That reference
is never supplied to Nav2 or used to move the plant. Original arena fixtures,
including D0 strict-parking SAFE_WAIT cases, remain unchanged.

Artifacts retain logs/trace/package lock for 14 days; generated maps are excluded.
The workflow has only branch/path-limited push, contents:read, one hosted job,
35-minute job timeout (12-minute build, 20-minute native step) and cancellation of obsolete runs. Build networking is separate
from runtime `--network none`; no secrets or robot endpoints.
