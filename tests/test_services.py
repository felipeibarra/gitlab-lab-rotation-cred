"""Local HTTP integration tests for the services (GitLab mocked only for auth)."""
import contextlib
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from lab.api import APIError, Client
from lab.storage import write_json
from services.app import DEFAULT_CATALOG, make_handler

@contextlib.contextmanager
def server(kind, runtime, catalog_url='http://localhost:1'):
    service = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(kind, runtime, 'http://localhost:8929', catalog_url))
    thread = threading.Thread(target=service.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{service.server_port}'
    finally:
        service.shutdown(); service.server_close(); thread.join(timeout=2)

class ServiceTests(unittest.TestCase):
    def test_catalog_http(self):
        with tempfile.TemporaryDirectory() as d, server('catalog', Path(d)) as url:
            self.assertEqual(Client(url, api=False).get('/products')['version'], 'initial')
    def test_config_update_without_restart(self):
        with tempfile.TemporaryDirectory() as d, server('catalog', Path(d)) as url:
            write_json(Path(d) / 'release.json', {'version': '42', 'catalog': DEFAULT_CATALOG})
            self.assertEqual(Client(url, api=False).get('/products')['version'], '42')
    def test_actual_order_between_services(self):
        with tempfile.TemporaryDirectory() as d, server('catalog', Path(d)) as catalog:
            with server('orders', Path(d), catalog) as orders:
                order = Client(orders, api=False).request('POST', '/orders', {'sku': 'MUG-001', 'quantity': 3})
                self.assertEqual(order['total_cents'], 3600)
    def test_non_object_order_rejected(self):
        with tempfile.TemporaryDirectory() as d, server('orders', Path(d)) as orders:
            with self.assertRaises(APIError) as caught:
                Client(orders, api=False).request('POST', '/orders', ['invalid'])
            self.assertEqual(caught.exception.status, 400)
    def test_invalid_order_rejected(self):
        with tempfile.TemporaryDirectory() as d, server('catalog', Path(d)) as catalog:
            with server('orders', Path(d), catalog) as orders:
                with self.assertRaises(APIError) as exc:
                    Client(orders, api=False).request('POST', '/orders', {'sku': 'MUG-001', 'quantity': 0})
                self.assertEqual(exc.exception.status, 400)
    def test_deploy_requires_credential(self):
        with tempfile.TemporaryDirectory() as d, server('deployer', Path(d)) as url:
            with self.assertRaises(APIError) as exc:
                Client(url, api=False).request('POST', '/deploy', {'version': '1', 'catalog': DEFAULT_CATALOG})
            self.assertEqual(exc.exception.status, 401)
    def test_developer_cannot_deploy(self):
        fake = Mock(); fake.get.side_effect = [{'id': 7}, {'permissions': {'project_access': {'access_level': 30}}}]
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d) / 'topology.json', {'deployment_project_id': 1})
            with patch('services.app.Client', return_value=fake), server('deployer', Path(d)) as url:
                with self.assertRaises(APIError) as exc:
                    Client(url, 'test-token', api=False).request('POST', '/deploy', {'version': '1', 'catalog': DEFAULT_CATALOG})
                self.assertEqual(exc.exception.status, 403)
    def test_maintainer_deploys(self):
        fake = Mock(); fake.get.side_effect = [{'id': 7}, {'permissions': {'project_access': {'access_level': 40}}}]
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d) / 'topology.json', {'deployment_project_id': 1})
            with patch('services.app.Client', return_value=fake), server('deployer', Path(d)) as url:
                result = Client(url, 'test-token', api=False).request('POST', '/deploy', {'version': '1', 'catalog': DEFAULT_CATALOG})
                self.assertEqual(result, {'version': '1', 'deployed_by': 7})
    def test_inherited_maintainer_can_deploy(self):
        fake = Mock(); fake.get.side_effect = [{'id': 9}, {'permissions': {'project_access': None, 'group_access': {'access_level': 40}}}]
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d) / 'topology.json', {'deployment_project_id': 1})
            with patch('services.app.Client', return_value=fake), server('deployer', Path(d)) as url:
                result = Client(url, 'test-token', api=False).request('POST', '/deploy', {'version': '2', 'catalog': DEFAULT_CATALOG})
                self.assertEqual(result['deployed_by'], 9)

if __name__ == '__main__': unittest.main()
