# C1 localhost fixture host

From repository root, run `python -m experiments.expansion_20261029.c1_service_host.host`.
Binds 127.0.0.1:8765 only; prints an ephemeral test bearer. Send Authorization:
Bearer plus that value to every route. Mutations also require application/json
and Origin: http://127.0.0.1:8765. Data is generated in a temporary directory and
removed at exit. OpenAPI is a local inspection aid; no product app is imported.

GET /api/v1/extensions/multimap/sources supplies descriptor pins. Construct a
FusionRequest using expansion_contracts.fixtures.request(descriptors), POST jobs,
poll status, review with expected_proposal_revision and explicit accepted, then
export with the returned revision. This host uses the identity fixture only;
registration quality is NOT_RUN. It has no activation or motion endpoint.

Injected workers run in the single daemon worker, outside the HTTP event loop.
They must honor cancellation/progress and their deadline. A noncooperative worker
retains the sole slot; bounded admission rejects excess requests. Shutdown is
bounded; this is not a sandbox for untrusted solver code. Store roots and
resolver/preview callbacks must be trusted, private, local service-owned data.

Reproducible localhost smoke (temporary generated maps, server shuts down):
`python -m experiments.expansion_20261029.c1_service_host.smoke`.
Default explicit host limits: 16 concurrent HTTP requests, backlog 16; worker
concurrency 1, queue 4, history 32, aggregate read-only source snapshot bytes
256 MiB/job. Export cap 256 MiB/20M points, chunk cap 1 MiB, occupancy <=1M cells.
Scene cap 16 KiB/sample, 80 KiB latest payload total, 16 metadata history entries.
All geometry remains an uninstalled candidate; no observed free is reconstructed.
