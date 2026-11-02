"""Shared admission policy. Systemd active alone is never an observation proof."""


def bridge_admission_error(runtime, bridge):
    if bridge.get('available') is not True:
        return 'CONTROL_BRIDGE_STATE_UNKNOWN'
    if bridge.get('active_state') == 'inactive':
        return None
    if (bridge.get('available') is not True or bridge.get('active_state') != 'active'
            or bridge.get('sub_state') != 'running'
            or not isinstance(bridge.get('invocation_id'), str)
            or len(bridge['invocation_id']) != 32):
        return 'CONTROL_BRIDGE_STATE_UNKNOWN'
    try:
        return runtime.agent._control_transport.observation_inhibit_preflight()
    except (AttributeError, TypeError, ValueError):
        return 'CONTROL_BRIDGE_INHIBIT_UNSUPPORTED'


def bridge_observation_error(runtime):
    owner = runtime.fastlio_observation
    reason = owner.bridge_safety_error() if hasattr(owner, 'bridge_safety_error') else None
    if reason:
        return reason
    bridge = runtime.lifecycle.control_bridge_lifecycle._read_systemd()
    if bridge.get('available') is not True:
        return 'CONTROL_BRIDGE_STATE_UNKNOWN'
    if bridge.get('active_state') == 'inactive':
        if getattr(owner, '_bridge_context', None) and owner._bridge_context.get('token'):
            return owner._latch_safety('CONTROL_BRIDGE_STATE_CHANGED_DURING_OBSERVATION')
        return None
    context = getattr(owner, '_bridge_context', None)
    if (bridge.get('active_state') != 'active' or bridge.get('sub_state') != 'running'
            or not context or not context.get('token')
            or bridge.get('invocation_id') != context.get('invocation_id')):
        reason = 'CONTROL_BRIDGE_NOT_INACTIVE'
        return owner._latch_safety(reason) if context else reason
    return owner.bridge_safety_error()
