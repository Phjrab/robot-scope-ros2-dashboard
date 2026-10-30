# C1 services handoff — independent expansion, 2026-10-29 KST

Latest (2026-10-30): [CURRENT_COMPOSITION_20261030.md](CURRENT_COMPOSITION_20261030.md)
— latest actual C4→C1 0.2 HTTP→C3 acceptance and safe map-error propagation.
The minimum C2 consumer handoff is [ERROR_CONTRACT.md](ERROR_CONTRACT.md).

Previous continuation: [ROUND2_FOLLOWUP.md](ROUND2_FOLLOWUP.md) — new exact owner
SHAs, D2/D3-owned ports, actual C3 HTTP compatibility, new C4 runtime failure,
and reviewed D3 native evidence. C1 production code is unchanged.
[ROUND2.md](ROUND2.md) preserves the first round-2 implementation/CI record.
The round-1 record below is historical; use CURRENT_COMPOSITION_20261030 for current status.

Branch: [review/20261029-x-c1-services](https://github.com/Phjrab/robot-scope-ros2-dashboard/tree/review/20261029-x-c1-services)

- BASE_SHA: `f469155c2b0c505f3e472e878f75029d7b8d39df` (latest origin/main at clone; fixed throughout this submission).
- CONTRACT_BOOTSTRAP_SHA: [`2402c02c6f91ba54064894b21735e01b98610acd`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/2402c02c6f91ba54064894b21735e01b98610acd), published before services.
- TESTED_IMPLEMENTATION_SHA: [`fc7ab34c8c9597c0f0376b8c5c14cc85275ad809`](https://github.com/Phjrab/robot-scope-ros2-dashboard/commit/fc7ab34c8c9597c0f0376b8c5c14cc85275ad809). The frozen source content was tested before this focused commit; the subsequent handoff commit changes documentation only.
- FINAL_SHA: the final HEAD of the branch above after the handoff commit. A document cannot contain its own commit hash. Resolve with `git ls-remote origin refs/heads/review/20261029-x-c1-services`; the final chat report provides the exact value. This is distinct from TESTED_IMPLEMENTATION_SHA.
- Clone: `/tmp/robot-scope-expansion-20261029-c1-services`, ordinary independent clone. Shared checkout `/home/desktop1/Documents/ChatGPT/robot` branch/index/files were not modified.

## Implemented candidate

`expansion_contracts` supplies dataclasses and strict finite/bounded wire validation
for source descriptors, fusion requests/proposals, obstacle frames, collision
assessments and scene packets. Transform, clock, epoch, map/revision/hash pins,
source evidence and missing-data semantics are explicit. No alignment, perception
or collision solver is implemented by C1.

`CatalogueAdapter` takes trusted allowlist/resolver/preview callbacks and returns
public descriptors without server paths. `FusionJobManager` has one explicit
heavy worker, bounded admission and bounded idempotency/history; request IDs with
changed inputs conflict. It calls injected D1 with detached contract data and
private read-only source snapshots, never original source paths. Aggregate job
snapshot bytes are capped. Progress, cancel/late results, result identity/pins,
review revision, manual transform labels and export ownership are fenced.

Calculation ends at SOLVED_CANDIDATE. Explicit accepted review increments the
proposal revision. Export requires that revision and publishes a new immutable
candidate under a shared registry lock via private staging/fsync/rename. It
streams the complete binary sources, transforms XYZ/normals, preserves scalar
fields, rejects heterogeneous/multicount schemas rather than silently losing data,
and rechecks source/output hashes. Output includes original PCD header metadata,
source descriptors/transforms, options/request hashes, quality and edge review,
manual review, semantic-mask prisms and provenance DAG. Tilted or missing-Z masks
stay review candidates. No selected original map is overwritten.

Occupancy uses materialized final coordinates, conservative point marking and
UNKNOWN by default; absent PCD points never imply FREE and no scan-ray/free
reconstruction is claimed. `BundleStore.reload()` returns an unregistered source
for 2→3-session fusion and preserves ancestry; cycles/shared ancestors are rejected.
The legacy map-family parser cannot honestly describe a merged source because it
requires a real single mapping_session_id. The bundle records DEFERRED legacy
family linking and actual planar materialization; no fake session or product
parser modification was introduced. Future shared schema approval is required
before product family registration.

`SceneSnapshotService` retains latest payloads plus a bounded metadata ring,
without persistent per-sample ledger writes. It fences map generations, sequence,
explicit source epochs and retired epochs. Clock/age uncertainty and absent
calibration remain UNKNOWN. Collision is exposed only when its exact current
obstacle reference and same-host validity interval match. Pose/path/local
trajectory/costmap remain null unless supplied through the read-only port.

`create_router(..., authorize=..., require_origin=...)` requires injected policies
and moves blocking work off the HTTP event loop. It supplies source/preview,
enqueue/status/cancel/review/export/get and scene routes only. Standalone factory
and localhost test host demonstrate these functions without importing/mounting
the root product app. Test bearer is explicit; the CLI generates an ephemeral
bearer and binds only 127.0.0.1. No product auth was bypassed.

Defaults: one worker; `max_queue+1=5` admitted job slots (at most four waiting
while one runs; up to five queued during worker startup); history 32; request
128 KiB; 2–8 sources; 256 correspondences; aggregate source snapshots 256 MiB;
PCD export 256 MiB/20M points; streaming chunks <=1 MiB; occupancy <=1M cells;
scene 16 KiB/sample, 80 KiB latest payload total and 16 metadata history entries;
explicit host HTTP concurrency/backlog 16. Trusted injected workers must honor
cancel/progress/deadline. An uncooperative worker retains the sole slot and is
not replaced; this in-process host is not a sandbox for untrusted solvers.

## Changed paths and dependencies

Only these owned paths changed:

- `robot_dashboard/expansion_contracts/`
- `robot_dashboard/expansion_services/`
- `tests/expansion_c1/`
- `experiments/expansion_20261029/c1_service_host/`
- `docs/parallel-expansion-20261029/CONTRACT.md`
- `docs/parallel-expansion-20261029/C1/`

Existing binary PCD parser, `SourceAsset` and safe immutable-store I/O primitives
are imported read only from BASE_SHA. No DB, worker, api/models.py, root app,
product JS or navigation setting was modified. No other role code was copied,
merged or cherry-picked. No PR, main push, force push or deployment was performed.

Dependency SHA status: D1, D2, D3 **unavailable / NOT_RUN**. The exact designated
refs were checked using one final bounded `git ls-remote --heads origin` request:

```
refs/heads/review/20261029-x-d1-multimap
refs/heads/review/20261029-x-d2-perception
refs/heads/review/20261029-x-d3-collision-sim
```

The request succeeded with no matching refs. No exact counterpart SHA was
therefore available for read-only temporary export/function invocation. Fixture
ports were tested instead; there is no background watcher or future-run promise.

## Validation and reproduction

See [VALIDATION.md](VALIDATION.md) for the complete PASS/FAIL/SKIP/NOT_RUN history,
environment and preserved skip reasons. Final results:

| Check | Final result |
| --- | --- |
| C1 focused | PASS: 20 UNIT/SYNTHETIC tests, no skip |
| Python full discovery | PASS: 3,103 run, 5 existing skips, zero failures/errors |
| JavaScript | PASS: 77/77 with bundled Node 24.22.1 |
| Frontend syntax | PASS: 112 modules |
| Real localhost HTTP service smoke | PASS: SYNTHETIC auth→job→review→immutable export/query→scene and shutdown |
| Ruff owned scope and repository `robot_dashboard scripts` | PASS |
| compileall, pip check, diff checks, tracked-source secret scan | PASS |
| D1/D2/D3 exact-SHA function compatibility | NOT_RUN: refs unavailable |
| C1 REPLAY_REAL, NATIVE_NAV2_SIM, UI_FIXTURE | NOT_RUN; not inferred from synthetic regression |
| DEVICE_NOT_RUN | no SSH/HTTP/DDS/ROS/camera/sensor/robot/service/config/TF/motion/deployment access |

Reproduction from repository root (use normal localhost-capable execution;
restricted sandbox event-loop wakeup caused the initial timeout):

```sh
python3 -m venv /tmp/c1-repro-venv
/tmp/c1-repro-venv/bin/python -m pip install -r requirements.txt -r requirements-competition-offline.txt httpx==0.28.1 ruff==0.6.9
/tmp/c1-repro-venv/bin/python -m unittest discover -s tests/expansion_c1 -v
/tmp/c1-repro-venv/bin/python -m unittest discover -s tests -v
/tmp/c1-repro-venv/bin/python -m experiments.expansion_20261029.c1_service_host.smoke
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
/tmp/c1-repro-venv/bin/python -m ruff check robot_dashboard scripts
python3 scripts/check_repository_secrets.py
```

Actual environment: Linux x86_64, Python 3.12.3; FastAPI 0.162.0, Starlette 1.10.0,
httpx 0.28.1, numpy 1.26.4, scipy 1.11.4, PyYAML 6.0.1, OpenCV 4.10.0, ruff 0.6.9.
Node used:
`/home/desktop1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`.
Exact final frozen logs stayed in /tmp; generated maps, PCD, video, weights,
rosbag, environment files and build/install/log trees were not committed.

Input provenance: repository code at BASE_SHA, adopted role specification
`20_CODEX_C1_SERVICES.md` and its common v0.1 interface; C1 fixture generators
produce three-point synthetic clouds and synthetic messages. No real replay or
live sensor input was used for C1 validation. Humble/Nav2 1.1.20 compatibility is
an unchanged integration target, not a native ROS validation claim.

Future factory/router/catalogue links and exact base line contexts are in
[INTEGRATION_POINTS.md](INTEGRATION_POINTS.md). Existing 3D Nav2, Goal URDF and
final heading work is untouched. Main/product integration, legacy family schema
adaptation, operational activation, deployment and hardware verification require
the separately requested future integration phase.

## Next one thing

When Dots publishes D1/D2/D3, perform one read-only temporary-export compatibility
check at their exact SHAs against these C1 injection ports and record the result.
This is a remaining counterpart check; it does not authorize product integration
or device validation. C1's independent candidate is committed and ready to review.
