# C3 ROUND6 — actual checker reproduction and isolated correctness overlay

Starting local/remote HEAD `86e73f8349581c26dc3af59505b55407b3d0412c`, clean role clone;
main `104692fa0070ef085eee918913ea05fdb2d88c05`. ROUND5 remains rejected:
native40260839144 tested a70f22dd, .58 inflation applied, actual distance .9611m,
zero actual contacts but 15/51 truth-invalid and 51/51 grid-invalid paths, no goal.
The first invalid path predates motion. Later progress/Spin failure and 377 missed
20Hz cycles are retained, not used to explain away the first invalid path.
ROUND5/FAILURE/NATIVE and read-only D0 dc24b598 ROUND5 were reviewed.

Stage A introduces only a native C++ test executable linked to the locked installed
Smac Lattice and MPPI libraries. CostCritic's protected test seam initializes state
but calls the original inCollision and score methods; NodeLattice::isNodeValid is
also called. No original checker function is reimplemented in Python. It records
direct/score results, actual/cached-pose perimeter cost, primitive acceptance,
per-case duration and loaded library hashes. Stock failures are evidence, not a
navigation PASS. The native result is pending publication/execution.

Inputs and exact upstream commit/source hashes are under
`experiments/competition_nav2/overlay/`. D0's actual published results/checker_cases.json
and coverage.json are hash-pinned read-only copies. Explicit synthetic raw bytes
cover shortcuts, fractional pose/yaw, interior lethal/unknown, out-of-map,
nonlethal inflation, a valid .68m corridor for the .62m-wide rectangle, and a
rotation with free endpoints. B1 point10/16 sparse cells are synthetic raw-field
reproductions with assigned ordinary costs, **not recovered historical raw bytes**.
Point16 is not assumed to have point10's cause. These inputs never become a native
planner prior. The real old atomic raw checker packet alone is INPUT_REQUIRED.

The preserved image lock already contains compiler/CMake/development dependencies;
the probe build adds no apt packages. A separate image contains the test executable,
leaving /opt/ros unchanged. No native navigation case, retuning, common-role write,
robot/camera access, service change, deployment, main merge/push or PR is performed
by stage A. Subsequent planner-only and closed-loop gates remain NOT_RUN until the
small original/fixed C++ comparisons pass. Robot qualification is always NOT_RUN.
