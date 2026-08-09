"""Small HTTP origin checks shared by mutation routes and WebSockets."""

from __future__ import annotations

from urllib.parse import urlsplit


def is_same_origin(origin: str, host: str) -> bool:
    """Return true only for an explicit Origin whose authority matches Host."""

    if not isinstance(origin, str) or not isinstance(host, str) or not origin or not host:
        return False
    try:
        origin_host = urlsplit(origin).netloc
    except ValueError:
        return False
    return bool(origin_host) and origin_host.lower() == host.lower()
