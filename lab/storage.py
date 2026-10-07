from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

def atomic_write(path: Path, data: str, mode: int = 0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def write_json(path: Path, data, mode: int = 0o600):
    atomic_write(path, json.dumps(data, indent=2, sort_keys=True) + '\n', mode)

def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))
