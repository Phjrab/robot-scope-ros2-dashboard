# Publication subset and reproduction

This is a separately prepared publication subset of a completed, frozen VM
experiment. It does not replace the previous rendered candidate or alter the
existing D0 integration/UI/runtime defaults. Original README, VALIDATION,
source, tests and independent-review files are copied byte-for-byte. Their
historical “no publication” wording describes the original experiment stage.
The later publication preparation is documented here, not retroactively in
those frozen records.

## Payload and provenance

- `PUBLICATION_SUBSET.json` maps every included original to its original and
  published byte counts and SHA256. It also records omitted exploratory,
  duplicate-repeat and scene-mesh files with hashes and available metrics.
- Five complete candidate02 traces are deterministic lossless gzip files,
  about 5.8 MB together, not lossy projections or shortened test fixtures.
  Their decompressed bytes are checked before the unchanged 22 tests run.
- Candidate01 rejected raw traces, duplicate repeat02 raw data, and unused
  scene meshes remain omitted. Their existence, failures and hashes are not
  promoted into a successful final candidate. No new video is included.
- `SHA256SUMS.txt` is the frozen original-production inventory. It includes
  original uncompressed and omitted files and is not a remote subset list.
  `PUBLICATION_FILES.txt` and `PUBLICATION_SHA256SUMS.txt` describe this subset.
  The checksum list hashes every listed file except itself, avoiding a
  recursive self-hash. The path list includes the checksum list itself.
- `PUBLICATION_DEPENDENCIES.json` binds the unchanged code, geometry and exact
  previously published baseline inputs. No existing repository file was
  edited as part of this preparation. The source revision was untracked at
  its original repository HEAD, so file hashes, not membership in that HEAD,
  establish the source identity.

## Reproduce without changing frozen outputs

From the repository root:

```sh
python3 -B experiments/competition_vm/arena_robot_sim/revisions/curved_progress_20261024/publication_checks.py --check-only
python3 -B experiments/competition_vm/arena_robot_sim/revisions/curved_progress_20261024/publication_checks.py --output-dir /tmp/followup-publication-check
```

Use a new, empty output directory. Python 3 with NumPy/SciPy, Node.js and Linux
process/thread support are required for all selected checks. The helper
restores exact missing gzip fixtures but refuses to overwrite changed ones;
when an exact fixture is already present, it is not rewritten. It runs the
unchanged progress 22 tests, unchanged watchdog 15 tests, actual frozen-planner
timeout probe, six original geometry/motion reports, two original race probes,
full repository Python and JavaScript checks, and tracked/new-artifact secret
scans. `--focused-only` omits full-repository checks and is never a full-pass
claim. Generated results go to the new output directory.

`publication_replay_review.py` is an explicitly publisher-owned adapter:
progress review changes only the in-memory `ROOT` and `HERE` assignments;
watchdog review changes only its absolute import-path constant. Original
review source bytes are unchanged. All six progress reports must equal the
frozen reports exactly; the race probe must retain TIMEOUT/CANCELLED, no result,
and zero gate output. These are reproducibility checks, not a new independent
review or new source/trajectory validation.

Frozen `compare_progress.py`, `repeat_progress.py`, and `run_candidate.py`
write to their experiment paths. Run them only in a disposable copy if new
regeneration is wanted. Frozen profiling scripts retain VM absolute paths and
require separately generated profile inputs. They are preserved as original
provenance, not presented as portable runnable benchmark commands.

## Interpretation limits

- Candidate02 improves fixed-OPEN planar command smoothness with an approximately
  11% longer simulated duration. The original tight layout remains SAFE_WAIT.
- Synchronous source timing is NOT REALTIME. Source acquisition timestamps are
  synthetic; recorded offline progress cannot prove control-loop freshness.
- This progress revision is NOT animated/articulated-mesh validated. Earlier
  rendered meshes and clearances do not automatically validate this trajectory.
- The watchdog is a separate synthetic command-output gate, not integrated
  navigation, ROS, actuator delivery or physical stopping. Pending planning
  gates output to zero, but pipe `recv` itself is not bounded. Neither measured
  timeout nor lease expiry is a hard realtime deadline guarantee.
- The local 0.1 s planning budget is a test assumption, not a user operating
  cap. TTLs were not extended and the isolated memoization experiment was not
  adopted into the frozen controller.
- Repository-wide known manifest integration failure and sandbox socket errors
  remain reportable failures, not skipped checks or a clean-suite claim. See
  `publication_validation/VERIFICATION.md` for this preparation's actual result.
- No main/UI/hardware changes, commits, remote branch updates, new renders or
  remote-CI claims are made by this local preparation. Publication and remote
  commit/CI verification are separate publisher actions.
