"""Finite generated scene certificates for the separately pinned current cores."""
from copy import deepcopy
from dataclasses import replace

from . import fixtures
from robot_dashboard.expansion_runtime.canonical_ports import CanonicalCorePorts


def setup(**kwargs):
    runtime, packet, state, clock = fixtures.setup(**kwargs)
    runtime.ports = CanonicalCorePorts.from_installed(runtime.ports.geometry)
    return runtime, packet, state, clock


def coverage(runtime, packet, **kwargs):
    attestation = fixtures.coverage(runtime, packet, **kwargs)
    evidence = {k: deepcopy(packet.meta[k]) for k in
                ('evidence_kind', 'source_epoch', 'clock_domain', 'frame_key', 'map_binding')}
    evidence.update(kind='GENERATED_CLOSED_SCENE_VOLUME', complete_for_motion=True,
        source_refs=[dict(generator='FINITE_SYNTHETIC_SCENE_C4', sequence=packet.meta['sequence'])],
        horizon_s=kwargs.get('horizon', .1), volume_min=[-10., -10., -10.], volume_max=[10., 10., 10.],
        valid_from_ns=packet.meta['stamp_ns'], valid_until_ns=str(int(packet.meta['stamp_ns'])+250_000_000))
    return replace(attestation, evidence=evidence)


def run(runtime, packet, state, *, complete=False, **kwargs):
    options = dict(command_sequence=1, velocity=(.1, 0., 0.), authority_present=True)
    options.update(kwargs)
    if complete:
        options['coverage'] = coverage(runtime, packet, command_sequence=options['command_sequence'],
                                       velocity=options['velocity'], horizon=options.get('horizon_s', .1))
    return runtime.process(packet, state, **options)


def scene(runtime, result, clock, *, version='0.2'):
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    service = SceneSnapshotService(runtime.context.map_binding, host_clock_id=runtime.context.host_clock_id,
                                   clock=clock, schema_version=version)
    runtime.ports.ingest_scene(service, result, legacy_profile=version == '0.1')
    return service


def http_snapshot(service):
    """Actual C1 router through ASGI HTTP, synthetic host authorization only."""
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient
    from robot_dashboard.expansion_services.router import create_router

    async def authorize(request: Request):
        if request.headers.get('authorization') != 'Bearer synthetic-fixture':
            raise HTTPException(401, 'fixture authorization required')

    def origin(request):
        raise AssertionError('read-only GET cannot mutate')

    app = FastAPI()
    app.include_router(create_router(None, None, service, None, authorize=authorize, require_origin=origin))
    with TestClient(app) as client:
        assert client.get('/api/v1/extensions/scene/snapshot').status_code == 401
        response = client.get('/api/v1/extensions/scene/snapshot', headers={'authorization': 'Bearer synthetic-fixture'})
        assert response.status_code == 200, response.text
        return response.text
