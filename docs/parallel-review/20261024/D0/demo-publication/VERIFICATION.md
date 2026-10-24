# Fresh publication-copy verification, 2026-10-24

The copy was created by ordinary local clone at fixed D0 review baseline `6403aab3afef96efa778b5265afd7ce5b351265c`, without commits, remote publication, hardware access, deployment, or changes to existing runtime/source files. Source projects remain untouched. The final GitHub publication is a separate authorized step.

## Results

- 172 selected source artifacts: SHA-256 and byte-size verified against frozen source bytes.
- 17 lossless gzip fixtures: both compressed and decompressed hashes/sizes verified; restored exact bytes at original test paths.
- 95 focused tests: PASS. Original gait 10, curved gait 10, left slalom 10, curved controller 14, partial flat course 7, old independent FK/trace review 16, new open-normal actual/synthetic review 14, same-layout baseline actual/synthetic review 14. The common six synthetic tests are intentionally rerun for each selected curved-review case; these are 95 test executions, not 95 distinct test definitions.
- Selected combined/comparison/partial videos: 3 PASS, checking source bytes plus ffprobe-decoded frame counts, dimensions, frame rates and duration. Counts are 491, 775 and 642 frames respectively. This is integrity/timing validation, not new visual or physical qualification.
- Full repository Python: 2,691 tests executed; FAILED with 1 failure, 25 errors and 1 skipped. The failure is `test_vm_manifest_uses_published_hashes_without_registration_or_native_promotion`, where `traffic_signals.scope` returns `UNAVAILABLE_OR_CHANGED` rather than `SYNTHETIC_ONLY`. The 25 errors are sandbox-denied Unix socket creation (`PermissionError: [Errno 1] Operation not permitted`) in broker tests. These match the known baseline failure categories; this report does not relabel the full suite as passing or fix unrelated runtime code.
- Repository JavaScript: 660 PASS, 0 failed, 0 skipped.
- Repository tracked-source secret scan: PASS. Additional selected-artifact scan including expanded gzip and large original text: PASS, 0 findings.
- Existing D0 230-case regression: NOT_RERUN for this artifact-only addition; existing D0 source bytes are unchanged.
- Native Nav2, SLAM, contact/gait physics, terrain transitions, actual sitting/stopping, official exit registration, real robot or deployment: NOT_RUN / NOT_VALIDATED.

The exact commands, environment selections, return codes and complete logs are under `validation/`. `verify_publication.py` exits nonzero when the full repository suite fails, even though the focused additions pass. Historical author checks remain separate from these fresh results.

## Publication boundaries

Only new revision artifacts and `docs/parallel-review/20261024/D0/` evidence/support are included. The root `.gitignore` and all existing tracked files remain byte-identical to the baseline at this preparation stage. Restored fixture JSONs are ignored by new nested `.gitignore` files and excluded from the authoritative publication list; only their gzip representations are published. The original author source bytes are unchanged, including the historical renderer's absolute-path reference; a new portable wrapper supplies the current-clone trace path at execution time.

All source hash manifests retain their historical meaning. The compact publication intentionally omits 89 specified failed/repeated/redundant artifacts, plus non-deliverable raw frames/caches. Their source hashes and compact trace metrics are preserved in the subset manifest and summaries. No rejected result is promoted to success. No `curved_progress_20261024` path is included.
