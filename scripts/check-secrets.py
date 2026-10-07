#!/usr/bin/env python3
"""Small pre-publication guard; not a replacement for a full secret scanner."""
import argparse
import re
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--staged', action='store_true')
args = p.parse_args()
root = Path(__file__).resolve().parents[1]
if args.staged:
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    files = [root / n for n in names if n]
else:
    files = [f for f in root.rglob('*') if f.is_file() and not set(f.relative_to(root).parts) & {'.git', '.lab', '.venv', '__pycache__'} and f.name != '.env']
patterns = [re.compile(r'glpat-[A-Za-z0-9_-]{15,}'), re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
            re.compile(r'glrt-[A-Za-z0-9_-]{15,}'), re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
errors = []
for file in files:
    rel = file.relative_to(root)
    if '.lab' in rel.parts or file.name == '.env' or file.suffix in ('.pem', '.key'):
        errors.append(f'Ruta sensible en Git: {rel}')
        continue
    try:
        if args.staged:
            text = subprocess.check_output(['git', 'show', f':{rel.as_posix()}'], cwd=root).decode('utf-8')
        else:
            text = file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    if any(pattern.search(text) for pattern in patterns):
        errors.append(f'Posible credencial en: {rel}')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Guardia de secretos: {len(files)} archivos revisados, sin patrones detectados. Revisión humana aún necesaria.')
