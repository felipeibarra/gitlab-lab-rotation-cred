"""LOCAL LAB ONLY: catalog, order API and a GitLab-authorized config deployer.

The deployment changes application configuration, not the running Docker image.
The deployer is a lab authorization adapter, not GitLab Protected Environments.
"""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lab.api import APIError, Client
from lab.storage import read_json, write_json
from services.model import order_total, validate_catalog

DEFAULT_CATALOG = {'products': [{'sku': 'BOOK-001', 'price_cents': 2500}, {'sku': 'MUG-001', 'price_cents': 1200}]}

def make_handler(kind, runtime: Path, gitlab_url: str, catalog_url: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Never log auth headers, bodies, raw request paths or token values.
            pass

        def send_json(self, code, data):
            content = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def read_body(self):
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                raise ValueError('invalid body length')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('body must be a JSON object')
            return body

        def do_GET(self):
            try:
                if self.path == '/health':
                    self.send_json(200, {'status': 'ok', 'service': kind})
                elif kind == 'catalog' and self.path == '/products':
                    release = read_json(runtime / 'release.json') if (runtime / 'release.json').exists() else {'catalog': DEFAULT_CATALOG, 'version': 'initial'}
                    self.send_json(200, {**release['catalog'], 'version': release['version']})
                elif kind == 'deployer' and self.path == '/release':
                    self.send_json(200, read_json(runtime / 'release.json') if (runtime / 'release.json').exists() else {'version': 'initial'})
                else:
                    self.send_json(404, {'error': 'not_found'})
            except (ValueError, OSError):
                self.send_json(503, {'error': 'runtime_unavailable'})

        def do_POST(self):
            try:
                if kind == 'orders' and self.path == '/orders':
                    body = self.read_body()
                    catalog = Client(catalog_url, api=False).get('/products')
                    total = order_total(catalog, body.get('sku'), body.get('quantity'))
                    self.send_json(201, {'id': str(uuid.uuid4()), 'total_cents': total, 'catalog_version': catalog['version']})
                elif kind == 'deployer' and self.path == '/deploy':
                    token = self.headers.get('PRIVATE-TOKEN', '')
                    if not token:
                        self.send_json(401, {'error': 'credential_missing'})
                        return
                    client = Client(gitlab_url, token)
                    user = client.get('/user')
                    topology = read_json(runtime / 'topology.json')
                    project = client.get(f"/projects/{topology['deployment_project_id']}")
                    permissions = project.get('permissions', {})
                    level = max([(v or {}).get('access_level', 0) for v in permissions.values()] or [0])
                    if level < 40:
                        self.send_json(403, {'error': 'maintainer_required'})
                        return
                    body = self.read_body()
                    catalog = validate_catalog(body['catalog'])
                    version = str(body['version'])
                    if not version.isdigit() or len(version) > 20:
                        raise ValueError('Invalid version')
                    release = {'version': version, 'catalog': catalog, 'deployed_by': user['id'], 'at': time.time()}
                    write_json(runtime / 'release.json', release)
                    self.send_json(200, {'version': version, 'deployed_by': user['id']})
                else:
                    self.send_json(404, {'error': 'not_found'})
            except APIError as exc:
                self.send_json(exc.status if exc.status in (401, 403, 404) else 502, {'error': 'dependency_request_failed', 'upstream_status': exc.status})
            except (ValueError, KeyError, TypeError):
                self.send_json(400, {'error': 'invalid_input'})
            except OSError:
                self.send_json(503, {'error': 'runtime_unavailable'})
    return Handler

if __name__ == '__main__':
    kind = sys.argv[1] if len(sys.argv) > 1 else 'catalog'
    if kind not in ('catalog', 'orders', 'deployer'):
        raise SystemExit('Unknown service')
    handler = make_handler(kind, Path(os.environ.get('RUNTIME_DIR', '/runtime')),
                           os.environ.get('GITLAB_URL', 'http://gitlab.lab:8929'),
                           os.environ.get('CATALOG_URL', 'http://catalog:8000'))
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8000'))), handler).serve_forever()
