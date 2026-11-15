# Initial position review window

The operator-prior and initialization handoff validity window is 300 seconds
(five minutes), increased from 120 seconds to allow time for supervised review.
For a conditional proposal, the window starts when the server accepts the prior
anchor during calculation admission. Calculation time consumes this window.
Confirmation cannot extend the deadline beyond the original prior expiry, and
polling does not renew it. The UI and backend enforce the same upper bound.

This changes the review/start window only. It does not extend the one-second
current-pose freshness check, observation ownership, stop/continuity checks,
source/map/calibration identity checks, 0.25 m / 0.20 rad candidate bounds, or
runtime localization quality limits. Stopped or replaced observation sessions
still invalidate the proposal. A new initialization after expiry requires a
new calculation. An already accepted healthy matching runtime retains its
existing behavior after the initialization deadline.

Regression coverage checks admission at four minutes, expiry at five minutes,
the exact floating-point deadline and its next representable value, and the
browser's conditional-proposal and handoff validation.
