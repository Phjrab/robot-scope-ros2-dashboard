"""Read-only real C1 HTTP, using the pinned C1 stdlib transport (no httpx2)."""


def http_snapshot(service):
    from fastapi import FastAPI, HTTPException, Request
    from robot_dashboard.expansion_services.router import create_router
    from tests.expansion_services.http_client import TestClient

    async def authorize(request: Request):
        if request.headers.get('x-i0-diagnostic-fixture') != 'synthetic-only':
            raise HTTPException(401, 'fixture authorization required')

    def origin(request):
        raise AssertionError('read-only diagnostic cannot mutate')

    app = FastAPI()
    app.include_router(create_router(None, None, service, None,
                                    authorize=authorize, require_origin=origin))
    with TestClient(app) as client:
        assert client.get('/api/v1/extensions/scene/snapshot').status_code == 401
        response = client.get('/api/v1/extensions/scene/snapshot',
                              headers={'x-i0-diagnostic-fixture': 'synthetic-only'})
        assert response.status_code == 200, response.text
        return response.text
