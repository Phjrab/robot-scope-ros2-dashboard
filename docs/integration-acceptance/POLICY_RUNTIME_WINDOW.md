# Stage40 policy-only runtime window — 2026-10-15

Candidate `47c77af19246bd6a455ee873a7c55884ed6e4122` is deployed on the operating
dashboard. The separately approved localization-only window completed one START,
60.00048 seconds of observation and one owned STOP. Initialpose, goal and lease
requests were zero; no nonzero movement or camera operation was issued. The
dashboard is available at `http://192.168.50.30:8088` on the management network.
The exact records and private evidence hashes are in
[POLICY_RUNTIME_WINDOW.json](POLICY_RUNTIME_WINDOW.json).

## Deployment and preserved UI

Only `robot-scope.service` was restarted. Its final PID is54752, invocation
`f1f5a924a4494901917d1d4f8fe6d66e`, cwd `/home/unitree/robot-scope`, interpreter
`/usr/bin/python3.10`. The clean main checkout matches all1265 candidate files.
These are checkout/process identities; per-module loaded attestation and an
aggregate effective runtime configuration digest remain unavailable.

The first application and rollback both reported a validation failure because
the private deployment checker incorrectly required schematic revision to
increase on every restart. Actual product initialization is lazy: the first
schematic access creates the session. Independent inspection found revision25
unchanged, all1261 previous-source files restored, HTTP200 and the old service
active. The checker was corrected to permit zero through one revision-only lazy
initialization per qualified incarnation, retaining exact other payload and
byte equality when revision is unchanged. The corrected application passed;
no product policy, timer, deadline or freshness check was changed.

The UI from a67c5f5 remains included. All five changed UI files returned HTTP200,
exact source hashes and `Cache-Control: no-store` after this window. The global
control HUD and its SOFTWARE STOP remain Settings-only by explicit user choice;
the existing Controls-page STOP remains. Mapping, native-map detail, capture and
mission layout repairs are preserved. See
[UI_WORKSPACE_REPAIR_20261015.md](../ui-redesign/UI_WORKSPACE_REPAIR_20261015.md).

All54 map hashes, five selected-state files, unit definitions and environment
file hashes remain unchanged. Bridge PID976/invocation
`ac5bf5a37a5b470385c9268a042f6680` and camera PID982/invocation
`c99004f7d9194f0ab1a53a55d2a6110b` are unchanged from the user's reboot. No bag,
native database or installed VSLAM artifact was edited; those stores were not
exhaustively rehashed.

## Actual observation and cleanup

The current catalogue and parameter revision were checked against the existing
private map record. No coordinates were applied. START was sent at13:01:22.601644Z;
the session reached `waiting_initial_pose` before the observation began at
13:01:32.349162Z. The60-second window ended at13:02:32.349642Z. Runtime instance
`59632:3113222857356` and its input generations remained stable.

All60 production `/api/v1/mission-plans` samples reported policy evidence
unavailable and enforcement false: one `PARAMETERS_CHANGED`, then59
`POLICY_READBACK_TIMEOUT`. No successful readback sequence or age was available.
The navigation context revision stayed constant. Readback timer250ms,
batch deadline500ms and TTL750ms are unchanged.

Within the exact observation interval,59 independent graph samples saw one
node and one nonzero24-byte parameter-event publisher GID for each of the five
fixed policy authorities, with all ten GetParameters/GetState services ready.
This observer's graph is not the dashboard gateway's own graph, and parameter
event GIDs do not attest service responder identity. Service discovery/readiness
does not establish completed parameter or lifecycle responses.

The timeout denotes batch age beyond500ms. The implementation checks this before
future completion, and the age includes authority lookup, readiness, dispatch and
executor scheduling. It does not prove that all ten requests failed or that
network transport consumed500ms. Without initialpose, map-to-odom is absent and
Nav2 activation may wait; the current evidence does not establish that as the
cause. The cause of the historical localized180-second readback failure, and
the historical stale-startup cause, remain unconfirmed.

STOP's HTTP response exceeded the collector's3-second request bound. There was
no retry: subsequent reads confirmed the exact owned jobs cleaned up, followed
by an empty runtime/FAST-LIO process inventory. The graph child exited normally.
Independent inspection at13:03:52Z confirmed navigation/session/goal idle,
initialpose count0, lease/deadman false and exact-zero dashboard/accepted commands;
bridge nonzero_move_count stayed0. Defensive StopMove counters may advance while
disarmed and were retained separately.

Before this START, the graph helper's first attempt failed because it used the
global executor with a private ROS Context. The wrapper stopped before launching
the collector, so START remained0. The helper was corrected to own an executor
for its Context and clean up that exact executor/node. Original failed artifacts
were retained. The final collector also distinguishes initial empty DDS discovery
from a qualified publisher change;34 deterministic fake-transport cases and an
actual diagnostic-class reproduction passed. These are collector tests, not
native acceptance evidence.

## Judgment and smallest next work

The qualified deployment, policy observation and owned cleanup are complete.
This no-pose60-second diagnostic window does not replace the earlier localized
180-second acceptance row. D01/D04/D05 remain BLOCKED; MR-MS-003 enforcement,
NativePlanner product execution, MS native reuse and MAP-02 complete retained
export are not promoted. SOFTWARE_CLOSURE and LOCALIZATION_LIVE_VERIFIED remain
false. No stage41–43 operation or additional runtime window was performed.

The next minimal policy change is bounded evidence from the final batch: fixed
ten-endpoint done/cancelled state, batch age, tick gap and authority/dispatch
duration, with an allowlisted provider projection. Preserve the current
deadline/TTL and semantic revision rules. This will distinguish late polling of
completed futures from named pending endpoints; it still must not equate client
scheduling delay with transport latency. Qualified collision/mask ingestion,
controller/BT enforcement and map binding remain separate dependencies.

Exact candidate CI38733978639 passed both Linux jobs, including1998 Python tests
(one optional skip),381 JavaScript and100 Chromium tests. Final local repository
checks collected1998 Python tests:1996 passed and two platform/optional checks
were skipped;381 JavaScript tests passed. No new product source or configuration was changed by this
deployment/observation follow-up; this publication records the evidence.

The user subsequently expanded the scope to41, then explicitly requested immediate
completion before any41 operation began. Work stops here. No camera handoff,
native session, additional deployment or background continuation is pending.
