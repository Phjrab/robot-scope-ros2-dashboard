"""Fixed peer-to-peer datagram transport for signed control envelopes.

The payload remains the existing HMAC-authenticated control protocol.  This
module only carries one bounded UTF-8 envelope between two explicitly
configured private addresses on one repository-owned port.  It is not a ROS
topic relay, a generic UDP proxy, or a discovery mechanism.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Mapping

from .control_protocol import MAX_MESSAGE_BYTES


CONTROL_TRANSPORT_ENV = "ROBOT_SCOPE_CONTROL_TRANSPORT"
CONTROL_DATAGRAM_BIND_HOST_ENV = "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST"
CONTROL_DATAGRAM_PEER_HOST_ENV = "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST"
CONTROL_DATAGRAM_PORT = 46010
CONTROL_DATAGRAM_TIMEOUT_S = 0.2
CONTROL_TRANSPORT_ROS = "ros"
CONTROL_TRANSPORT_UDP = "udp"
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class ControlDatagramError(ValueError):
    """Raised when the fixed datagram contract cannot be used safely."""


def control_transport_mode(environ: Mapping[str, str]) -> str:
    value = str(environ.get(CONTROL_TRANSPORT_ENV, CONTROL_TRANSPORT_ROS)).strip()
    value = value.casefold() or CONTROL_TRANSPORT_ROS
    if value not in {CONTROL_TRANSPORT_ROS, CONTROL_TRANSPORT_UDP}:
        raise ControlDatagramError("control transport must be ros or udp")
    return value


def private_control_host(value: object, *, field: str) -> str:
    rendered = str(value or "").strip()
    try:
        address = ipaddress.ip_address(rendered)
    except ValueError as exc:
        raise ControlDatagramError(f"{field} must be an explicit IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise ControlDatagramError(f"{field} must be an IPv4 address")
    if not (
        address.is_link_local
        or any(address in network for network in _PRIVATE_NETWORKS)
    ):
        raise ControlDatagramError(f"{field} must be RFC1918 or link-local")
    if address.is_unspecified or address.is_loopback or address.is_multicast:
        raise ControlDatagramError(f"{field} is not an allowed control address")
    return str(address)


@dataclass(frozen=True)
class ControlDatagramConfig:
    bind_host: str
    peer_host: str
    port: int = CONTROL_DATAGRAM_PORT

    def __post_init__(self) -> None:
        validated_bind = private_control_host(
            self.bind_host,
            field="control datagram bind host",
        )
        validated_peer = private_control_host(
            self.peer_host,
            field="control datagram peer host",
        )
        if validated_bind == validated_peer:
            raise ControlDatagramError(
                "control datagram peer must be a different host"
            )
        if isinstance(self.port, bool) or self.port != CONTROL_DATAGRAM_PORT:
            raise ControlDatagramError("control datagram port is fixed")
        object.__setattr__(self, "bind_host", validated_bind)
        object.__setattr__(self, "peer_host", validated_peer)

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str]
    ) -> "ControlDatagramConfig":
        bind_host = private_control_host(
            environ.get(CONTROL_DATAGRAM_BIND_HOST_ENV),
            field="control datagram bind host",
        )
        peer_host = private_control_host(
            environ.get(CONTROL_DATAGRAM_PEER_HOST_ENV),
            field="control datagram peer host",
        )
        if bind_host == peer_host:
            raise ControlDatagramError("control datagram peer must be a different host")
        return cls(bind_host=bind_host, peer_host=peer_host)


class ConnectedControlDatagram:
    """One connected UDP socket that rejects packets from every other peer."""

    def __init__(
        self,
        config: ControlDatagramConfig,
        *,
        socket_factory=socket.socket,
    ) -> None:
        endpoint = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            endpoint.bind((config.bind_host, config.port))
            endpoint.connect((config.peer_host, config.port))
            endpoint.settimeout(CONTROL_DATAGRAM_TIMEOUT_S)
        except Exception:
            endpoint.close()
            raise
        self.config = config
        self._socket = endpoint

    def send_text(self, value: object) -> None:
        if not isinstance(value, str) or not value:
            raise ControlDatagramError("control datagram payload must be non-empty text")
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise ControlDatagramError("control datagram payload is too large")
        sent = self._socket.send(encoded)
        if sent != len(encoded):
            raise OSError("control datagram send was incomplete")

    def receive_text(self) -> str | None:
        try:
            encoded = self._socket.recv(MAX_MESSAGE_BYTES + 1)
        except socket.timeout:
            return None
        if not encoded:
            raise ControlDatagramError("control datagram payload is empty")
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise ControlDatagramError("control datagram payload is too large")
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ControlDatagramError("control datagram payload is not UTF-8") from exc

    def close(self) -> None:
        self._socket.close()


class DatagramStringPublisher:
    """Small publisher-shaped adapter used by the existing signed transport."""

    def __init__(self, endpoint: ConnectedControlDatagram) -> None:
        self._endpoint = endpoint

    def publish(self, message: object) -> None:
        self._endpoint.send_text(getattr(message, "data", None))


__all__ = [
    "CONTROL_DATAGRAM_BIND_HOST_ENV",
    "CONTROL_DATAGRAM_PEER_HOST_ENV",
    "CONTROL_DATAGRAM_PORT",
    "CONTROL_TRANSPORT_ENV",
    "CONTROL_TRANSPORT_ROS",
    "CONTROL_TRANSPORT_UDP",
    "ConnectedControlDatagram",
    "ControlDatagramConfig",
    "ControlDatagramError",
    "DatagramStringPublisher",
    "control_transport_mode",
    "private_control_host",
]
