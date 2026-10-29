# C1 round 2 continuation — latest owner ports

Branch: `review/20261029-x-c1-services`. Previous delivery:
`4e1dd519a707169da5f88cf2a92a20ed3e701cc7`.
**NO_PRODUCTION_SOURCE_CHANGE**: C1 production implementation remains identical
to `4b9c02b2119c984d0bf4322bc292007df90fd032`. This continuation adds C1-owned
replay/evidence only. Historical [ROUND2.md](ROUND2.md) and its original pins and
reproducer remain intact; this report supersedes their dependency-status claims.

Test-code SHA and final delivery SHA are the commit containing this report.
Resolve with `git rev-parse HEAD` and compare the existing branch's `git ls-remote`;
the final chat receipt gives the exact value and remote equality. Pre-commit
test-file hashes are in [FOLLOWUP_EVIDENCE.json](FOLLOWUP_EVIDENCE.json).

## Read-only dependency pins

| Role | Exact executed SHA |
|---|---|
| D1 | `203c144f6b4a90966839c34b603ae12ee676cb12` |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` |
| C2 | `47a1d031d797c098c38a0147894523d07d30db8f` |
| C3 | `a2b6d37f61ac426ac8a21e941750099b28318fd8` |
| C4 | `073d05b24c73b4de08c754833d4c05e537a23727` |

Each exact commit was fetched and exported with `git archive` to a read-only
temporary directory. Package-origin assertions verify actual D1/D2/D3/C4 imports.
Nothing was merged, cherry-picked, or copied into C1 production code. D1 ran
before D2, then D3; the new C4 runtime was checked last with those same pins.

## Actual results

| Executed boundary | Result |
|---|---|
| D1 solver → C1 worker → actual C2 HTTP ports → BundleStore | PASS; frozen |
| C4 PointCloud2/worker → D2-owned `C4CorePort` → C4 obstacle sink → C1 | PASS |
| Actual D3 `assess` → D3-owned `canonical_assessment` using C1 converter → C1 0.2 | PASS; explicit separate assessment port |
| Actual D3 `c4_constraint` → old C4 `constraint_from_d3` | PASS; original UNKNOWN/expiry retained |
| Actual C1 0.1 HTTP response → actual C3 parser/adapter | PASS for obstacle-only display |
| Actual C1 0.2 HTTP response → actual C3 parser/adapter | **FAIL: `C1_VERSION_UNSUPPORTED`** |
| New C4 `expansion_runtime.Runtime`, using actual latest D2/D3 | **FAIL: `UNSUPPORTED_D3_ASSESSMENT`** |
| Complete observation consumer chain | **FAIL; replay exits 2** |

Map compatibility reuses the previous actual map flow: 2 × 400 generated points
produce all 800 output points, preserving XYZ/normals/intensity, input hashes,
output hash, list/reload and ancestry. Shared-root fusion and stale apply reject;
actual D1 cancellation fences publication. Output PCD SHA-256 remains
`46be1a0ec38166fc78e7d0344d3e241d57e3c29807f22e819e22e04d1ec9dbde`.
No C2 or map-path tuning follows this short compatibility check.

The D2-owned port replaces the previous C1 test shim. All 2,051 generated input
points enter the actual C4 decoder/D2 numerical path. Geometry survives the
owner's provenance compaction. C4's PointCloud2 port supplies no calibration
metadata argument: `calibration_id` stays null and C1 reports UNKNOWN. A generated
pose/joint fixture is explicitly supplied to D3; it is not measured sensor state
or physical calibration evidence. No invented calibration is inserted into the
PointCloud2 output. Previous C1 calibration-change regression remains preserved.

D3 now emits schema 0.2 with an empty host validity interval and retains source
validity in `freshness.source_validity_interval`. Its own adapter invokes C1's
explicit clock binding; original 1,000,000,000..1,250,000,000 ns and full obstacle
refs survive unchanged. Partial coverage remains `MOTION_COVERAGE_NOT_QUALIFIED`
and UNKNOWN; positive clearance or zero obstacles never becomes CLEAR.
Calibration unknown, stale input, map mismatch, wrong source/host clock, wrong
epoch, oversized TTL, original expiry, source restart/sequence reset, old epoch,
map reset and missing input are separately asserted. Synthetic zero-offset clock
binding is declared test input, not real clock calibration.

D3's explicit legacy command projection now works with a declared synthetic
goal/lease/command binding. The actual old C4 gate writes zero/HOLD to its
**MockCommandSink only**. The new C4 runtime executes D2 and D3, then rejects
D3 0.2 in `CorePorts.canonical_assessment`, which still requires 0.1. Its scene
port rejects `NO_VALIDATED_SCENE_SAMPLE`; ACTIVE_CONSTRAINT stays active, and
its separate memory-only FinalIntentPort holds zero. No ROS/control enforcement
or physical avoidance is established by these memory sink checks.

C3 fixed its old fictitious `sources.display` requirement and now accepts actual
0.1 obstacle data, including geometry and server age plus transport delay. It
still rejects the published C1 0.2 contract. Bulk cloud resolution is still
`NO_C1_RESOLVER_CONTRACT`; no pose/joint/path/cloud data is fabricated for display.
The old C4 sink still forwards obstacles only; the separate D3→C1 call is never
reported as C4 assessment forwarding.

## Size bounds, unchanged

Actual generated outputs through the new D2-owned compactor:

| Objects | Input points | Full frame bytes | Compacted bytes | Outcome |
|---|---:|---:|---:|---|
| 0 | 984 | 1,867 | 1,914 | Accepted |
| 1 | 1,176 | 3,544 | 2,706 | Accepted |
| 4 | 1,752 | 8,620 | 5,127 | Accepted |
| 12 | 3,288 | 22,123 | 11,550 | Accepted all geometry |
| 16 | 4,056 | 28,876 | 14,763 | Entire frame rejected: +2,048 reserve >16,384 |
| 32 | 7,128 | 55,904 | 27,631 | Entire frame rejected: +2,048 reserve >16,384 |

No object is truncated and no bound is relaxed. The actual paired C1 0.2 snapshot
is 10,379 bytes. Empty/stale/unavailable snapshots retain their distinct meanings.
Private display asset behavior and fixed bulk route remain as in ROUND2_CONTRACT.

## ROS/native evidence boundary

C1 local ROS/native: **NOT_RUN**. D3 has now published real isolated hosted native
evidence: [run 40840774827](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774827),
exact source `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`, remote SUCCESS.
The executed D3 dependency above differs from that source only in D3 documentation.
We reviewed its source-pinned summary and remote run status read-only: five native
Nav2 simulation cases pass (empty, spacious obstacle, blocked, appearing obstacle,
sensor stale). Existing stock RPP collision detection is ACTIVE; the new URDF
constraint is explicitly **ADVISORY_ONLY**. This is not a C4→D2→D3 native full-chain
run and was not executed by C1. No physical robot evidence is claimed. Real maps,
bags, calibration and detector weights remain INPUT_REQUIRED for their checks.

## Reproduction and validation

Changes: `tests/expansion_services/{followup_composition.py,
check_followup_consumer.mjs,followup_pins.json}`; `prepare_dependencies.py` adds an
optional `--pins` argument while retaining its original default. Documentation
and evidence stay under C1. No workflow, production entrypoint or counterpart edit.

```sh
# Fetch the exact six SHAs listed above first; then export immutable dependencies.
python -m tests.expansion_services.prepare_dependencies \
  --pins tests/expansion_services/followup_pins.json
PYTHONDONTWRITEBYTECODE=1 python -m tests.expansion_services.followup_composition \
  --deps /tmp/<reported-readonly-root> --node /path/to/node-24 \
  --output /tmp/c1-followup-composition.json
# Expected exit 2: recorded consumer FAIL, not a successful full-chain result.
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python -m ruff check robot_dashboard scripts
python scripts/check_repository_secrets.py
```

The explicit composition is not silently included in ordinary mock/unit totals;
it requires fetched read-only dependencies and is run separately. No test was
deleted or newly skipped, and no acceptance threshold changed.

- Local Python 3.12.3: **3,146 PASS, 2 existing skips**, 104.269 s, with
  `C2_CROSS_REQUIRED=1`. Skips are optional SVG plotting and rosbags libraries.
- Node 24: **77 test files PASS**; **112 dashboard modules** plus the new consumer
  probe pass syntax checks. The new probe also executed against actual HTTP above.
- Ruff, tracked-source credential scan, whitespace check: PASS. Local mypy is
  NOT_RUN (module absent); the unchanged remote workflow runs it.
- Explicit actual composition exits **2**, preserving the full-chain FAIL above.
- The new delivery's own remote CI state is separate, reported in the final chat.

Previous delivery `4e1dd519a707169da5f88cf2a92a20ed3e701cc7` completed full CI
**SUCCESS** in [run 40842714164](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40842714164).
This success is not a claim about the new commit's CI or full consumer composition.

Dependency CI is also not relabelled by this C1 compatibility pass: D1's published
source CI [40836821084](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40836821084)
at `70d94b51669af8e9fb496de400de394cf088a5f2` is **FAIL** (Python 3.12 matrix job;
Python 3.10 and integration jobs pass). No shared CI or counterpart test was
changed to conceal that result. This receipt does not claim every dependency's
latest HEAD has a successful general CI run.

## One remaining action

**Align the C4 runtime and C3 consumer with the already published C1/D3 0.2
contract**, then replay these exact actual boundaries with their new pinned SHAs.
The reproducible blockers are C4 `UNSUPPORTED_D3_ASSESSMENT` and C3
`C1_VERSION_UNSUPPORTED`; C1 cannot fix these by editing another role or weakening
its canonical contract. No robot access, main integration, shared product mount,
deployment, TF/command publication or real motion occurred.
