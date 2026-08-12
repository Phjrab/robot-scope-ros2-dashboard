import asyncio
import ast
import unittest
from pathlib import Path

from robot_dashboard.websocket_stream import stream_until_disconnect


class _DisconnectingWebSocket:
    def __init__(self):
        self.accepted = False
        self.receive_count = 0

    async def accept(self):
        self.accepted = True

    async def receive(self):
        self.receive_count += 1
        await asyncio.sleep(0)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send_bytes(self, _payload):
        raise AssertionError("an empty stream must not send a binary frame")

    async def send_text(self, _payload):
        raise AssertionError("an empty stream must not send metadata")

    async def close(self, **_kwargs):
        return None


class StreamWebSocketTests(unittest.TestCase):
    def test_disconnect_exits_an_empty_outbound_stream(self):
        websocket = _DisconnectingWebSocket()
        pump_count = 0

        async def send_next():
            nonlocal pump_count
            pump_count += 1

        asyncio.run(stream_until_disconnect(websocket, send_next))

        self.assertEqual(websocket.receive_count, 1)
        self.assertGreaterEqual(pump_count, 1)

    def test_camera_endpoint_closes_consumer_after_stream_helper(self):
        source = (
            Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        camera = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_camera_stream_source"
        )
        calls = {
            node.func.id
            for node in ast.walk(camera)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attributes = {
            node.attr
            for node in ast.walk(camera)
            if isinstance(node, ast.Attribute)
        }
        self.assertIn("stream_until_disconnect", calls)
        self.assertIn("camera_stream_close", attributes)
        self.assertIn("wait_for", attributes)

    def test_pointcloud_endpoint_uses_disconnect_helper(self):
        source = (
            Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        pointcloud = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "pointcloud_stream"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "stream_until_disconnect"
                for node in ast.walk(pointcloud)
            )
        )


if __name__ == "__main__":
    unittest.main()
