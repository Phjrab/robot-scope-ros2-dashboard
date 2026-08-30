import socket
import unittest

from robot_dashboard.control_datagram import (
    CONTROL_DATAGRAM_PORT,
    ConnectedControlDatagram,
    ControlDatagramConfig,
    ControlDatagramError,
    DatagramStringPublisher,
    control_transport_mode,
)
from robot_dashboard.control_protocol import MAX_MESSAGE_BYTES


class FakeSocket:
    def __init__(self):
        self.bound = None
        self.connected = None
        self.timeout = None
        self.sent = []
        self.received = []
        self.closed = False

    def bind(self, address):
        self.bound = address

    def connect(self, address):
        self.connected = address

    def settimeout(self, timeout):
        self.timeout = timeout

    def send(self, payload):
        self.sent.append(payload)
        return len(payload)

    def recv(self, size):
        if not self.received:
            raise socket.timeout
        return self.received.pop(0)[:size]

    def close(self):
        self.closed = True


class ControlDatagramTests(unittest.TestCase):
    def test_mode_and_private_fixed_peer_configuration_fail_closed(self):
        self.assertEqual(control_transport_mode({}), "ros")
        self.assertEqual(
            control_transport_mode({"ROBOT_SCOPE_CONTROL_TRANSPORT": "UDP"}),
            "udp",
        )
        with self.assertRaises(ControlDatagramError):
            control_transport_mode({"ROBOT_SCOPE_CONTROL_TRANSPORT": "tcp"})

        config = ControlDatagramConfig.from_environment(
            {
                "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST": "192.168.50.10",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST": "192.168.50.30",
            }
        )
        self.assertEqual(config.bind_host, "192.168.50.10")
        self.assertEqual(config.peer_host, "192.168.50.30")
        self.assertEqual(config.port, CONTROL_DATAGRAM_PORT)

        for values in (
            {},
            {
                "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST": "127.0.0.1",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST": "192.168.50.30",
            },
            {
                "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST": "8.8.8.8",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST": "192.168.50.30",
            },
            {
                "ROBOT_SCOPE_CONTROL_DATAGRAM_BIND_HOST": "192.168.50.30",
                "ROBOT_SCOPE_CONTROL_DATAGRAM_PEER_HOST": "192.168.50.30",
            },
        ):
            with self.subTest(values=values):
                with self.assertRaises(ControlDatagramError):
                    ControlDatagramConfig.from_environment(values)
        with self.assertRaises(ControlDatagramError):
            ControlDatagramConfig("192.168.50.10", "192.168.50.30", port=46011)

    def test_connected_socket_binds_and_connects_one_fixed_port(self):
        fake = FakeSocket()
        calls = []

        def factory(family, kind):
            calls.append((family, kind))
            return fake

        endpoint = ConnectedControlDatagram(
            ControlDatagramConfig("192.168.50.10", "192.168.50.30"),
            socket_factory=factory,
        )
        self.assertEqual(calls, [(socket.AF_INET, socket.SOCK_DGRAM)])
        self.assertEqual(fake.bound, ("192.168.50.10", CONTROL_DATAGRAM_PORT))
        self.assertEqual(fake.connected, ("192.168.50.30", CONTROL_DATAGRAM_PORT))
        self.assertGreater(fake.timeout, 0)
        endpoint.close()
        self.assertTrue(fake.closed)

    def test_payload_is_utf8_bounded_and_publisher_does_not_transform_it(self):
        fake = FakeSocket()
        endpoint = ConnectedControlDatagram(
            ControlDatagramConfig("192.168.50.10", "192.168.50.30"),
            socket_factory=lambda *_args: fake,
        )
        message = type("Message", (), {"data": "signed-envelope"})()
        DatagramStringPublisher(endpoint).publish(message)
        self.assertEqual(fake.sent, [b"signed-envelope"])

        fake.received.append("상태".encode("utf-8"))
        self.assertEqual(endpoint.receive_text(), "상태")
        self.assertIsNone(endpoint.receive_text())
        for invalid in (None, "", "x" * (MAX_MESSAGE_BYTES + 1)):
            with self.subTest(invalid_type=type(invalid).__name__):
                with self.assertRaises(ControlDatagramError):
                    endpoint.send_text(invalid)
        fake.received.append(b"\xff")
        with self.assertRaises(ControlDatagramError):
            endpoint.receive_text()


if __name__ == "__main__":
    unittest.main()
