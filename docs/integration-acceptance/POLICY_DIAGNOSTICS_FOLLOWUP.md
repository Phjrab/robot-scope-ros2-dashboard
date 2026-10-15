# Policy readback follow-up within stage40

Latest controlled follow-up: candidate47c77af is deployed and the one-start,
no-pose60-second policy diagnostic window is complete. Cleanup and preservation
are verified; readback remains unavailable with bounded timeout evidence. See
[POLICY_RUNTIME_WINDOW.md](POLICY_RUNTIME_WINDOW.md) and its exact validation JSON.
The following sections preserve the earlier timestamped evidence.

## Earlier evidence

The user's continuation reopens software investigation through40. It does not
repeat the consumed localization retry or extend execution to41–43. The dashboard
address is `http://192.168.50.30:8088` on the robot management network. The
2026-10-15T11:52:29Z read-only inspection returned HTTP200 from health, navigation,
control and mission-plans. Existing Settings-only global HUD/STOP behavior remains
as explicitly chosen by the user; the Controls-page STOP remains in that UI.
At the final access recheck, SSH timed out and HTTP could not connect. Therefore
the earlier successful snapshot below is historical, and the current device state
is unverified. No restart or recovery operation was attempted.

## Changes and diagnosis

The production provider previously discarded observer diagnostics whenever its
parameter set was empty or incomplete. It now retains allowlisted observer reasons,
observer status, finite nonnegative age and bounded integer sequence in
`GET /api/v1/mission-plans` → `context.policy_evidence`. Provider evidence remains
`unavailable` for incomplete parameters, with `POLICY_READBACK_UNAVAILABLE` plus
the bounded failure code. This distinguishes observer initialization/setup,
authority, service, source-change, timeout, partial-response and generic readback
failures without exporting arbitrary exception text. Unsupported schemas remain
generic. Diagnostic changes never enter semantic context revisions.

The gateway explicitly reports `POLICY_OBSERVER_NOT_INITIALIZED`,
`POLICY_OBSERVER_SETUP_FAILED` or `POLICY_READBACK_FAILED`; optional observer
failure preserves the existing transport and StopMove-before-cancel path.

A separate reproduced observer defect could leave earlier futures untracked if a
later `call_async` raised while constructing a batch. The observer now records
each future immediately, including a half parameter/state pair. The existing
failure cleanup cancels all pending owned futures before another batch can begin.
This preserves the ten-request bound. Cancellation is local future cleanup;
already dispatched read-only services can finish on their servers.

No policy-success branch, config/mask installation, timer/deadline/TTL change,
timestamp rebasing or motion path was added. The timer remains250ms, batch deadline
500ms and freshness boundary750ms. All runtime enforcement scopes remain false
because qualified mask ingestion, controller collision and map binding evidence
are still missing. MR-MS-003 remains PARTIAL.

Localization-only uses the same fixed Nav2 launcher and starts planner, controller,
BT and their costmaps. The mode gates goal/velocity admission; it does not omit
the required policy nodes. The deployed launch/config path is unchanged. During
the earlier stage40 observation,155 active API samples reported planner/controller/
action readiness, but these topic/action proxies do not prove all five exact
authority/service/lifecycle endpoints. The20 retained policy samples contain only
the former generic unavailable result. Their historical failure cannot be assigned
to setup, authority, service or timeout. No matching setup-failure log message was
found in the available dashboard journal; this absence does not prove setup success.
The historical stale-startup cause also remains UNCONFIRMED.

## Source, runtime and verification

The continuation began on clean main/origin/main
`72d8f9b108f1776f37bd9b071c250d5d1e71cf2b`; fetch found no newer main. During validation, separate UI source/test changes
were independently published as`a67c5f53da9d570d7679a6bf2a49e878599e0bea`. They
are preserved as this continuation's integration parent; no policy source/test file
overlaps. Local isolated regressions used the earlier baseline plus the six
follow-up source/test files; exact final Linux CI is checked after publication. The published follow-up source is
`a3288795d33029e41ce3e2736197695d10c617c2`; exact changed-source/test/config hashes
and validation results are in [POLICY_DIAGNOSTICS_VALIDATION.json](POLICY_DIAGNOSTICS_VALIDATION.json).
These are software regressions with raw ROS-shaped fixtures, not live readback or
native enforcement acceptance. The factory regression uses the real default
provider and confirms unavailable evidence never sends a goal. Separate regressions
cover diagnostic sanitization, semantic stability, all ten partial-dispatch failure
positions, repeated failure/recovery and STOP preservation.

The new backend source is **not deployed**. Device disk/UI remains
`1656e4d15d752e82178e1c0272824c5ed3252f37`; backend bytes remain from the controlled
`863682ed4c566a56e676c2a4ed42fef1808885e5` restart. Dashboard PID62370 and invocation
`f614b41a474543b5b272b83f335669aa` are unchanged. Bridge PID984 and camera PID988
retain their earlier invocations. All1256 source-manifest files match and all54
map-file hashes are preserved. Unit/environment definitions remain unchanged.
Effective aggregate loaded configuration and per-module loaded attestation remain
unavailable; disk hashes are not substituted for these runtime facts.

Navigation is idle, initialpose count1 retained, no owned observer/runtime processes
remain and the recorded nonzero movement count is0. This continuation only read
device APIs, files and logs: no deployment, restart, ROS subscriber, service query,
pipeline, initialpose, goal, lease, camera operation or motion was initiated.
Private raw inspection/journal and test logs are preserved in the sibling private
evidence directory; no coordinates, map labels or environment contents are published.

## Next minimum work

Use a separately qualified exact-candidate backend application and current
localization-only window to observe the new bounded reason through the production
mission-plans context. Pin the five parameter-event authorities and fixed
GetParameters/GetState endpoint readiness within that same invocation to isolate
the reported failure. Do not infer current-pose consent from the completed retry.
Successful parameter readback alone still cannot open mission admission: qualified
collision profile producers and global/local/BT/map-epoch ingestion remain separate
software/native dependencies. NativePlanner product execution, MS native reuse and
MAP-02 full retained-map export remain blocked on their recorded conditions.

No live acceptance row is promoted by these fixture tests. SOFTWARE_CLOSURE and
LOCALIZATION_LIVE_VERIFIED remain false; stages41–43 remain NOT_RUN. No background
continuation is scheduled.

## User reboot and restored access

After the failed access recheck, the user reported a completed reboot. At
2026-10-15T12:10:57Z, read-only inspection again returned HTTP200 for health,
control, navigation, mapping and mission-plans. Disk/UI checkout remains1656e4d,
clean, and all1256 manifest files plus54 map hashes match. The user reboot changed
all three service invocations: dashboard PID988, bridge PID976 and camera PID982;
exact IDs are in the validation record. The earlier863682e invocation is now
historical. No per-module loaded attestation is claimed.

Navigation/goal are idle, lease/deadman false and command zero, with no owned
runtime/observer remaining. Initialpose count reset to0 with the restarted process;
no historical pose was replayed. Policy evidence remains unavailable on the older
source. Neither follow-up policy source a328879 nor the separately published UI
source a67c5f5 was deployed by this continuation. The agent performed no service
restart or additional robot window.

## Exact source CI

[CI38732453021](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38732453021)
passed on exact source`a3288795d33029e41ce3e2736197695d10c617c2`, including the
separate UI parent. Both Ubuntu22.04/Python3.10 and Ubuntu24.04/Python3.12 passed
1998 Python tests (1997pass,1 optional skip),381 JavaScript tests and100 Chromium
E2E tests, plus static/dependency/secret checks. These are hardware-free results.
Later documentation-only commits do not change the six pinned source/test files
and are not represented as this exact source CI run.

## Subsequent separate UI deployment

The UI owner independently applied a67c5f5 after the user reboot; see
[UI_WORKSPACE_REPAIR_20261015.md](../ui-redesign/UI_WORKSPACE_REPAIR_20261015.md).
This integration independently rechecked at2026-10-15T12:19:36Z: clean device
checkout a67c5f5, HTTP200, the same post-reboot service invocations,54 preserved
map hashes and no owned runtime/observer. Its separate deployment record verifies
all1261 archive files and five HTTP static hashes. The17 differences against the
older1656 manifest are expected documentation/static updates, not an integrity
failure of the a67 release. The new policy backend a328879 remains undeployed.
