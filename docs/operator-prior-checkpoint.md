# Operator-prior candidate selection checkpoint

This checkpoint adds an optional operator-provided map-frame position, heading,
and uncertainty to navigation initialization. A successful selection is
conditional on that input and on the retained hypotheses; it is not a claim of
global uniqueness or measured localization accuracy. The original observation
quality and ambiguity remain visible. Requests without a prior retain the
existing proposal and handoff path.

Confirmation requires an explicit conditional acknowledgment and verifies both
the operator's bounds and the existing handoff distance limits against a fresh
propagated pose. The subsequent initial pose must satisfy both limits as well.
The existing session, source, calibration, expiry and stop-receipt checks remain
required. This change does not issue motion, localization, or navigation
commands automatically.

## Known limitation

The reviewed backend can retain several candidates marked as duplicates of the
same hypothesis. This checkpoint compares every retained candidate separately,
so such results can be rejected as multiple matches even when their poses are
near each other. Reusing the backend's duplicate classification safely remains
unresolved, including candidates at prior boundaries and candidates differing
in height or tilt. Do not interpret rejection as proof that the physical
location is ambiguous, or a successful selection as proof of absolute accuracy.

Verification so far uses synthetic inputs and offline tests. Integration with
the operator interface, field measurements, hardware operation, and deployment
require separate verification and authorization.

## Checkpoint verification

The targeted navigation proposal, handoff, and prior-selection Python suites
passed 68 tests; JavaScript unit tests passed 80 tests. A full Python discovery
run was started but did not complete: it was interrupted after making no
visible progress in the first competition endurance test. Full-suite coverage
therefore remains unverified. No hardware or field tests were run.
