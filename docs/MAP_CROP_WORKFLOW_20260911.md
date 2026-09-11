# Non-destructive 2D map crop

Saved Maps now exposes a rectangular crop workflow for managed P5/trinary
occupancy maps. It is intended for cases where LiDAR observations outside the
competition field make the useful field occupy only a small part of the 2D
map.

The operator selects a managed 2D map, presses **CROP AREA**, drags a rectangle
around the competition field, reviews the resulting cell and metric size, and
saves a named copy. The source YAML, PGM, PCD and annotations are not modified.
The copy receives a new map identity and revision; annotations must be created
against that exact copy.

The server treats crop coordinates as half-open occupancy-grid cell bounds.
It validates exact source revision, strict integer fields, ordered in-bounds
coordinates, a minimum 2 by 2 result, and a proper reduction from the source.
It maps bottom-left occupancy cells to top-left PGM rows and translates the YAML
origin by the cropped cell offset, including the source origin yaw. Map-family
lineage is retained with the new dimensions, origin, map ID and revision.

Publication uses the existing private staging, source signature recheck,
atomic pair publication and rollback path. Existing lifecycle, Navigation and
map-operation interlocks remain unchanged. No mapping, localization, Nav2,
control or robot motion operation is part of crop creation.

This feature crops the Nav2/Route Planner 2D occupancy map. It deliberately
does not rewrite or filter the source 3D PCD; a separate bounded 3D crop would
need its own point/frame/lineage contract.
