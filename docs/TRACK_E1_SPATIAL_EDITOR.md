# E1 spatial route editor — software authoring

The existing Route Planner panel now contains a spatial editor. Orders and
recommendations remain in the existing flow. This editor can copy the selected
recommendation's geometry only when its exact occupancy map ID/revision matches.
It does not copy order semantics into a new mission or change the recommendation.

## Implemented

- Actual saved occupancy map loading with an exact, unique D0 family match.
- Existing annotations overlaid; schematic pixels never become ROS coordinates.
- Click/drag drawing, point dragging/deletion, undo, zoom/pan and final heading.
- FLEXIBLE/CORRIDOR/STRICT policy and blocked-behavior authoring. CORRIDOR shows
  its full width as a visual band; this is not an obstacle-free corridor proof.
- Bounded 4,096 poses, current-revision CAS updates, new-copy save, route loading.
- Existing E0 validator runs on save, with violations shown in red. Invalid
  routes remain explicitly invalid authoring drafts, not executable missions.
- Current map-family checks reject stale route loads. Stored validation on load
  is historical; save revalidates against current map and annotations.

On 2026-09-12 the user lifted the software verification and deployment hold.
Focused tests cover rotated-map transforms, exact lineage, final heading,
CAS requests and schematic write rejection. Browser tests cover drawing,
deletion/undo, corridor-policy saving and retaining edits after a CAS rejection.
The existing E0 suite covers segment/footprint/zone validation. This authoring
release does not export or run missions. See `UI_SPATIAL_DELIVERY_20260912.md`.

## Next phases, not implemented here

E2 must connect execution projections to the existing order/stop semantics and
revalidate route/map/annotation pins before creating an execution draft. Geometry
alone cannot stand in for pickup/delivery events or arrival posture completion.

E3 must implement actual Nav2 constraints: route corridor membership, planned
path and observed robot deviation checks, STOP/operator handling, and explicitly
defined replanning boundaries. STRICT requires a supported constrained tracking
path. Sending ordinary goals through the polyline does not enforce either mode.
Both modes remain authoring-only under the E0 backend eligibility contract.

Runtime integration must retain exclusive control ownership, cancellation,
E-stop, freshness limits and restart handling. Later field acceptance is separate
from editor software verification and needs the user's authorization.
