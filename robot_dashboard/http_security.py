"""Small HTTP origin checks shared by mutation routes and WebSockets."""

from __future__ import annotations

from urllib.parse import urlsplit


def is_same_origin(origin: str, host: str) -> bool:
    """Return true only for an explicit Origin whose authority matches Host."""

    if not isinstance(origin, str) or not isinstance(host, str) or not origin or not host:
        return False
    if len(origin) > 512 or len(host) > 255:
        return False
    if any(
        ord(character) < 0x21 or ord(character) == 0x7F
        for character in origin + host
    ):
        return False
    try:
        parsed = urlsplit(origin)
        host_authority = urlsplit(f"//{host}")
        # urllib validates malformed and out-of-range ports lazily.
        parsed_port = parsed.port
        host_port = host_authority.port
    except ValueError:
        return False
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if (
        not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not host_authority.netloc
        or host_authority.username is not None
        or host_authority.password is not None
        or host_authority.path
        or host_authority.query
        or host_authority.fragment
        or parsed_port != host_port
    ):
        return False
    return parsed.netloc.lower() == host.lower()
