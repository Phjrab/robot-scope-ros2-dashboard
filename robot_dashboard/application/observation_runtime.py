"""Compose the historical global owner and its explicit sensor-only follower."""
from .global_observation import close_global_observation, configure_global_observation
from .sensor_tracking import close_sensor_tracking, configure_sensor_tracking
from .fastlio_observation import configure_fastlio_observation


def configure_observations(runtime):
    configure_global_observation(runtime)
    configure_sensor_tracking(runtime)
    configure_fastlio_observation(runtime)


async def start_observations(runtime):
    if runtime.fastlio_observation is not None:
        await runtime.fastlio_observation.start_monitor()


async def close_observations(runtime, logger):
    if runtime.fastlio_observation is not None:
        try:
            await runtime.fastlio_observation.close()
        except Exception:
            logger.exception("observation service monitor shutdown failed")
    # The follower owns fresh capture slots and must stop before its seed owner.
    await close_sensor_tracking(runtime, logger)
    await close_global_observation(runtime, logger)
