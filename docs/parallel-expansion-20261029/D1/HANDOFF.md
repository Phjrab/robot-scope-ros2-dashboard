# D1 handoff — offline multimap candidate

**Latest: [ROUND2.md](ROUND2.md) — D1_ZERO_RMSE_FIXED, current exact-SHA
C1 actual solver/full-source storage compatibility.** First-round evidence below
is retained as historical evidence, not overwritten.

- Branch: `review/20261029-x-d1-multimap`.
- Fixed BASE_SHA: `f469155c2b0c505f3e472e878f75029d7b8d39df` (fresh ordinary
  clone of then-current remote main; no reset/shared checkout).
- Tested implementation SHA: `3af445814d6dacb65e11c98e11ad26cb011fa22d`.
- Final publication HEAD: the commit containing this HANDOFF; retrieve exact
  full SHA with `git rev-parse HEAD` or the branch's GitHub commit link. A commit
  cannot contain its own hash; the final full SHA is also in the delivery report.
- Exact read-only C1 dependency: `2402c02c6f91ba54064894b21735e01b98610acd`.
- Execution: current dot cloud VM, independent ordinary clone at
  `/workspace/scratch/b09eacf6919d/d1-multimap`; Linux x86_64, Python 3.12.14,
  NumPy 2.3.5, SciPy 1.17.0, Node 24.22.1. No user Mac or separate saved executor.

## Delivered

Only four owned directory trees changed: `robot_dashboard/multimap_core/`,
`tests/expansion_d1/`, `experiments/expansion_20261029/d1_multimap/`, and this
`docs/parallel-expansion-20261029/D1/` directory. Actual seeded/automatic SE3
solver, bounded graph optimization, disconnected/ambiguous/degenerate handling,
full-record chunk export, conservative occupancy candidate and provenance DAG,
trusted-local CLI, generators, tests and C1 translation adapter. No original or
generated PCD/private assets, model weights, build outputs or environment files
are committed. No main integration, PR, force push, ROS adapter/UI duplication,
robot connection or deployment.

## Executed checks (do not conflate scopes)

| Evidence/check | Result |
|---|---|
| UNIT/SYNTHETIC final D1 tests, exact C1 export enabled | PASS, 19 tests, 0.610 s |
| C1 exact-SHA contract subset | PASS, 3 tests included above; no service/UI integration |
| Actual 2-map partial/noisy solve + full export | PASS; 1,496 records; 18.47 ms solver; 0.0255 CPU s including export |
| Actual 3-map partial/noisy solve + full export | PASS; 2,165 records; 38.50 ms solver; 0.0442 CPU s including export |
| CLI subprocess synthetic request | PASS |
| Peak process RSS in small synthetic benchmark | 61,468 KiB; VM only, NOT Jetson latency |
| Required full Python discovery | EXECUTED, NOT PASS: 2,989 tests / 102.101 s; 36 errors, 11 skips |
| Full JavaScript unit suite | PASS, 699 tests |
| Frontend syntax smoke | PASS, 112 dashboard modules |
| Whole robot_dashboard/scripts Ruff correctness check | PASS |
| Tracked-source secret scanner and git diff whitespace check | PASS |
| REPLAY_REAL independent mapping accuracy | INPUT_REQUIRED, no actual map assets/ground truth supplied |
| DEVICE_NOT_RUN | All robot, ROS graph, hardware latency, operational install and navigation |
| UI_FIXTURE / NATIVE_NAV2_SIM | NOT_RUN, outside D1 ownership |

The full Python errors are 25 denied local socket creation operations
(`PermissionError: Operation not permitted`) and 11 missing `cv2` imports in
existing competition tests. The failing common code/tests are byte-identical to
BASE_SHA (`git diff BASE_SHA -- tests robot_dashboard` excluding D1 paths is
empty). This establishes unchanged-base/environment blockers, NOT a claimed
separate baseline test pass. No permission escalation or retry of denied socket
operations was attempted. The full run preceded the final C1 adapter additions;
final D1-specific checks include all 19 final tests. No full-suite pass is claimed.
11 existing dependency-dependent skips are preserved, not recast as success.

## Reproduction

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
# C1 export recipe and exact SHA are in C1_COMPATIBILITY.md.
D1_C1_EXPORT=/tmp/d1-c1-2402c02 python3 -m unittest discover -s tests/expansion_d1 -v
python3 -m experiments.expansion_20261029.d1_multimap.reproduce
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 -m ruff check robot_dashboard scripts
python3 scripts/check_repository_secrets.py
```

Heavy local checks were sequential. Generated assets use temporary directories.
`SYNTHETIC_RESULTS.json` contains metrics only, not PCD data. Local detailed logs:
`/tmp/d1-full-python.log`, `/tmp/d1-focused-final.log`, `/tmp/d1-js.log`,
`/tmp/d1-syntax.log`, `/tmp/d1-ruff.log` (not portable deliverables).

## Limits and next one action

See README.md for numerical gates/bounds and caveats, INTEGRATION_POINTS.md for
exact future C1/C2/service/map-family hooks. Unknown ground/overhang/multi-floor
selection does not become automatic traversability. Free-space evidence merge,
annotation transfer, elastic correction, semantic masking and real-map quality
are not implemented or claimed. DAG duplicate roots always require review;
missing lineage on externally fused inputs cannot be inferred. Current service
revision and approval remain C1's responsibility. Native/real hardware safety
is untested. GitHub CI status is reported separately after remote verification.

**Next one action:** begin D2 in its own independent clone and specified branch,
keeping this D1 result pinned; do not integrate main or connect to a robot.

Publication used the authorized GitHub Git-data connector because local HTTPS
push had no credentials. The implementation tree is byte-identical to locally
tested tree `b5fb65fff050e1847f5f20acd5f95e45014d0548`; parent is fixed BASE_SHA.
No original tree entries or user changes were replaced.
