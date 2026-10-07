"""Standard-library HTTP client: local-only endpoints and no secret-bearing errors."""
from __future__ import annotations
import json
import time
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = {'127.0.0.1', 'localhost', 'gitlab.lab', 'catalog', 'orders', 'deployer'}

class APIError(RuntimeError):
    def __init__(self, status: int, method: str, path: str):
        self.status = status
        # Never include response bodies, headers or query values: APIs may echo secrets.
        super().__init__(f'HTTP {status}: {method} {path.split("?")[0]}')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Client:
    def __init__(self, base: str, token: str = '', api: bool = True):
        p = urllib.parse.urlsplit(base)
        if p.hostname not in ALLOWED_HOSTS or p.username or p.password or p.query or p.fragment:
            raise ValueError('Este laboratorio solo acepta hosts locales expresamente permitidos.')
        if p.scheme != 'http' or p.path not in ('', '/'):
            raise ValueError('Base URL local inválida.')
        self.base = base.rstrip('/') + ('/api/v4' if api else '')
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method: str, path: str, data=None, *, raw: bool = False):
        if not path.startswith('/') or path.startswith('//') or '://' in path:
            raise ValueError('Se requiere una ruta relativa a la API.')
        body = data if isinstance(data, bytes) else (json.dumps(data).encode() if data is not None else None)
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['PRIVATE-TOKEN'] = self.token
        if body is not None:
            headers['Content-Type'] = 'application/octet-stream' if isinstance(data, bytes) else 'application/json'
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        # Retry safe reads only. A failed write can have committed at the remote end.
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=30) as response:
                    content = response.read()
                    if raw:
                        return content
                    return json.loads(content) if content else None
            except urllib.error.HTTPError as exc:
                if method == 'GET' and exc.code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise APIError(exc.code, method, path) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                if method == 'GET' and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise APIError(0, method, path) from None
        raise RuntimeError('Unreachable')

    def get(self, path):
        return self.request('GET', path)

    def pages(self, path):
        result = []
        separator = '&' if '?' in path else '?'
        for page in range(1, 1001):
            items = self.get(f'{path}{separator}per_page=100&page={page}')
            if not isinstance(items, list):
                raise ValueError('La API no devolvió una colección.')
            result.extend(items)
            if len(items) < 100:
                return result
        raise RuntimeError('Límite de paginación alcanzado; revisar alcance.')
