"""Real loopback HTTP test transport, using only declared uvicorn + stdlib.

No Starlette TestClient/httpx/httpx2 optional test dependency is required.
"""

import json as jsonlib
import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import uvicorn


class Response:
    def __init__(self, response):
        self.status_code = response.status
        self.headers = response.headers
        self.content = response.read()
        self.text = self.content.decode("utf-8")

    def json(self):
        return jsonlib.loads(self.content)


class TestClient:
    def __init__(self, app, base_url="http://127.0.0.1"):
        self.app, self.host_header = app, urlsplit(base_url).netloc
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def __enter__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.url = f"http://127.0.0.1:{self.listener.getsockname()[1]}"
        self.server = uvicorn.Server(
            uvicorn.Config(self.app, log_level="error", lifespan="on")
        )
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.listener]}, daemon=True
        )
        self.thread.start()
        deadline = time.monotonic() + 5
        while (
            not self.server.started
            and self.thread.is_alive()
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        if not self.server.started:
            self.__exit__(None, None, None)
            raise RuntimeError("loopback HTTP test server failed to start")
        return self

    def __exit__(self, *args):
        self.server.should_exit = True
        self.thread.join(5)
        self.listener.close()
        if self.thread.is_alive():
            raise RuntimeError("loopback HTTP test server failed to stop")

    def request(self, method, path, *, headers=None, json=None, content=None):
        h = {"Host": self.host_header, **(headers or {})}
        if json is not None:
            content = jsonlib.dumps(json, allow_nan=False).encode()
            h.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(
            self.url + path, data=content, headers=h, method=method
        )
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return Response(response)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)
