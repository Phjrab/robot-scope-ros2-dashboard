# C3 Humble Nav2 native comparison candidate

This directory implements an isolated **native execution harness** and offline
tests. The first actual Humble minimum comparison completed on a GitHub-hosted
Ubuntu 22.04 runner: **8 native records, 8 evidence/safety validation PASS,
7/8 scenario expectations met**. RPP reached both goals; MPPI reached the empty
goal but timed out in the separate obstacle diagnostic and safely waited.
See [the recorded summary](results/minimum_native_summary.json) and
[C3 follow-up](../../docs/parallel-review/20261024/C3/FOLLOWUP.md) for source,
Actions/artifact URLs, actual image digest/package versions and failure details.
The authoring host still has no Humble/container runtime. No physical qualification
or controller winner is claimed.

The fixture generator, geometry tests and command-boundary tests are
`surrogate/offline`. They contain no navigation planner and cannot substitute for
Nav2 execution. Actual NavFn, RPP/MPPI, controller server, BT navigator and behavior
server are selected by `launch/native.launch.py`. Native execution uses Humble
Nav2 1.1.20. Original `native_plan.json`, `native_comparison.json`, image-lock and
offline results describe the initial preparation stage; the minimum summary
supersedes their NOT_RUN status only for these eight cases. The 144-run expansion
has not been executed and is not automatically started.

## Local checks

Run from the repository root. Use a project virtual environment; no global install:

```bash
python3 -m venv --system-site-packages work/c3-venv
work/c3-venv/bin/python -m pip install -r experiments/competition_nav2/requirements-offline.txt
work/c3-venv/bin/python -m unittest discover -s experiments/competition_nav2/tests -v
work/c3-venv/bin/python experiments/competition_nav2/configure.py
work/c3-venv/bin/python experiments/competition_nav2/fixtures.py --output work/c3-fixtures
work/c3-venv/bin/python experiments/competition_nav2/preflight.py --output work/c3-preflight.json
```

Preflight returns code 2 for an unavailable container runtime. `unshare -Urn true`
is only a capability probe; success does not provide Humble or authorize a host ROS
launch. On this host it succeeded; native launch was still not attempted.

## Build once, run with no network

On an existing Docker/Podman Linux host (do not install a daemon as part of C3):

```bash
python3 experiments/competition_nav2/container/manage.py build --lock work/c3-image-lock.json
python3 experiments/competition_nav2/container/manage.py run \
  --lock work/c3-image-lock.json --controller rpp --variant baseline \
  --scenario empty --output work/c3-native/rpp-empty
python3 experiments/competition_nav2/validate.py work/c3-native/rpp-empty/run
python3 experiments/competition_nav2/run_minimum.py \
  --lock work/c3-image-lock.json --output work/c3-minimum
```

The one-case driver supports `--runtime podman`; the eight-case driver uses Docker.
The minimum run gates on actual empty RPP goal success plus independent validation,
then executes the other seven cases, retaining failures. Every run uses a fresh
container and the same immutable image. Build resolves the Ubuntu 22.04/Humble base digest,
records the installed package list and immutable local image ID. Subsequent runs
require that exact image. Rebuild compares the full package lock and refuses
transitive drift; an apt snapshot/archive may be needed to recreate it later.
No digest or installed package versions are invented: image lock remains unresolved
until a real build occurs. `docs/REFERENCES.md` pins the *inspected source* independently.

Runtime uses `--network none`, no capabilities, no privilege, no host PID/IPC/network,
read-only root/repository and a dedicated result mount. The driver verifies the
container NetworkMode before start. Launch and runner both reject non-loopback
interfaces, non-Jammy/Humble environments or DDS discovery overrides. Domain 193,
namespace `/c3_nav2` and ROS_LOCALHOST_ONLY are additional containment, not proof alone.

The wrapper terminates only its launch/runner process groups and tracked descendants,
records cleanup, and removes its uniquely named container even on failure. A forced
kill is a failed cleanup check. To stop an externally interrupted run, use the exact
container name in `container_receipt.json`: `docker stop <that-name>` then
`docker rm <that-name>`. No robot services are involved.

## Shared test conditions and limits

- Read-only rulebook-20261015 arena geometry, original 8 x 6 m design coordinates.
  `map_transform=null`, DRAFT route and dimensional uncertainties remain unchanged.
- Same start `(5.99, 1.65, pi/2)` and goal `(5.99, 4.35, pi/2)` in every original arena case. The
  original centered cone `(5.99, 3)` and failed `(5.75, 3)` case are preserved;
  the successful historical demonstration at `(5.70, 3)` is a separate case.
- `diagnostic_single_obstacle` is a separate synthetic flat room, start `(2,3,0)`,
  goal `(6,3,0)`, obstacle `[3.7,4.3] x [2.7,3.3]`. Its 1,846-sample swept reference
  has 0.307 m minimum conservative clearance and is only a feasibility check;
  it never drives the plant or supplies a Nav2 path. The original strict-parking
  D0 obstacle SAFE_WAIT results are unchanged.
- Standing mesh envelope 0.716 x 0.324 m, same polygon for both controllers. This is
  neither a measured walking envelope nor the smaller avoidance prototype footprint.
- Ramps, stairs and central platform are occupied. No whole-course success is counted.
  Static occupied/unknown/outside cells block motion; static geometry remains immutable.
- Parking is provisionally allowed for the historical comparison; `parking_forbidden`
  makes it occupied. Any footprint intrusion is tested, not just center position.
- SIM_GT map/odom/base_link; differential planar plant, no gait/slip/braking physics.
  Virtual scan is 360 ideal horizontal rays, first hit at <=2 cm increments, 10 Hz,
  50 ms delivery delay. Cones use their 0.26 m square base projection. This differs
  from the old multi-height triangle renderer and is not XT16 calibration.
- Both candidates use 20 Hz controller cycles, final v <=0.18 m/s, |w| <=0.6 rad/s,
  normal-command a <=0.3 m/s² and alpha <=1.2 rad/s². Emergency zero is instantaneous
  by simulation assumption and is not a physical stopping-distance claim.
- `baseline` is a safety-constrained comparison starting point, not untouched upstream
  defaults. Tuned deltas are explicit in `config/manifest.json`: RPP lookahead .4→.25 m;
  MPPI steps 56→40 and batch 1000→1500. No empirical tuning claim is made.
- MPPI uses DiffDrive, shared velocity limits and model_dt .05 s matching 20 Hz. No
  unsupported newer acceleration parameters are injected. Acceleration is enforced at
  the same final plant boundary for both; MPPI's internal model does not model it.
- Fixture seed is fixed. Humble MPPI exposes no RNG seed parameter. This minimum
  comparison has one sample per case; stochastic variability remains unmeasured.

## Final command boundary and evidence

Raw controller and behavior Twist outputs have separate private topics. Only the
plant publishes `sim_actuator_cmd`. Action status gates ownership; conflicting active
owners outside HOLD latch a fault. HOLD clears commands and advances epoch. RELEASE
requires a new command/source timestamp. Receipt TTL is .25 s; source age is checked
separately using DDS realtime timestamps on the same container host. Unavailable/future
timestamps fail closed. Sensor source age plus receiver-local receipt age must be
<=.3 s; stale faults do not auto-resume. There is no cross-host monotonic subtraction.

The delayed command probe is explicitly synthetic. Recovery probing calls the actual
native Spin action while held and requires native nonzero recovery output plus exact
zero simulated actuator output. No manual GREEN or production motion API is added.
This experimental boundary does not replace or duplicate the production arbiter.

Native receipts include active lifecycle readback, all explicit controller parameters,
plugin libraries in the real controller process, package versions, native logs,
actual NavigateToPose/Spin results, raw and final commands, scan timing, graph owner
snapshots and per-process CPU/RSS samples. Native evidence is rejected without these.
Compiler/parameter presence alone does not prove a parameter is consumed by a plugin.

Independent validation recomputes motion from actual actuator commands and interpolates
contact at <=5 mm footprint-corner displacement / <=.01 rad. Static grid cells use
convex SAT and unknown is blocked. Clearance is a conservative EDT/radius/cell-diagonal
proxy combined with dynamic polygon distance, sampled along the same interpolation;
it is not a continuous physical clearance certificate. Reports retain goal success,
SAFE_WAIT, failures, wall/sim time, path length, plant deadlines, raw command timing
and resource samples separately. VM/host timings are never converted to Jetson speed.

See `docs/HANDOFF.md` for integration boundaries and the role review document at
`docs/parallel-review/20261024/C3/REVIEW.md` in the repository root.

## Round 3: preserved RPP and observed replanning

`repro/image-lock.json` preserves the **executed** Humble 1.1.20/rclpy 3.3.22
package graph and base digest from native run 40099437117, not an untested tag.
`repro/rpp-native-params.yaml` is its actual RPP config; the new tests compare it
against the unchanged candidate. `repro/provenance.json` retains action terminals,
validation and evidence hashes before the remote artifact expires.

The existing executor now records the native planner's `Path`, native global
costmap messages (lossless zlib occupancy bytes), and source-pose-tagged scans.
These are subscribers only. The plant still moves exclusively from gated native
commands. The appearance proof reconstructs scan hits, new lethal costmap cells,
and a changed native path avoiding the obstacle. The independent actuator replay
continues checking swept full-footprint contact, freshness, HOLD and final ZERO.

The new cases preserve start `[2,3,0]`, goal `[6,3,0]`, 65 s budget, body, sensor
and parking/terrain policy of the separate diagnostic room. The appearing case
changes only appearance to 3 s. The two-obstacle case adds `[5.0,2.7]–[5.3,3.3]`
to the original `[3.7,2.7]–[4.3,3.3]` obstacle. Offline witness paths only prove
feasibility and are never supplied to Nav2 or the plant. These are not competition
geometry or physical feet/gait clearance claims. Original strict cases and
historical MPPI failures remain available and unchanged.

C1 can inspect the ROS-free machine-readable contract or invoke the existing
isolated executor. The CLI has no live mode or production consumer:

```sh
python3 experiments/competition_nav2/rpp_contract.py manifest
cp experiments/competition_nav2/repro/image-lock.json /tmp/c3-lock.json
python3 experiments/competition_nav2/container/manage.py build --lock /tmp/c3-lock.json
python3 experiments/competition_nav2/rpp_contract.py run --mode isolated-sim \
  --scenario diagnostic_single_obstacle --lock /tmp/c3-lock.json --output /tmp/c3-new-run
python3 experiments/competition_nav2/run_extension.py --lock /tmp/c3-lock.json \
  --output /tmp/c3-new-extension
```

The build rejects transitive package drift. Hosted runners need to reconstruct
the image because prior local image IDs do not survive a job; this reuses the
existing build harness and exact lock. Execution always uses network-none.
`run_extension.py` schedules three identical RPP baselines, appearing and two
obstacles, then blocked/dropout (seven runs). It retains evidence/safety and
expected-outcome gates separately; no MPPI success condition is imposed on RPP.
Results and exact tested source are recorded in `docs/parallel-review/20261024/C3/ROUND3.md`.
