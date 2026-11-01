"""Synthetic preparation GET for browser contract tests; no robot or ROS access."""
import asyncio
import copy
import json
import sys

from fastapi import FastAPI

from robot_dashboard.api.routers.operational_navigation import router
from robot_dashboard.application.runtime import ApplicationRuntime
from test_navigation_preparation_inputs import fixture


async def response(case, selected):
    manager, session, agent, state, _ = fixture()
    state['selected'].update(selected)
    state['pair'].update(generation=selected['generation'],
                         localization_3d=selected['localization_3d'],
                         navigation_2d=selected['navigation_2d'])
    manager.preparation_snapshot = lambda: copy.deepcopy(state)
    manager.preparation_execution = lambda: None
    if case == 'missing_receipt':
        agent.pose['observation']['received_monotonic_s'] = None
    elif case == 'source_changed':
        def changed():
            agent.cloud['observation']['publisher_epoch'] = '9' * 32
            return copy.deepcopy(state)
        manager.status = changed
    elif case == 'subscription_missing':
        agent.pose['observation']['observer_id'] = None
    elif case == 'bad_units':
        agent.cloud['units'] = 'mm'
    elif case == 'unknown_states':
        agent.pose['state'] = 'initializing'
        agent.cloud['observation']['subscription_evidence']['graph']['state'] = 'unresolved'
    elif case != 'success':
        raise ValueError('Unknown synthetic case')
    runtime = ApplicationRuntime()
    runtime.operational_navigation = manager
    runtime.fastlio_observation = session
    runtime.agent = agent
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router)
    messages = []

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message):
        messages.append(message)

    path = '/api/v1/navigation/operational-3d/preparation-inputs'
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
             'query_string': b'', 'root_path': '', 'headers': [(b'host', b'test')],
             'server': ('test', 80), 'client': ('test', 1)}
    # Exercise the actual ASGI route and asyncio.to_thread, not an inline substitute.
    await app(scope, receive, send)
    assert messages[0]['status'] == 200
    assert (b'cache-control', b'no-store') in messages[0]['headers']
    return json.loads(b''.join(message.get('body', b'') for message in messages[1:]))


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(asyncio.run(response(request['case'], request['selected']))))
