# Independent software integration matrix

Validated on 2026-11-02 against frozen snapshot `C0-INTEGRATED-OFFLINE-20261102-01` with `PRIOR_REQUIRE_GROUPING=1`. The component matrix and full-app scenario each ran once, in that order. All 2,323 source paths/hashes and the Git index contents were unchanged across execution. Documentation was updated afterward.

All inputs are synthetic. “Actual backend” means product ASGI/coordinator/manager execution, not hardware or an external solver process. The component injects a synthetic draft getter; the full app uses actual canvas pointer handling.

## Component: 31 PASS / 0 FAIL

| Case identifier | Verified behavior | Result |
|---|---|---|
| `missing_prior_draft_or_bounds_never_posts` | Missing draft, XY/yaw bounds or stationary acknowledgement keeps proposal POST count at zero | PASS |
| `prior_wire_exact_and_one_conditional` | Exact pose/map/units/bounds; product proof; no seed before explicit confirm; one synthetic solver call; executor separation; exact-session stop receipt | PASS |
| `unique_global_inside_still_conditional` | Original ambiguity false preserved; complete conditional proof; nonambiguous UI wording | PASS |
| `unique_global_outside_prior_rejected` | Originally nonambiguous result outside the prior returns `PRIOR_NO_MATCH` | PASS |
| `missing-proof_cannot_show_conditional_ready` | Stripped server proof cannot enable preview/confirmation | PASS |
| `missing-original-ambiguity_cannot_show_conditional_ready` | Missing original ambiguity field cannot enable preview/confirmation | PASS |
| `confirm_rejects_missing_ack_and_client_proof` | Missing explicit acknowledgement returns 409; client-supplied proof returns 422 | PASS |
| `confirm_response_lost_and_status_failure_no_retry` | Successful server confirm with lost response; failed readback; no automatic retry; reload recovery and explicit exact-session stop | PASS |
| `ambiguous_zero_does_not_confirm` | No matching candidate: no geometry or confirm | PASS |
| `ambiguous_multiple_does_not_confirm` | Multiple matches, including a z-only difference: no geometry or confirm | PASS |
| `ambiguous_bad-quality_does_not_confirm` | Invalid candidate quality is rejected | PASS |
| `ambiguous_truncated_does_not_confirm` | Deliberately omitted synthetic attempt cannot obtain valid retention metadata | PASS |
| `ambiguous_unknown-quality_does_not_confirm` | Unknown quality gate is rejected | PASS |
| `ambiguous_missing-metadata_does_not_confirm` | Missing retention metadata is rejected | PASS |
| `ambiguous_tampered-metadata_does_not_confirm` | Altered retention digest is rejected | PASS |
| `transient_status_preserves_unconfirmed_draft_no_post` | Read failure preserves draft values as unusable; no automatic action | PASS |
| `draft_change_clears_ack_and_no_auto_post` | Changed draft clears acknowledgement and blocks submission | PASS |
| `duplicate_id_changed_prior_rejected` | Reusing a request ID with a changed prior conflicts without another synthetic solver call | PASS |
| `invalidate_source-epoch` | Changed source epoch invalidates proposal | PASS |
| `invalidate_session` | Changed observation session invalidates proposal | PASS |
| `invalidate_generation` | Changed bundle generation invalidates proposal | PASS |
| `invalidate_map-revision` | Changed map revision invalidates proposal | PASS |
| `invalidate_calibration` | Changed calibration invalidates proposal | PASS |
| `invalidate_expire-prior` | Expired prior invalidates proposal | PASS |
| `prior_bounds_change_invalidates_confirmation` | Changed bounds clear acknowledgement and invalidate confirmation | PASS |
| `legacy_no_prior_backend_preserved` | Existing no-prior API stays available without conditional proof | PASS |
| `wide_prior_does_not_relax_existing_handoff` | A wide prior does not relax the existing 0.25 m / 0.20 rad handoff limits | PASS |
| `grouped_two_members_one_hypothesis_real_confirmation` | Six retained entries, two matching raw members, one verified hypothesis; product proof and server handoff member checks | PASS |
| `grouped_reject_duplicate-bad-marker` | Invalid original duplicate marker is rejected | PASS |
| `grouped_reject_multiple-roll` | Roll difference beyond duplicate tolerance remains a separate hypothesis and is rejected as multiple matches | PASS |
| `grouped_current_member_drift_blocks_confirm` | Representative remains inside prior but another member drifts outside; current member evidence blocks confirm with 409 | PASS |

The ambiguous and originally nonambiguous passing cases preserve their original boolean and display distinct wording. Both remain conditional on the operator prior. Retained raw-member counts are distinct from matching-hypothesis counts; the original candidate array is not silently reduced.

## Full app: one scenario PASS

These are stages/assertions within one scenario, not additional independent component tests.

| Stage or assertion | Verified behavior | Result |
|---|---|---|
| App mount | Actual index/app.js loads without commands | PASS |
| Canvas draft / stage 1 | Actual pointer drawing creates a local draft; SEND POSE remains disabled; missing prior inputs cause no proposal POST | PASS |
| Draft → actual prior ASGI | UI values reach the real selector; conditional proof and executor evidence are checked | PASS |
| Explicit confirm → explicit stop | Confirmation contains acknowledgement and no client prior/proof; stop POST/dispatch occur once with exact session/start/nonce receipt binding | PASS |
| Explicit mock Nav2 start | No automatic INITIAL POSE or goal; runtime has no accepted initial pose yet | PASS |
| Preserved-draft reconfirmation assertion | Old draft remains visibly unconfirmed, then requires explicit user reconfirmation; no fresh-redraw fallback used | PASS |
| Explicit SEND POSE → receipt | Sent pose equals the original operator draft; actual manager/localizer/receipt waiter accepts it through synthetic transport; matching is not automatically armed | PASS |
| Explicit match | Actual ASGI match route and localizer arm matching; actual preparation readback reports `MATCH_ARMED`; no goal is sent | PASS |

## Evidence boundaries

Actual product code includes the retention metadata producer, selector, proposal/global coordinators, manager, preparation ASGI routes, app/canvas draft handling, localizer reseed/start-matching, and receipt waiters. The executor is real; `asyncio.to_thread` is not replaced.

Synthetic layers include dashboard HTTP/WebSockets, map pixels, sensor observations, solver candidate arrays and trusted execution envelope, ownership, stop service, Nav2 launch, and ROS receipt transport. Attempt/FAILED_RANSAC padding and injected worker-reaped/source-pin fields do not establish external solver execution, process reaping, or verification of real solver files. The product generates the resolution proof.

**NOT RUN:** actual navigation coordinator start, ROS callbacks/publishers, external solver subprocess, Nav2 nodes/TF, registration convergence, device access, and deployment. Final match arming is not successful alignment: localizer ready remained false and estimated pose remained null. Mock readiness/receipts do not measure physical stationarity, position accuracy, or motion safety. HTTP origin checks are not an OS-wide network isolation certification.

Earlier baseline failures, the fixture coordination repair, and the frozen passing runs are separate evidence; their counts are not combined.
