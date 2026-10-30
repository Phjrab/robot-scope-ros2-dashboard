# C1 map-service errors — additive consumer contract, 2026-10-30

No C2 source change is included. C2's host request transport can consume the
following additive fields; existing success bodies and HTTP statuses stay intact.

## Synchronous service failure

Example: an exported merged map and one of its original sources are selected
together. The actual catalogue DAG check still rejects the request before a job
is created. HTTP **409**, JSON:

```json
{
  "detail": "Selected maps share original sources and cannot be merged together.",
  "error": {
    "code": "ANCESTRY_OVERLAP",
    "message": "Selected maps share original sources and cannot be merged together."
  }
}
```

`detail` remains a string and equals `error.message`, so transports already
displaying a string detail show the specific reason. Do not compare message text
or parse exception names for logic. Prefer `error.code`; display `error.message`
as plain text, with string `detail` as the legacy fallback. Unknown codes must
remain failures rather than permitting a retry/apply implicitly.

| HTTP | Code | Meaning / minimum consumer behavior |
|---|---|---|
| 409 | `ANCESTRY_OVERLAP` | Selected inputs share original source ancestry. Change the selection; do not repeatedly solve the same pair. |
| 409 | `INVALID_PROVENANCE` | Missing/conflicting/cyclic/bounded DAG is invalid. Refresh/review the catalogue. |
| 409 | `STALE_SOURCE_REVISION` | Pinned source revision changed. Refresh and solve again. |
| 409 | `SOURCE_IDENTITY_MISMATCH` | Resolver asset/descriptor or solver result identity differs from its pins. Do not apply. |
| 409 | `SOURCE_CONTENT_CHANGED` | Source checksum or private worker snapshot changed. Refresh and solve again. |
| 409 | `SOURCE_DESCRIPTOR_CHANGED` | Other pinned metadata changed. Refresh and solve again. |
| 409 | `STALE_PROPOSAL_REVISION` | Review/save refers to an older proposal revision. Refresh the job; review explicitly. |
| 409 | `REQUEST_CONFLICT` | Changed idempotency request, invalid job state, immutable export or other existing conflict. |
| 429 | `SERVICE_BUSY` | Bounded worker/queue/history or closed-manager rejection. |
| 404 | `NOT_FOUND` | Requested candidate is missing. |
| 422 | `INVALID_CONTRACT` | Candidate violates the existing contract. |
| 503 | `STORAGE_UNAVAILABLE` | Internal I/O unavailable. No private exception text is returned. |
| 500 | `INTERNAL_ERROR` | Unexpected synchronous service failure, with a fixed safe message. |

The wrapper applies to service calls, including list/preview/asset error paths;
errors are never wrapped inside a successful `sources`/`exports` envelope.
Authentication/origin callbacks and request-body validation are unchanged and
may still return their original FastAPI error shapes. Consumers must not assume
every 401/403/413/415/422 response has `error.code`.

## Asynchronous job failure

Enqueue remains HTTP 202. Polling a failed job remains HTTP 200 with `state=FAILED`.
Existing `error` (exception type name) remains for compatibility. The new
`error_detail` is null until failure, then contains the same safe `{code,message}`
shape. Unexpected worker failures use `JOB_FAILED`; known conflict/I/O/contract
causes retain their specific code. No failed worker result becomes a proposal.

Minimum C2 change, by C2's owner: in `c1_ports.js` job-status normalization, prefer
`raw.error_detail?.message` for the displayed reason and retain
`raw.error_detail?.code` as diagnostic metadata; fall back to `raw.error`/state.
The host request wrapper should retain HTTP `error.code` and use the safe message.
No UI, request authorization, automatic retry, acceptance or save policy change
is requested by C1. Existing C2 real HTTP solve/review/save passes unchanged.

## Evidence and safety

`tests/expansion_services/test_errors.py` exercises real C1 worker, BundleStore
and loopback HTTP. Its identity solver is explicitly a plumbing fixture; injected
I/O/worker failures are fault tests. `current_composition.py` separately checks
the ancestry error using an actual D1 solve saved through actual C2 HTTP ports.
No path, bearer, arbitrary exception string or traceback is interpolated into
the new public messages. No DAG acceptance, source hashing, coordinate,
provenance, buffer or storage policy changed.
