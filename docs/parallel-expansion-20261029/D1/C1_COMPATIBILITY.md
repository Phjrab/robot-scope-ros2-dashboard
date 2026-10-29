# C1 contract compatibility (read-only dependency)

Tested contract SHA: `2402c02c6f91ba54064894b21735e01b98610acd`, branch
`review/20261029-x-c1-services`. C1 is not copied, merged, or cherry-picked.

`contract_adapter.py` translates a **C1-validated** `FusionRequest` into D1's
internal request. C1 remains the sole shared-schema validator. The adapter
accepts an injected `FusionProposal` class, invokes its constructor, and emits
its validated object. It requires no C1 import at module-import time.

Differences handled:

- C1 source keys use `map_id:revision:frame_id`; D1 internal keys use `@`.
- C1 transforms are flat 16-value row-major arrays; D1 uses 4×4 arrays. Both
  implement `p_target = T_target_source @ p_source` and no scale optimization.
- C1 anchor-relative guesses become pairwise initial guesses; correspondence
  groups are ordered consistently even when the anchor appears later.
- C1 pins are a key/hash dictionary; D1 retains full pinned descriptors.
- C1 proposal `state` maps from D1 `status`. Service-assigned 24-hex `job_id`
  is an explicit argument, independent of the original request identifier.
- C1 `voxel_size` maps to D1's resolution parameter (supported `.005.. .5 m`).
  `max_iterations` and `max_runtime_s` are **explicitly rejected** by this adapter:
  D1 currently uses fixed bounded iterations and does not implement external
  worker termination budgets. C1 must omit those options or implement budgeted
  process isolation; silently ignoring supplied bounds is forbidden.
- Full residual sample arrays remain in the core proposal; bounded C1 wire
  messages retain aggregate edge metrics and state this omission in `quality`.

For export, retain the internal proposal returned by `solve(to_core_request(...))`
and pass it to D1 `export`; then use `proposal_to_contract` for the service/UI
message. Do not reconstruct a full export from the reduced wire proposal.
`solve_contract` is a convenience for callers needing only the validated wire
proposal. Neither function registers anything in a service or operates a robot.

## Reproduce exact-SHA contract check

```sh
DEP=/tmp/d1-c1-2402c02
mkdir -p "$DEP/expansion_contracts"
for f in __init__.py messages.py fixtures.py; do
  git show 2402c02c6f91ba54064894b21735e01b98610acd:robot_dashboard/expansion_contracts/$f > "$DEP/expansion_contracts/$f"
done
D1_C1_EXPORT="$DEP" OPENBLAS_NUM_THREADS=1 python3 -m unittest discover \
  -s tests/expansion_d1 -p test_contract_adapter.py -v
```

Observed: 3 tests PASS (real C1 validation round-trip of an actual synthetic
solver result; explicit unsupported-budget rejection; reversed anchor
correspondence translation). Without `D1_C1_EXPORT`, those three compatibility
tests explicitly SKIP rather than inventing a replacement validator.
This is a contract-level check, not service, HTTP, C2 UI, or product integration.
