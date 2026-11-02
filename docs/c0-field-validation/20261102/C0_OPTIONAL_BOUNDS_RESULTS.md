# Pose drafts without operator uncertainty inputs

Result ID: `C0-OPTIONAL-BOUNDS-INTEGRATION-20261102-01`

The navigation preparation flow no longer requires an operator to estimate a position uncertainty radius or yaw uncertainty. A current map draft supplies X, Y and yaw, with the existing explicit stationary-current-pose acknowledgement. The API omits `operator_prior.bounds`; it never fills missing user uncertainty with fabricated values.

The server separately reports `bounds_source=server_policy` and `effective_bounds={xy_m:0.25,yaw_rad:0.20}`. These are the existing server acceptance limits, not measured uncertainty or position accuracy. The UI explains the default before calculation and after rejection. Valid restored explicit/legacy proofs show their original selection bounds separately from the handoff limit. Existing explicit-bounds API clients remain supported; new UI requests use the bounds-free path.

The raw draft remains bound to the request identity. Selection provenance and effective limits are regenerated and compared during confirmation. An omitted-bounds proof cannot remove its server provenance and fall back to legacy handling. All group members, current pose, later INITIAL POSE and the separate handoff checks retain their limits. Source, map/revision, calibration, generation, freshness, TTL, quality, ambiguity, stop and supervision checks remain in force. Multiple matching candidates or no candidate in the accepted range still prevent application. The flow does not automatically send INITIAL POSE, start matching or send a goal.

## Missing health values

The UI now renders unavailable health metrics as `—` while preserving a real numeric zero. An actually inactive navigation session hides metrics even when another diagnostic reason takes precedence. The gateway preserves missing reported input/accepted point counts and translation/heading jump counts as null, rejects malformed or contradictory provided values, and retains its own actual fresh-sequence count. No classifier order, threshold, speed, progress, tolerance or other driving policy was changed.

## Preserved first results

- The original display counterexample rendered missing values as zero. The first inactive-session follow-up also failed before its separate repair.
- The optional-bounds baseline recorded one failure and five errors across six tests. The repaired core set passed 98 tests. A separate extended bridge-async invocation stopped after one method printed `ok` but the invocation did not terminate; it was interrupted and is not counted as a pass.
- The callback baseline recorded seven subtest failures across four methods. After repair, the related set passed 84 tests. Earlier missing-public-counter checks passed 80 tests at their own source version; these sets overlap and are not additive.
- The UI candidate passed nine proof unit cases and 99 affected browser cases, plus a separate synthetic full-app path and five component cases at its recorded candidate. The subsequent display-only follow-up passed five targeted browser cases. Earlier UI candidate results are not represented as the final full-source integration result.

## Final frozen integration

The frozen source is commit `3d9eff1fa399e441b8319734f3f41f3e366029ce`: 2,331 tracked paths. The C1.3 exact archive manifest SHA-256 is `c9b2eb2a84c988871105d24af493d2af5d0e84ca3e684afd2eb9489951e29c25`; its 13-file harness manifest is `8a8c2da5c99788bd5f878bec8b7e02c7b6fa6f9bde7824d07888d76dc2f8965e`. C0's Python, Node and static runs used matching full tracked-file manifests, unchanged before and after each invocation.

| Check | Result | Scope |
| --- | --- | --- |
| Python discovery | 3,416 PASS / 2 optional SKIP, 132.786 s | 3,418 total; missing optional matplotlib and rosbags; required cross-test objects and libraries present |
| Node | 82 test files PASS | This invocation reports file-level TAP results, not individual case totals |
| Harness helper | 1 test file PASS | Separate invocation; not included in the Node total |
| Ruff / mypy / syntax / secret scan / whitespace | PASS | Existing configured scope; mypy 4 files, JavaScript syntax 114 modules |
| Affected UI browser cases | 99 PASS, then 5 targeted display-follow-up PASS | Earlier UI candidate plus the final display-only change; not a complete final-head browser suite |
| Actual ASGI preparation component | 37 PASS / 0 FAIL | One invocation at the frozen source |
| Full application flow | 8 assertions PASS | One actual browser invocation after the port-preflight repair |

The first full-app attempt stopped in the private runner's port preflight (`EADDRINUSE`), with no server/browser invocation. A read-only follow-up found no listener or fixture process and one TIME_WAIT connection. The preflight had not enabled SO_REUSEADDR; the separate private-runner correction uses the same reuse behavior as the server. Original runner and first failure are preserved. Product and pinned harness remain unchanged; the passing component suite is not repeated. The follow-up full-app invocation passed and the owned fixture server terminated. C0 compared all 2,331 archive hashes with its three validation manifests; they match.

The Node output exposed file outcomes only. An intentionally failing separate `node:test` sentinel correctly returned exit 1 in the same environment. This supports failure propagation for that sentinel and does not supply an invented case count.

The API/browser harness uses real dashboard routes and request/receipt code with synthetic observations, candidate solver results, maps and Nav2/ROS behavior. It separately verifies omitted request bounds, server provenance, unchanged explicit-bounds support, a representative inside the server limit with another member outside, and exact explicit confirmation/stop dispatch. A successful match request is not convergence or sustained localization readiness. The full app sent one proposal, one geometry confirmation, one exact observation stop, one mock Nav2 start, one explicit INITIAL POSE and one match request; no goal was sent. The preparation readback reached `MATCH_ARMED`. The later generic diagnostic read returned `OUTCOME_UNKNOWN / HANDOFF_MATCH_CURRENT_UNCONFIRMED`, which is preserved separately. That collector calls status without the current health sample supplied by the preparation API; these are non-atomic synthetic reads, not evidence of persistent matching or operational readiness.

## Role commits and limits

| Owner | Commit | Change |
| --- | --- | --- |
| C1.2 | `0ca5f218c06e4159220c938dd9cb86db37065563` | Preserve unavailable UI health metrics |
| C1.2 | `191c481a2d2eb00d731b00c7cd08ebe9ba4f068b` | Hide metrics for actually inactive sessions |
| C1.1 | `5dc9911ab5a662a184fc254184870a6f052363b3` | Preserve unknown public counters |
| C1.1 | `69e52b45773c3262c91d17928daab934bd756104` | Optional-bounds API, selection and handoff provenance |
| C1.2 | `c83ba7263401ac6f626c1bf215c38eb53d740715` | Bounds-free draft UI and proof validation |
| C1.1 | `ea03bd42964f10ee9ce57c19c6f230c3bf01bebf` | Preserve missing callback reports and strict provided types |
| C1.2 | `f8fc08003f8aef04e2b5008e8e2352feac519985` | Explain server selection and separate handoff limits |
| C1.3 | `3d9eff1fa399e441b8319734f3f41f3e366029ce` | Actual-API fixture contract and negative-case updates |
| C0 | This report's commit | Combined validation and limits |

At this report commit, remote publication and the new exact-SHA CI result remain pending. Prior CI success applies to its previous commit only.

C1.4 independently reviewed the final source and found no additional blocking issue within the checked scope. A separate C0 review confirmed the two display follow-ups and their validated-proof call boundaries. Neither review substitutes for the integration runs or hardware evidence.

This report covers local software implementation and hardware-free verification. It does not establish a new CI outcome, deployment, live sensor acquisition, actual Nav2/TF application, continuous map correction or physical navigation. It contains no device credentials, private coordinates, raw maps or point clouds. Existing URDF rendering and extension branches were not changed. Field operations and their separate private evidence remain outside this software report.
