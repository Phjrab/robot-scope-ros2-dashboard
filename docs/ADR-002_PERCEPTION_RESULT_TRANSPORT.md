# ADR-002: fixed HTTP pull for shadow-perception results

Status: accepted for WP04; hardware path remains `BLOCKED`.

## Context

Read-only inventory on 2026-08-30 found ROS 2 Foxy/Python 3.8 on the Go2-mounted
Jetson and ROS 2 Humble/Python 3.10 on the external Orin. Both hosts have
CycloneDDS and Fast DDS RMW packages, but the repository and installed systems
have no exact WP04 custom message package and no recorded Foxy-to-Humble typed
message hardware test. Common middleware availability alone is not evidence
that this result contract is compatible or isolated.

## Decision

Use server-to-server HTTP pull with all routing fixed by administrator-owned
configuration:

- robot-side bind: one locally assigned private IPv4 and port 8092;
- peer: one exact external-Orin private IPv4;
- path: `GET /api/v1/perception/snapshot` only;
- response: JSON with a 64 KiB limit and explicit content length;
- dashboard source: one exact private IPv4, port and local model policy;
- no request body, mutation, arbitrary URL, arbitrary ROS topic, shell command,
  credential, control key, lease or command publisher.

The robot-side peer check and private network are exposure reduction, not
cryptographic authentication. Deployment is limited to the trusted management
LAN. A later authenticated transport requires a separate threat model and must
not reuse the control-bridge signing key.

## Clock handling

Capture, inference start/completion and snapshot time use the robot kernel's
monotonic domain. The external Orin validates their ordering and robot-relative
freshness against `server_monotonic`, then records its own receive monotonic
time. It never subtracts one host's monotonic value from the other. Therefore
`clock_domain_verified=false` remains visible until a separately measured clock
contract exists.

The receiver derives `input_age_s` only from robot-domain
`server_monotonic - capture_timestamp`, then ages that value using its own
receive-domain elapsed time. It never subtracts a robot timestamp from an
external-Orin timestamp. A source frame older than the fixed 1.5-second input
limit is rejected even if inference completed recently.

Each result also carries a sidecar-monotonic result `sequence` plus the exact
relay `source_sequence` and `source_epoch`. The result sequence remains
monotonic across relay reconnects; the source pair preserves traceability to
the encoded frame and identifies relay-process restarts.

## Rejected alternatives

- Typed ROS 2/DDS: preferred only after the exact interface is deployed and
  Foxy/Humble hardware interoperability is recorded. That evidence is absent.
- Generic topic relay: rejected because it widens data and mutation surface.
- Browser-to-robot fetch: rejected because it exposes robot routing to clients
  and prevents the application runtime from owning validation and history.
- Push/mutation API: rejected because WP04 requires observation only.

## Consequences

The bridge is deliberately narrow and easy to disable, but it adds polling and
does not provide cryptographic peer identity. The dashboard treats duplicates,
unknown models and stale results as non-live and retains only 120 validated
history entries. Result data never feeds control or navigation.
