#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "${1:-}" == 'RESET-LOCAL-LAB' ]] || { echo 'BORRA GitLab, proyectos, tokens y datos locales. Usa make reset CONFIRM=RESET-LOCAL-LAB para autorizar.' >&2; exit 1; }
python3 - <<'PY'
import shutil
from lab.cli import ROOT, WORK, docker
if WORK.is_symlink() or WORK.resolve() != ROOT.resolve() / '.lab':
    raise SystemExit('Ruta de estado inesperada; reset bloqueado.')
if 'name: gitlab-migration-lab' not in (ROOT / 'compose.yaml').read_text():
    raise SystemExit('No se reconoce el proyecto Compose del laboratorio.')
docker('--profile', 'ci', 'down', '--volumes')
if WORK.exists():
    shutil.rmtree(WORK)
print('Solo el laboratorio fue eliminado. El repositorio GitHub no se modifica.')
PY
