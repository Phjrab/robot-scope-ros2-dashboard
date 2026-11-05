"""Optional direct TLS listener sharing the dashboard's one loop and lifespan."""
from contextlib import contextmanager
from dataclasses import dataclass
import asyncio
import ipaddress
import os
from pathlib import Path
import signal
import ssl
import stat

import uvicorn


@dataclass(frozen=True)
class HttpsListener:
    host: str
    port: int
    certfile: str
    keyfile: str


def _credential(value, *, private):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("HTTPS credentials require canonical absolute files")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or info.st_mode & (0o077 if private else 0o022)):
        raise ValueError("HTTPS credential ownership or permissions are invalid")
    for parent in path.parents:
        if parent.stat().st_mode & 0o022 and not parent.stat().st_mode & stat.S_ISVTX:
            raise ValueError("HTTPS credential parent is writable by another account")
    return str(path)


def configured_https(environ, *, http_port):
    names = ("HOST", "PORT", "CERTFILE", "KEYFILE")
    values = [environ.get("ROBOT_SCOPE_HTTPS_" + name) for name in names]
    if not any(values):
        return None
    if not all(values):
        raise ValueError("All four HTTPS listener settings are required")
    host, port, cert, key = values
    address = ipaddress.ip_address(host)
    if not (address.is_private or address.is_loopback) or address.is_unspecified:
        raise ValueError("HTTPS must bind an explicit private or loopback address")
    port = int(port)
    if not 1024 <= port <= 65535 or port == http_port:
        raise ValueError("HTTPS requires a separate unprivileged port")
    netloc = f"[{host}]" if address.version == 6 else host
    if environ.get("ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN") != f"https://{netloc}:{port}":
        raise ValueError("Review origin must match the direct HTTPS listener")
    cert, key = _credential(cert, private=False), _credential(key, private=True)
    # Validate the pair before entering the application lifespan or opening HTTP.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    return HttpsListener(host, port, cert, key)


class _ManagedServer(uvicorn.Server):
    # Both supported Uvicorn signal APIs are disabled; the pair has one owner.
    def install_signal_handlers(self):
        pass

    @contextmanager
    def capture_signals(self):
        yield


async def _serve_pair(app, http_host, http_port, tls):
    options = dict(workers=1, lifespan="off", proxy_headers=False,
                   access_log=False, timeout_graceful_shutdown=3)
    servers = [
        _ManagedServer(uvicorn.Config(app, host=http_host, port=http_port, **options)),
        _ManagedServer(uvicorn.Config(app, host=tls.host, port=tls.port,
            ssl_certfile=tls.certfile, ssl_keyfile=tls.keyfile,
            ssl_version=ssl.PROTOCOL_TLS_SERVER, **options)),
    ]
    tasks = []
    previous = {}

    async def serve(server):
        try:
            await server.serve()
        except SystemExit as exc:
            raise RuntimeError("Dashboard listener startup failed") from exc

    def stop(signum, frame):
        for server in servers:
            server.handle_exit(signum, frame)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, stop)
        # FastAPI's complete configured lifespan runs exactly once. Both
        # listeners drain before its ROS/control/worker cleanup is allowed.
        async with app.router.lifespan_context(app) as state:
            if state is not None:
                raise ValueError("Dual listener requires the dashboard's stateless lifespan")
            try:
                tasks = [asyncio.create_task(serve(server)) for server in servers]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
            finally:
                for server in servers:
                    server.should_exit = True
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def run_with_https(app, *, host, port, tls):
    """Serve existing HTTP plus direct HTTPS; never trust forwarded headers."""
    asyncio.run(_serve_pair(app, host, port, tls))


def run_dashboard(app, *, host, port, environ):
    tls = configured_https(environ, http_port=port)
    if tls is not None:
        return run_with_https(app, host=host, port=port, tls=tls)
    return uvicorn.run(app, host=host, port=port, workers=1,
                       access_log=False, timeout_graceful_shutdown=3)
