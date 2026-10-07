"""CI jobs use the migrated credentials, not the operator/admin PAT."""
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.api import APIError, Client
from services.model import validate_catalog

BUILD = Path('build')
BUILD.mkdir(exist_ok=True)
BASE = os.environ.get('CI_SERVER_URL', 'http://gitlab.lab:8929')

def identity(role):
    value = os.environ.get(role.upper() + '_TOKEN', '')
    if not value:
        raise ValueError(f'{role}: falta variable de credencial; revisar protected/environment_scope')
    client = Client(BASE, value)
    user = client.get('/user')
    expected = int(os.environ['EXPECTED_' + role.upper() + '_ID'])
    if user['id'] != expected:
        raise ValueError(f'{role}: identidad efectiva inesperada')
    # Evidence contains IDs, never tokens, headers or complete API user objects.
    (BUILD / f'{role}.json').write_text(json.dumps({'role': role, 'user_id': user['id']}))
    print(f'{role}: identidad {user["id"]} validada')
    return client

def run(command):
    if command == 'read':
        client = identity('reader')
        raw = client.request('GET', f"/projects/{os.environ['CONFIG_PROJECT_ID']}/repository/files/catalog.json/raw?ref=main", raw=True)
        validate_catalog(json.loads(raw))
        (BUILD / 'catalog.json').write_bytes(raw)
    elif command == 'publish':
        client = identity('publisher')
        content = (BUILD / 'catalog.json').read_bytes()
        url = f"/projects/{os.environ['PACKAGES_PROJECT_ID']}/packages/generic/catalog/{os.environ['CI_PIPELINE_ID']}/catalog.json"
        client.request('PUT', url, content)
        fetched = client.request('GET', url, raw=True)
        if hashlib.sha256(content).digest() != hashlib.sha256(fetched).digest():
            raise ValueError('Checksum de paquete incorrecto')
        print('Paquete publicado y descargado; SHA256 coincide')
    elif command == 'deploy':
        identity('deployer')
        body = {'version': os.environ['CI_PIPELINE_ID'], 'catalog': json.loads((BUILD / 'catalog.json').read_text())}
        response = Client('http://deployer:8000', os.environ['DEPLOYER_TOKEN'], api=False).request('POST', '/deploy', body)
        if response['deployed_by'] != int(os.environ['EXPECTED_DEPLOYER_ID']):
            raise ValueError('El despliegue no usó la identidad esperada')
    elif command == 'smoke':
        catalog = Client('http://catalog:8000', api=False).get('/products')
        if str(catalog['version']) != os.environ['CI_PIPELINE_ID']:
            raise ValueError('El catálogo no cargó la nueva versión')
        product = catalog['products'][0]
        order = Client('http://orders:8000', api=False).request('POST', '/orders', {'sku': product['sku'], 'quantity': 2})
        if order['total_cents'] != product['price_cents'] * 2:
            raise ValueError('Transacción de negocio incorrecta')
        print('Pedido real validado, catálogo y cálculo correctos')
    else:
        raise ValueError('Comando desconocido')

if __name__ == '__main__':
    try:
        run(sys.argv[1])
    except (APIError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
