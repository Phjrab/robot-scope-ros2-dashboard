# Route Planner main compatibility acceptance

## Integration identity

- Main before integration: `0e0f3cebaee59c72538a879c4832d068f9b73976`
- Feature tip: `ab1010be1ec11e343e04b38fed7e3b11cd3f7a48`
- Common ancestor: `ee315d2f1ff733857f75cf43ea73e8b889f79931`
- Main-only commits reviewed: 24
- Feature-only commits reviewed: 8

The feature was merged with normal three-way history preservation. The two
tracks overlapped in `robot_dashboard/app.py` and
`tests/test_api_contract_phase8.py`; Git reported no textual conflict. All C4,
C4C, wireless transport, camera, mapping, localization, control, Mission and
Cockpit changes from current main remain present.

## Compatibility correction

The final Route Planner rehearsal work added five endpoints after the feature
branch's earlier global route inventory update. The application therefore has
104 HTTP routes, including 103 under `/api/v1/`, and 60 mutations. The exact
method counts are 44 GET, 53 POST, 1 PUT, 4 PATCH and 2 DELETE. The global
same-origin assertion still covers every mutation; its expected inventory was
updated to the exact current values rather than weakened or removed.

## Runtime and safety boundary

Route Planner is an external-dashboard component. It owns order, graph,
recommendation, advisory guidance, rehearsal and Mission-draft state only. It
does not own a ROS node, Control lease, ARM, deadman, velocity command, Sport
request, Navigation goal or Mission start.

The live perception provider remains deliberately unavailable: the current
provider reports typed `UNKNOWN` evidence and cannot make an autonomous edge
ready. Rehearsal remains disabled unless the server-owned
`ROBOT_SCOPE_ROUTE_PLANNER_REHEARSAL` opt-in is explicitly set. External
deployment must leave that flag unset. The known cross-application rehearsal
interlock remains a later integration item and cannot affect production while
the rehearsal feature is disabled.

This integration changes no robot-side service or artifact. Deployment is
limited to the external dashboard host; onboard Jetson deployment is deferred.

## Verification

- Route Planner Python: 156 passed
- Route Planner/Cockpit focused JavaScript: 11 passed
- API inventory and C4C compatibility: 49 passed
- Full repository Python in the pinned environment: 1,288 passed
- JavaScript unit: 278 passed
- Playwright browser E2E: 34 passed
- Ruff, configured mypy, frontend syntax, tracked-source secret scan and
  `git diff --check`: passed
- System Python: 1,284 tests ran with the existing single import error because
  `fastapi` is not installed in the system interpreter

No Jetson command, service transition, Navigation goal, Mission start, lease,
ARM, deadman or robot motion occurred during repository compatibility testing.

## External dashboard deployment

The merge commit `3d62e254decaafda9b793bb43901141fd237ae48`
passed CI run `33969563051` on both supported Ubuntu/Python jobs before
deployment. Its Git archive SHA-256 is
`3825e035d06eca5be82d84bf676f2c4199b982dbcf38aac490b72da55be89a5f`.

Only the external dashboard Jetson at `192.168.50.10` was changed. The archive
was verified before extraction into the immutable release directory
`/home/jetson_orin_nano/releases/robot-scope/3d62e254decaafda9b793bb43901141fd237ae48`.
The stable `robot-scope` symlink was switched atomically from exact release
`10a7fa9cec2c329f2c50edc9ad98de13a22689da`; the rollback symlink
`robot-scope.pre-3d62e25` preserves that release. The dashboard-only lifecycle
API reported no blockers and restarted `robot-scope.service`. The active
symlink and process working directory then both resolved to the new exact
release.

Post-deployment verification established:

- dashboard service active and root page HTTP 200;
- deployed OpenAPI inventory: 104 HTTP operations, 103 under `/api/v1/`, 60
  mutations and 21 Route Planner operations;
- deployed Route Planner panel SHA-256
  `2bc0bcd8599287fe0e41aa3777f21d50811d72ff1815f2f4c6cbc042632c1cd8`,
  identical to the committed source;
- Route Planner available in `EMPTY` state with `motion_authority=false`;
- perception explicitly `UNKNOWN`/not fresh and rehearsal disabled/inactive
  with side-effect count zero;
- no Control lease, deadman or non-zero manager command;
- Navigation pipeline, localization session and goal all idle;
- Mapping pipeline and operation idle.

The robot was offline during this external-only deployment, so the Control
Bridge and XT16 preview remained unavailable. This is not a Route Planner
failure and no attempt was made to start either one. The onboard Jetson was
not contacted, modified, restarted or pointed at this release; its deployment
remains explicitly deferred.
