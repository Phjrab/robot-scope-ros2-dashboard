# Route Planner destination start

## Observed production blocker

The live Route Planner page showed `MAP — / GRAPH —` and an empty start
selector. The graph API returned `configured=false, graph=null`. Annotation
reads for `map_20260911_152807`, `map_20260911_124030_edited`, and
`map_20260911_111611_edited` all returned empty points and polygons.
No live order, map, graph, guidance, or robot state was mutated by this audit.

## Change

The selector exposes COEX, Whimoon, Gangnam Police, and GTX Site even before
graph setup. It reports an unset start or missing graph/location explicitly.
Existing START nodes remain supported. Each venue resolves to one destination
dock, or one approach when there is no dock; ambiguous locations remain blocked.
The selected venue survives polling and graph disappearance. Recommendation
requests use the resolved graph node ID and existing revision-pinned optimizer.
No coordinates or edges are inferred from venue names.

## Validation and remaining input

JavaScript unit tests: 291 passed. Route Planner browser tests: 6 passed,
including destination selection, the recommendation request and cards, and
the missing-graph state. A Python optimizer regression verifies departure
from a delivery node, pickup visits, and return delivery. Browser recommendation
cards use the isolated mock backend; this is not live venue route acceptance.

Live recommendation requires an operator-selected map, the four delivery and
three restaurant locations, and their validated connecting paths. These are
absent from the inspected production state. Production deployment is separate
from this software change.
