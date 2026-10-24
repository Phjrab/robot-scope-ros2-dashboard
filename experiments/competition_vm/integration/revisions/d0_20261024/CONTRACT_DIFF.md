# D0 experimental adapter boundary, 2026-10-24

LOCAL-ONLY. Source base main@7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a.
No production/schema/UI/API/CI changes, native transport, robot contact, or deployment.

## Time and transport
- Receiver receipt TTL remains 0.25 s, not raised to the mission fixture observation-gap allowance of 0.5 s.
- The independently configured source maximum age is 0.25 s. At evaluation, source age plus receiver-local elapsed time must fit that budget. No subtraction of monotonic clocks from different hosts is used; source_stamp_ns is only an ordering token.
- Continuous stop evidence gap is a lifecycle rule (0.5 s), never permission for a 0.5-s-old motion constraint. The lifecycle/adapter must be ticked independently if sensing is slower; expired constraints stop movement.
- Existing `ConstraintAdapter.ingest` accepts source_age_s, producer_epoch, source_sequence, source_stamp_ns as a local envelope. Receiver sequence remains separate. Duplicate or reversed source sequence/stamp revokes previous permission even if receiver sequence is new.
- Missing envelope parameters retain the historical receiver-local in-process API for compatibility. This is NOT a network adapter: external inputs must supply verified source envelope and bind producer identity before calling it. Owner allowlisting is not authentication.
- A producer epoch change permanently closes the adapter for that session, retires the old and unexpected epochs, and requires a new mission generation and adapter. No automatic re-arm or producer restart success is claimed. Restart persistence and authentication remain C1/C2 responsibilities.
- `close()` is terminal for the current adapter. `bind_goal` binds command goal identity and requires a strictly increasing generation on a changed goal. Rebinding drops previous releases. A goal bind is not an action ACK and does not submit a goal.

## Canonical contract differences (proposals only)
The canonical competition-evidence.v0.1 includes run/step/goal/generation, producer epoch/sequence, source age, cancel_ack, hold_ack and body_motion_status. These fields are preserved in meaning. However the VM StopInput has no goal identity, precise hold request correlation, exit acceptance identity, or trusted physical-departure observer. Lifecycle events and observed goal identity are local adapter arguments, NOT additions to canonical runtime enums or schema.

The fixture `current_generation_only` validity must not be copied as a live freshness guarantee. C1 should build one clock-aware receiver envelope boundary, map fields explicitly, retain terminal/cancel/hold/exit request correlation, and reject unsupported evidence. A fixture mode string change cannot activate a native adapter. SDK receipt or goal send is not physical stop, movement or departure evidence. Map transform is null and route remains DRAFT.

## Safe adoption order for C1/C2
1. Apply D0 changed files only to the four authorized VM module directories after checking base hashes. Retain old results/fixtures as immutable evidence.
2. Run original and D0 unit/replay/integration suites on the target checkout. Use the actual lifecycle output in the revised smoke path, not direct historical StopGoFSM APPROACH constraints.
3. Implement authenticated clock-aware receiver mapping and explicit action/hold request correlation in C1/C2 scope. Use a fresh mission generation on restart, and new exit goal identity/generation before any motion permission.
4. Qualify physical feet/stop/departure and pose/path freshness separately. Synthetic observations below are not those qualifications.
5. Native ROS and robot deployment remain NOT_RUN and require a separate authorized workflow. Do not enable via a mode toggle.

A matching HOLD ACK is a terminal action event, not a heartbeat: it remains acknowledged for the current session after arrival validation and request correlation. It does not keep stop evidence fresh. Physical stop/feet/pose observations must continue within their own source-age and gap rules. A delayed ACK is rejected using source age plus receiver residence, separately from request ordering. Before departure a retained RELEASE expires with the oldest of pose, observation and GREEN evidence; after committed departure GREEN is no longer an eligibility dependency, but pose/observation freshness and collision safety remain mandatory.
