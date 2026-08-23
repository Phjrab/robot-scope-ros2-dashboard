# Phase 13 — Diagnostics Bundle and Operator Event Timeline

Phase 13 adds a read-only incident handoff artifact and a bounded record of
browser mutation intent. It does not add authentication, a shell, arbitrary
ROS inspection, metrics, or any robot/service lifecycle side effect. The
roadmap's metrics endpoint is optional and was deliberately not added; the ZIP
reuses existing bounded public snapshots instead of creating another status
authority.

## Ownership and request flow

`ApplicationRuntime` owns exactly one `OperatorEventTimeline` and one
`DiagnosticsBundleService`. The shared API middleware observes the final HTTP
status of a fixed mutation catalog and appends a public event on a worker
thread. Recording is best effort: an event-storage failure is logged privately
but can never change a control, cleanup, mapping, navigation, dataset or
lifecycle response.

The Settings feature issues one same-origin
`POST /api/v1/system/diagnostics/export`. The system router builds the bundle
on a worker thread without acquiring the pipeline coordination lock or calling
a lifecycle, mapping, navigation, dataset or control mutation. Duplicate UI
clicks are suppressed while a bundle is in progress.

## Deterministic bundle contract

The ZIP has a fixed filename pattern, fixed entry order, fixed timestamps and
permissions, canonical JSON, and fixed compression settings:

```text
robot-scope-diagnostics-<UTC timestamp>.zip
├── summary.json
├── versions.json
├── health.json
├── ros-graph-summary.json
├── network-summary.json
├── mapping-events.jsonl
├── navigation-events.jsonl
├── operator-events.jsonl
└── redaction-report.json
```

The compressed limit is 2 MiB, the aggregate uncompressed limit is 3 MiB,
each JSON section is at most 256 KiB, and each event stream contains at most
256 lines of at most 1 KiB. A bundle that cannot satisfy those limits fails
with one fixed public error. Provider exception detail remains server-private.

The export includes the Robot Scope commit and exact tag when present,
Python/ROS/RMW versions, a credential-excluding active-profile fingerprint,
pinned external dependency revisions, graph cardinality without raw topic
names, selected sensor metadata/freshness, recent redacted mapping/navigation
events, authenticated bridge readiness and bounded status age, active opaque
map ID/revision, disk capacity labels without paths, safe interface names and
bounded route reachability state, and the latest acceptance-report reference.

The bundle never includes a bridge key, credential, Authorization header, SSH
key, environment dump, raw child argv/output, arbitrary absolute path, IP
address, raw ROS message, OS process ID, private bridge epoch, or unbounded
log. Mapping/navigation messages are passed through the same
`public_diagnostic.v1` sanitizer used by public runtime projections. Profile
keys containing auth, credential, key, password, secret or token are removed
before hashing, so the fingerprint is not a credential-derived oracle.

## Operator event contract

The timeline is append-only JSONL under the configured project-local runtime
root. Its directory is real, absolute, non-root and non-symlink with mode
`0700`; files are regular, non-symlink, `0600`, opened with `O_NOFOLLOW` where
available, fsynced, rotated at 256 KiB and retained to four files. Recovery and
export skip malformed, oversized, symlink or non-regular entries.

Each record contains only:

```text
schema, event_id, timestamp,
browser_session_id, request_sequence,
fixed event_type, bounded opaque target IDs,
accepted/rejected result, fixed HTTP reason code
```

The browser session is a per-page correlation identifier, not a verified
person or authentication credential. Request bodies and arbitrary response or
exception text are never persisted. The fixed catalog covers control
arm/disarm, software stop latch/clear, mapping start/stop/save, navigation
start/stop/initial pose/goal/cancel/costmap clear, managed map
convert/edit/rename/delete, dataset start/stop, dashboard restart/stop, control
bridge start/stop, and diagnostics export. Mission events are intentionally
absent because the Mission Manager is not implemented before Phase 16.

An accepted background-start request records the HTTP acceptance result, not
eventual task success. The bounded mapping/navigation transition streams in
the same bundle provide the subsequent runtime outcome. The export request is
written after its response has been built, so it appears in the next bundle.

## Safety invariants preserved

- Same-origin remains mandatory for every mutation and for diagnostics export.
- The new browser headers grant no capability and are not trusted identity.
- No control lease, bridge status, watchdog, E-stop, navigation freshness,
  mapping allowlist, opaque-map boundary, dataset quota or filesystem boundary
  was changed.
- Bundle generation is read-only and does not interrupt active work.
- Event persistence failure cannot make cleanup unavailable.
- No live robot, ROS graph, mapping/Nav2 process, dataset, systemd unit or map
  was touched during Phase 13 validation.

## Hardware-free acceptance

Unit tests cover deterministic ZIP bytes/order/limits, secret/path/IP/topic and
private-field absence, credential-independent profile hashing, fixed public
provider failures, event rotation/retention/modes/symlink rejection, one-owner
wiring and same-origin transport. Node tests cover browser correlation headers,
bounded ZIP handling, duplicate suppression and cleanup. Playwright uses only
the repository fake backend to verify one browser download and no duplicate
mutation. Live hardware validation remains deferred.

The final local acceptance result was 623/623 Python tests, 156/156 Node
tests, 10/10 Playwright fake-backend scenarios, syntax checks for 19 dashboard
modules, Python compileall, repository secret scan, `pip check`, npm production
audit and staged diff check all passing. Ruff and Mypy are CI-owned quality
checks and were not installed in this local workspace; their configured scope
was not weakened.
