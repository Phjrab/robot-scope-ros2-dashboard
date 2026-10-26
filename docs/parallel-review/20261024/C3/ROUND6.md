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

## Recorded stock reproduction and one candidate

Native small checker run [40275256434](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40275256434),
code `290a885e51d4d19b1b4adcded3dec6941e52cf85`, completed SUCCESS:
**CHECKER_REPRODUCED**. [Initial packet](ROUND6_STOCK_INITIAL.json) records actual
installed Smac Lattice SHA256 `2c4c5568c78626c1f66d91a4518ae325af6a4e48c93cac46c1dac91383b6679b`
and MPPI critics SHA256 `570f0e692329a00721140320b126c336ea56e322bb806c66d3dac2a4196e6f7b`.
Free-center/78<T82 and point10 synthetic cases pass both stock shortcuts despite
native actual-pose perimeter cost254. Point16 synthetic raw field gives actual-pose
perimeter254, cached-pose0; stock Smac accepts, MPPI rejects. Interior lethal and
unknown also escape perimeter-only checking. NodeLattice accepts the endpoint-free
rotation whose middle pose is natively colliding. This directly measures distinct
mechanisms; it does not recover B1's absent historical atomic raw field.

Initial packets also exposed an input-detail issue in the positive corridor:
Smac's integer center lookup differs from the actual continuous center. The initial
uniform253 field and one assigned center200 make stock Smac reject at an adjacent
253 cell. This is **not** claimed as failure to fit the physical corridor. The final
comparison refines only that synthetic field to D0's explicit wall-distance
inflation recipe and records actual stock center/cached pose. Both stock and fixed
classes evaluate the same final input file. Original packets remain immutable.

Three earlier reproduction infrastructure runs are retained separately:40274348913
link search failure;40274599835 library discovery failure;40274895639 compiled and
ran but output could not be persisted by capability-free root. Explicit library
prefix, host UID and checked output stream repair those issues. No navigation run
occurred in any of these attempts. They are not checker/goal PASS counts.

The single correctness candidate is `omni_checked_overlay`. Its generated YAML is
identical to B1; all seven old RPP/MPPI/SE2/B/B1 configurations were compared with
86e73f8 and are unchanged. All original geometry, margin/padding, primitives,
inflation .58, weights, frequency, CPU/memory, sensor/time/TTL and goal limits stay
fixed. `/opt/ros/humble` and its package lock remain intact. The two source packages
build under `/opt/c3-overlay` in a distinct image using already locked tools.
Exact upstream commit is `a097086719c88f781aa59788eca29ac6ca5e56db`; original hashes,
patch, helper, post-patch hashes and actual loaded libraries are separately recorded.

Smac checks the actual fractional pose/yaw and complete convex polygon against
closed lethal/unknown cells. MPPI bypasses both the free-center skip and conditional
footprint gate when consider_footprint=true. Nonlethal costs remain scoring costs;
unknown follows the caller policy, map exterior is blocked and unknown cannot mask
lethal cells. Lattice primitive points, joins and analytic expansion transitions
are checked during search. A supplemental returned-path/start-connector check does
not replace those search checks. The already-disabled smoother is unchanged.
Sweep spacing is <=resolution/10 corner displacement (2mm here), <=.005rad and
max4096 subdivisions; bound overflow rejects. This is bounded numerical checking,
not proof of exact continuous clearance. MPPI's existing rollout point sampling is
unchanged; actual plant sweep remains a separate required validation.

The sequence is stock packet, same fixed C++ regressions, one planner-only feasible1
with original virtual sensors and actuator held, then one closed-loop feasible1
only if a valid native path is published. Later fixed cases are conditional on
success and stop at the first failure. Real robot qualification remains NOT_RUN.
