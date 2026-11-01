"""Actual authenticated loopback TCP HTTP, using the adapter's C1 SceneView."""
from contextlib import contextmanager
import socket
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request as URLRequest, urlopen


@contextmanager
def server(scene):
    from fastapi import FastAPI, HTTPException, Request
    import uvicorn
    from robot_dashboard.expansion_services.router import create_router
    async def authorize(request: Request):
        if request.headers.get('authorization') != 'Bearer synthetic-review':
            raise HTTPException(401,'synthetic review authorization required')
    def origin(request):
        raise HTTPException(403,'read-only review')
    app=FastAPI()
    app.include_router(create_router(None,None,scene,None,authorize=authorize,require_origin=origin))
    sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen(8)
    runner=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',log_level='error',lifespan='off'))
    thread=threading.Thread(target=runner.run,kwargs={'sockets':[sock]},daemon=True); thread.start()
    try:
        deadline=time.monotonic()+5
        while not runner.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.01)
        if not runner.started: raise RuntimeError('HTTP_START_FAILED')
        yield f'http://127.0.0.1:{sock.getsockname()[1]}/api/v1/extensions/scene/snapshot'
    finally:
        runner.should_exit=True; thread.join(5); sock.close()
        if thread.is_alive(): raise RuntimeError('HTTP_SHUTDOWN_FAILED')


def fetch(url):
    try:
        urlopen(url,timeout=3)
        raise AssertionError('unauthorized HTTP accepted')
    except HTTPError as exc:
        assert exc.code==401
    request=URLRequest(url,headers={'Authorization':'Bearer synthetic-review'})
    with urlopen(request,timeout=3) as response:
        assert response.status==200
        return response.read()
