# C3 Humble Nav2 native comparison candidate

This directory implements an isolated **native execution harness** and offline
tests. Native execution is **NOT_RUN on the authoring host**: Ubuntu 24.04,
Jazzy present, no Docker/Podman/nerdctl and no Humble installation. There is no
native performance winner, native PASS, or physical qualification in this delivery.

The fixture generator, geometry tests and command-boundary tests are
`surrogate/offline`. They contain no navigation planner and cannot substitute for
Nav2 execution. Actual NavFn, RPP/MPPI, controller server, BT navigator and behavior
server are selected by `launch/native.launch.py`. The launch has not been exercised
against a Humble installation; package/launch/QoS compatibility remains a review risk.

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
python3 experiments/competition_nav2/matrix.py --run --lock work/c3-image-lock.json --output work/c3-matrix
python3 experiments/competition_nav2/compare.py work/c3-matrix --output work/c3-comparison.json
```

Use `--runtime podman` for an existing Podman installation. All 144 runs use fresh
containers and retain failures. Build resolves the Ubuntu 22.04/Humble base digest,
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
- Same start `(5.99, 1.65, pi/2)` and goal `(5.99, 4.35, pi/2)` in every case. The
  original centered cone `(5.99, 3)` and failed `(5.75, 3)` case are preserved;
  the successful historical demonstration at `(5.70, 3)` is a separate case.
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
- Fixture seed is fixed. Inspected Humble MPPI exposes no RNG seed parameter; three
  repeated runs characterize stochastic variability, not bitwise reproducibility.

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
