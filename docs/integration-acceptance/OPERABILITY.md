# Stage35 operability and provenance

> Current scope through40: the user explicitly extended the completed stage36 snapshot. Candidate863682e was deployed; initialpose1 and180s stationary observation were completed and owned resources cleaned. Live acceptance remains partial/false. See [STAGE40_VALIDATION.json](STAGE40_VALIDATION.json), [DEPLOYMENT_ACCEPTANCE.md](DEPLOYMENT_ACCEPTANCE.md) and [LOCALIZATION_LIVE_ACCEPTANCE.md](LOCALIZATION_LIVE_ACCEPTANCE.md). Earlier stop-after36/no-deployment statements below describe the historical software snapshot.41–43 remain NOT_RUN.

No startup/deployed-artifact manifest proving loaded source/config identity exists
for new managed runs. `source_sha`/`runtime_sha` remain null and provenance remains
unavailable; the local Git HEAD and device checkout are not substituted. Existing
history is never backfilled. New planner results preserve exact goal UUID, fixed
action/server GID, inherited ROS/config hashes, request start kind and original
native path headers/xyz/quaternion in read-only preview responses. Dispatch history
keeps compact native provenance plus a digest of the original path to respect the
existing512KiB private-store bound; it does not claim that digest can recreate raw
poses. Auth tokens, environment contents and DDS XML bytes are not exported.

Preview reserves the existing resource gate under the shared lock, waits outside
it, then rechecks definition/map/annotation/route/context and live pose freshness.
MS/legacy mutation and concurrent mission admission are blocked by the reservation.
Uncertain native cleanup retains the resource fence, including repeated HTTP
cancellation. No long native wait or ROS readback runs under that shared lock.

`live_plan` stays unavailable (`NAV2_RUNTIME_PATH_WITH_PROVENANCE_UNAVAILABLE`).
Bare Nav2 Path messages have no verified goal binding. Dispatch planning, current
controller/global replans, authoring geometry and observed pose trajectory remain
separate. ETA is null; no waypoint count/straight line is relabelled as runtime ETA.

Retention remains definitions64/runs32/requests256/JSON512KiB/events200/trajectory256.
There is no destructive maintenance API or implicit eviction. A safe manual archive
procedure is: select only inactive terminal runs; use the existing token-free,
`executable=false` run export endpoint; save into a separate private archive;
record definition/run revisions, export length and SHA256; reread/validate the
archive before considering any separate cleanup. Keep every active, paused,
canceling, uncertain run and all needed idempotency receipts. Exporting alone does
not free capacity. Receipt deletion needs a versioned namespace/tombstone design
to prevent delayed request replay; that software unit remains open. Do not edit
live store JSON or increase caps as a workaround. Current source does not delete,
migrate, prune or archive the user's operational data.

Existing saturation/audit failure tests and integration regressions retain STOP,
pause, abort and owned cleanup despite durable storage failure. An uncertain cancel
keeps ownership and blocks another dispatch. Stored schema remains mission-plans.v1;
new fields are additive result/provenance/context evidence. Previous strict readers
and rollback candidates must be tested against a copied fixture before use.

Rollback is separate by layer: normally revert the focused source commit on main
without history rewriting; preserve private data and exports; review compatibility
before changing readers; deployment/service rollback requires a separate stage40
manifest and approval. No data restoration may recreate lease/ARM/active goals.
This session stops after36; no background device polling or scheduled follow-up.
