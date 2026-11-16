"""Shared access boundary for standalone and mounted offline analysis APIs."""

import base64
import binascii
import ipaddress
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from robot_dashboard.http_security import is_same_origin


class AccessPolicy:
    def __init__(self, *, authorities=(), password=None, networks=()):
        self.authorities = frozenset(authorities)
        self.password = password
        self.networks = tuple(ipaddress.ip_network(n, strict=False) for n in networks)
        if self.authorities:
            if (
                not isinstance(password, str)
                or not 32 <= len(password) <= 256
                or not password.isascii()
            ):
                raise ValueError("NETWORK_PASSWORD_MUST_BE_32_TO_256_ASCII_CHARACTERS")
            if not self.networks or any(
                not n.is_private or n.prefixlen == 0 for n in self.networks
            ):
                raise ValueError("EXPLICIT_PRIVATE_NETWORK_REQUIRED")
            for authority in self.authorities:
                if "*" in authority or not is_same_origin(
                    "http://" + authority, authority
                ):
                    raise ValueError("INVALID_ALLOWED_HOST")
        elif password is not None or self.networks:
            raise ValueError("EXPLICIT_ALLOWED_HOST_REQUIRED")

    def authorize(self, request: Request):
        host = request.headers.get("host", "")
        if self.authorities:
            if host not in self.authorities:
                raise HTTPException(403, "HOST_NOT_ALLOWED")
            try:
                peer = ipaddress.ip_address(request.client.host)
            except (ValueError, AttributeError):
                raise HTTPException(403, "NETWORK_NOT_ALLOWED") from None
            if not peer.is_loopback and not any(peer in n for n in self.networks):
                raise HTTPException(403, "NETWORK_NOT_ALLOWED")
            header = request.headers.get("authorization", "")
            supplied = b""
            if header.startswith("Basic ") and len(header) < 1024:
                try:
                    supplied = base64.b64decode(header[6:], validate=True)
                except (ValueError, binascii.Error):
                    pass
            if not secrets.compare_digest(
                supplied, ("review:" + self.password).encode("ascii")
            ):
                raise HTTPException(
                    401,
                    "AUTHENTICATION_REQUIRED",
                    headers={
                        "WWW-Authenticate": 'Basic realm="Offline SLAM", charset="UTF-8"',
                        "Cache-Control": "no-store",
                    },
                )
        else:
            try:
                parsed = urlsplit("//" + host)
                valid = parsed.hostname in {
                    "127.0.0.1",
                    "::1",
                    "localhost",
                    "testserver",
                } and is_same_origin("http://" + host, host)
            except ValueError:
                valid = False
            if not valid:
                raise HTTPException(403, "LOOPBACK_HOST_REQUIRED")

    def mutation(self, request: Request):
        self.authorize(request)
        if not is_same_origin(
            request.headers.get("origin", ""), request.headers.get("host", "")
        ):
            raise HTTPException(403, "SAME_ORIGIN_REQUIRED")
        if urlsplit(request.headers["origin"]).scheme != request.url.scheme:
            raise HTTPException(403, "SAME_ORIGIN_REQUIRED")
