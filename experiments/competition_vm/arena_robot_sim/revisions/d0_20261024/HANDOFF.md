# D0 arena regression handoff

Generated 2026-10-24 UTC against main7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a.
This submodule is LOCAL-ONLY and synthetic/planar. No commit/push, device connection,
service, UI, public schema or immutable arena asset was modified.

## Changes

All new files are under `arena_robot_sim/revisions/d0_20261024/`. The existing
`simulate.py`, planner, published result records, failed examples and videos remain
unchanged. This runner directly reuses their morphology, original start/goal,
ray/cone geometry, occupancy, A* and controller; adds explicit no-parking policy,
terrain ray occlusion, actual delayed-sample queue and swept evaluator. It is not a
replacement planner or claim of native integration.

48 runs:12 fixed layouts × strict/legacy policy ×2. All24 paired payload hashes
are identical across repeats.10 runs reached the planar goal and38 waited safely.
All strict obstacle layouts and all multi-cone layouts SAFE_WAIT; there is NO
multi-cone navigation success claim. The conservative circumscribed-radius
planner was not relaxed to manufacture a pass.13 unit tests passed. Independent
saved-trace audit22,913 poses: zero cone/fence/static-floor/terrain/forbidden-parking
violations. See summary/validation for measured walltimes and distinct clearance
metrics.

## Before/after reproducer

The unchanged published `results/cone_detour.json` contains16 sampled body overlaps
with the parking polygon; maximum x intrusion0.077819m. Its old GOAL_REACHED label
is preserved as historical legacy evidence, not accepted under the new policy.
The same x5.70 cone, model footprint, start and goal run through the original planner
with strict parking exclusion yields SAFE_WAIT. Empty strict navigation still
reaches the goal. Original centered and x5.75 failure configurations are included,
not discarded. The strict policy is a separate input mask, not a moved wall.

## C1 application sequence

1. Verify fixed base or review intervening main changes. Inspect INPUTS.json hashes.
2. Copy only this new revision directory; do not replace old results or common assets.
3. Run the four README commands and inspect comparison video/validation JSON.
4. Keep this an offline regression entrypoint. If production needs this policy,
   implement a reviewed native semantic-zone adapter in C1/C2; do not import the
   synthetic truth evaluator or permit parking based on a UI mode string.
5. Add a publication-index reference only through the C1-owned change. No public
   publication or shared schema was edited here.

## Public contract differences and missing evidence

The policy strings and metrics here are local experiment metadata, NOT new runtime
enums. A future owner must bind semantic zone permission to run/step/goal/generation
and a registered map transform. Existing `map_transform=null` remains unresolved.
The0.25s sensor receiver/source checks are explicit local test assumptions, not a
change to mission fixture continuity-gap semantics. Terrain/parking posture/whole
OUT crossing are NOT_RUN. The full-course sequence in README is DRAFT only; there
is no newly rendered full-lap terrain walk.

Rendering is a literal2D rectangle-envelope trace replay,20.7s/207frames, with
SYNTHETIC/PLANAR, seed, per-panel policy and true terminal reason. Four panels compare
empty strict success, one-cone legacy success, same one-cone strict hold and10-cone
strict hold. No successful multi-cone path was animated or hand-inserted.

## Rollback and preservation

Do not apply/adopt the new revision to roll back. No original files were deleted,
moved or rewritten. Exclude __pycache__ from deliverables; hashes omit checksum
file itself. No raw hardware measurements, credentials, model weights or large
map caches were added. Native/full-repository verification is reported separately
by the D0 coordinator, not copied from remote CI.

## Later approved compact publication

The user's subsequent approval replaces LOCAL-ONLY publication restrictions solely
for the D0 review branch `review/20261024-d0-vm-offline`. The coordinator handles Git;
this worker made no commit/push. Main/PR/hardware restrictions remain unchanged.
Stage only `PUBLICATION_FILES.txt` entries. Full48 JSON traces remain local and are
excluded; `RAW_TRACE_MANIFEST.json` preserves exact hashes. Compact delay/dropout
fixtures retain every tested field and every source frame, not sampled successes.
Remote unit tests no longer need those large raw trace files. Full replay/audit
requires regenerating them first; missing audit input fails explicitly.
