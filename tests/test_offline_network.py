"""Authenticated LAN boundary on both real mounted offline API families."""

import base64
from pathlib import Path
import tempfile
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from robot_dashboard.offline_slam.access import AccessPolicy
from robot_dashboard.offline_slam.demo import fixture
from robot_dashboard.offline_slam.workbench import create_app
from tests.expansion_services.http_client import TestClient

PASSWORD = "synthetic-test-password-only-1234567890"
HOST = "192.168.50.10:8092"
AUTH = "Basic " + base64.b64encode(("review:" + PASSWORD).encode()).decode()


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.policy = AccessPolicy(
            authorities=[HOST], password=PASSWORD, networks=["192.168.50.0/24"]
        )
        self.app = create_app(
            Path(self.temp.name), access=self.policy, synthetic_demo=True
        )
        self.client = TestClient(self.app, base_url="http://" + HOST).__enter__()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_every_page_api_and_download_requires_authentication(self):
        for path in [
            "/",
            "/extensions",
            "/static/index.html",
            "/analysis/",
            "/analysis/api/sessions",
            "/analysis/api/sessions/unknown/export",
            "/api/v1/extensions/multimap/sources",
            "/api/v1/extensions/multimap/exports",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertIn("Basic", response.headers["WWW-Authenticate"])
                self.assertNotIn(PASSWORD, response.text)
                self.assertEqual(
                    self.client.get(
                        path, headers={"Authorization": "Basic invalid"}
                    ).status_code,
                    401,
                )

    def test_authorized_main_both_modes_and_mounted_import(self):
        headers = {"Authorization": AUTH, "Origin": "http://" + HOST}
        for path in [
            "/",
            "/extensions",
            "/analysis/",
            "/analysis/api/sessions",
            "/api/v1/extensions/multimap/sources",
        ]:
            self.assertEqual(self.client.get(path, headers=headers).status_code, 200)
        response = self.client.post(
            "/analysis/api/sessions", json=fixture(), headers=headers
        )
        self.assertEqual(response.status_code, 201, response.text)
        session = response.json()
        response = self.client.get(
            "/analysis/api/sessions/" + session["id"] + "/comparison", headers=headers
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_wrong_host_origin_and_network_remain_blocked(self):
        for path in ["/analysis/api/sessions", "/api/v1/extensions/multimap/jobs"]:
            for origin in ["http://evil.invalid", "https://" + HOST, ""]:
                response = self.client.post(
                    path, content=b"", headers={"Authorization": AUTH, "Origin": origin}
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get(
                "/", headers={"Authorization": AUTH, "Host": "evil.invalid"}
            ).status_code,
            403,
        )
        for peer in ["192.168.50.23", "10.0.0.9", "8.8.8.8"]:
            request = Request(
                {
                    "type": "http",
                    "scheme": "http",
                    "method": "GET",
                    "path": "/",
                    "client": (peer, 1000),
                    "headers": [
                        (b"host", HOST.encode()),
                        (b"authorization", AUTH.encode()),
                    ],
                }
            )
            if peer == "192.168.50.23":
                self.policy.authorize(request)
            else:
                with self.assertRaises(HTTPException) as raised:
                    self.policy.authorize(request)
                self.assertEqual(raised.exception.detail, "NETWORK_NOT_ALLOWED")

    def test_network_configuration_fails_closed(self):
        for kwargs in [
            dict(authorities=[HOST]),
            dict(authorities=[HOST], password=PASSWORD),
            dict(authorities=[HOST], password=PASSWORD, networks=["0.0.0.0/0"]),
            dict(authorities=["*"], password=PASSWORD, networks=["192.168.50.0/24"]),
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AccessPolicy(**kwargs)


if __name__ == "__main__":
    unittest.main()
