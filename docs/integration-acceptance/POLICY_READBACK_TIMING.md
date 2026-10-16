# Non-driving policy follow-up — 2026-10-16

The user reopened remaining work excluding driving. This change completes the
next software diagnostic unit identified in [POLICY_RUNTIME_WINDOW.md](POLICY_RUNTIME_WINDOW.md).
It does not complete MR-MS-003 enforcement or turn the earlier timeout into a
diagnosed transport failure. No device operation, service change, ROS query,
deployment, pipeline start, initialpose, goal, TF publication or motion was
performed by this policy subtask. The control bridge remains under the user's
manual-control handover; this change does not restore it.

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

The local baseline is clean main `361c019` before the coordinated follow-up.
The following hashes pin this subtask's source/test bytes; the integration owner
records the final combined source commit, full regressions and any separately
qualified deployment. Local interpreter is CPython 3.13.2 from the repository
`.venv`; this environment has neither `rclpy` nor a `ros2` executable. There is no
new native runtime/config identity for this software-only subtask.

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
partial-dispatch failure positions and healthy recovery. Local Ruff could not
run from `.venv/bin/ruff` or `python3 -m ruff` because it is not installed there;
the integration owner performs repository-wide static checks with the existing
validation environment. No package was installed for this subtask.

## Remaining policy and planner work

The production path already exists:
`NavigationRosGateway → RosPolicyReadback → RuntimePolicyProvider →`
`configure_mission_routes(default) → NavigationContext → compile/start/dispatch`.
Reimplementing it would not supply missing collision enforcement. MR-MS-003
still needs a versioned map/annotation-pinned mask producer and qualified actual
global/local costmap, controller, BT-replanning and map-epoch ingestion evidence.
All four enforcement scopes remain false. This is a remaining software/native
integration dependency, not merely missing equipment permission. None of it is
a prerequisite for independent Stereo VSLAM observation or new-map creation.

NativePlanner's existing product route was inspected without a native call:
`POST /api/v1/mission-plans/{identifier}/plan-preview → MissionRoutes.preview →`
`NativePlanner.plan → /compute_path_to_pose`, fixed `GridBased`, `map` and
`use_start=true`. `app.py` passes only the explicit server-side
`--mission-native-preview` resource window, whose default remains false. The
shared reservation, environment/server identity checks, bounded cleanup and
uncertain-goal quarantine are already implemented. Source hashes are
`wiring.py=a79872372ef0a4369d7ef48dc0c2e5989dd333fa7a43e9f9ff1f13d3e78e6ae4`
and `planner.py=115d96fd064f4e8c79fda5de74ea9a87d8bf31a02336fcd8d5bc1864ab5dde83`.
Inspection is not product-native execution acceptance. The matrix in
[NATIVE_PLANNER_ACCEPTANCE.md](NATIVE_PLANNER_ACCEPTANCE.md) still requires an
isolated Humble planning-only window with exact loaded plugin/config/server
identity and product HTTP evidence; no Nav2 pipeline is started here.

The next minimum runtime diagnostic is an approved exact-candidate,
localization-only window collecting the production context's new finished-attempt
record, own gateway graph and runtime invocation. It needs no new initialpose to
diagnose the readback's client-future state. A successful parameter reply still
cannot prove collision enforcement. If all futures are done at a late poll,
investigate executor scheduling/authority lookup with the recorded timings; if
specific futures remain pending, inspect only those fixed service endpoints and
their qualified responders. Do not infer transport failure from pending clients.

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
and `robot_base_frame=base_link`. No-initialpose startup may leave its activation
or costmap updates waiting on the absent map transform. A hypothetical action
start bypasses current-pose selection in the request, not this costmap lifecycle
requirement. The current evidence does not guarantee a successful path in that
window. Do not inject an unverified transform or replay historical initialpose
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
See [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). No further
speculative runtime change or repetition of unchanged full tests was made.
