# Restaurant-parallel food production

User-confirmed rule: each restaurant independently produces one item every
20 seconds, in order-sheet then menu-line order. First items are ready at 20s,
not immediately. Both legacy and grouped server orders use per-restaurant
queues. Catalog revision and recommendation assumptions identify the new policy;
old saved orders require an explicit resave before recommendation generation.
The supplied table's cheese pizza label is used; stable CHEESE_PIZZA ID retained.

Cockpit/shared Route Planner now has an independent advisory food board. It can
use the supplied eight sheets or the current saved order, without overwriting
server orders. The supplied batch totals 31 items: pizza 8 (160s), lunchboxes 13
(260s), drinks 10 (200s). The table's numeric references are retained in rows.
No coordinates or start-place interpretation are inferred from its blank cells.

Operator starts the clock explicitly. Estimated production, next-item countdown,
per-menu estimated uncollected inventory, manual receipt and receipt undo are
displayed. Start time, source snapshot and receipts persist in browser local
storage. This is not server/team synchronization or actual food detection, and
does not complete a Mission delivery. Reset requires a checkbox confirmation.
Invalid restored records do not auto-start; changed current-order revisions and
negative elapsed times suppress estimates. Map STALE and missing schematic
assets do not prevent the supplied-batch board from operating.

No robot, Nav2, Mission, deployment or restart calls are made by this feature.
Existing map/annotation validation, five-item robot capacity and the schematic
manual-prepared-two rules profile are unchanged. The food board is a separate
user-confirmed timing estimate, not an automatic change to schematic approvals.

Verification: full Python suite 1,460 tests OK (one skipped); JS unit suite,
frontend syntax and changed Python lint. Whole-route golden digests intentionally
updated for revised timing/catalog, not for map or navigation behavior.
Local Chromium E2E launch is blocked by macOS MachPort sandbox permissions;
an E2E regression is supplied for CI. In-app browser isolated local harness
verified start, parallel production, receipt persistence and full completion.
Deployment and service restart are not performed.
