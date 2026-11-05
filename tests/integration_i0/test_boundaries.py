from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from tests.expansion_services.http_client import TestClient
from robot_dashboard.expansion_integration.bootstrap import configure_expansion
from robot_dashboard.expansion_integration.flags import ExpansionFlags
from robot_dashboard.expansion_integration.host import ExpansionOwner, install_expansion


class ProductBoundaries(unittest.TestCase):
    def test_all_flags_off_only_adds_public_landing_and_links(self):
        app = FastAPI()
        before = list(app.routes)
        with patch('robot_dashboard.expansion_integration.host.install_expansion',
                   side_effect=AssertionError('OFF must not install services')):
            index = configure_expansion(app, {})
        self.assertEqual([route.path for route in app.routes[len(before):]], ['/extensions'])
        self.assertFalse(hasattr(app.state, 'expansion_owner'))
        response = index(headers={"Cache-Control": "no-store"})
        import re
        source = (Path(__file__).parents[2] / "robot_dashboard/static/index.html").read_text()
        html = response.body.decode()
        stripped, count = re.subn(r'<a [^>]*href="/extensions"[^>]*>.*?</a>', '', html)
        self.assertEqual(count, 2)
        stripped = stripped.replace('<link rel="stylesheet" href="/static/features/expansion/entry.css">', '')
        self.assertEqual(stripped, source)
        with TestClient(app, base_url="http://testserver") as client:
            self.assertEqual(client.get('/extensions').status_code, 200)
            self.assertEqual(client.get('/api/v1/extensions/scene/context').status_code, 404)
            self.assertEqual(client.get('/api/v1/extensions/multimap/sources').status_code, 404)
            self.assertEqual(client.post('/api/v1/extensions/session', json='x').status_code, 404)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertFalse(ExpansionFlags.from_environ({"ROBOT_SCOPE_EXPANSION_SCENE":"true"}).enabled)

    def test_unconfigured_product_auth_and_independent_flags_fail_closed(self):
        app = FastAPI()
        install_expansion(app, ExpansionFlags(multimap=True))
        with TestClient(app, base_url="http://testserver") as client:
            self.assertEqual(client.get('/api/v1/extensions/multimap/sources').status_code, 401)
            self.assertEqual(client.post('/api/v1/extensions/multimap/jobs', json={}).status_code, 401)
            self.assertEqual(client.get('/api/v1/extensions/scene/context').status_code, 404)
            self.assertIn('BLOCKED_AUTH', client.get('/extensions').text)
        app = FastAPI()
        install_expansion(app, ExpansionFlags(multimap=True), ExpansionOwner(authorize=lambda _:None))
        with TestClient(app, base_url="http://testserver") as client:
            self.assertEqual(client.post('/api/v1/extensions/multimap/jobs', json={},
                headers={'Origin':'http://testserver'}).status_code, 403)
            self.assertEqual(client.get('/api/v1/extensions/multimap/sources').status_code, 503)
