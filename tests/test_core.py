import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from lab.api import APIError, Client, NoRedirect
from lab.storage import atomic_write, read_json, write_json
from services.app import DEFAULT_CATALOG
from services.model import order_total, validate_catalog
from services.worker import sync_once

class DomainTests(unittest.TestCase):
    def test_valid_catalog(self):
        self.assertEqual(validate_catalog(DEFAULT_CATALOG), DEFAULT_CATALOG)
    def test_order(self):
        self.assertEqual(order_total(DEFAULT_CATALOG, 'BOOK-001', 2), 5000)
    def test_unknown_sku(self):
        with self.assertRaises(ValueError): order_total(DEFAULT_CATALOG, 'NONE', 1)
    def test_reject_bool_quantity(self):
        with self.assertRaises(ValueError): order_total(DEFAULT_CATALOG, 'BOOK-001', True)
    def test_reject_zero_quantity(self):
        with self.assertRaises(ValueError): order_total(DEFAULT_CATALOG, 'BOOK-001', 0)
    def test_reject_large_quantity(self):
        with self.assertRaises(ValueError): order_total(DEFAULT_CATALOG, 'BOOK-001', 101)
    def test_reject_float_price(self):
        with self.assertRaises(ValueError): validate_catalog({'products': [{'sku': 'A', 'price_cents': 1.2}]})
    def test_reject_negative_price(self):
        with self.assertRaises(ValueError): validate_catalog({'products': [{'sku': 'A', 'price_cents': -1}]})
    def test_reject_boolean_price(self):
        with self.assertRaises(ValueError): validate_catalog({'products': [{'sku': 'A', 'price_cents': True}]})
    def test_reject_empty(self):
        with self.assertRaises(ValueError): validate_catalog({'products': []})
    def test_reject_duplicate(self):
        with self.assertRaises(ValueError): validate_catalog({'products': [{'sku': 'A', 'price_cents': 1}] * 2})
    def test_reject_non_object_product(self):
        with self.assertRaises(ValueError): validate_catalog({'products': ['invalid']})
    def test_reject_missing_products(self):
        with self.assertRaises(ValueError): validate_catalog({})

class HTTPTests(unittest.TestCase):
    def test_no_external_hosts(self):
        with self.assertRaises(ValueError): Client('http://gitlab.com')
    def test_no_hostname_trick(self):
        with self.assertRaises(ValueError): Client('http://localhost.attacker.example')
    def test_no_embedded_credentials(self):
        with self.assertRaises(ValueError): Client('http://user:secret@localhost')
    def test_no_query_in_base(self):
        with self.assertRaises(ValueError): Client('http://localhost?token=secret')
    def test_no_base_paths(self):
        with self.assertRaises(ValueError): Client('http://localhost/api/v4')
    def test_no_absolute_request_url(self):
        with self.assertRaises(ValueError): Client('http://localhost').get('http://gitlab.com')
    def test_no_network_path_reference(self):
        with self.assertRaises(ValueError): Client('http://localhost').get('//gitlab.com')
    def test_no_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'http://elsewhere'))
    def test_errors_sanitized(self):
        error = APIError(403, 'PUT', '/variables/KEY?secret=SHOULD_NOT_APPEAR')
        self.assertNotIn('SHOULD_NOT_APPEAR', str(error))
    def test_pagination(self):
        c = Client('http://localhost')
        c.get = Mock(side_effect=[[{'id': i} for i in range(100)], [{'id': 100}]])
        self.assertEqual(len(c.pages('/projects?owned=true')), 101)
        self.assertIn('&per_page=100&page=2', c.get.call_args.args[0])
    def test_pagination_requires_list(self):
        c = Client('http://localhost'); c.get = Mock(return_value={'error': 'bad'})
        with self.assertRaises(ValueError): c.pages('/projects')
    def test_post_not_retried(self):
        c = Client('http://localhost')
        c.opener.open = Mock(side_effect=HTTPError('http://localhost', 503, 'secret', {}, None))
        with self.assertRaises(APIError): c.request('POST', '/users', {'password': 'not-exposed'})
        self.assertEqual(c.opener.open.call_count, 1)
    def test_get_retries_transient_errors(self):
        c = Client('http://localhost')
        c.opener.open = Mock(side_effect=[HTTPError('http://localhost', 503, 'secret', {}, None), io.BytesIO(b'{"id": 1}')])
        with patch('lab.api.time.sleep'): self.assertEqual(c.get('/user'), {'id': 1})
        self.assertEqual(c.opener.open.call_count, 2)
    def test_response_body_not_in_error(self):
        c = Client('http://localhost')
        c.opener.open = Mock(side_effect=HTTPError('http://localhost', 400, 'sensitive', {}, io.BytesIO(b'{"token":"secret"}')))
        with self.assertRaises(APIError) as caught: c.request('POST', '/users')
        self.assertNotIn('secret', str(caught.exception))

class StorageTests(unittest.TestCase):
    def test_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'token'; atomic_write(p, 'local-only')
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'state.json'; write_json(p, {'id': 3})
            self.assertEqual(read_json(p), {'id': 3})
    def test_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'state'; atomic_write(p, 'first'); atomic_write(p, 'second')
            self.assertEqual(p.read_text(), 'second')
            self.assertEqual(len(list(Path(d).iterdir())), 1)

class WorkerTests(unittest.TestCase):
    def test_success_records_identity_not_token(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); conf = root / 'config.json'; write_json(conf, {'project_id': 2, 'token': 'LOCAL-SECRET'})
            client = Mock(); client.get.return_value = {'id': 42}
            client.request.return_value = json.dumps(DEFAULT_CATALOG).encode()
            output = io.StringIO()
            with patch('services.worker.Client', return_value=client), contextlib.redirect_stdout(output):
                status = sync_once(conf, root, 'http://localhost')
            self.assertTrue(status['ok']); self.assertEqual(status['user_id'], 42)
            self.assertNotIn('LOCAL-SECRET', output.getvalue())
    def test_failure_preserves_cache_but_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); conf = root / 'config.json'; write_json(conf, {'project_id': 2, 'token': 'LOCAL-SECRET'})
            write_json(root / 'synced-config.json', DEFAULT_CATALOG)
            client = Mock(); client.get.side_effect = APIError(401, 'GET', '/user')
            with patch('services.worker.Client', return_value=client), contextlib.redirect_stdout(io.StringIO()):
                status = sync_once(conf, root, 'http://localhost')
            self.assertFalse(status['ok']); self.assertEqual(status['http_status'], 401)
            self.assertEqual(read_json(root / 'synced-config.json'), DEFAULT_CATALOG)
    def test_missing_file_reports_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()):
                status = sync_once(Path(d) / 'missing', Path(d), 'http://localhost')
            self.assertFalse(status['ok'])

if __name__ == '__main__': unittest.main()
