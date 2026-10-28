"""Global Nav2 STOP must run even when a mission cannot reconcile its goal."""
from .mission_coordinator import MissionConflict, MissionError


async def stop_navigation_with_mission(mission, navigation):
    mission_error = None
    if mission is not None and mission.blocks_navigation_goal():
        try:
            await mission.abort_active(reason='navigation_stop')
        except MissionError as exc:
            # Keep the mission fence, but never let uncertain goal ownership
            # prevent the existing global process/lease cleanup.
            mission_error = exc
    result = await navigation.stop()
    if mission_error is not None:
        raise MissionConflict(
            f'Nav2 stop requested; mission cleanup unresolved: {mission_error}'
        ) from mission_error
    return result
