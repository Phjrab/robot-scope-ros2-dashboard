# Articulated replay handoff

Base: main@7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a. No commit/push/PR/main/device changes by this worker. New source only under this revision.

Parent may deliver output/go2_articulated_slalom_and_blocked.mp4 and output/slalom_articulated_preview.png. Exact source tracing and geometry limitations are in README.md, review/SLALOM_REVIEW.md and output/RENDER_VALIDATION.json.

Prerequisite for final slalom replay tests: independent left_slalom_20261024 revision and its exact original traces, plus coherent corrected arena corridor-parallel-20261024. Set ARENA_SLALOM_SOURCE_ROOT to that checkout. Full source test data are not silently vendored into this revision. No planner/scene edits were made here. Parent owns publication scope.

Delivered final gait stride is .16m, unchanged after discovering initial planned-envelope violation. Rejected .245 envelope and intermediate shorter-stride exploratory outputs remain local; failure evidence is retained in review/. Final expanded .28 trace was independently audited and rendered.

Only files listed in DELIVERABLE_FILES.txt are selected for handoff. Render intermediate PNG sequences, generated .blend/.blend1 and caches are intentionally excluded. Regenerate them via README commands. No existing file outside this new revision was modified. Rollback removes this new visualization revision only.
