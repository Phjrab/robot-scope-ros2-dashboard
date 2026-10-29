"""Small operator adapter; cancellation stays on the existing goal-ID API."""
import re


def cancel_current_goal(api):
    """Read once, pin the current goal, send once. HTTP errors propagate.

    ``api`` is an authenticated operator transport, not supplied by HTTP users.
    A racing new goal is rejected by the existing server instead of retried.
    An accepted request is not a cancellation result or measured stop.
    """
    snapshot = api('GET', '/api/v1/navigation')
    navigation = snapshot.get('navigation', snapshot)
    goal = navigation.get('goal') or {}
    if goal.get('state') not in {'pending', 'active', 'canceling'}:
        return {'requested': False, 'reason': 'NO_ACTIVE_GOAL'}
    goal_id = goal.get('goal_id')
    if not isinstance(goal_id, str) or not re.fullmatch('[0-9a-f]{32}', goal_id):
        raise ValueError('current goal identifier is unavailable')
    response = api('POST', '/api/v1/navigation/cancel', {'goal_id': goal_id})
    return {'requested': True, 'goal_id': goal_id, 'response': response,
            'measured_stop_confirmed': False}
