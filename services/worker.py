"""External automation consumer; re-reads its mounted credential file each cycle."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from lab.api import APIError, Client
from lab.storage import read_json, write_json
from services.model import validate_catalog

def sync_once(config_path: Path, runtime: Path, base: str):
    status = {'ok': False, 'checked_at': time.time()}
    try:
        config = read_json(config_path)
        client = Client(base, config['token'])
        identity = client.get('/user')
        catalog = client.request('GET', f"/projects/{config['project_id']}/repository/files/catalog.json/raw?ref=main", raw=True)
        validate_catalog(json.loads(catalog))
        write_json(runtime / 'synced-config.json', json.loads(catalog))
        status.update(ok=True, user_id=identity['id'], project_id=config['project_id'])
    except APIError as exc:
        status['http_status'] = exc.status
    except (ValueError, KeyError, OSError):
        status['error'] = 'invalid_or_missing_local_config'
    write_json(runtime / 'worker-status.json', status)
    print(json.dumps(status), flush=True)
    return status

if __name__ == '__main__':
    while True:
        sync_once(Path(os.environ.get('WORKER_CONFIG', '/credentials/config.json')),
                  Path(os.environ.get('RUNTIME_DIR', '/runtime')),
                  os.environ.get('GITLAB_URL', 'http://gitlab.lab:8929'))
        time.sleep(5)
