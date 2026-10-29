"""Declared/active plugin applicability, independent of enforcement admission."""


def declaration_names(response):
    names = response.result.names
    if len(names) > 4096 or any(not isinstance(n, str) or not n or len(n) > 512 for n in names):
        raise ValueError('POLICY_PARTIAL_READBACK')
    if len(names) != len(set(names)):
        raise ValueError('POLICY_PARTIAL_READBACK')
    return frozenset(names)


def not_applicable(node, key, values):
    if node.endswith('_costmap'):
        plugins, filters = values.get('plugins'), values.get('filters')
        if not isinstance(plugins, list) or not isinstance(filters, list):
            return False
        prefix = key.split('.')[0]
        if prefix in {'static_layer', 'keepout_filter', 'policy_layer', 'inflation_layer'}:
            return prefix not in plugins + filters
    if node == '/controller_server' and key == 'progress_checker.required_movement_angle':
        return values.get('progress_checker.plugin') == 'nav2_controller::SimpleProgressChecker'
    return False


def complete_parameters(node, wanted, observed):
    values = dict(observed)
    applicability, missing = {}, []
    for key in wanted:
        if not_applicable(node, key, values):
            # Retain any declared value for evidence, but do not attest its use.
            values.setdefault(key, None)
            applicability[key] = 'NOT_APPLICABLE'
        elif key not in values or values[key] is None:
            values.setdefault(key, None)
            applicability[key] = 'MISSING_REQUIRED'
            missing.append(key)
        else:
            applicability[key] = 'OBSERVED'
    return values, applicability, missing
