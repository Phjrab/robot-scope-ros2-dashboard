# VM to Codex handoff: arena revision

Base: b1077e39e4ee456621c47eada49b1f0c85453661, local-only clone. No commits, staging, push, branch or worktree created. Only assets/competition-arena/revisions/rulebook-20261015 owned by this worker. Original arena hashes unchanged. Prompt baseline c00cc585 is older than inspected main; this asset revision stays isolated.

## Verified results
| Check | Status | Evidence |
|---|---|---|
| Rulebook pages6–8 actual PDF images reviewed | PASS | PDF rendered pages, figure/body discrepancies recorded |
| Legacy structural validation | PASS | copied legacy files and validator executed in /tmp; original untouched |
| CPU generation | PASS | Blender4.3.2 Debian13, CyclesCPU24samples, logs/build.log |
| New GLB actual vertex bounds/axis/IDs | PASS | Python/NumPy reading binary GLB, validation.json |
| Numeric bay/slalom/parking/marker dimensions | PASS | source-generated bbox checks tied to GLB vertices |
| Closed terrain mesh edge topology | PASS | each undirected terrain edge exactly two incident faces |
| Both-feet, full parking footprint, finite full-footprint finish | PASS | synthetic positive and boundary/center-only negative tests |
| Seven scenarios, seed repeatability,0..10 limit | PASS | purePython fixture validation |
| Saved blend reopen/nonfinite/empty mesh | PASS | actual Blender reopening; blend_reopen_validation.json |
| Re-generation consistency | PASS | independent second Blender build, eleven JSON manifests identical |
| OFF / AMBIGUOUS asset profiles | PASS | independent Blender export plus actual GLB validation; NOT camera recognition |
| Visual top/isometric/terrain/parking review | PASS | direct rendered-image inspection; provisional junction gaps corrected |
| All rulebook geometry simultaneously satisfied | BLOCKED | incompatible/ambiguous baselines, see ASSUMPTIONS |
| Browser interaction / native ROS / SDF physics / real camera / robot clearance | NOT_RUN | no such execution or hardware qualification |

## Downstream use
Read arena.semantic.json and scenario_*.json. The IDs stop_zone_01/02 map to signal_01/02. Both stops are provisional rectangles on the raised central area; footprint predicates do not prove dwell, actual stop or posture. Course graph is DRAFT, map_transform=null. Never treat a simulation five-second signal schedule as detector evidence. Obstacles are runtime scenario fixtures, not baked ground truth map content.

Do not connect these assets to live navigation until gap/X baseline interpretation, physical wall geometry, terrain-floor alignment, real stops/signals, QR payload, robot geometry and map registration are separately resolved. This is a design fixture, not ready-to-drive geometry.

## Reproduction and rollback
See README commands. Install dependencies only from official/reputable sources when needed; tested with existing Blender4.3.2, Python3.11/NumPy in this VM. No fonts shipped. No hardware control dependencies.

Deliver this entire directory as the source package; source files are geometry.py, build_arena.py, validate_arena.py, validate_blend_reopen.py, render_marker_closeup.py, profiles/*.json. No integration patch to shared runtime is required. To roll back, omit/remove only this new revision folder; original arena is untouched. Preserve unrelated worker changes elsewhere.

No secrets, real sensor measurements or robot weights included. CHANGED_FILES and SHA256SUMS describe this exact directory excluding generated Python caches and manifest self-hash.

## Git publication (2026-10-24)
This source snapshot is prepared for publication on main. Earlier no-publication statements describe the authoring stage. See experiments/competition_vm/PUBLICATION.md for included artifacts, exclusions and final test status. Module checksums describe the Git publication subset, not the separately delivered immutable ZIP. No real robot measurements are included.
