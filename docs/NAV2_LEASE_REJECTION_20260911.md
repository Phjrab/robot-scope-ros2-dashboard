# Navigation lease rejection, September 11

On external release `030b7f2f3d9eba069b22356982ff21c3040b6fc3`, operator
goal `1eebd305e727246bc36f002b4a2c8b0b` started at approximately
10:21:12 UTC and canceled at 10:21:15 UTC. The recorded reason was
`navigation command rejected: invalid or expired control lease`; no first
nonready health snapshot was recorded for this goal. The controller logged
missed 10 Hz control cycles. Bridge counters showed 41 nonzero requests and a
maximum forward command of 0.035 m/s. These counters do not prove physical
movement. The last read-only inspection showed zero command, inactive lease
and an existing running Nav2 pipeline, which was left untouched.

## Finding

`ControlManager._require_lease()` checks both heartbeat and command expiry
before accepting a new command. A drive gap of at least 0.2 seconds revokes
the lease even if its heartbeat remains fresh. The generic LeaseInvalid
message previously hid which check caused revocation. This is a plausible
explanation for the observed cancellation, not a proven reconstruction:
the historic stop envelope and exact callback gap were not retained.

## Diagnostic correction

Keep the first allowlisted lease-ending stop reason until the next successful
acquisition and append it to LeaseInvalid only when no lease is active.
Output draining and subsequent stop events cannot overwrite that cause.
Wrong tokens against a live new lease retain the generic error. No token or
caller-supplied text is exposed. Timeout, heartbeat, freshness and motion
behavior are unchanged; expired commands still stop and require a new lease.

Regression tests reproduce both expiry inside a new drive request and expiry
in a preceding tick, including output draining, subsequent readiness loss,
and new lease acquisition. Focused control/gateway tests passed 51/51.
This correction improves the next rejection's evidence; it does not claim
to fix controller scheduling or authorize another goal. Deployment and an
operator-coordinated trial remain separate from Git publication.

Full virtual-environment discovery ran 1398 tests successfully (one Linux-only
skip); JavaScript tests passed 293/293. Ruff and diff checks passed. System
Python lacks fastapi/pydantic and reported two import errors. A further shared
temporary-file collision occurred when both discoveries ran concurrently;
the affected saved-map test passed when repeated alone. Future full discovery
runs must be serialized because that test uses a shared temporary filename.
