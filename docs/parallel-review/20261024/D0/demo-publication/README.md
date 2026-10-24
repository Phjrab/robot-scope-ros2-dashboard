# Frozen offline demonstration publication

This compact, reproducible subset adds replay and research evidence to the existing D0 review baseline `6403aab3afef96efa778b5265afd7ce5b351265c`. It does not alter the runtime controller, deploy software, contact a robot, change the map, qualify hardware, merge to main, or adopt the rejected tight-layout curved controller. No `curved_progress_20261024` artifact is included.

## Start with the selected videos

- [Articulated five-cone slalom and blocked case](../../../../../experiments/competition_vm/arena_robot_sim/revisions/articulated-20261024/output/go2_articulated_slalom_and_blocked.mp4): the prior fixed-yaw planar trace visualized with 12-joint kinematics.
- [Same open-layout baseline/gradual-yaw comparison](../../../../../experiments/competition_vm/arena_robot_sim/revisions/articulated-curved-20261024/output/go2_open_diagnostic_before_after.mp4): the same cone layout and full planner footprint on both sides. This is an OPEN DIAGNOSTIC layout, not success on the rejected original tight layout. The new trace is slower, reduces command acceleration, and ends with zero commands; clearance is lower, not improved. The baseline's nonzero-command terminal frame is explicitly held and labeled, not presented as a physical stop.
- [Partial flat-segment course demo](../../../../../experiments/competition_vm/arena_robot_sim/revisions/full_course_flat_segments_20261024/output/full_course_partial_closed_loop.mp4): recorded IN, prior slalom, P approach/zero-command hold, and a proposed OUT opening. Terrain and signal transitions are visibly unexecuted gaps. This is not end-to-end autonomous course completion or proof of sitting, balance, force/contact dynamics, physical stopping, or official exit geometry.

All videos are synthetic planar/kinematic evidence. Existing Unitree-derived mesh attribution remains in `experiments/competition_vm/arena_robot_sim/rendering/UNITREE_BSD_LICENSE.txt`.

## Exact fixture restoration and tests

From the repository root, with Python, NumPy and SciPy installed:

```sh
python3 docs/parallel-review/20261024/D0/demo-publication/restore_fixtures.py
python3 docs/parallel-review/20261024/D0/demo-publication/verify_publication.py
python3 docs/parallel-review/20261024/D0/demo-publication/verify_videos.py
```

The last command also requires ffprobe. The verifier runs all 95 focused tests, then the full repository Python suite, JavaScript tests (Node required), the repository secret scan, and an additional scan that expands the gzip fixtures and does not skip their large original text. `--focused-only` intentionally omits repository checks and must not be represented as a full pass. Fresh results and complete commands are in [validation/SUMMARY.json](validation/SUMMARY.json).

The 17 `.gz` files are deterministic, lossless gzip copies of the original bytes, not downsampled, projected, or synthetic replacements. The restore helper verifies both packed and original SHA-256/size, refuses mismatching files or changed local fixtures, and restores the exact original paths expected by the unchanged tests. Missing traces remain a test error; no assertion is weakened or skipped. New nested `.gitignore` files keep restored raw copies out of publication. The unchanged original gait tests use the existing baseline's `arena_robot_sim/results/cone_detour.json` and `blocked.json`.

The curved actual-trace tests default to a rejected historical candidate. The publication verifier explicitly selects `final_regressions/open_normal.json` with `EXPECTED_YAW_MODE=variable`, and `open_baseline.json` with `EXPECTED_YAW_MODE=fixed`, with their respective recorded joint fixtures. It restores the frozen synthetic metric artifact after the unchanged test writes its fresh output; fresh outputs are retained separately in `validation/`.

## Replay and optional regeneration

The original author source files are byte-for-byte preserved. Author READMEs and hash lists describe the historical full local workspaces and may reference omitted intermediates; the publication manifest below is the authoritative distributed subset.

The partial-course renderer has a historical absolute source path and imports the drawing helper `full_course_sequence_20261024/build_sequence.py`. That unchanged helper is included as a dependency, not as publication of the earlier whole-course storyboard. Use this portable wrapper to point it to the restored slalom trace:

```sh
python3 docs/parallel-review/20261024/D0/demo-publication/render_partial_course.py
```

Rendering requires Pillow, ffmpeg and the DejaVuSans font. It overwrites the generated partial-course video/previews; use a separate clone if preserving distributed render bytes. Full articulated re-rendering additionally needs Blender/Python NumPy and regeneration of omitted raw/labeled frames, following each revision's README and corrected `corridor-parallel-20261024/arena.blend`. The old `verify_render.py` scripts intentionally require those raw/labeled frames and per-case videos; they are not advertised as runnable against the compact distribution. `verify_videos.py` verifies the three actual distributed videos instead.

For fresh controller reruns, use the unchanged `left_slalom_20261024/{simulate_slalom,audit,reproduce}.py`; for the selected open diagnostic use `curved_slalom_20261024/reproduce_baseline.py`, then `run_scenarios.py open_normal open_dropout open_delay blocked_5`, `analyze.py`, and `repeat_check.py`. Matplotlib is needed for analysis plots. These commands are optional regeneration, not prerequisites for running the restored-fixture assertions. Wall-clock metrics may differ on regeneration; do not overwrite or relabel the frozen original SHA-256 records as new evidence.

## What is retained and omitted

[PUBLICATION_SUBSET.json](PUBLICATION_SUBSET.json) identifies each exact source, stored and restored hashes/sizes, encoding, selected path, and individually omitted development artifact. [OMITTED_TRACE_SUMMARIES.json](OMITTED_TRACE_SUMMARIES.json) preserves metrics/validation/scene summaries for omitted raw failed or repeated traces. Rejected outputs remain rejected; omitting bulky raw histories does not turn them into passes. Historical development sources, including the candidate source snapshot, are retained where present.

Raw animation frames, caches, temporary Blender files, redundant per-case videos, and failed/repeated large intermediate traces are not distributed. Source `DELIVERABLE_FILES.txt` limits the two frozen articulated inputs; artifacts outside those author allowlists are not silently included. `PUBLICATION_FILES.txt` and `PUBLICATION_SHA256SUMS.txt` enumerate the entire newly added subset, including these support files and fresh verification evidence (the checksum file does not hash itself).

Read-only research evidence is under `../evidence/quadruped_navigation_research_20261024/` and `../evidence/nav2_parameter_evidence_20261024/`. It informs future design; it does not claim native Nav2, SLAM, learned locomotion, contact dynamics, or robot execution was performed here.
