"""Observation APIs share composition, never robot control ownership."""
from fastapi import APIRouter
from .global_observation import router as global_router
from .sensor_tracking import router as sensor_router
from .fastlio_observation import router as fastlio_router
from .observation_presets import router as presets_router
from .course_regions import router as course_router

router = APIRouter()
router.include_router(global_router)
router.include_router(sensor_router)
router.include_router(fastlio_router)
router.include_router(presets_router)
router.include_router(course_router)
