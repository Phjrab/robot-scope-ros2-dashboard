# D0 atomic snapshot review (2026-10-27)

Small offline continuation of the completed D0 ROUND6 review. No native Nav2,
robot, planner changes, route export, tuning or physical qualification.

Inputs are private retained GitHub artifact **12638597871**, run40296598053,
source `cf7662123bf13c9c38d565c03a978a4b9ae357a2`, and its exact ZIP. ZIP SHA256:
`91a7d37428dc838e324de82152ff7f84082a0cd618546376e559dfb73fead404`.
Unzip without modifying original files. Raw grids/observations are not in Git.

From repository root:

```sh
python experiments/competition_vm/arena_robot_sim/revisions/atomic_snapshot_review_20261027/review.py /path/to/unzipped /path/to/archive.zip /tmp/review.json
D0_ATOMIC_ARTIFACT_ROOT=/path/to/unzipped D0_ATOMIC_ARTIFACT_ZIP=/path/to/archive.zip python -m unittest discover -s experiments/competition_vm/arena_robot_sim/revisions/atomic_snapshot_review_20261027 -p 'test_*.py' -v
```

Eight tests; artifact replay/negative provenance checks skip if private input is
absent. The saved sparse result is a review receipt, **not a runtime input**.
Reuses prior D0 Sutherland–Hodgman clipping rather than C3 SAT/native expected
verdicts. Exact identity is checked for all33 packets/returned paths; geometry is
independently recomputed only for two selected discrepancy intervals. Published
100 versus raw253 is not a codec inversion. A synthetic raw254 flip must still
collide. Full33-path sweep count and native lock assertion are retained C3 evidence,
not a second D0 native capture. Finite samples do not prove continuous safety.

Historical ROUND6 exact raw bytes remain unavailable. Current discrepancies are
explained; no new checker patch or automatic follow-up is justified. Navigation
remains NOT_ADOPTED because goal/progress and runtime results did not pass.
