# D1 Round 2 — D1_ZERO_RMSE_FIXED

## Scope and pinned inputs

Continued the existing dot VM clone and `review/20261029-x-d1-multimap` branch.
No checkout reset, new clone, main update or discarded user changes. Existing
local connector-publication history differs from remote commit identities but
was clean and tree-identical before this change. Remote starting HEAD:
`cbedd05ba6f97dad5506e8003302f689ed8fcb4c`.

Read-only dependencies, looked up once and frozen for this round:
- C1 `54629c793ad4ae0ea88127f00ed1b7f8805fc4e2`
- C2 `5eed1a9959ca25a4f30bd5b5712806a5ad660c51`
- Contract schema `0.1`; existing solver algorithm/gates unchanged.

## Fixed defect and numerical behavior

The actual pinned solver contained **one** `rmse_m or 1e9` expression in fine
ranking, not the two reported by the review text. Coarse RANSAC separately
ranked median distances. Both real ranking paths now use explicit residual
ranking: finite 0 is valid and precedes .02; None is missing and sorts after
valid metrics. NaN, +/-infinity and negative values raise `ValueError`, not a
fake low confidence or valid candidate. Fine ranking still prioritizes minimum
bidirectional overlap exactly as before. Equal overlap/residual ties use
lexicographic transform values deterministically. None on the highest-overlap
candidate cannot crash ambiguity comparison or become accepted.

No overlap, residual, geometry, ambiguity, seed or iteration gate was relaxed.
No new registration algorithm or tuning project was introduced.

Changed production files: `multimap_core/solver.py` and the latest-tested C1
SHA constant in `multimap_core/contract_adapter.py`. Added dedicated numerical,
incremental and connection regressions plus owned evidence/docs. C1/C2 and
all common product/CI files remain read-only.

## Evidence classification

- **Injected numerical-boundary regressions**, not whole-solver mocks: actual
  coarse shortlisting and fine candidate selection with 0/.02/None and invalid
  metrics, overlap priority, all-missing residuals and deterministic ties.
  `_rigid_fit`/metric/refine boundaries are injected explicitly for those cases.
- **Unmocked actual solver**: seeded and automatic identity, noisy partial maps,
  3-map graph, wrong seed/no-overlap, symmetric alternatives, plane degeneration
  and anchor/transform-direction checks remain exercised.
- **Actual core + storage**, no mock solver: D1 `solve_contract` → latest C1
  `FusionJobManager` → review revision 2 → `BundleStore` chunk size 17 → reload.
  All 800 XYZ/normal/intensity records checked; input hashes preserved, stale
  export rejected, occupancy UNKNOWN with no inferred free cells.
- This round's connection test is **not HTTP/UI execution**. C2's pinned actual
  HTTP/UI producer was inspected read-only and the new output PCD hash matches
  its already-published evidence exactly; the C2 UI/path is frozen, not rebuilt.
- **Actual incremental solver/full export**: (A+B)+C has 600 records and three
  immutable root IDs; (A+B)+(B+C) is explicitly rejected before publication for
  duplicate B, including conflicting transform. No automatic deduplication claim.
- Real private mapping accuracy: INPUT_REQUIRED. ROS/native/robot: NOT_RUN.

PCD output SHA:
`46be1a0ec38166fc78e7d0344d3e241d57e3c29807f22e819e22e04d1ec9dbde`.
Exact synthetic input/output hashes and metadata are recorded in
`experiments/expansion_20261029/d1_multimap/ROUND2_CORE_STORAGE.json`; no PCD is
committed. This hash comparison is storage-byte evidence, not field accuracy.

## Reproduce

From this clone, export only pinned dependencies into temporary directories:

```sh
git fetch origin 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 5eed1a9959ca25a4f30bd5b5712806a5ad660c51
mkdir -p /tmp/d1-round2-c1-54629c7
git archive 54629c793ad4ae0ea88127f00ed1b7f8805fc4e2 \
  robot_dashboard/expansion_contracts robot_dashboard/expansion_services \
  | tar -x -C /tmp/d1-round2-c1-54629c7
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export D1_C1_EXPORT=/tmp/d1-round2-c1-54629c7/robot_dashboard
export D1_C1_ROUND2_EXPORT=/tmp/d1-round2-c1-54629c7
python3 -m unittest discover -s tests/expansion_d1 -v
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
python3 -m ruff check robot_dashboard scripts
```

External dependency tests SKIP explicitly when the pinned export is not supplied;
no replacement validator is substituted. HTTP/ROS/native tests are not claimed.

## Local execution results

- Final focused suite: **28 PASS**, 1.269 s, external C1 tests enabled.
- Required full discovery: **3,001 tests, 109.576 s; 36 errors, 11 skips**.
  All 36 error names match the prior local full regression exactly: 25 denied
  local mock socket creations and 11 missing `cv2` imports in unchanged common
  tests. No full local PASS is claimed. The later-added incremental test is
  included in the final focused suite rather than that earlier discovery.
- JavaScript: **699 PASS**; syntax smoke **112 modules PASS**.
- Whole production/scripts Ruff and whitespace: **PASS**.
- The optional escalated full-test wrapper failed before running Python because
  its sandbox setup could not create a runtime session file in read-only
  storage. No protected-path read or escalation retry was made. The ordinary
  sandbox run above completed and its limitations are retained unchanged.
- Local logs: `/tmp/d1-round2-full.log`, `/tmp/d1-round2-focused.log`,
  `/tmp/d1-round2-js.log`. Remote final CI is separately reported, not inferred
  from these focused results. No heavy VM jobs overlapped.

## Publication and remaining one item

Source and final publication SHAs plus current CI results are in the delivery
report; this commit cannot embed its own hash. Publication preserves the prior
remote parent and all original tree entries, uses only the specified D1 branch,
and never force-pushes. No main/product/robot/deploy changes.

**Next one item:** proceed to D2's bounded latest-contract/consumer compatibility
in its existing independent clone; real-map accuracy still requires actual maps.

## Source commit and remote CI observation

- Locally tested source/test commit: `0a00649b4baa46408481f61d9d23ffb3bf7e48be`.
- Published source/test SHA: `70d94b51669af8e9fb496de400de394cf088a5f2`.
  Remote and local complete trees both `297f513618ab5a33b92a8496b93bb0193729c876`.
- [Exact source CI run 40836821084](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40836821084):
  **FAIL overall**, not hidden by the D1-focused results.
  `competition-offline-integration` and Ubuntu22/Python3.10 matrix **PASS**.
  Ubuntu24/Python3.12 full Python coverage, static/security/audits, JS and syntax
  **PASS**; browser E2E **226 PASS, 1 FAIL**, subsequent mission fixture SKIPPED.
- First actual error: `tests/e2e/mount_calibration.spec.mjs:343:3`, saved synthetic
  artifact import/relative-only export case. 20,000 ms test timeout; helper
  line 142 expected `#mount-calibration-results-content` visible but it stayed
  hidden. This is a mocked calibration UI integration case, not D1 solver or
  real-camera evidence. [Failed job](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40836821084/job/123323429669).
- Baseline comparison: test, common product sources and CI configuration are
  unchanged from `cbedd05ba6f97dad5506e8003302f689ed8fcb4c`; its
  [prior CI 40827660911](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40827660911)
  passed both matrices. The same source SHA's other matrix also passed. These
  observations suggest timing/environment sensitivity but do NOT prove a flaky
  root cause or turn this failure into a pass. No timeout/threshold was relaxed,
  no tests deleted, and common calibration code is outside D1 ownership.
- This evidence-only documentation commit leaves source/test bytes unchanged.
  Its final remote HEAD and CI are checked and reported separately in delivery.
  No repeated tuning or shared-code fix is authorized by the D1 scope.

If the unchanged calibration failure persists, the next required input is the
common calibration owner's diagnosis of this exact failed UI trace; D1 numerical
and latest pinned core/storage verification is complete.
