"""Combined transport surface for planning and authored route artifacts."""

from fastapi import APIRouter

from .route_planner import router as route_planner_router
from .spatial_routes import router as spatial_routes_router
from .schematic import router as schematic_router


router = APIRouter()
router.include_router(route_planner_router)
router.include_router(spatial_routes_router)
router.include_router(schematic_router)
