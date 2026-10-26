# D0 independent review — final bounded verdict

2026-10-24 12:08 UTC. Base7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a.

## Result

No remaining blocking defect was found in the reviewed D0 software scope after the fixes below. This is a finite source/test review, not proof of absence of errors or robot qualification.

- Independent black-box regressions:11/11 PASS (`test_independent_review.py`, `review_tests.log`).
- Independently rerun traffic tests:136 PASS (`traffic_tests.log`).
- Independently rerun integration tests:44 PASS (`integration_tests.log`).
- Write-scope/canonical/history check PASS (`scope_check.json`): changed and untracked repository files stay in the four authorized module trees; no historical result/checksum, shared schema, assets or production file changed. HEAD remains requested base. Python source hashes record the reviewed snapshot.

## Defects found and corrected during review

1. Invalid input set core INTERRUPTED but next approach observation could release: session now closes.
2. Source age plus receiver residence could exceed freshness while checked separately: composite effective age now used.
3. TemporalFilter stale/reset erased replay history and allowed repeated sequence to regain GREEN: per-epoch high-water preserved.
4. Fault retained cached departure intent: eligibility now cleared immediately.
5. Delayed stop samples credited receipt duration toward physical2s: conservative source-supported lower bound now required.
6. Delayed ACK/movement could precede its triggering request despite later receipt: acquisition lower-bound chronology now checked.
7. Retained RELEASE outlived GREEN/pose evidence: integration ages oldest required evidence before applying commands.
8. Approach terminal/fault could leave old RELEASE usable until next sensor callback: lifecycle mutation/event barrier now invalidates it before apply.
9. Empty/None/unhashable observation epochs could release/crash: typed nonempty identity checks now fail closed.

## Arena evidence and limits

Reviewed24 scenario/policy pairs with two deterministic repetitions, covering0/1/2/5/10cones, centered/boundary/narrow/occluded/delayed/dropout/mapped obstacles. All pair trace hashes agree across repetitions. Strict no-parking cases reach goal ONLY in the empty case; every tested strict obstacle case ends SAFE_WAIT. This is an honest safety-regression result, NOT demonstrated general multi-obstacle navigation success.

The preserved historical detour has16 recorded parking-overlap frames and maximum body intrusion0.077819011m. Existing permissive experiment remains visible, while strict policy prevents the maneuver.

Viewed final render PNG: SYNTHETIC/PLANAR, seed, recorded terminal reasons and no-gait/no-full-course caveat are legible. It shows actual traced empty success, legacy-permission one-cone success and strict blocked waits. No hand-authored success motion is asserted. The geometry audit uses finite sampling and some shared geometry utilities; do not describe it as independent physics or continuous-time proof.

## Integration qualifications

- Local dataclasses are an explicit D0 adapter contract, not changes to canonical v0.1 schemas.
- A trusted onboard receiver must validate event provenance and clock-aware source age; simulated callbacks/ACK fixtures are not measured hardware evidence.
- Source age,0.25s receiver TTL and0.5s observation-gap policy remain distinct.
- Physical departure threshold/calibration, real RGB/weights, native ROS/Nav2, gait/posture, map registration and Jetson validation remain INPUT_REQUIRED/NOT_RUN.
- Signal RED after bound observed departure does not stop the same crossing solely due to signal color; collision/safety checks still hold.
- No commit, push, robot access or production deployment was performed by this review.

## Addendum — C1 integration blocker discovered by full repository regression

2026-10-24 12:12 UTC. The bounded D0 module verdict above does NOT mean the full repository has zero integration blockers.

The full suite exposes a new expected failure at `tests/test_competition_mission.py:97`, `test_vm_manifest_uses_published_hashes_without_registration_or_native_promotion`: expected `SYNTHETIC_ONLY`, actual `UNAVAILABLE_OR_CHANGED` for traffic VM evidence. Independently read and invoked `robot_dashboard/mission_routes/competition_assets.py:47–56`: traffic and integration both return `UNAVAILABLE_OR_CHANGED`; avoidance remains `SYNTHETIC_ONLY`.

Cause: the production read-only evidence adapter selects the original immutable publication manifest, `traffic_signals/SHA256SUMS` for `core.py` and `integration/SHA256SUMS.txt` for `adapter.py`. D0 correctly modifies those source files while preserving old publication evidence. Therefore the old checksum comparison correctly rejects the changed source. This is not a failure of the new D0 unit/synthetic checks, but it is a real unresolved repository integration dependency and must be disclosed.

D0 must NOT overwrite historical manifests, loosen checksum checks, change production `competition_assets.py`, or update common test expectations merely to obtain PASS. Those files belong to C1.

Exact C1 remedy:
1. Review/apply the D0 source patch and newly shipped files at the recorded base, resolving concurrent common changes as C1 owner.
2. Verify `D0_SOURCE_EVIDENCE.json`, current source hashes, new validation/log hashes and the corresponding reproduced results. The new evidence must bind to this actual D0 source revision, not old test counts.
3. Add an explicit versioned evidence selection/allowlist in the shared production adapter for the new D0 source + validation revision; preserve the old manifest and old source-evidence history. Do not promote by changing a hash alone.
4. Update the common adapter tests to cover both approved revision integrity and mismatch refusal, plus the explicit source-to-validation binding. Native capability must remain unconnected and evidence synthetic only.
5. Rerun the affected mission manifest test, complete repository tests and relevant CI before claiming integration complete. No deployment or robot action is implied.

Status: D0 software regression reviewed; C1 evidence-adapter integration BLOCKED/PENDING. The overall repository must not be reported as all tests green or free of integration blockers.
