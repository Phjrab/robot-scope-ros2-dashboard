# Stage32 runtime policy contract

> Current scope through40: the user explicitly extended the completed stage36 snapshot. Candidate863682e was deployed; initialpose1 and180s stationary observation were completed and owned resources cleaned. Live acceptance remains partial/false. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). Earlier stop-after36/no-deployment statements below describe the historical software snapshot.41–43 remain NOT_RUN.

**PARTIAL. Production readback/provider connection implemented; runtime policy
enforcement is not complete.** This is not merely a pending equipment approval.

`NavigationRosGateway.setup → RosPolicyReadback → agent.navigation_runtime_snapshot
→ RuntimePolicyProvider → configure_mission_routes(default) → NavigationContext
→ compile/start/dispatch guard → existing MissionCoordinator/NavigationCoordinator`
is the production path. No app/router motion bypass, policy-true request field or
new executor was introduced. The CLI's native preview default remains false.
The optional explicit in-process provider is retained for existing integration
tests; no HTTP endpoint can set it.

Follow-up diagnostics preserve allowlisted observer reason/status/age/sequence even
when parameters are incomplete. Provider evidence stays unavailable, semantic pins
stay unchanged by diagnostics, and all enforcement scopes stay false. The gateway
distinguishes observer initialization/setup/snapshot failures without weakening STOP.
Partially dispatched batches own each future immediately and cancel pending futures
on failure. See [POLICY_DIAGNOSTICS_FOLLOWUP.md](POLICY_DIAGNOSTICS_FOLLOWUP.md);
this follow-up source is not yet deployed.

The existing ROS node asynchronously queries fixed GetParameters/GetState services
on planner_server, controller_server, bt_navigator and both costmaps. A separate
mutually-exclusive callback group checks batches on a250ms timer. There are at most
10 outstanding requests, a500ms batch deadline and the existing750ms runtime-health
freshness boundary. No synchronous ROS service call runs inside render, mission
admission or a shared coordination lock. Each batch pins all unique parameter-event
endpoint GIDs. Parameter events, absent/duplicate authorities, changed GIDs,
timeout/partial/malformed readback and lifecycle inactivity invalidate evidence.
Age begins at request start; a late result cannot rebase freshness. Installed
Humble uses TopicEndpointInfo.endpoint_gid, covered by a genuine-shape fixture.

Canonical semantic pins include effective parameter values, actual circular
radius/padding, footprint revision, node authority incarnations and localization
runtime invocation. Timestamp/sequence/heartbeat/status are observation evidence,
not policy meaning. Expiry closes the gate without changing the semantic pin.
An authority change invalidates immediately before its replacement batch completes.
Unsupported polygon footprints return unavailable; they are not converted to the
authoring default. Effective circular radius conservatively includes both costmap
radii and padding. Spatial planning now checks footprint overlap with KEEP_OUT
edges, in addition to the existing unknown/occupied/grid footprint checks.

**There is no qualified enforcement witness in the installed profile.** Current
Navfn allows unknown; local costmap does not persist map unknown/KEEP_OUT semantics;
annotation zones have no global/local native collision mechanism. The provider
therefore explicitly reports false for global_planning, local_control,
internal_replanning and map_epoch, and returns specific blocking reasons.
An installed plugin name, configuration file, lifecycle active flag, readback or
one valid path cannot turn these scopes true. The implementation deliberately has
no success branch for unsupported mask/controller evidence. MR-MS-003 remains
PARTIAL until that software path and native proof exist.

Next minimum software unit: introduce a versioned Humble collision profile with a
separate immutable map/annotation-pinned mask (preserve original unknown bytes),
conservative circle/polygon footprint and rotated-origin rasterization; connect
both global and local collision behavior plus BT replanning. Add a native witness
for actual ingestion, transform/frame, mask source incarnation and clear/restart
retention. Extend this observer and evaluator only after those producers exist,
with positive production-factory tests from raw observations. Required native
cases include middle-of-path unknown, KEEP_OUT, narrow passage/footprint edge,
clear/restart/parameter change, and active-run loss. No default radius, guessed
alignment, larger timeout or freshness relaxation may open the gate.

Tests distinguish real production factory/observer code with raw ROS-shaped
observations from older synthetic admission fixtures with final policy true.
The raw-observation tests currently prove connection/negative admission/semantic
stability, not positive enforcement. Existing owner-monitor tests prove guarded
policy/source loss cancels only owned goals and retains uncertain ownership.
Provider absence/failure returns blocked state; STOP uses the existing independent
cancellation path. Raw exception/environment text is not exported.
