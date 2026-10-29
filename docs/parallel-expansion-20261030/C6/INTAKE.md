# C6 intake and reuse decisions

2026-10-30 KST. Separate ordinary clone, explicit user branch
`review/20261030-x-c6-run-review`. The repository's default-main rule has an
explicit-user-branch exception. No peer branch, existing checkout, device, API
root, recorder, navigation gateway, app.js/index.html or CI workflow is edited.

| Read-only pin | SHA |
|---|---|
| latest main and requested investigation baseline | `5154761bba6fa4f171881e61f986901e2b415ed9` |
| C1 | `50600c7bce6f5fae743cd836ca1d8ee68d91b05a` |
| C3 | `5bf58097f4a67806f5515b931a3b8013d65bf01e` |
| C4 | `7ac0d55b07abd20902d6d756c6b225733613fea7` |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` |

All refs were resolved once from a fresh GitHub clone. Exact Git blobs are
exported into a new read-only dependency directory, with origin and content
hashes verified before imports. No merge or cherry-pick. C4 is document-only;
C1 validator/SceneSnapshotService and C3 parser/adapter/consumer/mount execute.
D3 native source is separately `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`.

| Inspected existing component | Reuse and missing capability |
|---|---|
| `goal_precision.py` | Reuse `pose_error`, actual producer tests and original near-result/after-stop semantics. Never rerun live freshness with current wall time. No independent accepted-event timestamp in the sink. |
| `goal_evidence_sink.py` | Reuse its actual JSONL records and bounded sink in generated tests. No new recorder. Sample rows intentionally omit full context; retain the last observed goal context. |
| datasets/capture | Camera capture/export manager is not a run timeline and would introduce camera/archive access. Inspect only; no capture, demand token, video, or dataset export. |
| recorded_report/recorded_view | Follow bounded local-file loading, generation fencing and text-node rendering; reuse the same existing RobotScene3D renderer. Its SE3 report schema is not a navigation run, so do not relabel it. |
| route_planner/replay, competition replay_clock | Reuse their design separation of source time and local playback. Their advisory scenario generator and CPU workload clock are different estimands; do not feed recorded goals to those controllers or retimestamp sensor frames. |
| C1 scene 0.1/0.2 | Actual owner validator on import; archive envelope is explicitly C6 internal. Owner DTO unchanged. Original canonical packet remains in the private bundle. |
| C3 public `mountObstacleScene` | Inject `scene`, `subscribe`, `getMap`, replay `clock`. Actual C3 adapter draws supplied obstacles/paths; no copied renderer or URDF pipeline. |
| D3 native evidence | Fixed result/trace/observations JSON profile; verified original artifact and member hashes. Existing C1 producer projects provided pose/path for C3. No native process launch. |

Read before implementation: C1 ROUND2_CONTRACT and ROUND2_FOLLOWUP, C3 ROUND2_V02,
C4 FOLLOWUP, D3 ROUND2_RESULTS, and GOAL_HEADING_FIELD_CHECK_20261029. The C1/C4
reports' earlier C3 0.2 refusal refers to older C3 pins. **Current pinned C3 0.2
parsing and display pass here.** No current defect is inferred from those older
reports. Native baseline protection remains D3 ADVISORY_ONLY; archived display
adds no command authority.

The accessible local private sink contains both documented real canceled trials
(128 original records). It is read in place; original hash remains
`bb5e23e1f3e0a02bb67afa7e362e11ec626cbd15be9275e4daf214643acf1c1c`.
No attempt was made to contact the robot or acquire another real recording.
