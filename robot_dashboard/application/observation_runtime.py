"""Compose the historical global owner and its explicit sensor-only follower."""
from .global_observation import close_global_observation, configure_global_observation
from .sensor_tracking import close_sensor_tracking, configure_sensor_tracking


def configure_observations(runtime):
    configure_global_observation(runtime)
    configure_sensor_tracking(runtime)


async def close_observations(runtime, logger):
    # The follower owns fresh capture slots and must stop before its seed owner.
    await close_sensor_tracking(runtime, logger)
    await close_global_observation(runtime, logger)
