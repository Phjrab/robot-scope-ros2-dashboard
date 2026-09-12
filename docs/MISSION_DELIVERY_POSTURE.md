# Delivery arrival posture (configuration only)

Each mission waypoint can store `arrival_action: "none" | "sit_then_rise"`.
Existing missions default to `none`. The panel configures each visit separately,
including repeated visits to the same annotation. Map and annotation pins and
their validation remain mandatory.

The requested sequence is Go2 `sit` (1009), followed by `rise_sit` (1010).
`stand_down` is a prone posture and is not a substitute for sitting.

This change implements configuration, persistence, and display only. A mission
containing this action cannot start or dispatch goals. No posture executor is
wired in. This is a preparation state, not a verified automatic delivery feature.
The UI labels it as pending verification; API callers receive a mission conflict.

Before enabling automatic execution, implement and validate:

- Exclusive navigation/control ownership transfer after the owned goal succeeds.
- Confirmed stationary state before sitting, and actual posture completion
  feedback for both sit and rise. Command acceptance is not completion.
- A bounded failure state for missing/rejected commands or feedback; never use
  an elapsed timer alone to mark delivery completed or resume navigation.
- Cancellation, E-stop, manual takeover, restart recovery, and no automatic
  replay of partially completed posture actions.
- Completion counting only after the rise is confirmed, including the final
  waypoint; preserve visit ordering and map/annotation revision validation.
- Unit coverage and browser checks, followed by separately authorized field
  verification. The user deferred verification for this change.

The initial draft was untested. On 2026-09-12 the user authorized software
verification and dashboard deployment. Tests now cover persisted visit-specific
actions, legacy defaults, unknown-action rejection, and rejection before any
navigation ownership or goal is created. Browser coverage checks reordering
repeated visits and the disabled Start control after saving.

This software verification does not qualify physical sit/rise execution. The
completion-aware executor above remains unimplemented and the execution gate
remains closed. See `UI_SPATIAL_DELIVERY_20260912.md` for release verification.
