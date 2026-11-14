# Moved-position proposal and active-handoff validation

2026-11-14, Asia/Seoul. The operator moved the robot and requested a fresh
proposal through step 2 confirmation. They explicitly authorized the necessary
work and later identified candidate #0 as the better current-position assumption.
No INITIAL POSE transmission, Nav2 start, operational registration, goal, STOP
release or motion was performed in these trials.

## Initial moved-position trial

The browser displayed the unsent, unconfirmed draft X -2.123 m, Y 2.016 m,
yaw 0.146 rad. Only three-decimal display values were available; the API trial
records that precision and does not invent a browser draft revision. The user
could not provide new wall tape distances.

Observation `b31744f0ae2641f18206a8754a8de82e` remained READY with signed inhibit
HELD, STOP=true, lease=false and bridge Move=0.

- First proposal admission returned HTTP 409 `EXACT_STAMP_PAIR_UNAVAILABLE`;
  no proposal job was created.
- Three subsequent preparation reads had valid exact-stamp input pairs. One
  explicit retry with the same request ID created job `84cff604f6a3d1a07047bc13`.
- The calculation succeeded and settled, but proposal validation returned
  `PRIOR_NO_MATCH`. Candidate #0 was 0.273303 m from the draft, beyond the
  unchanged 0.25 m limit; yaw difference 0.013507 rad passed the 0.20 rad limit.
- Original worker input was copied without changing the worker: 319 scan points
  and 32,387 map points. Sizes, hashes and complete job context matched.
- Independent offline refinement from the draft converged 0.2620-0.2754 m away.
  A later same-session dense sample also converged about 0.263 m away. These are
  diagnostic estimates, not proof of physical position accuracy.

The new simultaneous UDP/ROS capture at 16:36 retained 10,012 UDP packets.
Seven full driver frames, 448,000 XYZ/ring/intensity records, exactly matched
decoded packets in order. This did not establish why the operator's clicked
point differed from the registration estimate. The session was stopped by its
exact ID; 16:39 readback was STOPPED/inactive/not busy, STOP=true, no lease, Move=0.

## Operator-confirmed candidate and reproduced step 2 failure

The user explicitly identified the latest closest candidate #0 as the position
that looked more accurate. A new operator assumption used its recorded
projection: X -2.33953628860697 m, Y 1.8492468932820465 m, yaw
0.1595070696381258 rad. This was a new user-confirmed hypothesis, not an enlarged
acceptance bound or a claim that the earlier failed prior had passed.

Fresh observation `4df327dd97d5440da3eb628c0b53b0f5` and proposal
`979c461b3883542abe55f5e1` produced a ready conditional proposal. The retained
members #0 and #3 formed one verified group. Candidate/prior distance was
0.008444 m; all current member checks passed. Global ambiguity remained explicit.
Complete ready responses, original inputs, proof and confirmation were preserved.

The confirmation request stored `seed_geometry.source=proposal_confirmed`, but
immediately returned handoff `b136123a231047448bc271f5ad583a74` as
`INVALID / INITIAL_GEOMETRY_PROVENANCE_REQUIRED`, with about 100 seconds remaining.
The UI also displayed an invalid applied value. **This was not step 2 success.**
The diagnostic client's `confirmed` flag only checked geometry storage; a separate
`validation-correction.json` explicitly records the failed success criterion.

The observed failure is reproducible: the actual UI uses an operator-confirmed
map pair. Its asset revalidation passed the entire bundle into execution bundle
validation. A newly confirmed, still-active observation legitimately has
`stop_nonce=""` and `stop_state=NOT_REQUESTED`, which execution validation rejects.
Existing handoff tests used conversion-lineage pairs and missed the UI path.

## Fix and validation boundaries

For proposal-derived geometry only, operator-confirmed asset validation now uses
a non-mutating view without the execution geometry. Map revisions, calibration,
operator map confirmation and policy remain validated. The actual geometry and
proof remain stored unchanged. Before execution, the exact stopped-session gate
and full seed-geometry validation are still required.

Regression tests exercise the real operator-confirmed pair path: confirmation
while observation remains active; status readback; refusal to start before stop;
normal stop receipt; runtime snapshot; rejected map confirmation tampering,
invalid height and wrong stop nonce.

A separate exact-stamp race was also fixed. If the exact pose arrives between
history lookup and the latest-pose read, the original cloud's history is checked
once more. Missing data still fails without extra waiting. The 150 ms receipt
window, source checks and computation deadline were not extended. This race was
software-reproduced; it is not established as the cause of the first field 409.

On an isolated Linux copy of the deployed release, the new handoff regression
and four pairing interleavings failed before the changes. After the changes,
93 focused tests passed. Full-suite, publication and post-deployment field results
are recorded below when available; a stored invalid geometry is never counted
as a valid handoff.

The isolated Linux full unittest run executed 3,584 tests in 281.262 seconds:
2 failures, 6 errors and 50 skips. Two errors lacked Node; three errors and both
failures required Git metadata omitted from the isolated deployment copy. The
remaining HTTPS error came from the shell's 0002 umask making its generated
certificate group-writable. With umask 0022, all three HTTPS tests passed. These
environment failures are not reported as a passing full run. The Windows full
run encountered Linux-only resource imports and stalled in an unrelated existing
competition worker test; its bounded retry timed out. Relevant local JavaScript
tests passed (39 tests). Exact published-commit CI is required before deployment.

Raw inputs, packets, CDRs and complete API responses remain outside Git under
`../nav2-live-analysis-20261114/`. The two pre-fix archives have SHA256
`07ca7262ee1356c801d4e738db0ab3f55a12a9d292d0505eaac5e5f59e02b34d`
and `8ac6710092edf85d987a6d407bd8588758b36e9fb03a14dc9e912e7a624a577f`.

## Published fix and first post-deployment trial

Commit `d13fdfb9b204e2ac8c96b9de24ce13643e48910d` passed exact-commit CI
[43574818650](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43574818650)
and I0 [43574818696](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43574818696).
The Python 3.12 job ran 3,759 tests (35 skips), all passing, and 774 JavaScript
tests passed. Both Linux Python matrix jobs and all four browser shards passed.
An additional Windows browser run passed 116/122; six Python-backed fixtures
could not invoke the Windows `python3` alias. This local run is not all-green.

The dashboard and control bridge were restarted onto this release at 17:26 KST.
Both actual process working directories and the signed bridge release matched.
The release preserves both shared dependency links; tracked UTF-8 text was
normalized to LF for deployment, with before/after hashes retained outside Git.
The previous 8234fcd release and configuration rollback remain available.
The same confirmed map revisions were selected again after restart.

One observation start created `414117809f9b4aa19edbb2d0bfa39a33`. One proposal
request created `d8cf1faf281dcaa48bd71299`, which was cancelled before ready as
`stale / OBSERVATION_SESSION_CHANGED`; worker cleanup was SETTLED. No confirmation
request followed. This reason also covers a same-ID session that is temporarily
not READY; it is not evidence that the ID changed. Pre/post records retained the
same ID and READY, so the exact first transient condition remains unconfirmed.
No original worker files were copied before cancellation; the job's captured
metadata is preserved, not mislabelled as preserved original input bytes.

At 17:30, 50 subsequent samples had the same ID but were INVALIDATED with
`CONTROL_OWNER_UNKNOWN_DURING_OBSERVATION`, signed guard HELD, owner_failure null.
The service invocation matched the ID and NRestarts was zero. This later sticky
failure cannot retroactively explain the earlier transient cancellation.
The exact session was then stopped normally: STOPPED/inactive/not busy, no guard,
STOP=true, no lease and Move=0. No automatic recalculation or reapplication ran.

## Control-owner contention reproduced separately

Native RLock tests reproduce the later guard failure without commands: a normal
reader briefly holding the control operation or manager lock caused the direct
guard's nonblocking copy to latch UNKNOWN permanently. The actual field lock
holder was not captured. General ownership readback remains nonblocking.
Only the observation guard may acquire a fresh control copy within one shared
100 ms deadline across both locks. No cached idle state, output draining, lease
expiry or command publication is used. Deadline failure, malformed ownership,
actual work and lost inhibit still invalidate; the first control failure site is
now retained. This is a bound on the control copy, not the entire snapshot call.

The coordinated async monitor also retries control-only/native-navigation lock
contention within its existing 100 ms budget, yielding before fresh full-owner
reads. It does not synchronously wait for the same control lock on the event loop.
The signed inhibit is still checked before admission/retention, and unresolved
unknown ownership still blocks. Tests include an event-loop-released reader and
inhibit loss during that wait. This is separate from the earlier navigation jobs
lock fix and is not counted as a field pass before a fresh trial succeeds.

The direct guard regressions failed on the previous code (four failing cases,
two missing-diagnostic errors); the separate monitor regression failed in both
healthy contention cases before its change. The final candidate passed 81 related
Python tests and 39 JavaScript tests. Full isolated Linux unittest ran 3,587 tests
in 281.620 seconds, with the same two Git-dependent failures, two missing-Node
errors, three missing-Git errors and 50 skips. Exact-commit CI supplies the complete
repository/dependency environment before activation.

The operator subsequently requested completion of the current software work,
then planned to perform observation through proposal application personally.
No further observation start, calculation or confirmation is to be issued as
part of this handoff. Deployment and final read-only checks remain in scope.
The next field attempt must use a fresh current-location assumption and retain
its valid session/proof; step 2 field success remains unverified at this point.
