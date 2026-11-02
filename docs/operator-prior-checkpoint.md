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

## Retained duplicate candidates

The reviewed backend can retain several candidates marked as duplicates of the
same hypothesis. Prior-based selection independently verifies those markers by
replaying the pinned backend's original full 3D translation and rotation tests
and first-representative order. It evaluates every retained candidate against
the prior and counts a verified group once only if all members agree on being
inside or outside the prior. A group that straddles either boundary is rejected.
Missing or inconsistent markers, references, and candidate quality are rejected.
The original candidate list, measurements, and ambiguity state remain unchanged.
The proof preserves raw candidate counts, identifies the grouping policy and
every member, and reports each member's height and tilt differences from the
representative. Small differences within the backend's original 3D threshold
are not claims of identical geometry.

At confirmation and handoff creation, every selected group member is
propagated using the same current odometry sample and must remain within the
operator's prior. The sample and member checks are bound to the handoff. After
the observation session stops, those checks describe the confirmation sample;
they do not continuously measure position or prove physical stationarity.

The backend's bounded candidate set does not cover every possible pose. Do not
interpret rejection as proof that the physical location is ambiguous, or a
successful selection as proof of absolute accuracy. Differences in height and
tilt are part of the original 3D duplicate test rather than ignored by a new
planar distance rule.

Verification so far uses synthetic inputs and offline tests. Integration with
the operator interface, field measurements, hardware operation, and deployment
require separate verification and authorization.

## Checkpoint verification

The targeted navigation proposal, handoff, and prior-selection Python suites
passed 68 tests; JavaScript unit tests passed 80 tests. A full Python discovery
run was started but did not complete: it was interrupted after making no
visible progress in the first competition endurance test. Full-suite coverage
therefore remains unverified. No hardware or field tests were run.
