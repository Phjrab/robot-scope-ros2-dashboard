# Non-driving policy follow-up — 2026-10-16

The user reopened remaining work excluding driving. The diagnostic software
identified in [POLICY_RUNTIME_WINDOW.md](POLICY_RUNTIME_WINDOW.md) was deployed
as `cdebee40d212759703300ffc1e2de17ed93a4846` and used in one separately approved
operating localization-only window on 2026-10-16. That window reached fresh input
readiness without initialpose, then retained **ABORTED: 38 complete samples plus
one partial API sample** because the collector hit its observation boundary.
Owned cleanup succeeded. The planner's two readback futures remained pending
while its global costmap waited for the absent map transform; the evidence below
separates this runtime condition from the collector error. MR-MS-003 enforcement
remains incomplete. The bridge remains stopped under the manual-control handover.

## Actual change

The existing production observer still issues only the fixed five
`GetParameters` and five `GetState` requests. It now retains one finished attempt
as optional `robot-scope.nav2-policy-timing.v1` diagnostics. The real default
provider projects these through `GET /api/v1/mission-plans` →
`context.policy_evidence.diagnostics`, including when effective parameters are
missing. This adds no HTTP setter or alternate policy provider.

Each fixed service endpoint reports `dispatched`, `done` and `cancelled`. Future
state is sampled **before owned cleanup**: cancelling a pending future cannot
make the diagnostic imply that its response arrived. A partially dispatched
parameter/state pair remains visible; unsubmitted endpoints have null future
states. The record contains an attempt sequence, outcome, allowlisted reason,
batch age, interval between tick entries, authority lookup duration in the final
tick and duration of the attempt's request-dispatch loop. Batch age is measured
at diagnostic capture, after the final authority lookup; the existing deadline
decision still uses the tick-entry clock. These are local monotonic durations,
not measured network or server latency.

The record is retained across a newly started in-flight batch and has its own
`age_s`. Reading the cache does not dispatch requests or refresh that age. This
prevents the narrow interval after a failed attempt from being the only chance
to inspect its evidence. A later authority/service failure replaces the record
with its own failed attempt, zero dispatched endpoints and no batch age.

The provider accepts only the known schema, fixed ten endpoint names, boolean
future states, finite nonnegative durations and a bounded integer attempt
sequence. Arbitrary keys, paths and exception text are discarded; unavailable
future metadata remains null. The record is diagnostic evidence only and never
enters semantic context revisions, footprint/config pins or enforcement scopes.

The 250 ms timer, 500 ms batch deadline and 750 ms evidence freshness boundary
are unchanged. Late polling of ten completed futures still returns
`POLICY_READBACK_TIMEOUT`; its record distinguishes that state from a named
pending endpoint. It cannot establish exactly when a future completed, why the
executor was late, whether a service server replied, or which network segment
was delayed. No timeout/freshness relaxation, rebasing or policy-true branch was
introduced.

## Source, local validation and runtime boundary

The original software baseline was clean main `361c019`. The following hashes
also match the subsequently deployed, clean source
`cdebee40d212759703300ffc1e2de17ed93a4846`; they were checked against that Git
revision rather than reassigned from a later source tip. The local software
validation used CPython 3.13.2 from `.venv`, without `rclpy` or a `ros2` executable.
The later actual device window is recorded separately below and in
[NONMOTION_FOLLOWUP.md](NONMOTION_FOLLOWUP.md).

| File | SHA-256 |
| --- | --- |
| `robot_dashboard/ros/policy_readback.py` | `e2ddf6fa9428f600736f48a8bf1bfa82d754784ad19abc2e95418fbeefcf63f3` |
| `robot_dashboard/navigation_policy.py` | `510722c323cafe332da7bb5d4f211163663416a7ed1117661b7d1a6d87845a05` |
| `tests/test_policy_readback_diagnostics.py` | `afd1bdc62c32b16886e25f22efd6da4e205896d9c2121d6bbb71cc286b6fa0eb` |
| `tests/test_runtime_policy.py` | `b405be8c30c340e71f5259dbb1a6db4a32ba0867a2c0c600347d62b13f9b7a24` |

Focused commands:

```text
.venv/bin/python -m unittest discover -s tests -p 'test_policy_readback*.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_runtime_policy.py' -v
git diff --check
```

Results: **9 + 17 tests PASS**, diff check PASS. These are software tests using
the actual observer, provider, default factory and context with ROS-shaped
fixtures. They cover all-ten-done late polling, a single named pending endpoint,
partial dispatch/cleanup, authority/service absence, retained-record age,
unchanged exact deadline/freshness boundaries, sanitization, semantic stability
and no goal submission. Existing dispatch tests cover every one of the ten
partial-dispatch failure positions and healthy recovery. The initial focused
Ruff invocation was unavailable in that interpreter; the integration owner
subsequently completed the combined static/full checks with the existing
validation environment, recorded in `NONMOTION_VALIDATION.json`. No package was
installed for this subtask.

## Actual approved policy window

One start and one stop ran on 2026-10-16, from 11:13:55.592Z to 11:15:16.219Z.
The source was clean `cdebee40d212759703300ffc1e2de17ed93a4846`, dashboard
PID 87657/invocation `162f310dab5a44ac8526e803f6a05c74`, and localization runtime
invocation `102796:5146075596344`. Operating ROS remained domain 0,
`rmw_cyclonedds_cpp`, interface `enP8p1s0`; the Isaac environment was not applied
to the dashboard. The map and parameter revisions were pinned by the collector;
the parameter revision was
`194c9c18648f9201df464802884022184095422d1b0b91e6d9a75917c9519d77`.
There were zero initialpose, lease and navigation-goal requests. Fifty complete
host probes retained bridge `inactive/dead/MainPID0` and one dashboard identity.
Historical bridge counters were unavailable and were not used as fresh motion
or stationarity evidence. The approved launcher did emit its existing static
and odometry TF; there was no `map → odom` alignment or localized pose.

Startup reached `WAITING_INITIAL_POSE` after 12.3669s. The collector then began
its 60s observation at 11:14:09.784Z. Its original result remains `ABORTED` and
`collector_success=false`: 38 samples completed host/safety/ownership checks;
the last partial sample contained all ten HTTP responses but had no host probe,
completion timestamp or final safety/ownership check. The last complete sample
finished at observation elapsed 58.9110s. All ten GETs in the partial sample
returned HTTP200, leaving only about 3.43ms before the observation deadline.
`host_probe()` reused that remaining budget for a subprocess and raised
`TimeoutExpired`; the exact host command was not logged. This is a collector
boundary error, distinct from ROS `POLICY_READBACK_TIMEOUT`. The 39 API payloads
are usable diagnostic observations, not 39 fully qualified collector samples.
Neither this record nor a later collector repair converts the run to PASS.

All 39 API samples contained distinct finished-attempt diagnostics (attempts
2385 through 2453, with intervening attempts not sampled). Every sample reported
`POLICY_READBACK_TIMEOUT`, unavailable policy evidence and false enforcement:

| Pre-cleanup future state | Samples |
| --- | --- |
| `/planner_server/get_parameters` and `/planner_server/get_state`: dispatched, pending, not cancelled | 39/39 |
| Other eight fixed node/costmap endpoints: dispatched, done, not cancelled | 39/39 |
| All ten done at a late poll | 0/39 |

The batch age at capture ranged from 0.5026s to 0.7654s; tick-entry gaps were
0.2342–0.2662s, authority lookup 0.0012–0.0149s and dispatch 0.0009–0.0193s.
These are local observer durations, not server/network latency. A done future
at capture does not prove completion within the 500ms deadline. Retained
diagnostic age reached 0.9150s; that is separate from successful policy-evidence
freshness. Successful policy sequence and age remained null. Semantic context
revision stayed constant. The 250/500/750ms timer/deadline/freshness contract was
not changed.

The exact navigation job's retained log ring contains 300 entries, seq172–471;
earlier entries were explicitly truncated. Between 11:14:19.824Z and
11:15:09.825Z, 101 entries report global-costmap waits for `base_link → map`
because frame `map` does not exist. This matches the deliberately omitted
initialpose and absent map alignment. After owned STOP began at seq391,
11:15:10.237Z, the costmap transition unwound, planner logged `Activating plugin
GridBased`, and context-invalid transition/bringup errors followed. All retained
ERROR entries are after STOP; they are not evidence of a pre-stop stale-input
failure. The logs strongly support incomplete planner activation behind the
missing map transform as the explanation for its two pending service futures.
They do not establish an exact native executor stack or a DDS transport fault.
The dashboard's `readiness.planner` flag checks `/plan` publisher presence, not
lifecycle ACTIVE, so its true value does not contradict these observations.

STOP's HTTP response exceeded the collector's separate 3s response budget.
The consumed stop attempt was not retried. Subsequent owned-job polls reached
`API_OWNER_CLEAN`, the final process scan was empty, `cleanup_verified=true`,
and no manual recovery was required. Cleanup took 6.4307s. No additional native
window was executed to repair or reinterpret these results.

Private evidence remains outside Git under the coordinated follow-up directory:
`device-evidence/policy-window/policy-window-summary.json`,
`policy-window-api-trace.json`, `device-evidence/navigation-retained-log-pages.json`
and `policy-review.json`. The integration record indexes the exact captures.

## Remaining policy and planner work

The production path already exists:
`NavigationRosGateway → RosPolicyReadback → RuntimePolicyProvider →`
`configure_mission_routes(default) → NavigationContext → compile/start/dispatch`.
Reimplementing it would not supply missing collision enforcement. MR-MS-003
now has a separate geometry-only artifact builder documented in
[COLLISION_MASK_ARTIFACT.md](COLLISION_MASK_ARTIFACT.md). It still needs a native
publisher and qualified global/local costmap, controller, BT-replanning and
map-epoch ingestion evidence, including verified effective footprint behavior.
All four enforcement scopes remain false. This is a remaining software/native
integration dependency, not merely missing equipment permission. None of it is
a prerequisite for independent Stereo VSLAM observation or new-map creation.

NativePlanner's existing product route is:
`POST /api/v1/mission-plans/{identifier}/plan-preview → MissionRoutes.preview →`
`NativePlanner.plan → /compute_path_to_pose`, fixed `GridBased`, `map` and
`use_start=true`. `app.py` passes only the explicit server-side
`--mission-native-preview` resource window, whose default remains false. The
shared reservation, environment/server identity checks, bounded cleanup and
uncertain-goal quarantine are already implemented. Source hashes are
`wiring.py=a79872372ef0a4369d7ef48dc0c2e5989dd333fa7a43e9f9ff1f13d3e78e6ae4`
and `planner.py=115d96fd064f4e8c79fda5de74ea9a87d8bf31a02336fcd8d5bc1864ab5dde83`.
The separately approved isolated synthetic-map product HTTP run on deployed
`cdebee4` now reports `actual_native_synthetic_http_route=PASS`, with qualified
owned cleanup. It used domain 84/localhost CycloneDDS and private map/TF topics;
the real router, factory and NativePlanner reached the installed native planner.
Free-space planning succeeded, invalid authored targets were rejected, a
disconnected target was native-infeasible, and the unknown-crossing case was
rejected by product path validation. These results do not prove native unknown
collision enforcement, operating-map acceptance or mission execution. The
production policy stayed false. See the current combined record in
[NONMOTION_FOLLOWUP.md](NONMOTION_FOLLOWUP.md); the older acceptance matrix's
NOT_RUN statements describe its earlier snapshot and must not erase this actual
isolated result or promote it to broader operating acceptance.

The minimum diagnostic proposed before this run has been executed: its pending
endpoints and retained native logs now identify the missing-map-frame condition.
No additional localization source fix, longer policy deadline or looser
freshness gate is justified by that deliberately no-initialpose window. The
private v4 collector preparation now distinguishes its observation-boundary
exception and complete/partial records; 54 existing and 26 focused fake checks
passed. It has not run on the device, and it preserves this original v3 result.
A future policy readback window needs its actual map-frame/lifecycle
prerequisites and current field authorization; do not repeat the same condition,
inject an unverified transform or replay an old initialpose merely to pass.
Successful parameter replies would still not establish collision enforcement.

### Concrete stationary-window constraints

The existing `POST /api/v1/navigation/localization/start` takes the current
`map_id`, `map_revision` and `parameters_revision`. Its preflight does not require
a ready control bridge; the bridge can remain stopped. It does require configured
transport, the expected target, no active manual lease/action window, zero
navigation command state, an exact saved map and idle shared ownership. Existing
stop is `POST /api/v1/navigation/localization/stop`. Starting a new window is a
pipeline operation, not a passive API read.

The fixed launcher starts the navigation runtime, map server, controller,
planner, behavior server and BT navigator plus their lifecycle manager; the
coordinator also owns the required localization input job. It does not have a
planner-only launch mode. Without initialpose, `navigation_runtime` still
publishes the configured static `base_link → hesai_lidar` and fresh
`odom → base_link` transforms. It does not publish `map → odom` until alignment
exists. Therefore an approval that excludes **all operational TF publication**
does not authorize this launcher. The exact required TF/pipeline scope must be
included when preparing a stationary policy window; do not describe it as
"no TF".

Hypothetical preview is deliberately separate from execution readiness: valid
authoring geometry, the exact selected navigation map and idle MS/MR ownership
can reach `NativePlanner` even while policy enforcement is false. Its body uses
`start_source="hypothetical_preview_start"` with an explicit map-frame start,
definition revision and request ID. It never establishes current robot pose or
opens mission dispatch. The installed `run_go2_humble.sh` does not currently pass
`--mission-native-preview`, so enabling that window needs an explicit qualified
dashboard invocation/configuration; setting an unrelated environment variable
will not enable it.

Even with that window enabled, the current global costmap uses `global_frame=map`
and `robot_base_frame=base_link`. This actual no-initialpose startup retained
global-costmap waits on the absent map transform. A hypothetical action
start bypasses current-pose selection in the request, not this costmap lifecycle
requirement. The successful isolated synthetic-map run does not guarantee a
successful path in that operating window. Do not inject an unverified transform
or replay historical initialpose
to make it pass. A missing/inactive server is a native blocked/negative result;
positive product acceptance instead needs a qualified isolated planning
environment or independently authorized valid alignment. Collision-mask and
controller enforcement remain unavailable even if a free-space path succeeds.

## Localization startup status

The independently reproduced startup-adjacent defects and bounded callback
diagnostics were already fixed. This follow-up did not modify them: current
`navigation_runtime.py` hash is
`66e4fbe4fb57113cde459cc45fb3306569bbf41dba00d7f0c1abf710963ac519`,
`localization_diagnostics.py` is
`90a010d966573f83aa35515e0da4af475e51196dc01de1eda2ddce76c93fc029`,
and `nav2_params_go2_humble.yaml` remains
`b69ad567f6ab2a6cc8b8a651191676ae69b02e8d9fca162f1afdce5f8007b6c0`.
The actual earlier candidate863682e stationary window recorded cloud and odometry
callback/accepted deltas of 1810 each with no new rejection, stable invocation
and publisher generations. That is useful successful current-input evidence;
it does not establish the cause of the older stale startup. The historical cause
remains **UNCONFIRMED**, as do independent geometry/TF-authority acceptance rows.

In the new `cdebee4` window, all 39 API observations reported
`INITIAL_POSE_REQUIRED` and `inputs_ready_waiting_initial_pose`; no retained
health record reported STALE. Maximum current health ages were cloud 0.0401s,
odometry 0.1223s and runtime health 0.1220s. Cloud and odometry diagnostic accepted
counters each advanced from 20 to 603, with one initial `publisher_not_unique`
rejection apiece and no additional rejection; publisher GIDs and source generation 1 stayed
stable. This agrees with normal graph-discovery warmup, not a permanent rejection
latch. The 39 API records contain 37 distinct producer diagnostic sequences
because those snapshots are emitted at about 1Hz and carry their own timestamps.
RMW receive metadata remained unavailable, so executor-queue latency cannot be
inferred by substituting source or callback timestamps.

These are actual fresh-input observations before initialpose. They do not prove
map localization, precision accuracy, body alignment or the historical stale
failure's cause; no localized pose was produced in this window. See
[LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). No further
speculative runtime change or repeated unchanged full validation was required by
this evidence review.
