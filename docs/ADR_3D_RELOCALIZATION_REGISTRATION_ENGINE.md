# ADR: bounded offline 3D relocalization registration engine

Status: accepted for Track D1 software use; live use remains gated

## Decision

Robot Scope adds a ROS-independent C++17 `bounded-se2-icp` reference engine
for deterministic, offline 3DoF registration. It estimates only `x`, `y` and
`yaw`; `z`, roll and pitch are never estimated or silently replaced. A strict
Python adapter owns validation, one-job concurrency, fixed argv construction,
timeout/process-group cleanup and bounded JSON result validation.

This is not a live localization owner and it is not wired to HTTP, Cockpit,
ROS, Nav2 or the control path in D1.

## Dependency audit and backend choice

`config/ros_dependencies_humble.json` already declares `libpcl-dev`,
`libeigen3-dev`, CMake, ament and the ROS PCL packages for x86_64/aarch64.
The repository installation script consumes those fixed apt groups. It does
not pin the Ubuntu archive's resolved PCL package version.

The authorized hardware-free macOS environment had Apple Clang 17 on arm64,
but no CMake, PCL pkg-config record or Eigen pkg-config record. D1 forbids
Jetson access and adding an unreviewed large dependency. Consequently PCL NDT
and GICP were not falsely reported as built or benchmarked. No Open3D, Eigen,
OpenMP, pip package or production apt dependency was added.

The portable bounded SE2 implementation was selected as a software reference
backend because it could be built and exercised in the authorized environment.
It does not claim equivalence to PCL NDT or GICP. A future production backend
decision requires an exact aarch64 release build and same-corpus PCL NDT/GICP
comparison before D2 may treat either as the deployed default.

## Fixed algorithm contract

Preprocessing is compiled into the server-owned core:

| Setting | Value |
|---|---:|
| reference voxel | 0.20 m |
| query voxel | 0.15 m |
| minimum range | 0.50 m |
| maximum local range | 20.0 m |
| z band | -2.0 to 3.0 m |
| sensor self radius | 0.35 m |
| correspondence bound | 0.75 m |
| minimum filtered query | 500 points |
| coarse candidates | at most 128 |
| refinements | at most 8 |
| returned candidates | at most 3 |
| refine iterations | at most 30 |

Finite points are range/z filtered, voxelized and sorted deterministically.
The coarse search is a bounded XY/yaw grid around the caller's validated seed.
The best eight candidates are refined by bounded point-to-point SE2 ICP over a
spatial hash. No unbounded correspondence matrix or GPU is used.

The JSON-facing request permits explicit files only for offline tests and
staging. The adapter requires absolute regular binary PCD files beneath a
server-owned allowed root, rejects symlinks, validates float32 `x/y/z`, bounds
header/file/point counts and never accepts an output path. Future HTTP must
resolve opaque map IDs internally and cannot forward caller paths.

## Result and confidence

The strict result schema is `robot-scope.relocalization-result.v1` with backend
identity, up to three ranked candidates and bounded timing. Every numeric
value must be finite. The adapter recomputes confidence and rejects a child
whose label does not match policy.

| Confidence | Required evidence |
|---|---|
| HIGH | converged, >=500 query points, overlap >=0.70, fitness <=0.04, top margin >=0.15 |
| MEDIUM | converged, >=500 query points, overlap >=0.50, fitness <=0.09, top margin >=0.05 |
| LOW | converged, >=500 points, overlap >=0.30, fitness <=0.16, but not stronger evidence |
| REJECTED | any required minimum fails |

Convergence alone never accepts a candidate. Symmetric geometry with no
top-one margin cannot be HIGH. These thresholds are synthetic acceptance
policy, not certified live safety or localization accuracy limits. Occupancy
known-free/clearance checks remain D2/D3 work.

## Process and safety boundary

- one child at a time;
- fixed executable identity and fixed argv, `shell=False`, no stdin;
- 15 second maximum timeout and process-group kill;
- 64 KiB stdout, 4 KiB stderr and 16 KiB request bounds;
- no output path, URL, topic, host or port in the contract;
- no ROS imports in the core;
- no API/UI/live owner, initial pose, goal, lease, ARM, deadman or motion.

Track A/B/C, strict wireless odometry/time guards, C2 FAST-LIO, C3
localization-only ownership and the D0 family contract are unchanged.

## Aarch64 PCL follow-up — 2026-09-08

The external Orin resolves `libpcl-dev 1.12.1+dfsg-3build1` and
`libeigen3-dev 3.4.0-2ubuntu2`. A retained, path-free stationary D2 query was
compared offline against the exact source PCD. PCL GICP and unconstrained
six-degree-of-freedom NDT both reported optimizer convergence, but their
solutions varied materially by seed. The six-degree-of-freedom result also
cannot be admitted as a 3DoF result merely by dropping z, roll and pitch.

The package therefore adds two compile-time-only PCL executables behind
`ROBOT_SCOPE_BUILD_PCL_BACKENDS=OFF`:

- `pcl-ndt2d`, using PCL's x/y/yaw-only NDT implementation;
- `pcl-gicp`, retaining explicit z/roll/pitch correction rejection.

Both reuse the existing bounded SE2 search results as at most three refinement
seeds. They retain the 30-iteration ceiling, 0.75 m correspondence bound,
point-count limits, process timeout, strict result contract and confidence
policy. The server chooses one exact executable from a fixed environment-owned
allowlist before constructing the manager. HTTP callers cannot select a
backend, and the default remains `bounded-se2-icp`.

GICP is available for offline comparison only and is not in the D2 runtime
selection allowlist. A failed refinement, exception or non-finite
or out-of-plane transform is converted to a rejected candidate using the
original bounded seed for diagnostics. Such a failure can never be repackaged
as a converged result or trigger a fallback to another backend.

The deterministic comparison tool reports converged and policy-accepted case
counts separately from aggregate error. With `--require-acceptance`, it exits
non-zero unless every case converges, every top candidate is non-rejected and
the published D1 median/p95 translation and yaw limits all pass. A clean child
exit therefore cannot be mistaken for backend qualification.

On the retained live query, `pcl-ndt2d` produced converged candidates, but the
top two were spatially distinct and had no positive fitness margin under the
existing ordering. This correctly remains an advisory ambiguous result. It is
evidence that the previous `converged=false` condition can be isolated without
weakening the portable engine's convergence threshold; it is not evidence for
automatic pose application or navigation readiness.

The exact `bc3b7c9e0e137b7c385befe41aaa91d8b1bfdfac` aarch64 release then
re-ran the deterministic ten-case corpus with the strict acceptance switch.
NDT2D safely returned rejected bounded-seed diagnostics for all ten cases:
zero converged and zero policy-accepted cases. Its small aggregate error is
therefore not an NDT2D result and cannot qualify the backend. Even identical
reference/query input reproduced the no-overlap failure. GICP had already
shown that malformed optimizer state can terminate inside PCL before a C++
exception is available. Both backends consequently remain build-time offline
experiments; the runtime allowlist is again the portable bounded backend only.

A bounded grid sweep then tested 2.0 m and 4.0 m cells without changing the
extent, iteration ceiling, timeout or any acceptance threshold. The 2.0 m
build again produced zero converged cases. The fixed 4.0 m build produced ten
converged and ten policy-accepted cases, with translation median/p95 of
0.001277/0.003105 m and yaw median/p95 of 0.028152/0.097858 degrees. NDT2D may
therefore be selected explicitly only with this compiled grid; the portable
backend remains the default and GICP remains excluded.

The first exact-release live attempt also exposed a bounded performance bug:
the NDT2D target grid was rebuilt independently for each of the three bounded
refinement seeds. The 182,949-point live reference therefore exceeded the
unchanged 15-second child timeout even though collection and map eligibility
passed. NDT2D now constructs the fixed target/source representation once per
child and reuses it for the same three seed refinements. It does not cache
across jobs or inputs. The seed count, grid, extent, iteration ceiling,
timeout, result ordering, convergence, confidence and out-of-plane checks are
unchanged. On the same aarch64 ten-case corpus, runtime p50/p95 fell from
7,465/8,297 ms to 956/1,003 ms while all ten cases retained the identical
published error summary and remained converged and policy-accepted.
