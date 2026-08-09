import json
import unittest

from robot_dashboard.control_protocol import (
    ControlProtocolError,
    decode_signed,
    encode_signed,
    shared_key,
)


KEY = "k" * 32


class ControlProtocolTests(unittest.TestCase):
    def test_round_trip_and_signature(self):
        encoded = encode_signed({"type": "stop", "seq": 4}, KEY, now=100.0)
        decoded = decode_signed(encoded, KEY, now=102.9)
        self.assertEqual(decoded["type"], "stop")
        self.assertEqual(decoded["seq"], 4)
        self.assertNotIn("mac", decoded)

    def test_tampering_and_wrong_key_are_rejected(self):
        body = json.loads(encode_signed({"type": "drive", "seq": 1}, KEY, now=10))
        body["seq"] = 2
        with self.assertRaises(ControlProtocolError):
            decode_signed(json.dumps(body), KEY, now=10)
        with self.assertRaises(ControlProtocolError):
            decode_signed(
                encode_signed({"type": "stop"}, KEY, now=10),
                "z" * 32,
                now=10,
            )

    def test_stale_nonfinite_and_short_keys_are_rejected(self):
        encoded = encode_signed({"type": "stop"}, KEY, now=10)
        with self.assertRaises(ControlProtocolError):
            decode_signed(encoded, KEY, now=13.1)
        with self.assertRaises(ControlProtocolError):
            encode_signed({"value": float("nan")}, KEY, now=10)
        with self.assertRaises(ControlProtocolError):
            shared_key("too-short")


if __name__ == "__main__":
    unittest.main()
